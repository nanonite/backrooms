"""Tests for neighbour palettes (issue 192): registry, assignment rules, gmap-0.5.0 maps and rooms."""

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
from deterministic_json import ROOT
from gmap_library import Library, LibraryModule
from gmap_svg import render_svg
from gmap_validate import validate_document
from library_index import load_json

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
CATALOG = ROOT / "godot_walk/room_catalog"
MAP_DIR = CATALOG / "generative_maps"
V5 = "gmap-0.5.0"
HALL = ("godot_gopro_industrial_hall_south_socket_v1", ("industrial_hall", "concrete_grey"), 2)
DEBRIS = ("video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1", ("rock_field", "plaster_walls"), 3)
KIT = ("godot_early_pocket_single_west_v1", ("backrooms_yellow", "wallpaper"), 0)
VIOLA = ("video_b9161c467ed2d30a_bill_viola_single_room_v1", ("bare_walls", "domestic_room"), 3)


@pytest.fixture(scope="module")
def registry() -> dict:
    return reg.load_registry()


@pytest.fixture(scope="module")
def lib() -> Library:
    return library.load_library(INDEX)


def fake_module(spec: tuple, role: str = "figure") -> LibraryModule:
    module_id, tags, tier = spec
    return LibraryModule(module_id, 1, None, (), (), True, role, tier, None, None, tags)


def fake_library(*specs: tuple, roles: dict | None = None) -> Library:
    roles = roles or {}
    return Library({}, {}, tuple(fake_module(s, roles.get(s[0], "figure")) for s in specs))


def synthetic(chain: int, modules: dict[str, tuple], extra_edges: list | None = None, seed: int = 7) -> dict:
    """c00..c{chain-1} joined in a line by direct edges; `modules` maps a module cell to (spec, parent cell)."""
    cells = [{"cell_id": f"c{i:02d}", "role": "ground"} for i in range(chain)]
    edges = [{"from": f"c{i:02d}:p1", "to": f"c{i + 1:02d}:p0", "connector": "direct"} for i in range(chain - 1)]
    for cell_id, (spec, parent) in modules.items():
        cells.append({"cell_id": cell_id, "role": "figure", "module": {"module_id": spec[0], "version": 1}})
        edges.append({"from": f"{parent}:pm", "to": f"{cell_id}:p0", "connector": "direct"})
    cells.append({"cell_id": "c99", "role": "void"})
    return {"seed": seed, "attempt": 0, "generator_version": V5, "cells": cells, "edges": edges + (extra_edges or [])}


def palette_ids(records: dict) -> dict[str, str]:
    return {cell: r["palette_id"] for cell, r in records.items()}


# --- registry ------------------------------------------------------------------------------------------


def test_committed_registry_is_valid_with_one_default(registry):
    assert reg.registry_errors(registry) == []
    assert [p["palette_id"] for p in registry["palettes"]] == ["backrooms_yellow", "industrial_concrete", "plaster_debris"]
    assert reg.default_palette(registry)["palette_id"] == "backrooms_yellow"


def test_default_palette_is_exactly_the_old_kit_material_block(registry):
    from shape_room_spec import MATERIALS

    block = reg.spec_materials(reg.default_palette(registry))
    assert block["wall"]["texture"] == MATERIALS["wallpaper_texture"] and block["floor"]["texture"] == MATERIALS["floor_texture"]
    assert block["ceiling"]["texture"] == MATERIALS["ceiling_texture"]
    assert block["trim_color"] == MATERIALS["trim_color"] and block["lamp_color"] == MATERIALS["lamp_color"]
    assert (block["wall"]["tile_m"], block["floor"]["tile_m"], block["ceiling"]["tile_m"]) == (1.5, 4.0, 4.0)


def test_source_palettes_carry_the_library_values(registry):
    hall, debris = reg.palette_by_id(registry, "industrial_concrete"), reg.palette_by_id(registry, "plaster_debris")
    assert hall["wall"]["color"] == [0.43, 0.43, 0.40] and hall["ceiling"]["color"] == [0.34, 0.35, 0.33]
    assert hall["trim_color"]["color"] == [0.28, 0.29, 0.28] and hall["floor"]["texture"].endswith("industrial-hall-panorama-v3/textures/concrete_floor.png")
    assert debris["wall"]["texture"].endswith("direct-source-crops-v1/painted_wall.png") and debris["ceiling"]["color"] == [0.43, 0.42, 0.38]
    assert debris["trim_color"]["color"] == [0.24, 0.25, 0.23] and debris["floor"]["color"] == [0.34, 0.33, 0.31]
    assert "texture" not in debris["floor"] and "texture" in hall["floor"]
    assert hall["lamp_color"]["provenance"]["sign"] == debris["lamp_color"]["provenance"]["sign"] == "symbol"


def broken(registry: dict, mutate) -> list[str]:
    copied = copy.deepcopy(registry)
    mutate(copied)
    return reg.registry_errors(copied)


def test_registry_validation_catches_each_kind_of_damage(registry):
    hall = lambda r: r["palettes"][1]  # noqa: E731
    assert any("missing" in e for e in broken(registry, lambda r: hall(r)["floor"].update(texture="res://nope/none.png")))
    assert any("does not contain" in e for e in broken(registry, lambda r: hall(r)["wall"]["provenance"].update({"from": hall(r)["wall"]["provenance"]["from"].split("::")[0] + "::materials.nothing"})))
    assert any("provenance file" in e for e in broken(registry, lambda r: hall(r)["wall"]["provenance"].update({"from": "res://nope.gd::x"})))
    assert any("holds Color" in e for e in broken(registry, lambda r: hall(r)["wall"].update(color=[0.1, 0.2, 0.3])))
    assert any("unique" in e for e in broken(registry, lambda r: hall(r).update(palette_id="backrooms_yellow")))
    assert any("exactly one default" in e for e in broken(registry, lambda r: hall(r).update(is_default=True)))
    assert any("exactly one default" in e for e in broken(registry, lambda r: r["palettes"][0].update(is_default=False)))
    assert broken(registry, lambda r: hall(r).pop("lamp_color"))  # schema


def test_style_tags_select_the_first_overlapping_non_default_palette(registry):
    pick = lambda tags: (reg.select_palette(registry, tags) or {}).get("palette_id")  # noqa: E731
    assert pick(HALL[1]) == "industrial_concrete" and pick(("window_strip",)) == "plaster_debris"
    assert pick(KIT[1]) is None and pick(VIOLA[1]) is None and pick(()) is None
    assert pick(("concrete_grey", "rock_field")) == "industrial_concrete"  # sorted registry order


# --- assignment rules ----------------------------------------------------------------------------------


def test_distance_one_takes_the_palette_and_distance_three_stays_default(registry):
    document = synthetic(6, {"c10": (HALL, "c00")})
    records = pal.assign_palettes(document, fake_library(HALL), registry)
    assert records["c00"] == {"palette_id": "industrial_concrete", "anchor_module_id": HALL[0], "distance": 1}
    assert all(records[f"c0{i}"] == pal.record("backrooms_yellow") for i in (3, 4, 5))
    assert set(records) == {f"c0{i}" for i in range(6)}  # module and void cells get none


def test_distance_two_is_a_seeded_coin_drawn_in_cell_order(registry):
    outcomes = set()
    for seed in range(40):
        document = synthetic(4, {"c10": (HALL, "c00")}, seed=seed)
        records = pal.assign_palettes(document, fake_library(HALL), registry)
        again = pal.assign_palettes(copy.deepcopy(document), fake_library(HALL), registry)
        assert records == again
        rng = pal.palette_rng(seed, 0, V5)
        coin = [rng.random() for _ in range(4)][1]  # c01 is the second cell drawn
        wins = coin < pal.COIN_PROBABILITY
        assert (records["c01"]["palette_id"] == "industrial_concrete") == wins
        assert records["c01"] == (pal.record("industrial_concrete", HALL[0], 2) if wins else pal.record("backrooms_yellow"))
        outcomes.add(wins)
    assert outcomes == {True, False}


def test_competing_anchors_smaller_distance_then_higher_tier_then_module_id(registry):
    both = fake_library(HALL, DEBRIS)
    near_one = synthetic(5, {"c10": (HALL, "c00"), "c11": (DEBRIS, "c03")})  # c00 is 1 from the hall, 4 from the debris room
    assert pal.assign_palettes(near_one, both, registry)["c00"]["anchor_module_id"] == HALL[0]
    tie = synthetic(3, {"c10": (HALL, "c01"), "c11": (DEBRIS, "c01")})  # c01 is 1 from both: tier 3 beats tier 2
    assert pal.assign_palettes(tie, both, registry)["c01"] == pal.record("plaster_debris", DEBRIS[0], 1)
    a, b = DEBRIS, (DEBRIS[0].replace("video_", "audio_"), ("window_strip",), 3)  # same tier: module_id decides
    flat = synthetic(3, {"c10": (a, "c01"), "c11": (b, "c01")})
    assert pal.assign_palettes(flat, fake_library(a, b), registry)["c01"]["anchor_module_id"] == b[0]


def test_kit_modules_and_unmatched_figures_exert_no_influence(registry):
    for spec, roles in ((KIT, {KIT[0]: "ground"}), (VIOLA, {})):
        records = pal.assign_palettes(synthetic(3, {"c10": (spec, "c00")}), fake_library(spec, roles=roles), registry)
        assert set(palette_ids(records).values()) == {"backrooms_yellow"}
        assert all(r["anchor_module_id"] is None and r["distance"] is None for r in records.values())
    tagged_ground = fake_library(HALL, roles={HALL[0]: "ground"})  # a ground-role module never anchors, whatever its tags
    assert set(palette_ids(pal.assign_palettes(synthetic(3, {"c10": (HALL, "c00")}), tagged_ground, registry)).values()) == {"backrooms_yellow"}


def test_only_open_edges_carry_distance(registry):
    document = synthetic(4, {"c10": (HALL, "c00")})
    document["edges"][0]["connector"] = "closed_visible"  # c00 | c01 is a closed doorway
    records = pal.assign_palettes(document, fake_library(HALL), registry)
    assert records["c00"]["distance"] == 1 and records["c01"] == pal.record("backrooms_yellow")


# --- gmap-0.5.0 maps ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def maps(lib) -> dict[int, dict]:
    return {seed: build.build_map(seed, lib, version=V5) for seed in range(1, 61)}


def test_v5_map_equals_the_v4_map_apart_from_version_and_palettes(lib, maps):
    for seed in (1, 2, 3, 14, 20, 33):
        v4 = build.build_map(seed, lib, version="gmap-0.4.0")
        v5 = copy.deepcopy(maps[seed] if seed in maps else build.build_map(seed, lib, version=V5))
        for cell in v5["cells"]:
            cell.pop("palette", None)
        v5.pop("palette_registry")
        v5["map_id"], v5["generator_version"], v5["rules"] = v4["map_id"], v4["generator_version"], v4["rules"]
        assert v5 == v4, seed


def test_v5_cells_carry_palettes_exactly_on_generated_walkable_cells(maps):
    for seed, document in maps.items():
        assert validate_document(document) == [], seed
        for cell in document["cells"]:
            assert ("palette" in cell) == (cell["role"] != "void" and "module" not in cell), (seed, cell["cell_id"])
        assert "palette_assignment" in document["rules"] and document["palette_registry"] == reg.registry_ref()


def test_validation_catches_a_wrong_or_stale_palette(maps):
    document = copy.deepcopy(maps[3])
    plain = next(c for c in document["cells"] if c.get("palette", {}).get("anchor_module_id") is None and "palette" in c)
    plain["palette"] = {"palette_id": "industrial_concrete", "anchor_module_id": None, "distance": None}
    assert "palette_mismatch" in {e["code"] for e in validate_document(document)}
    unknown = copy.deepcopy(maps[3])
    next(c for c in unknown["cells"] if "palette" in c)["palette"]["palette_id"] = "no_such_palette"
    assert "palette_unknown" in {e["code"] for e in validate_document(unknown)}
    stale = copy.deepcopy(maps[3])
    stale["palette_registry"]["sha256"] = "0" * 64
    assert "stale_palette_registry" in {e["code"] for e in validate_document(stale)}
    missing = copy.deepcopy(maps[3])
    del missing["palette_registry"]
    assert "palette_registry_missing" in {e["code"] for e in validate_document(missing)}


def test_seed_3_has_both_a_hall_ring_and_a_debris_ring(maps):
    anchored = {c["palette"]["palette_id"]: c["palette"]["anchor_module_id"] for c in maps[3]["cells"] if c.get("palette", {}).get("anchor_module_id")}
    assert anchored == {"industrial_concrete": HALL[0], "plaster_debris": DEBRIS[0]}


@pytest.fixture(scope="module")
def rooms300(tmp_path_factory):
    base = tmp_path_factory.mktemp("palette")
    found = {}
    for seed in range(1, 301):
        gm.generate(seed, INDEX, out_dir=base, version=V5)
        path = base / f"gmap-{seed}-{V5}.json"
        assert gm.validate_path(path) == [], seed
        found[seed] = (load_json(path), {n[:-5]: json.loads(d) for n, d in sr.derive(path, "all_walkable").items() if n != "index.json"})
    return found


def test_seeds_1_to_300_are_valid_and_every_room_resolves_its_palette(rooms300, registry):
    seen = Counter()
    for seed, (document, specs) in rooms300.items():
        cells = {c["cell_id"]: c for c in document["cells"]}
        for cell_id, spec in specs.items():
            palette = reg.palette_by_id(registry, cells[cell_id]["palette"]["palette_id"])
            assert spec["generator_version"] == "shape-room-0.5.0" and spec["material_source"] == "palette_registry"
            assert spec["materials"] == reg.spec_materials(palette), (seed, cell_id)
            seen[palette["palette_id"]] += 1
    assert set(seen) == {"backrooms_yellow", "industrial_concrete", "plaster_debris"}


def test_v5_rooms_have_the_v4_geometry(rooms300, tmp_path):
    for seed in (2, 3, 14):
        gm.generate(seed, INDEX, out_dir=tmp_path, version="gmap-0.4.0")
        path = tmp_path / f"gmap-{seed}-gmap-0.4.0.json"
        old = {n[:-5]: json.loads(d) for n, d in sr.derive(path, "all_walkable").items() if n != "index.json"}
        for cell_id, spec in rooms300[seed][1].items():
            same = {k: v for k, v in spec.items() if k not in ("generator_version", "map_id", "map_sha256", "material_source", "materials")}
            assert same == {k: v for k, v in old[cell_id].items() if k in same}, (seed, cell_id)


def test_index_lists_each_rooms_palette_and_the_committed_schema_accepts_it(tmp_path):
    gm.generate(3, INDEX, out_dir=tmp_path, version=V5)
    path = tmp_path / f"gmap-3-{V5}.json"
    sr.generate(path, "all_walkable", out_dir=tmp_path / "rooms")
    assert sr.validate(path, "all_walkable", out_dir=tmp_path / "rooms") == []
    index = load_json(tmp_path / "rooms" / f"gmap-3-{V5}" / "index.json")
    assert Counter(r["palette_id"] for r in index["rooms"]) == {"backrooms_yellow": 9, "industrial_concrete": 1, "plaster_debris": 2}


def test_svg_tints_only_the_cells_that_took_a_palette(maps):
    svg = render_svg(maps[3])
    assert svg.count("industrial_concrete d1") == 1 and svg.count("plaster_debris d") == 2
    assert render_svg(maps[1]).count("d1") == 0  # a seed with kit modules only: no tint, no palette label


# --- older generators are untouched ----------------------------------------------------------------------


@pytest.mark.parametrize("version", ["gmap-0.1.0", "gmap-0.2.0", "gmap-0.3.0", "gmap-0.4.0"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_older_artifacts_regenerate_byte_identically(version, seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=version)
    stem = f"gmap-{seed}-{version}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    sr.generate(tmp_path / f"{stem}.json", "all_walkable", out_dir=tmp_path / "rooms")
    committed, regenerated = CATALOG / "shape_rooms" / stem, tmp_path / "rooms" / stem
    assert sorted(p.name for p in committed.glob("*.json")) == sorted(p.name for p in regenerated.glob("*.json"))
    for path in committed.glob("*.json"):
        assert path.read_bytes() == (regenerated / path.name).read_bytes(), path.name


def test_the_cli_default_is_still_gmap_0_2_0_and_offers_0_5_0():
    assert build.GENERATOR_VERSION_V5 in build.VERSIONS and build.GENERATOR_VERSION_V2 == "gmap-0.2.0"
    source = Path(gm.__file__).read_text(encoding="utf-8")
    assert "choices=VERSIONS, default=GENERATOR_VERSION_V2" in source


@pytest.mark.parametrize("seed", [1, 2, 3, 14, 30, 129])
def test_committed_v5_outputs_are_current_and_valid(seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=V5)
    stem = f"gmap-{seed}-{V5}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []
    assert sr.validate(MAP_DIR / f"{stem}.json", "all_walkable") == []
