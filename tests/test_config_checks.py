"""The config checks pass on this repository and catch each problem they were written for.

Every regression test copies the repository's configs into a temporary folder, breaks
one thing the way it was really broken in October 2026, and expects an error.
"""

import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from checks import config_checks, mmcfg  # noqa: E402

LC = "config_LCPolScope.yml"
HAM_CFG = "_MM2/config_LCPolScope_Hamamatsu.cfg"
ORYX_CFG = "_MM2/config_LCPolScope.cfg"
HAM = "LCPS_DETECTOR_HAMAMATSU_FLASH_001"
ORYX = "LCPS_DETECTOR_FLIR_ORYX_001"


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


def edit_value(path: Path, pattern: str, new: str) -> None:
    """Replace the one match of ``pattern`` whatever value the live config holds today."""
    text = path.read_text(encoding="utf-8")
    assert len(re.findall(pattern, text, re.M)) == 1, f"{pattern!r} must match once in {path.name}"
    path.write_text(re.sub(pattern, new, text, flags=re.M), encoding="utf-8")


def errors(repo_dir):
    return [str(f) for f in config_checks.run(repo_dir).errors]


def test_this_repository_passes():
    report = config_checks.run()
    assert report.errors == [], "\n".join(map(str, report.errors))


def test_unchanged_copy_passes(repo):
    assert errors(repo) == []


def test_each_camera_is_checked_with_its_own_values(repo):
    # The base mm_preset group is the Hamamatsu's ("Objective"); the Oryx's Micro-Manager
    # config calls it "Objective Lens". Only the Oryx's per_detector entry makes the
    # Oryx pair pass, so dropping it must fail against config_LCPolScope.cfg alone.
    text = (repo / LC).read_text(encoding="utf-8")
    old = f"      {ORYX}:\n        mm_preset:\n          group: Objective Lens\n"
    assert text.count(old) == 3
    (repo / LC).write_text(text.replace(old, ""), encoding="utf-8")
    found = errors(repo)
    assert found and all("no such group" in e and ORYX_CFG in e for e in found), found


def test_shared_values_overridden_for_every_camera_do_not_matter(repo):
    # Both cameras override the group, so the shared value is never seen by a .cfg.
    text = (repo / LC).read_text(encoding="utf-8")
    (repo / LC).write_text(
        text.replace("mm_preset: {group: Objective,", "mm_preset: {group: Unused,"),
        encoding="utf-8",
    )
    assert errors(repo) == []


def test_per_detector_naming_an_unknown_camera_is_caught(repo):
    edit(
        repo / LC,
        "      per_detector:\n        LCPS_DETECTOR_HAMAMATSU_FLASH_001:\n          black_level",
        "      per_detector:\n        NO_SUCH_CAMERA:\n          black_level",
    )
    found = errors(repo)
    assert any("NO_SUCH_CAMERA" in e and "per_detector" in e for e in found), found


def test_flow_style_per_detector_is_caught(repo):
    text = (repo / LC).read_text(encoding="utf-8")
    old = f"      {HAM}:\n        mm_preset:\n          group: Objective\n"
    (repo / LC).write_text(
        text.replace(old, f"      {HAM}:\n        mm_preset: {{group: Objective}}\n", 1),
        encoding="utf-8",
    )
    found = errors(repo)
    assert any("flow style inside a per_detector block" in e for e in found), found


def test_a_camera_block_missing_a_field_is_caught(repo):
    edit(repo / LC, "          black_level: 99\n", "")
    found = errors(repo)
    assert any(f"{ORYX}' lacks black_level" in e for e in found), found


def test_profile_without_fields_in_a_two_camera_config_is_caught(repo):
    edit(
        repo / LC,
        "  lcpolscope_20x_oryx:\n    modality: lcpolscope\n",
        "  lcpolscope_20x_oryx:\n",
    )
    found = errors(repo)
    assert any("lcpolscope_20x_oryx' has no modality" in e for e in found), found


def test_cfg_listed_for_the_wrong_camera_is_caught(repo, monkeypatch):
    monkeypatch.setitem(config_checks.MM_CONFIGS, LC, [(HAM_CFG, ORYX), (ORYX_CFG, HAM)])
    found = errors(repo)
    assert any("is listed as" in e and HAM_CFG in e for e in found), found


def test_overlay_copy_matches_the_rules():
    from checks.per_detector import apply_detector_overlay

    cfg = {
        "x": 1,
        "dp": [{"device": "d", "property": "p", "value": 0}],
        "per_detector": {
            "A": {
                "x": 2,
                "device_properties": [{"device": "d", "property": "q", "value": 1}],
            }
        },
        "device_properties": [{"device": "d", "property": "p", "value": 0}],
    }
    out = apply_detector_overlay(cfg, "A")
    assert out["x"] == 2
    assert out["device_properties"] == [
        {"device": "d", "property": "p", "value": 0},
        {"device": "d", "property": "q", "value": 1},
    ]
    assert apply_detector_overlay(cfg, "B") == cfg
    assert cfg["x"] == 1


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
    edit(
        repo / "resources" / "resources_LOCI.yml",
        "device: 'Flash4'",
        "device: 'HamamatsuHam_DCAM'",
    )
    found = errors(repo)
    assert any("'Flash4' matches no detector" in e for e in found), found


def test_missing_mm_preset_group_is_caught(repo):
    # 10-21: the YAML said "Objective Lens"; the Flash4 config calls the group "Objective".
    text = (repo / LC).read_text(encoding="utf-8")
    old = f"      {HAM}:\n        mm_preset:\n          group: Objective\n"
    assert text.count(old) == 3
    (repo / LC).write_text(
        text.replace(old, f"      {HAM}:\n        mm_preset:\n          group: Objective Lens\n"),
        encoding="utf-8",
    )
    found = errors(repo)
    assert any("no such group" in e and HAM_CFG in e for e in found), found


def test_pixel_size_disagreement_is_caught(repo):
    edit(repo / HAM_CFG, "PixelSize_um,20x,0.2695", "PixelSize_um,20x,0.3231")
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
    assert mm.pixel_size_for(mm.preset("Objective", "20x")) == [("20x", 0.2695)]
