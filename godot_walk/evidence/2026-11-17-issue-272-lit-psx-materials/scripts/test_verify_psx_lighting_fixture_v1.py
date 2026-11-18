"""Tests for the issue-272 lit PSX fixture integrity validator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from verify_psx_lighting_fixture_v1 import FIXTURE_DIR, ROOT, collect_errors


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
    assert (FIXTURE_DIR / "shader_decision_v1.json").is_file()
    assert (FIXTURE_DIR / "views_v1.json").is_file()
    assert (ROOT / "godot_walk/shaders/library_psx_vertex.gdshader").is_file()
    assert (ROOT / "godot_walk/project.godot").is_file()


def test_wrong_unshaded_define_is_reported(fixture_copy: Path) -> None:
    def flip(record):
        record["shader_variants"]["psx_solid_lit_v1"]["unshaded_defined"] = True

    replace(fixture_copy, "shader_decision_v1.json", flip)
    assert any("unshaded_defined" in error for error in collect_errors(fixture_copy))


def test_edited_shader_define_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "psx_solid_lit_v1.gdshader",
        "#define CULL_MODE cull_disabled",
        "#define UNSHADED\n#define CULL_MODE cull_disabled",
    )
    errors = collect_errors(fixture_copy)
    assert any("UNSHADED define" in error for error in errors)


def test_fog_change_is_reported(fixture_copy: Path) -> None:
    def change(record):
        record["fog"]["unchanged_between_baseline_and_lit"] = False
        record["fog"]["environment_fog_enabled"] = True

    replace(fixture_copy, "shader_decision_v1.json", change)
    errors = collect_errors(fixture_copy)
    assert any("fog" in error.lower() for error in errors)


def test_fog_define_removal_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "psx_textured_lit_v1.gdshader",
        "#define FOG_DISABLED\n",
        "",
    )
    errors = collect_errors(fixture_copy)
    assert any("FOG_DISABLED" in error for error in errors)


def test_missing_material_path_is_reported(fixture_copy: Path) -> None:
    def drop(record):
        record["comparison"]["surface_paths"] = ["solid"]

    replace(fixture_copy, "shader_decision_v1.json", drop)
    assert any("material paths" in error for error in collect_errors(fixture_copy))


def test_baseline_unavailable_is_reported(fixture_copy: Path) -> None:
    def drop(record):
        record["comparison"]["baseline_available"] = False

    replace(fixture_copy, "shader_decision_v1.json", drop)
    assert any("Baseline" in error for error in collect_errors(fixture_copy))


def test_preclaimed_response_is_reported(fixture_copy: Path) -> None:
    def claim(record):
        record["comparison"]["response_preclaimed"] = True

    replace(fixture_copy, "shader_decision_v1.json", claim)
    assert any("preclaim" in error for error in collect_errors(fixture_copy))


def test_shadows_enabled_is_reported(fixture_copy: Path) -> None:
    def change(record):
        record["light"]["shadow_enabled"] = True

    replace(fixture_copy, "shader_decision_v1.json", change)
    assert any("shadows" in error for error in collect_errors(fixture_copy))


def test_divergent_scene_mode_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "psx_lit_solid_v1.tscn",
        'lighting_mode = "lit"',
        'lighting_mode = "baseline"',
    )
    errors = collect_errors(fixture_copy)
    assert any("lighting_mode" in error for error in errors)


def test_scene_starting_light_on_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "psx_baseline_textured_v1.tscn",
        "light_on = false",
        "light_on = true",
    )
    errors = collect_errors(fixture_copy)
    assert any("light_on=false" in error for error in errors)


def test_branch_dependent_geometry_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "psx_lighting_fixture_v1.gd",
        "func _build_surfaces() -> void:\n",
        'func _build_surfaces() -> void:\n\tif surface_kind == "solid":\n\t\tpass\n',
    )
    errors = collect_errors(fixture_copy)
    assert any("must not branch" in error for error in errors)


def test_script_color_mismatch_is_reported(fixture_copy: Path) -> None:
    replace_text(
        fixture_copy,
        "psx_lighting_fixture_v1.gd",
        "Color(0.62, 0.66, 0.71, 1.0)",
        "Color(0.9, 0.9, 0.9, 1.0)",
    )
    errors = collect_errors(fixture_copy)
    assert any("solid albedo" in error.lower() for error in errors)


def test_missing_required_view_is_reported(fixture_copy: Path) -> None:
    def drop(record):
        record["views"] = [
            view for view in record["views"] if view["id"] != "sphere_close"
        ]

    replace(fixture_copy, "views_v1.json", drop)
    assert any("sphere_close" in error for error in collect_errors(fixture_copy))


def test_true_flag_is_reported(fixture_copy: Path) -> None:
    def accept(record):
        record["flags"]["scale_calibrated"] = True

    replace(fixture_copy, "views_v1.json", accept)
    assert any("scale_calibrated" in error for error in collect_errors(fixture_copy))


def test_edited_pinned_file_is_reported(fixture_copy: Path) -> None:
    def corrupt(record):
        record["files"]["godot_walk/shaders/library_psx_vertex.gdshader"] = "0" * 64

    replace(fixture_copy, "pinned_supplement_v1.json", corrupt)
    errors = collect_errors(fixture_copy)
    assert any("pinned supplement" in error for error in errors)
