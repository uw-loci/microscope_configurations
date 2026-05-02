#!/usr/bin/env python3
"""Rewrite deprecated metric names in autofocus_<scope>.yml files.

The focus_metrics_manifest.yml lists ``removed_aliases`` -- canonical
names that have been renamed. The runtime dispatcher
(microscope_imageprocessing.focus.resolve_metric) raises an error
naming the new spelling when it sees an old one. This script does the
rewrite in-place so live YAMLs match the canonical names without
needing every operator to edit by hand.

Currently the renames are::

    volath5            -> vollath_f5
    tenenbaum_gradient -> tenengrad

Usage::

    # Dry-run: print what would change.
    python3 scripts/migrate_autofocus_yaml.py --dry-run

    # Rewrite in place. Original is preserved as <file>.pre-migration.
    python3 scripts/migrate_autofocus_yaml.py

    # Limit to specific files (default scans the configurations dir).
    python3 scripts/migrate_autofocus_yaml.py autofocus_OWS3.yml

The script is idempotent: re-running on already-migrated files is a
no-op, and the .pre-migration backup is only written on the first
non-dry run that actually changes anything.

Why text-substitute rather than load+dump the YAML? Three reasons:
1. PyYAML's safe_dump strips header comments and reorders keys.
   Operators have spent time on those comments; preserving them
   matters more than a "tidy" rewrite.
2. The renames are unambiguous string-level substitutions inside
   ``score_metric: <name>`` lines.
3. The rewrite is the kind of minimal change that's easy to audit
   in a code review.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Source of truth: keep this in sync with focus_metrics_manifest.yml's
# removed_aliases section. The script intentionally does NOT load the
# manifest at runtime so it can be used standalone (no Python install
# of microscope_imageprocessing required on a config-only checkout).
ALIASES: Dict[str, str] = {
    "volath5": "vollath_f5",
    "tenenbaum_gradient": "tenengrad",
}

DEFAULT_GLOB = "autofocus_*.yml"


def _rewrite_text(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Apply alias substitutions to YAML text.

    Replaces tokens of the form ``score_metric: <old>`` (with optional
    quoting and trailing whitespace/comment) so a free-form mention of
    the old name in a docstring is not touched. Returns the new text
    and a list of (old, new) pairs that were applied at least once.
    """
    applied: List[Tuple[str, str]] = []
    new_text = text
    for old, new in ALIASES.items():
        # Match: score_metric: <opt-quote> old <opt-quote>  (anchored so
        # documentation prose mentioning 'volath5' is left alone).
        pattern = re.compile(
            rf"(\bscore_metric\s*:\s*[\"']?){re.escape(old)}([\"']?\s*(?:#.*)?$)",
            re.MULTILINE,
        )
        replaced, n = pattern.subn(rf"\g<1>{new}\g<2>", new_text)
        if n:
            applied.append((old, new))
            new_text = replaced
    return new_text, applied


def _process_file(path: Path, dry_run: bool) -> bool:
    """Process one YAML file. Returns True if it changed (or would
    change in dry-run mode), False otherwise."""
    try:
        original = path.read_text()
    except OSError as e:
        print(f"  [SKIP] {path}: cannot read ({e})", file=sys.stderr)
        return False

    new_text, applied = _rewrite_text(original)
    if not applied:
        print(f"  [OK]   {path.name}: no deprecated names found")
        return False

    summary = ", ".join(f"{o}->{n}" for o, n in applied)
    if dry_run:
        print(f"  [DRY]  {path.name}: would rewrite ({summary})")
        return True

    backup = path.with_suffix(path.suffix + ".pre-migration")
    if not backup.exists():
        backup.write_text(original)
    path.write_text(new_text)
    print(f"  [WRITE] {path.name}: rewrote ({summary}); backup -> {backup.name}")
    return True


def _resolve_targets(
    config_dir: Path, explicit: List[str]
) -> List[Path]:
    """Pick which YAML files to process. If the user named files
    explicitly, take those. Otherwise glob the config directory."""
    if explicit:
        return [Path(p) if Path(p).is_absolute() else config_dir / p
                for p in explicit]
    return sorted(config_dir.glob(DEFAULT_GLOB))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific YAML files to migrate. If omitted, all "
             f"{DEFAULT_GLOB!r} files in the configurations dir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change; do not write anything.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Directory containing autofocus_*.yml. Defaults to the "
             "configurations dir (one level above scripts/).",
    )
    args = parser.parse_args()

    if not args.config_dir.is_dir():
        print(f"Config directory not found: {args.config_dir}", file=sys.stderr)
        return 2

    targets = _resolve_targets(args.config_dir, args.files)
    if not targets:
        print(f"No files matched {DEFAULT_GLOB!r} in {args.config_dir}",
              file=sys.stderr)
        return 1

    print(f"{'Dry-run' if args.dry_run else 'Migrating'} "
          f"{len(targets)} file(s) under {args.config_dir}:")
    changes = 0
    for path in targets:
        if not path.is_file():
            print(f"  [SKIP] {path.name}: not found")
            continue
        if _process_file(path, args.dry_run):
            changes += 1

    print(f"Done. {changes} file(s) {'would change' if args.dry_run else 'changed'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
