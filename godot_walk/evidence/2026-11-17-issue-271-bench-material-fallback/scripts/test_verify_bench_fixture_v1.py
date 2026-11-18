"""Tests for the issue-271 bench material fallback fixture integrity validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from verify_bench_fixture_v1 import FIXTURE_DIR, ROOT, collect_errors


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


def replace_text(directory: Path, name: str, old: str, new: str) -> None:
    path = directory / name
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_real_fixture_has_no_errors() -> None:
    assert collect_errors() == []


def test_source_records_resolve_against_repository() -> None:
    assert (FIXTURE_DIR / "bench_material_decision_v1.json").is_file()
    assert (FIXTURE_DIR / "bench_geometry_v1.json").is_file()
    assert (ROOT / "godot_walk/project.godot").is_file()


def test_source_origin_is_reported(fixture_copy: Path) -> None:
    def claim_source(record):
        record["authored_material"]["origin"] = "source_crop:frame_4347"

    replace(fixture_copy, "bench_material_decision_v1.json", claim_source)
    assert any("project_authored" in error for error in collect_errors(fixture_copy))


def test_robe_crop_on_bench_is_reported(fixture_copy: Path) -> None:
    def assign_robe(record):
        record["source_crop_evidence"]["assigned_to_bench_in_candidate"] = True

    replace(fixture_copy, "bench_material_decision_v1.json", assign_robe)
    assert any("robe crop" in error for error in collect_errors(fixture_copy))


def test_observed_pixel_claim_is_reported(fixture_copy: Path) -> None:
    def claim_pixels(record):
        record["authored_material"]["no_claim_authored_pixels_observed_in_source"] = (
            False
        )

    replace(fixture_copy, "bench_material_decision_v1.json", claim_pixels)
    assert any("observed" in error for error in collect_errors(fixture_copy))


def test_plinth_material_switch_is_reported(fixture_copy: Path) -> None:
    def switch_plinth(record):
        record["statue_plinth"]["unchanged_relative_to_reference"] = False
        record["statue_plinth"]["material_key_in_both_views"] = "bench_stone"

    replace(fixture_copy, "bench_material_decision_v1.json", switch_plinth)
    errors = collect_errors(fixture_copy)
    assert any("plinth" in error for error in errors)


def test_unknown_bench_material_key_is_reported(fixture_copy: Path) -> None:
    def rename(record):
        record["bench_assignments"][5]["candidate_material_key"] = "robe_crop"

    replace(fixture_copy, "bench_material_decision_v1.json", rename)
    assert any(
        "unknown candidate material key" in error
        for error in collect_errors(fixture_copy)
    )


def test_changed_bench_collision_is_reported(fixture_copy: Path) -> None:
    def resize(record):
        record["colliders"][5]["size"] = [9.0, 1.6, 1.9]

    replace(fixture_copy, "bench_geometry_v1.json", resize)
    assert any(
        "Bench collision size" in error for error in collect_errors(fixture_copy)
    )


def test_divergent_scene_mode_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "bench_reference_v1.tscn",
        'bench_material_mode = "reference"',
        'bench_material_mode = "candidate"',
    )
    assert any("bench_material_mode" in error for error in collect_errors(fixture_copy))


def test_branch_dependent_bench_geometry_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "bench_fixture_v1.gd",
        "func _build_stone_bench() -> void:\n",
        'func _build_stone_bench() -> void:\n\tif bench_material_mode == "candidate":\n\t\tpass\n',
    )
    assert any("must not branch" in error for error in collect_errors(fixture_copy))


def test_script_color_mismatch_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "bench_fixture_v1.gd",
        "Color(0.42, 0.44, 0.47, 1.0)",
        "Color(0.9, 0.9, 0.9, 1.0)",
    )
    assert any("authored color" in error for error in collect_errors(fixture_copy))


def test_missing_required_view_is_reported(fixture_copy: Path) -> None:
    def drop(record):
        record["views"] = [
            view for view in record["views"] if view["id"] != "wider_scene"
        ]

    replace(fixture_copy, "views_v1.json", drop)
    assert any("wider_scene" in error for error in collect_errors(fixture_copy))


def test_true_flag_is_reported(fixture_copy: Path) -> None:
    def accept(record):
        record["flags"]["scale_calibrated"] = True

    replace(fixture_copy, "views_v1.json", accept)
    assert any("scale_calibrated" in error for error in collect_errors(fixture_copy))


def test_edited_pinned_file_is_reported(fixture_copy: Path) -> None:
    def corrupt(record):
        record["files"]["godot_walk/room_catalog/catalog.json"] = "0" * 64

    replace(fixture_copy, "pinned_supplement_v1.json", corrupt)
    assert any("pinned supplement" in error for error in collect_errors(fixture_copy))
