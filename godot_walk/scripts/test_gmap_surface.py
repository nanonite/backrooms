"""Tests for the gmap-0.9.0 surface layer and palettes 0.2.0 (issue 199)."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gmap_palette_registry as palette_registry
from deterministic_json import ROOT, sha256_file
from generate_surface_variants import check as check_textures
from gmap_build import GENERATOR_VERSION_V8, GENERATOR_VERSION_V9, build_map
from gmap_library import Library, load_library
from gmap_palette_registry import (
    ACOUSTIC_TAGS,
    SURFACES_V2,
    VARIANTS,
    load_registry_v2,
    registry_errors,
)
from gmap_surface import SURFACES, surface_errors
from gmap_validate import validate_document
from shape_room import edge_links
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
KEPT_SEEDS = (1, 2, 3, 11, 69)


@pytest.fixture(scope="module")
def library() -> Library:
    return load_library(INDEX)


@pytest.fixture(scope="module")
def registry() -> dict:
    return load_registry_v2()


def _without_surface(document: dict) -> dict:
    result = copy.deepcopy(document)
    result.pop("palette_registry", None)
    for key in ("generator_version", "map_id", "rules"):
        result.pop(key, None)
    for cell in result["cells"]:
        cell.pop("wear", None)
        cell.pop("surface_variants", None)
    return result


def test_v200_registry_has_variants_acoustic_tags_and_derived_textures(registry):
    assert registry_errors(registry) == []
    assert [palette["palette_id"] for palette in registry["palettes"]] == [
        "backrooms_yellow",
        "industrial_concrete",
        "plaster_debris",
    ]
    assert check_textures() == []
    for palette in registry["palettes"]:
        for surface in SURFACES_V2:
            field = palette["surfaces"][surface]
            assert field["acoustic"] in ACOUSTIC_TAGS
            assert set(field["variants"]) == set(VARIANTS)


def test_v90_rejects_noncanonical_registry(library, tmp_path):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V9)
    registry = json.loads(
        (
            ROOT / "godot_walk/room_catalog/material_palettes/palettes-0.2.0.json"
        ).read_text(encoding="utf-8")
    )
    registry["palettes"][0]["surfaces"]["floor"]["acoustic"] = "metal"
    path = tmp_path / "custom-registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    document["palette_registry"] = {"path": str(path), "sha256": sha256_file(path)}
    codes = {error["code"] for error in validate_document(document)}
    assert "palette_registry_not_canonical" in codes


def test_v90_invalid_registry_skips_surface_checks(library, tmp_path):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V9)
    registry = json.loads(
        (
            ROOT / "godot_walk/room_catalog/material_palettes/palettes-0.2.0.json"
        ).read_text(encoding="utf-8")
    )
    for palette in registry["palettes"]:
        palette["is_default"] = False
    path = tmp_path / "no-default-registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    document["palette_registry"] = {"path": str(path), "sha256": sha256_file(path)}
    errors = validate_document(document)
    codes = {error["code"] for error in errors}
    assert "palette_registry_invalid" in codes
    assert any("exactly one default" in error["message"] for error in errors)
    assert "surface_layer_mismatch" not in codes


def test_v200_registry_rejects_stale_generated_texture_hash(monkeypatch):
    target = (
        ROOT
        / "godot_walk/assets/psx_extension/textures/surfaces/backrooms_yellow_wall_worn.png"
    )
    real_sha256_file = palette_registry.sha256_file

    def stale_hash(path):
        return "0" * 64 if Path(path) == target else real_sha256_file(path)

    monkeypatch.setattr(palette_registry, "sha256_file", stale_hash)
    errors = registry_errors(palette_registry.load_registry_v2())
    assert any("backrooms_yellow.wall.worn" in error for error in errors)
    assert any("hash changed" in error for error in errors)


def _isolated_palette_root(tmp_path, include_wall_worn: bool = False):
    def copy(relative: str) -> None:
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    copy(palette_registry.SCHEMA_PATH_V2.as_posix())
    copy(palette_registry.GENERATED_MANIFEST.as_posix())
    copy("godot_walk/scripts/shape_room_spec.py")
    copy("godot_walk/scripts/generate_surface_variants.py")
    copy("godot_walk/room_catalog/material_palettes/PALETTES_0_2_0.md")
    copy("godot_walk/room_catalog/material_palettes/PALETTES.md")
    for texture in (
        "godot_walk/assets/psx_extension/textures/wallpaper_source_video.png",
        "godot_walk/assets/psx_extension/textures/floor_source_video.png",
        "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    ):
        copy(texture)
    surfaces = Path("godot_walk/assets/psx_extension/textures/surfaces")
    for texture in (ROOT / surfaces).glob("*.png"):
        if texture.name == "backrooms_yellow_wall_worn.png" and not include_wall_worn:
            continue
        copy((surfaces / texture.name).as_posix())
    return tmp_path


def _single_palette_registry():
    registry = json.loads(
        (
            ROOT / "godot_walk/room_catalog/material_palettes/palettes-0.2.0.json"
        ).read_text(encoding="utf-8")
    )
    registry["palettes"] = [registry["palettes"][0]]
    return registry


def test_v200_registry_reports_missing_generated_texture_without_hashing(tmp_path):
    root = _isolated_palette_root(tmp_path)
    errors = registry_errors(_single_palette_registry(), root)
    assert any(
        "backrooms_yellow.wall.worn" in error and "missing" in error for error in errors
    )


@pytest.mark.parametrize(
    "damage",
    [
        lambda record: record.pop("source"),
        lambda record: record.update(source=7),
        lambda record: record.update(source_sha256=7),
        lambda record: record.update(output_sha256=None),
    ],
    ids=["missing-source", "non-string-source", "non-string-hash", "null-hash"],
)
def test_v200_registry_reports_malformed_generated_manifest_record(tmp_path, damage):
    root = _isolated_palette_root(tmp_path, include_wall_worn=True)
    manifest_path = root / palette_registry.GENERATED_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = next(
        item
        for item in manifest["records"]
        if item["output"].endswith("backrooms_yellow_wall_worn.png")
    )
    damage(record)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = registry_errors(_single_palette_registry(), root)
    assert any(
        "backrooms_yellow.wall.worn" in error and "malformed" in error
        for error in errors
    )


def test_v90_preserves_v80_geometry_light_and_palette(library):
    for seed in KEPT_SEEDS:
        old = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V8)
        new = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V9)
        assert _without_surface(old) == _without_surface(new), seed
        old_light = [cell.get("light") for cell in old["cells"]]
        new_light = [cell.get("light") for cell in new["cells"]]
        old_palette = [cell.get("palette") for cell in old["cells"]]
        new_palette = [cell.get("palette") for cell in new["cells"]]
        assert old_light == new_light and old_palette == new_palette, seed


def test_v90_maps_validate_and_assign_surface_records(library, registry):
    for seed in KEPT_SEEDS:
        document = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V9)
        assert validate_document(document) == [], seed
        for cell in document["cells"]:
            generated = cell["role"] != "void" and not cell.get("module")
            assert ("wear" in cell) == generated, (seed, cell["cell_id"])
            assert ("surface_variants" in cell) == generated, (seed, cell["cell_id"])
            if not generated:
                continue
            assert 0 <= cell["wear"] <= 2
            assert set(cell["surface_variants"]) == set(SURFACES)
            palette = next(
                p
                for p in registry["palettes"]
                if p["palette_id"] == cell["palette"]["palette_id"]
            )
            for surface, variant in cell["surface_variants"].items():
                assert variant in palette["surfaces"][surface]["variants"]


def test_dark_wing_landmarks_and_spawn_follow_wear_constraints(library, registry):
    for seed in KEPT_SEEDS:
        document = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V9)
        spawn = document["cells"][0]["cell_id"]
        wing = set(document["dark_wing"]["cell_ids"])
        assert document["cells"][0]["wear"] == 0
        for cell in document["cells"]:
            if cell.get("landmark"):
                assert cell["wear"] == 0, (seed, cell["cell_id"])
            if cell["cell_id"] in wing:
                assert cell["wear"] >= 1, (seed, cell["cell_id"])
            if cell["cell_id"] == spawn:
                assert cell["wear"] == 0


def test_wear_skews_toward_dark_wings_from_the_seeded_stream(library):
    dark, bright = [], []
    for seed in range(1, 31):
        document = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V9)
        wing = set(document["dark_wing"]["cell_ids"])
        for cell in document["cells"]:
            if cell["cell_id"] in wing:
                dark.append(cell["wear"])
            elif "wear" in cell and cell.get("light", {}).get("tier") == "bright":
                bright.append(cell["wear"])
    assert dark and bright
    assert sum(dark) / len(dark) > sum(bright) / len(bright)


def test_surface_validator_rejects_tampering(library, registry):
    document = build_map(1, library, cells=12, version=GENERATOR_VERSION_V9)
    changed = copy.deepcopy(document)
    generated = next(cell for cell in changed["cells"] if "wear" in cell)
    generated["surface_variants"]["wall"] = "glossy"
    assert "surface_variant_unknown" in {
        error["code"] for error in surface_errors(changed, registry)
    }
    changed = copy.deepcopy(document)
    generated = next(cell for cell in changed["cells"] if "wear" in cell)
    generated["wear"] = 3
    assert "surface_wear_invalid" in {
        error["code"] for error in surface_errors(changed, registry)
    }
    changed = copy.deepcopy(document)
    generated = next(cell for cell in changed["cells"] if "wear" in cell)
    generated.pop("wear")
    assert "surface_layer_missing" in {
        error["code"] for error in surface_errors(changed, registry)
    }
    if document["dark_wing"]["cell_ids"]:
        changed = copy.deepcopy(document)
        wing_cell = next(
            cell
            for cell in changed["cells"]
            if cell["cell_id"] == document["dark_wing"]["cell_ids"][0]
        )
        wing_cell["wear"] = 0
        assert "surface_dark_wing_clean" in {
            error["code"] for error in surface_errors(changed, registry)
        }


def test_v90_shape_specs_carry_selected_variants_and_acoustic_tags(library):
    document = build_map(11, library, cells=12, version=GENERATOR_VERSION_V9)
    links = edge_links(document)
    checked = 0
    for cell in document["cells"]:
        if "wear" not in cell:
            continue
        spec = build_spec(document, "a" * 64, cell, "shape_room_pending", links)
        assert spec["materials"]["registry_version"] == "0.2.0"
        assert spec["materials"]["wear"] == cell["wear"]
        assert spec["materials"]["variants"] == cell["surface_variants"]
        if cell["wear"] > 0:
            checked += 1
            assert spec["materials"]["acoustic"]["floor"] in ACOUSTIC_TAGS
            assert (
                spec["materials"]["floor"]["variant"]
                == cell["surface_variants"]["floor"]
            )
    assert checked > 0


def test_older_maps_do_not_carry_surface_records(library):
    for version in ("gmap-0.5.0", "gmap-0.8.0"):
        document = build_map(1, library, cells=12, version=version)
        assert all("wear" not in cell for cell in document["cells"])


@pytest.mark.skipif(
    os.environ.get("GMAP_SURFACE_SWEEP") != "1",
    reason="600-map surface sweep; run with GMAP_SURFACE_SWEEP=1",
)
def test_v90_seed_sweep_12_and_20_cells(library):
    for cell_count in (12, 20):
        wear: Counter[int] = Counter()
        variants: Counter[str] = Counter()
        invalid = []
        for seed in range(1, 301):
            document = build_map(
                seed, library, cells=cell_count, version=GENERATOR_VERSION_V9
            )
            errors = validate_document(document)
            if errors:
                invalid.append((seed, errors[:2]))
            for cell in document["cells"]:
                if "wear" in cell:
                    wear[cell["wear"]] += 1
                    variants.update(cell["surface_variants"].values())
        assert not invalid
        assert wear[2] and variants["worn"] and variants["damaged"]
