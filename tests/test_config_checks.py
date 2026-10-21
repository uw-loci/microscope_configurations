"""The config checks pass on this repository and catch each problem they were written for.

Every regression test copies the repository's configs into a temporary folder, breaks
one thing the way it was really broken in October 2026, and expects an error.
"""

import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from checks import config_checks, mmcfg  # noqa: E402

LC = "config_LCPolScope.yml"
LC_HAM = "config_LCPolScope_Hamamatsu.yml"
HAM_CFG = "_MM2/config_LCPolScope_Hamamatsu.cfg"


@pytest.fixture
def repo(tmp_path):
    for p in REPO.glob("*.yml"):
        shutil.copy(p, tmp_path / p.name)
    shutil.copytree(REPO / "resources", tmp_path / "resources")
    shutil.copytree(REPO / "_MM2", tmp_path / "_MM2")
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} must occur once in {path.name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def errors(repo_dir):
    return [str(f) for f in config_checks.run(repo_dir).errors]


def test_this_repository_passes():
    report = config_checks.run()
    assert report.errors == [], "\n".join(map(str, report.errors))


def test_unchanged_copy_passes(repo):
    assert errors(repo) == []


def test_sibling_drift_is_caught(repo):
    # 10-19: the Oryx config's Z low limit went to -150; the Hamamatsu copy kept 0.
    edit(repo / LC_HAM, "      low: -150\n      high: 5000", "      low: 0\n      high: 5000")
    found = errors(repo)
    assert any("stage.limits.z_um.low" in e and LC_HAM in e for e in found), found


def test_allowed_sibling_difference_passes(repo):
    edit(repo / LC_HAM, "black_level: 103", "black_level: 99")
    assert errors(repo) == []


def test_autofocus_drift_is_caught(repo):
    af = repo / "autofocus_LCPolScope_Hamamatsu.yml"
    text = af.read_text(encoding="utf-8")
    af.write_text(text.replace("search_range_um: 30.0", "search_range_um: 100.0", 1), encoding="utf-8")
    found = errors(repo)
    assert any("search_range_um" in e for e in found), found


def test_missing_pixel_size_presets_are_caught(repo):
    # 10-21: the rig's Flash4 config had no pixel-size presets.
    cfg = repo / HAM_CFG
    kept = [
        line
        for line in cfg.read_text(encoding="utf-8").splitlines()
        if not line.startswith(("ConfigPixelSize", "PixelSize_um"))
    ]
    cfg.write_text("\n".join(kept) + "\n", encoding="utf-8")
    found = errors(repo)
    assert any("no pixel-size preset" in e for e in found), found


def test_camera_label_matching_no_detector_is_caught(repo):
    # 10-21: the Flash4 config renamed the camera; resources still said HamamatsuHam_DCAM.
    edit(repo / "resources" / "resources_LOCI.yml", "device: 'Flash4'", "device: 'HamamatsuHam_DCAM'")
    found = errors(repo)
    assert any("'Flash4' matches no detector" in e for e in found), found


def test_missing_mm_preset_group_is_caught(repo):
    # 10-21: the YAML said "Objective Lens"; the Flash4 config calls the group "Objective".
    text = (repo / LC_HAM).read_text(encoding="utf-8")
    (repo / LC_HAM).write_text(text.replace("group: Objective,", "group: Objective Lens,"), encoding="utf-8")
    found = errors(repo)
    assert any("no such group" in e for e in found), found


def test_pixel_size_disagreement_is_caught(repo):
    edit(repo / HAM_CFG, "PixelSize_um,20x 0.4 HAMAMATSU,0.2695", "PixelSize_um,20x 0.4 HAMAMATSU,0.3231")
    found = errors(repo)
    assert any("disagrees" in e and "0.3231" in e for e in found), found


def test_profile_with_unknown_detector_is_caught(repo):
    text = (repo / LC).read_text(encoding="utf-8")
    (repo / LC).write_text(
        text.replace("detector: LCPS_DETECTOR_FLIR_ORYX_001", "detector: NO_SUCH_CAMERA", 1),
        encoding="utf-8",
    )
    found = errors(repo)
    assert any("NO_SUCH_CAMERA" in e for e in found), found


def test_draft_config_problems_are_warnings(repo):
    report = config_checks.run(repo)
    camm = [f for f in report.findings if f.file == "config_CAMM.yml"]
    assert camm and all(f.level == "warning" for f in camm)


def test_mmcfg_parses_groups_and_pixel_presets():
    mm = mmcfg.parse(REPO / HAM_CFG)
    assert mm.core_camera == "Flash4"
    assert mm.preset("Objective", "20x") == [("Objective", "Label", "20x")]
    assert mm.pixel_size_for(mm.preset("Objective", "20x")) == [("20x 0.4 HAMAMATSU", 0.2695)]
