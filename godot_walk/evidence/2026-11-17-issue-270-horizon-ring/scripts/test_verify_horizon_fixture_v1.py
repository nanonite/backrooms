"""Tests for the issue-270 horizon-ring fixture integrity validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from verify_horizon_fixture_v1 import FIXTURE_DIR, ROOT, collect_errors


@pytest.fixture()
def fixture_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "fixture"
    shutil.copytree(FIXTURE_DIR, destination)
    return destination


def replace(directory: Path, name: str, mutate) -> None:
    path = directory / name
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def test_real_fixture_has_no_errors() -> None:
    assert collect_errors() == []


def test_source_records_resolve_against_repository() -> None:
    assert (FIXTURE_DIR / "horizon_spec_v1.json").is_file()
    assert (FIXTURE_DIR / "views_v1.json").is_file()
    assert (ROOT / "godot_walk/project.godot").is_file()


def test_missing_view_is_reported(fixture_copy: Path) -> None:
    def drop(record):
        record["views"] = [
            view for view in record["views"] if view["id"] != "seam_check"
        ]

    replace(fixture_copy, "views_v1.json", drop)
    assert any("seam_check" in error for error in collect_errors(fixture_copy))


def test_horizon_collision_is_reported(fixture_copy: Path) -> None:
    def add_collision(record):
        record["collision"]["policy"] = "static_body"

    replace(fixture_copy, "horizon_spec_v1.json", add_collision)
    assert any("collision" in error for error in collect_errors(fixture_copy))


def test_finite_sky_is_reported(fixture_copy: Path) -> None:
    def finite(record):
        record["sky"]["rendered_at"] = "finite"

    replace(fixture_copy, "horizon_spec_v1.json", finite)
    assert any("infinity" in error for error in collect_errors(fixture_copy))


def test_invalid_panel_height_is_reported(fixture_copy: Path) -> None:
    def flatten(record):
        record["panel_heights"][0] = 0.0

    replace(fixture_copy, "horizon_spec_v1.json", flatten)
    assert any("height" in error for error in collect_errors(fixture_copy))


def test_divergent_camera_orientation_is_reported(fixture_copy: Path) -> None:
    def rotate(record):
        for view in record["views"]:
            if view["id"] == "translate_b":
                view["target"] = [4.0, 1.6, -10.0]

    replace(fixture_copy, "views_v1.json", rotate)
    assert any("orientation" in error for error in collect_errors(fixture_copy))


def test_unmet_parallax_threshold_is_reported(fixture_copy: Path) -> None:
    def tighten(record):
        record["parallax"]["min_angular_shift_deg"] = 180.0

    replace(fixture_copy, "horizon_spec_v1.json", tighten)
    assert any("parallax" in error for error in collect_errors(fixture_copy))


def test_true_flag_is_reported(fixture_copy: Path) -> None:
    def accept(record):
        record["flags"]["registration_accepted"] = True

    replace(fixture_copy, "views_v1.json", accept)
    assert any(
        "registration_accepted" in error for error in collect_errors(fixture_copy)
    )


def test_edited_pinned_file_is_reported(fixture_copy: Path) -> None:
    def corrupt(record):
        record["files"]["godot_walk/room_catalog/catalog.json"] = "0" * 64

    replace(fixture_copy, "pinned_supplement_v1.json", corrupt)
    assert any("pinned supplement" in error for error in collect_errors(fixture_copy))


def test_missing_limitations_is_reported(fixture_copy: Path) -> None:
    (fixture_copy / "limitations_v1.md").unlink()
    assert any(
        "Limitations record is missing" in error
        for error in collect_errors(fixture_copy)
    )
