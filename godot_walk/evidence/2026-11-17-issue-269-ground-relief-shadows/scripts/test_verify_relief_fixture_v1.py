"""Tests for the issue-269 relief/shadow fixture integrity validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from verify_relief_fixture_v1 import FIXTURE_DIR, ROOT, collect_errors


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
    assert (FIXTURE_DIR / "relief_spec_v1.json").is_file()
    assert (FIXTURE_DIR / "shadow_spec_v1.json").is_file()
    assert (ROOT / "godot_walk/project.godot").is_file()


def test_missing_view_is_reported(fixture_copy: Path) -> None:
    def drop(record):
        record["views"] = [v for v in record["views"] if v["id"] != "elevated"]

    replace(fixture_copy, "views_v1.json", drop)
    assert any("elevated" in error for error in collect_errors(fixture_copy))


def test_non_flat_collision_is_reported(fixture_copy: Path) -> None:
    def follow_relief(record):
        record["collision"]["policy"] = "heightfield"

    replace(fixture_copy, "relief_spec_v1.json", follow_relief)
    assert any("flat" in error for error in collect_errors(fixture_copy))


def test_shadow_tree_mismatch_is_reported(fixture_copy: Path) -> None:
    def reassign(record):
        record["shadows"][0]["tree_id"] = "missing_tree"

    replace(fixture_copy, "shadow_spec_v1.json", reassign)
    assert any("unknown tree" in error for error in collect_errors(fixture_copy))


def test_divergent_shadow_direction_is_reported(fixture_copy: Path) -> None:
    def rotate(record):
        record["shadows"][1]["direction_xz"] = [0.0, 1.0]

    replace(fixture_copy, "shadow_spec_v1.json", rotate)
    assert any("common direction" in error for error in collect_errors(fixture_copy))


def test_height_bound_violation_is_reported(fixture_copy: Path) -> None:
    def tighten(record):
        record["visible_height_bound"] = 0.05

    replace(fixture_copy, "relief_spec_v1.json", tighten)
    assert any("height bound" in error for error in collect_errors(fixture_copy))


def test_flattened_relief_is_reported(fixture_copy: Path) -> None:
    def flatten(record):
        for drift in record["drifts"]:
            drift["amplitude"] = 0.0

    replace(fixture_copy, "relief_spec_v1.json", flatten)
    assert any("too shallow" in error for error in collect_errors(fixture_copy))


def test_true_flag_is_reported(fixture_copy: Path) -> None:
    def accept(record):
        record["flags"]["registration_accepted"] = True

    replace(fixture_copy, "shadow_spec_v1.json", accept)
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
