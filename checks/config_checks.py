"""Consistency checks for the microscope configs in this repository.

Three kinds of check, all on files, none on hardware:

1. **Structure and references.** Every ``config_*.yml`` parses, names its microscope,
   and every objective, detector and acquisition profile it uses resolves -- in the
   config itself or in ``resources/resources_LOCI.yml``, merged entry by entry with the
   config winning, as the server and QPSC both merge them. Its ``autofocus_`` and
   ``imageprocessing_`` companions only name objectives and detectors the config has.
2. **The YAML against its Micro-Manager config** in ``_MM2/`` (pairs in ``MM_CONFIGS``):
   the Core camera is one of the config's detectors (the server finds the detector by
   that exact label), each objective's ``mm_preset`` exists, and its pixel size agrees
   with the Micro-Manager pixel-size preset to within ``PIXEL_SIZE_TOLERANCE``.
3. **Sibling configs do not drift.** Files describing the same microscope through
   different cameras (``SIBLINGS``) must be identical except where ``allowed`` says a
   camera may differ. Each file's own detector IDs are replaced by ``<DETECTOR>``
   first, so a per-camera key does not count as a difference by itself.

Written 2026-10-21 after a run of problems no single file shows: the Hamamatsu
LC-PolScope config missed two changes made to the Oryx copy; a Micro-Manager config
had no pixel-size presets and a camera label no detector matched; an ``mm_preset``
named a group Micro-Manager did not have.

The checks see the repository's files only. The rig runs whatever Micro-Manager file
is loaded there, so keep ``_MM2/`` in step with the rig.

Run: ``python checks/config_checks.py`` (exit 1 on errors), or ``pytest tests``.
"""

from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks import mmcfg  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

#: Each tracked config and the Micro-Manager config the rig loads with it.
MM_CONFIGS: Dict[str, str] = {
    "config_LCPolScope.yml": "_MM2/config_LCPolScope.cfg",
    "config_LCPolScope_Hamamatsu.yml": "_MM2/config_LCPolScope_Hamamatsu.cfg",
    # config_PPM.yml is deliberately absent: _MM2/config_PPM.cfg dates from 2025-05 and
    # names a PVCAM MicroPublisher6, while the rig's 2026-04 device dump
    # (mm_device_properties_PPM_20260422.txt) shows it runs JAICamera. Add the pair back
    # when the rig's current .cfg is saved here.
    "config_CAMM.yml": "_MM2/OpenScan-CAMM-cal.cfg",
}

#: Configs that are not in service yet: their problems are reported, not failed on.
DRAFTS: Dict[str, str] = {
    "config_CAMM.yml": "CAMM is not in service yet; its config predates resources_LOCI.yml IDs",
}

#: Configs that describe no microscope stage (a slide scanner's macro settings).
SCANNER_CONFIGS = {"config_Ocus40.yml"}

#: How far a YAML pixel size may sit from Micro-Manager's before it is an error.
PIXEL_SIZE_TOLERANCE = 0.01


@dataclass(frozen=True)
class Sibling:
    """Two files for one microscope seen through different cameras."""

    a: str
    b: str
    allowed: tuple  # fnmatch patterns over flattened paths ("a.b.0.c")
    why: str


_LC_CONFIG_ALLOWED = (
    "microscope.name",  # keeps slide alignments apart per camera
    "hardware.objectives.*.mm_preset.group",  # each camera has its own MM config
    "hardware.objectives.*.pixel_size_xy_um.<DETECTOR>",
    "modalities.lcpolscope.channels.*.device_properties.*",  # LC palette per camera
    "modalities.lcpolscope.channels.*.exposure_ms",
    "modalities.lcpolscope.reconstruction.black_level",
    "modalities.lcpolscope.reconstruction.state_order.*",
    "modalities.lcpolscope.reconstruction.lc_calibrat*",
    "modalities.lcpolscope.reconstruction.lc_extinction_ratio",
)

SIBLINGS: List[Sibling] = [
    Sibling(
        "config_LCPolScope.yml",
        "config_LCPolScope_Hamamatsu.yml",
        _LC_CONFIG_ALLOWED,
        "LC-PolScope, Oryx and Hamamatsu ports: same stage, LCs, objectives",
    ),
    Sibling(
        "autofocus_LCPolScope.yml",
        "autofocus_LCPolScope_Hamamatsu.yml",
        ("autofocus_settings.*.calibrated",),
        "autofocus depends on the objective, not the camera",
    ),
    Sibling(
        "imageprocessing_LCPolScope.yml",
        "imageprocessing_LCPolScope_Hamamatsu.yml",
        (
            "background_correction.base_folder",
            "background_correction.*.enabled",
            "imaging_profiles.*.*.<DETECTOR>.*",
        ),
        "backgrounds and exposures are per camera; the rest is shared",
    ),
]

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
            report.warn(name, f"objective '{oid}' has no id_objective_lens entry (no display name)")
        for d in o.get("pixel_size_xy_um") or {}:
            if d not in dets:
                report.error(
                    name, f"objective '{oid}' has a pixel size for '{d}', not a detector here"
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
                    name, f"profile '{pname}' uses detector '{det}', not in hardware.detectors"
                )
            obj = prof.get("objective")
            if obj and obj not in obj_ids:
                report.error(
                    name, f"profile '{pname}' uses objective '{obj}', not in hardware.objectives"
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
                        ip_name, f"imaging_profiles.{mod} names objective '{oid}', not in {name}"
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
    cfg_rel = MM_CONFIGS.get(name)
    if not cfg_rel:
        return
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
    for dev, d in by_device.items():
        if dev not in mm.devices:
            report.warn(name, f"detector '{d}' (device '{dev}') is not a device in {cfg_rel}")

    for o in objectives(config):
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
                f"{cfg_rel} (it has: {have})",
            )
            continue
        if active is None:
            continue
        yaml_px = (o.get("pixel_size_xy_um") or {}).get(active)
        matches = mm.pixel_size_for(settings)
        if not matches:
            report.error(
                name,
                f"objective '{oid}': {cfg_rel} has no pixel-size preset for [{group}] '{preset}' "
                "(Micro-Manager would report pixel size 0)",
            )
        elif yaml_px is not None:
            for pname, px in matches:
                if abs(px - yaml_px) > PIXEL_SIZE_TOLERANCE * yaml_px:
                    report.error(
                        name,
                        f"objective '{oid}': pixel size {yaml_px} for {active} disagrees with "
                        f"{cfg_rel}'s '{pname}' = {px}",
                    )


# ---------------------------------------------------------------- check 3


def flatten(x: Any, prefix: str = "") -> Iterable:
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from flatten(v, f"{prefix}.{i}" if prefix else str(i))
    else:
        yield prefix, x


def _normalised(data: Any, own_detectors: Iterable[str]) -> Dict[str, Any]:
    own = set(own_detectors)
    out = {}
    for path, value in flatten(data):
        parts = ["<DETECTOR>" if p in own else p for p in path.split(".")]
        if isinstance(value, str) and value in own:
            value = "<DETECTOR>"
        out[".".join(parts)] = value
    return out


def _detectors_for(repo: Path, file: str) -> List[str]:
    """The detectors of the config a file belongs to (itself, or config_<stem>.yml)."""
    for kind in ("autofocus_", "imageprocessing_"):
        if file.startswith(kind):
            file = "config_" + file[len(kind) :]
            break
    path = repo / file
    return detectors(load_yaml(path) or {}) if path.exists() else []


def check_siblings(repo: Path, report: Report, siblings: Iterable[Sibling] = None) -> None:
    for s in siblings if siblings is not None else SIBLINGS:
        if not ((repo / s.a).exists() and (repo / s.b).exists()):
            continue
        a = _normalised(load_yaml(repo / s.a), _detectors_for(repo, s.a))
        b = _normalised(load_yaml(repo / s.b), _detectors_for(repo, s.b))
        for path in sorted(set(a) | set(b)):
            if a.get(path, "<missing>") == b.get(path, "<missing>"):
                continue
            if any(fnmatch.fnmatchcase(path, pat) for pat in s.allowed):
                continue
            report.error(
                s.b,
                f"differs from {s.a} at '{path}': {a.get(path, '<missing>')!r} vs "
                f"{b.get(path, '<missing>')!r} ({s.why}; copy the change across, or add the "
                "path to the sibling's allowed list in checks/config_checks.py)",
            )


# ---------------------------------------------------------------- driver


def run(repo: Path = REPO) -> Report:
    report = Report()
    for name in scope_configs(repo):
        config = check_structure(repo, name, report)
        if config is not None:
            check_against_mm(repo, name, config, report)
    check_siblings(repo, report)
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
