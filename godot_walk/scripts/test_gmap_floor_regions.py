"""Tests for the gmap-0.12.0 floor-material palettes (#208).

The new tile, metal and wood palettes arrive through a keyed regional floor
layer. The 0.1.0 and 0.2.0 registries, geometry, light, wear, surface-variant and
reverb draws stay unchanged.
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_library as library
import gmap_palette as pal
import gmap_palette_registry as reg
import shape_room as sr
from deterministic_json import ROOT, canonical_bytes
from generate_palette_0_3_0_textures import check as check_palette_textures
from gmap_elevation import directed_edges, strongly_connected, walkable_ids
from gmap_floor_regions import (
    FLOOR_PALETTES,
    MAX_REGION_SEEDS,
    MIN_DEFAULT_AREA_SHARE,
    REGION_RADIUS,
    STREAM,
    envelope_area_m2,
    palette_for_seed,
    palette_summary,
    seed_draw,
)
from gmap_library import Library
from gmap_validate import validate_document
from shape_room import edge_links
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAP_DIR = ROOT / "godot_walk/room_catalog/generative_maps"
CATALOG = ROOT / "godot_walk/room_catalog"
V11 = build.GENERATOR_VERSION_V11
V12 = build.GENERATOR_VERSION_V12
EXISTING = ("backrooms_yellow", "industrial_concrete", "plaster_debris")
SWEEP = range(1, 41)
COMMITTED_SEEDS = (1, 2, 3, 32, 279)


@pytest.fixture(scope="module")
def lib() -> Library:
    return library.load_library(INDEX)


@pytest.fixture(scope="module")
def registry() -> dict:
    return reg.load_registry_v3()


@pytest.fixture(scope="module")
def maps(lib: Library) -> dict[int, dict]:
    return {seed: build.build_map(seed, lib, cells=12, version=V12) for seed in SWEEP}


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


def walkable(document: dict) -> list[dict]:
    return [cell for cell in document["cells"] if cell["role"] != "void"]


def generated(document: dict) -> list[dict]:
    return [cell for cell in walkable(document) if not cell.get("module")]


def palette_id(cell: dict) -> str:
    return (cell.get("palette") or {}).get("palette_id", "")


def registry_palette(registry: dict, palette_id: str) -> dict:
    return next(p for p in registry["palettes"] if p["palette_id"] == palette_id)


def shape_area(cell: dict, document: dict, links: dict) -> float:
    return float(
        build_spec(document, "a" * 64, cell, "shape_room_pending", links)["area_m2"]
    )


def test_v3_registry_is_valid_and_keeps_the_three_existing_palettes(registry):
    assert reg.registry_errors(registry) == []
    ids = [palette["palette_id"] for palette in registry["palettes"]]
    assert ids == [
        *EXISTING,
        "tiled_institutional",
        "metal_service",
        "wood_parquet",
    ]
    v2 = {p["palette_id"]: p for p in reg.load_registry_v2()["palettes"]}
    v3 = {p["palette_id"]: p for p in registry["palettes"]}
    assert all(v3[palette_id] == v2[palette_id] for palette_id in EXISTING)
    assert reg.default_palette(registry)["palette_id"] == "backrooms_yellow"
    floors = {
        palette_id: v3[palette_id]["surfaces"]["floor"]["acoustic"]
        for palette_id in FLOOR_PALETTES
    }
    assert floors == {
        "tiled_institutional": "tile",
        "metal_service": "metal",
        "wood_parquet": "wood",
    }
    for palette in registry["palettes"]:
        for surface in reg.SURFACES_V2:
            field = palette["surfaces"][surface]
            assert field["acoustic"] in reg.ACOUSTIC_TAGS
            assert set(field["variants"]) == set(reg.VARIANTS)


def test_new_textures_are_reproducible_and_manifested():
    assert check_palette_textures() == []
    manifest = json.loads(
        (ROOT / reg.GENERATED_MANIFEST_V3).read_text(encoding="utf-8")
    )
    assert len(manifest["records"]) == 18
    assert {record["variant"] for record in manifest["records"]} == set(reg.VARIANTS)


def test_v12_maps_are_deterministic_valid_and_reference_the_canonical_registry(lib):
    first = build.build_map(32, lib, cells=12, version=V12)
    second = build.build_map(32, lib, cells=12, version=V12)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert validate_document(first) == []
    assert first["generator_version"] == V12
    assert first["map_id"] == f"gmap-32-{V12}"
    assert first["palette_registry"] == reg.registry_ref_v3()
    assert first["floor_regions"]["stream"] == STREAM
    assert first["floor_regions"]["max_seeds"] == MAX_REGION_SEEDS
    assert first["floor_regions"]["radius"] == REGION_RADIUS
    assert first["floor_regions"]["min_default_area_share"] == MIN_DEFAULT_AREA_SHARE
    assert "floor_region_layer" in first["rules"]


def test_v12_changes_only_the_palette_layer(lib):
    for seed in COMMITTED_SEEDS:
        old = build.build_map(seed, lib, cells=12, version=V11)
        new = build.build_map(seed, lib, cells=12, version=V12)
        for key in (
            "catalog_snapshot",
            "library_index",
            "lattice",
            "shape_stage_max",
            "distribution",
            "void_budget",
            "registration_accepted",
            "scale_calibrated",
            "layout_variant",
            "growth_cell_target",
            "dark_wing",
            "elevation",
            "elevation_loops",
            "reverb_layer",
            "module_budget",
            "degenerate_budget",
        ):
            assert old.get(key) == new.get(key), (seed, key)
        assert old["edges"] == new["edges"], seed
        for old_cell, new_cell in zip(old["cells"], new["cells"], strict=True):
            for key in (
                "cell_id",
                "envelope_xz",
                "ceiling_range_m",
                "allowed_primitives",
                "required_ports",
                "role",
                "rarity_tier",
                "mode",
                "module",
                "shape_stage_target",
                "shape_class_target",
                "light",
                "wear",
                "surface_variants",
                "reverb",
                "floor_y",
                "landmark",
                "diagonal_passage",
                "diagonal_link_chamfer",
            ):
                assert old_cell.get(key) == new_cell.get(key), (
                    seed,
                    old_cell["cell_id"],
                    key,
                )
            if old_cell.get("palette", {}).get("anchor_module_id"):
                assert (
                    new_cell["palette"]["anchor_module_id"]
                    == old_cell["palette"]["anchor_module_id"]
                )
                assert (
                    new_cell["palette"]["palette_id"]
                    == old_cell["palette"]["palette_id"]
                )


def test_v12_maps_stay_strongly_connected(maps):
    for seed, document in maps.items():
        assert strongly_connected(walkable_ids(document), directed_edges(document)), seed


def test_region_choices_are_per_cell_keyed_draws():
    assert seed_draw(1, 0, "c00") == seed_draw(1, 0, "c00")
    assert seed_draw(1, 0, "c00") != seed_draw(1, 0, "c01")
    assert seed_draw(1, 0, "c00") != seed_draw(2, 0, "c00")
    assert seed_draw(1, 0, "c00") != seed_draw(1, 1, "c00")
    assert [seed_draw(1, 0, cell) for cell in ("c00", "c01")] == [
        seed_draw(1, 0, "c00"),
        seed_draw(1, 0, "c01"),
    ]
    assert all(palette_for_seed(1, 0, cell) in FLOOR_PALETTES for cell in ("c00", "c01"))


def test_seed_32_has_a_coherent_patch_for_each_new_palette(maps):
    document = maps[32]
    seeds = document["floor_regions"]["seed_cells"]
    assert [(seed["cell_id"], seed["palette_id"]) for seed in seeds] == [
        ("c11", "metal_service"),
        ("c07", "tiled_institutional"),
        ("c02", "wood_parquet"),
    ]
    graph = pal.open_neighbours(document)
    by_id = {cell["cell_id"]: cell for cell in document["cells"]}
    spawn = document["cells"][0]["cell_id"]
    protected = {spawn} | set(graph[spawn])
    for seed in seeds:
        distance = pal.distances(graph, seed["cell_id"])
        members = [
            cell_id
            for cell_id, cell in by_id.items()
            if cell.get("palette", {}).get("region_seed_cell_id") == seed["cell_id"]
        ]
        assert seed["cell_id"] in members
        for cell_id in members:
            cell = by_id[cell_id]
            assert cell["palette"]["palette_id"] == seed["palette_id"]
            assert cell["palette"]["region_distance"] == distance[cell_id]
            assert distance[cell_id] <= REGION_RADIUS
            assert cell_id not in protected
            assert not cell.get("module")
            assert not cell.get("diagonal_passage")
    assert all(
        "region_seed_cell_id" not in by_id[cell_id].get("palette", {})
        for cell_id in protected
        if "palette" in by_id[cell_id]
    )


def test_default_carpet_share_stays_at_or_above_55_percent(maps):
    total_default = 0.0
    total_generated = 0.0
    total_non_anchor = 0.0
    seen = Counter()
    for seed, document in maps.items():
        links = edge_links(document)
        cells = generated(document)
        areas = {cell["cell_id"]: shape_area(cell, document, links) for cell in cells}
        non_anchor = [
            cell for cell in cells if not cell.get("palette", {}).get("anchor_module_id")
        ]
        default = [
            cell for cell in cells if palette_id(cell) == "backrooms_yellow"
        ]
        default_area = sum(areas[cell["cell_id"]] for cell in default)
        whole_area = sum(areas.values())
        non_anchor_area = sum(areas[cell["cell_id"]] for cell in non_anchor)
        assert non_anchor_area > 0
        assert default_area / non_anchor_area >= MIN_DEFAULT_AREA_SHARE, seed
        assert default_area / whole_area >= MIN_DEFAULT_AREA_SHARE, seed
        total_default += default_area
        total_generated += whole_area
        total_non_anchor += non_anchor_area
        seen.update(palette_id(cell) for cell in cells)
    assert total_default / total_generated >= MIN_DEFAULT_AREA_SHARE
    assert total_default / total_non_anchor >= MIN_DEFAULT_AREA_SHARE
    assert set(FLOOR_PALETTES) <= set(seen)
    assert all(
        registry_palette(reg.load_registry_v3(), palette)["surfaces"]["floor"][
            "acoustic"
        ]
        in reg.ACOUSTIC_TAGS
        for palette in FLOOR_PALETTES
    )


def test_palette_summary_reports_the_per_map_mix(maps, lib):
    document = maps[32]
    summary = palette_summary(document)
    assert summary["layer"] == "present"
    assert summary["stream"] == STREAM
    assert summary["default_palette"] == "backrooms_yellow"
    assert summary["cell_counts"]["metal_service"] == 2
    assert summary["cell_counts"]["tiled_institutional"] == 1
    assert summary["cell_counts"]["wood_parquet"] == 1
    assert sum(summary["cell_counts"].values()) == len(generated(document))
    assert 0.0 < summary["default_area_share"] < 1.0
    assert summary["default_non_anchor_area_share"] >= MIN_DEFAULT_AREA_SHARE
    assert sum(summary["area_m2"].values()) == pytest.approx(
        sum(envelope_area_m2(cell) for cell in generated(document)), abs=0.01
    )
    legacy = build.build_map(1, lib, cells=12, version=V11)
    legacy_summary = palette_summary(legacy)
    assert legacy_summary["layer"] == "absent"
    assert legacy_summary["stream"] is None
    assert legacy_summary["cell_counts"]["backrooms_yellow"] > 0


def test_cli_reports_the_floor_palette_mix(tmp_path, capsys, maps):
    path = tmp_path / "map.json"
    path.write_bytes(canonical_bytes(maps[32]))
    assert gm.main(["validate", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["summary"]["floor_palettes"] == palette_summary(maps[32])
    result = gm.generate(32, INDEX, out_dir=tmp_path, version=V12)
    assert result["summary"]["floor_palettes"]["layer"] == "present"
    assert result["summary"]["floor_palettes"]["stream"] == STREAM


def test_validator_accepts_canonical_v3_and_rejects_a_mismatched_hash(maps, tmp_path):
    document = maps[32]
    assert validate_document(document) == []
    stale = copy.deepcopy(document)
    stale["palette_registry"]["sha256"] = "0" * 64
    assert "stale_palette_registry" in codes(stale)
    missing = copy.deepcopy(document)
    missing.pop("palette_registry")
    assert codes(missing) == {"schema"}
    tampered = copy.deepcopy(document)
    region_cell = next(
        cell for cell in tampered["cells"] if cell.get("palette", {}).get(
            "region_seed_cell_id"
        )
    )
    region_cell["palette"]["palette_id"] = "industrial_concrete"
    assert "palette_mismatch" in codes(tampered)
    region_metadata = copy.deepcopy(document)
    region_metadata["floor_regions"]["seed_cells"][0]["palette_id"] = "wood_parquet"
    assert "floor_region_metadata_mismatch" in codes(region_metadata)
    no_regions = copy.deepcopy(document)
    no_regions.pop("floor_regions")
    assert codes(no_regions) == {"schema"}
    registry = json.loads(
        (ROOT / reg.REGISTRY_PATH_V3).read_text(encoding="utf-8")
    )
    registry["palettes"][-1]["surfaces"]["floor"]["acoustic"] = "carpet"
    custom = tmp_path / "custom-0.3.0.json"
    custom.write_text(json.dumps(registry), encoding="utf-8")
    noncanonical = copy.deepcopy(document)
    noncanonical["palette_registry"] = {
        "path": str(custom),
        "sha256": reg.sha256_file(custom),
    }
    assert "palette_registry_not_canonical" in codes(noncanonical)


def test_shape_specs_carry_v3_materials_and_floor_acoustics(maps, registry):
    document = maps[32]
    links = edge_links(document)
    seen = Counter()
    for cell in generated(document):
        spec = build_spec(document, "a" * 64, cell, "shape_room_pending", links)
        palette = registry_palette(registry, palette_id(cell))
        assert spec["materials"]["registry_version"] == "0.3.0"
        assert spec["materials"]["variants"] == cell["surface_variants"]
        assert (
            spec["materials"]["floor"]["acoustic"]
            == palette["surfaces"]["floor"]["acoustic"]
        )
        assert spec["materials"]["floor"]["variant"] == cell["surface_variants"]["floor"]
        seen[palette_id(cell)] += 1
    assert set(FLOOR_PALETTES) <= set(seen)


def test_v11_maps_still_validate_with_their_own_registry(lib):
    document = build.build_map(1, lib, cells=12, version=V11)
    assert validate_document(document) == []
    assert document["palette_registry"] == reg.registry_ref_v2()
    assert "floor_regions" not in document
    assert not any(
        cell.get("palette", {}).get("region_seed_cell_id")
        for cell in document["cells"]
    )


@pytest.mark.parametrize("seed", COMMITTED_SEEDS)
def test_committed_v12_outputs_are_current_and_valid(seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=V12)
    stem = f"gmap-{seed}-{V12}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (
            tmp_path / f"{stem}{suffix}"
        ).read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []
    assert sr.validate(MAP_DIR / f"{stem}.json", "all_walkable") == []
    committed = CATALOG / "shape_rooms" / stem
    regenerated = tmp_path / "rooms" / stem
    sr.generate(MAP_DIR / f"{stem}.json", "all_walkable", out_dir=tmp_path / "rooms")
    assert sorted(path.name for path in committed.glob("*.json")) == sorted(
        path.name for path in regenerated.glob("*.json")
    )
    for path in committed.glob("*.json"):
        assert path.read_bytes() == (regenerated / path.name).read_bytes(), path.name
