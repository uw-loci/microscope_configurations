"""Consistency checks for the microscope configs in this repository.

Two kinds of check, all on files, none on hardware:

1. **Structure and references.** Every ``config_*.yml`` parses, names its microscope,
   and every objective, detector and acquisition profile it uses resolves -- in the
   config itself or in ``resources/resources_LOCI.yml``, merged entry by entry with the
   config winning, as the server and QPSC both merge them. Every ``per_detector`` block
   names only the config's own detectors, is written in block style (QPSC edits it as
   text), and gives every camera the same fields; with several cameras every profile
   carries ``modality``, ``objective`` and ``detector``. Its ``autofocus_`` and ``imageprocessing_``
   companions only name objectives and detectors the config has.
2. **The YAML against its Micro-Manager configs** in ``_MM2/`` (``MM_CONFIGS``). A
   microscope with two cameras has one YAML and one Micro-Manager config per camera, so
   each pair is checked with that camera's ``per_detector`` values merged in, as QPSC
   and the server merge them when that camera is active: the Core camera is the
   declared detector (the server finds the detector by that exact label), each
   objective's ``mm_preset`` exists, and its pixel size agrees with the Micro-Manager
   pixel-size preset to within ``PIXEL_SIZE_TOLERANCE``.

Written 2026-10-21 after a run of problems no single file shows: the Hamamatsu
LC-PolScope config missed two changes made to the Oryx copy (the two files are one
since 2026-11-17, with per_detector values); a Micro-Manager config had no pixel-size
presets and a camera label no detector matched; an ``mm_preset`` named a group
Micro-Manager did not have.

The checks see the repository's files only. The rig runs whatever Micro-Manager file
is loaded there, so keep ``_MM2/`` in step with the rig.

Run: ``python checks/config_checks.py`` (exit 1 on errors), or ``pytest tests``.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks import mmcfg  # noqa: E402
from checks.per_detector import PER_DETECTOR_KEY, apply_detector_overlay  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

#: Each tracked config and the Micro-Manager configs the rig loads with it, as
#: (.cfg, detector) pairs: the detector whose camera that .cfg runs, or None for a
#: single-camera scope (the .cfg's camera is then whichever detector it matches).
MM_CONFIGS: Dict[str, List[Tuple[str, Optional[str]]]] = {
    "config_LCPolScope.yml": [
        ("_MM2/config_LCPolScope_Hamamatsu.cfg", "LCPS_DETECTOR_HAMAMATSU_FLASH_001"),
        ("_MM2/config_LCPolScope.cfg", "LCPS_DETECTOR_FLIR_ORYX_001"),
    ],
    # config_PPM.yml is deliberately absent: _MM2/config_PPM.cfg dates from 2025-05 and
    # names a PVCAM MicroPublisher6, while the rig's 2026-04 device dump
    # (mm_device_properties_PPM_20260422.txt) shows it runs JAICamera. Add the pair back
    # when the rig's current .cfg is saved here.
    "config_CAMM.yml": [("_MM2/OpenScan-CAMM-cal.cfg", None)],
}

#: Configs that are not in service yet: their problems are reported, not failed on.
DRAFTS: Dict[str, str] = {
    "config_CAMM.yml": "CAMM is not in service yet; its config predates resources_LOCI.yml IDs",
}

#: Configs that describe no microscope stage (a slide scanner's macro settings).
SCANNER_CONFIGS = {"config_Ocus40.yml"}

#: How far a YAML pixel size may sit from Micro-Manager's before it is an error.
PIXEL_SIZE_TOLERANCE = 0.01


#: Top-level keys some code reads. Anything else is reported as unread.
KNOWN_TOP_LEVEL = {
    "microscope",
    "light_path",
    "modalities",
    "hardware",
    "stage",
    "slide_size_um",
    "acquisition_profiles",
    "id_detector",
    "id_objective_lens",
    "id_stage",
    "obj_slider",
    "pmt_safety",
    "mode_positions",
    "objective_swap_sequences",
    "modality_xy_offsets",
    "macro",
    "scanner_settings",
    "scanner_info",
}

#: Paths no code reads, kept from a format that changed. ``*`` is any one level.
DEAD_PATHS = {
    "modalities.*.background_correction": (
        "background folders are read from imageprocessing_<scope>.yml only"
    ),
}


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    file: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.file}: {self.message}"


class Report:
    def __init__(self) -> None:
        self.findings: List[Finding] = []

    def error(self, file: str, message: str) -> None:
        level = "warning" if file in DRAFTS else "error"
        if level == "warning":
            message += f" (draft: {DRAFTS[file]})"
        self.findings.append(Finding(level, file, message))

    def warn(self, file: str, message: str) -> None:
        self.findings.append(Finding("warning", file, message))

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "error"]


# ---------------------------------------------------------------- loading


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def merged_section(config: dict, resources: dict, name: str) -> Dict[str, Any]:
    """An id_* section as the server and QPSC see it: resources, the config's entries on top."""
    merged = dict(resources.get(name) or {})
    merged.update(config.get(name) or {})
    return merged


def companion(config_file: str, kind: str) -> str:
    """autofocus_<stem>.yml / imageprocessing_<stem>.yml for config_<stem>.yml."""
    return f"{kind}_{config_file[len('config_'):]}"


def scope_configs(repo: Path) -> List[str]:
    return sorted(
        p.name
        for p in repo.glob("config_*.yml")
        if "template" not in p.name and p.name not in SCANNER_CONFIGS
    )


def detectors(config: dict) -> List[str]:
    return list(((config.get("hardware") or {}).get("detectors")) or [])


def objectives(config: dict) -> List[dict]:
    return [o for o in ((config.get("hardware") or {}).get("objectives") or []) if o]


# ---------------------------------------------------------------- check 1


def check_structure(repo: Path, name: str, report: Report) -> Optional[dict]:
    try:
        config = load_yaml(repo / name)
    except yaml.YAMLError as e:
        report.error(name, f"does not parse: {e}")
        return None
    if not isinstance(config, dict):
        report.error(name, "is not a mapping")
        return None
    resources = load_yaml(repo / "resources" / "resources_LOCI.yml") or {}

    if not (config.get("microscope") or {}).get("name"):
        report.error(name, "microscope.name is missing")
    if not config.get("stage"):
        report.error(name, "stage section is missing (the server refuses CONFIG without it)")

    for key in config:
        if key not in KNOWN_TOP_LEVEL:
            report.warn(name, f"top-level key '{key}' is not read by QPSC or the server")
    for pattern, why in DEAD_PATHS.items():
        for path, _ in flatten(config):
            if fnmatch.fnmatchcase(path, pattern):
                report.warn(name, f"'{path}' is never read: {why}")
                break

    id_obj = merged_section(config, resources, "id_objective_lens")
    id_det = merged_section(config, resources, "id_detector")
    dets = detectors(config)
    objs = objectives(config)
    obj_ids = [o.get("id") for o in objs]
    for d in dets:
        if d not in id_det:
            report.error(name, f"detector '{d}' is in neither the config nor resources_LOCI.yml")
    for o in objs:
        oid = o.get("id")
        if oid not in id_obj:
            # Only the display name comes from there; the UI falls back to the raw ID.
            report.warn(
                name,
                f"objective '{oid}' has no id_objective_lens entry (no display name)",
            )
        for d in o.get("pixel_size_xy_um") or {}:
            if d not in dets:
                report.error(
                    name,
                    f"objective '{oid}' has a pixel size for '{d}', not a detector here",
                )

    for path, node in per_detector_blocks(config):
        if not isinstance(node, dict):
            report.error(name, f"'{path}' is not a mapping of detector ID to values")
            continue
        for d, values in node.items():
            if d not in dets:
                report.error(
                    name,
                    f"'{path}' names '{d}', not in hardware.detectors ({', '.join(dets)})",
                )
            elif not isinstance(values, dict):
                report.error(name, f"'{path}.{d}' is not a mapping")
        # QPSC's calibration writers update a field in the active camera's block only
        # when the block already holds it, so every camera's block names the same fields.
        fields = {
            d: _overlay_fields(v) for d, v in node.items() if d in dets and isinstance(v, dict)
        }
        if len(fields) > 1:
            union = set().union(*fields.values())
            for d, have in fields.items():
                missing = sorted(union - have)
                if missing:
                    report.error(
                        name,
                        f"'{path}.{d}' lacks {', '.join(missing)}, which another camera's "
                        "block sets (each camera's block must hold every per-camera field)",
                    )
    for line_no, line in _flow_style_per_detector_lines(repo / name):
        report.error(
            name,
            f"line {line_no}: flow style inside a per_detector block ({line.strip()!r}); "
            "QPSC edits these blocks as text, so write one key per line",
        )

    modalities = config.get("modalities") or {}
    profiles = config.get("acquisition_profiles") or {}
    if isinstance(profiles, dict):
        for pname, prof in profiles.items():
            if not isinstance(prof, dict):
                continue
            mod = prof.get("modality")
            if mod and mod not in modalities:
                report.error(name, f"profile '{pname}' uses modality '{mod}', not defined here")
            det = prof.get("detector")
            if det and det not in dets:
                report.error(
                    name,
                    f"profile '{pname}' uses detector '{det}', not in hardware.detectors",
                )
            if len(dets) > 1:
                # The second camera's profiles (lcpolscope_20x_oryx) resolve only through
                # these fields; the <modality>_<objective substring> name rule cannot match.
                absent = [f for f in ("modality", "objective", "detector") if not prof.get(f)]
                if absent:
                    report.error(
                        name,
                        f"profile '{pname}' has no {', '.join(absent)}: a config with several "
                        "cameras picks profiles by these fields",
                    )
            obj = prof.get("objective")
            if obj and obj not in obj_ids:
                report.error(
                    name,
                    f"profile '{pname}' uses objective '{obj}', not in hardware.objectives",
                )

    af_name = companion(name, "autofocus")
    if (repo / af_name).exists():
        af = load_yaml(repo / af_name) or {}
        for row in af.get("autofocus_settings") or []:
            oid = (row or {}).get("objective")
            if oid and oid not in obj_ids:
                report.error(af_name, f"autofocus row for '{oid}', not an objective of {name}")
    ip_name = companion(name, "imageprocessing")
    if (repo / ip_name).exists():
        ip = load_yaml(repo / ip_name) or {}
        for mod, per_obj in (ip.get("imaging_profiles") or {}).items():
            for oid, per_det in (per_obj or {}).items():
                if oid not in obj_ids:
                    report.error(
                        ip_name,
                        f"imaging_profiles.{mod} names objective '{oid}', not in {name}",
                    )
                    continue
                for d in per_det or {}:
                    if d not in dets:
                        report.error(
                            ip_name,
                            f"imaging_profiles.{mod}.{oid} names detector '{d}', not in {name}",
                        )
    return config


# ---------------------------------------------------------------- check 2


def check_against_mm(repo: Path, name: str, config: dict, report: Report) -> None:
    for cfg_rel, detector in MM_CONFIGS.get(name, []):
        _check_one_mm(repo, name, config, cfg_rel, detector, report)


def _check_one_mm(
    repo: Path,
    name: str,
    config: dict,
    cfg_rel: str,
    detector: Optional[str],
    report: Report,
) -> None:
    cfg_path = repo / cfg_rel
    if not cfg_path.exists():
        report.error(name, f"its Micro-Manager config {cfg_rel} is missing")
        return
    mm = mmcfg.parse(cfg_path)
    resources = load_yaml(repo / "resources" / "resources_LOCI.yml") or {}
    id_det = merged_section(config, resources, "id_detector")
    by_device = {}
    for d in detectors(config):
        dev = (id_det.get(d) or {}).get("device")
        if dev:
            by_device[dev] = d

    active = by_device.get(mm.core_camera or "")
    if mm.core_camera is None:
        report.error(name, f"{cfg_rel} sets no Core camera")
    elif active is None:
        report.error(
            name,
            f"{cfg_rel}'s camera '{mm.core_camera}' matches no detector's 'device' "
            f"({', '.join(sorted(by_device)) or 'none'}); the server could not find it",
        )
    elif detector is not None and active != detector:
        report.error(
            name,
            f"{cfg_rel} is listed as {detector}'s Micro-Manager config, but its camera "
            f"'{mm.core_camera}' is {active}'s",
        )
    if detector is None:
        for dev, d in by_device.items():
            if dev not in mm.devices:
                report.warn(
                    name,
                    f"detector '{d}' (device '{dev}') is not a device in {cfg_rel}",
                )
    elif detector not in detectors(config):
        report.error(name, f"MM_CONFIGS lists {cfg_rel} for '{detector}', not a detector here")

    # The config as QPSC and the server see it while this .cfg's camera is active.
    camera = detector if detector is not None else active
    seen = apply_detector_overlay(config, camera)
    where = f"{cfg_rel} ({camera})" if detector is not None else cfg_rel

    for o in objectives(seen):
        oid = o.get("id")
        spec = o.get("mm_preset")
        if not spec:
            continue
        group, preset = spec.get("group"), spec.get("preset")
        settings = mm.preset(group, preset)
        if settings is None:
            have = (
                ", ".join(sorted(mm.groups))
                if group not in mm.groups
                else ", ".join(sorted(mm.groups[group]))
            )
            what = "group" if group not in mm.groups else f"preset in group '{group}'"
            report.error(
                name,
                f"objective '{oid}' mm_preset [{group}] '{preset}': no such {what} in "
                f"{where} (it has: {have})",
            )
            continue
        if camera is None:
            continue
        yaml_px = (o.get("pixel_size_xy_um") or {}).get(camera)
        matches = mm.pixel_size_for(settings)
        if not matches:
            report.error(
                name,
                f"objective '{oid}': {where} has no pixel-size preset for [{group}] '{preset}' "
                "(Micro-Manager would report pixel size 0)",
            )
        elif yaml_px is not None:
            for pname, px in matches:
                if abs(px - yaml_px) > PIXEL_SIZE_TOLERANCE * yaml_px:
                    report.error(
                        name,
                        f"objective '{oid}': pixel size {yaml_px} for {camera} disagrees with "
                        f"{cfg_rel}'s '{pname}' = {px}",
                    )


# ---------------------------------------------------------------- helpers


def flatten(x: Any, prefix: str = "") -> Iterable:
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from flatten(v, f"{prefix}.{i}" if prefix else str(i))
    else:
        yield prefix, x


def per_detector_blocks(x: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    """Every ``per_detector`` value in the tree, with its dotted path."""
    if isinstance(x, dict):
        for k, v in x.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if k == PER_DETECTOR_KEY:
                yield path, v
            else:
                yield from per_detector_blocks(v, path)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from per_detector_blocks(v, f"{prefix}.{i}" if prefix else str(i))


def _overlay_fields(values: dict, prefix: str = "") -> set:
    """The fields a per_detector entry sets: dotted keys, device_properties by pair."""
    out = set()
    for k, v in values.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        if k == "device_properties" and isinstance(v, list):
            for e in v:
                if isinstance(e, dict):
                    out.add(f"{path}[{e.get('device')}/{e.get('property')}]")
        elif isinstance(v, dict):
            out |= _overlay_fields(v, path)
        else:
            out.add(path)
    return out


def _flow_style_per_detector_lines(path: Path) -> List[Tuple[int, str]]:
    """Lines inside a per_detector block that open a flow mapping or sequence."""
    hits = []
    block_indent = None
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip())
        if block_indent is not None and indent <= block_indent:
            block_indent = None
        key = stripped.strip()
        if key.startswith("per_detector:"):
            block_indent = indent
            rest = key[len("per_detector:") :].strip()
            if rest:
                hits.append((no, line))
            continue
        if block_indent is not None and re.search(r"(^-\s*|:\s+)[\[{]", key):
            hits.append((no, line))
    return hits


# ---------------------------------------------------------------- driver


def run(repo: Path = REPO) -> Report:
    report = Report()
    for name in scope_configs(repo):
        config = check_structure(repo, name, report)
        if config is not None:
            check_against_mm(repo, name, config, report)
    return report


def main() -> int:
    report = run()
    for f in report.findings:
        print(f)
    n_err = len(report.errors)
    print(f"{n_err} error(s), {len(report.findings) - n_err} warning(s)")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
