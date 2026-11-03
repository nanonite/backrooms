"""Tests for gmap-0.2.0 standard doorway margins and rare degenerate corner doorways (issue 186)."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_library as library
import shape_room as sr
from deterministic_json import ROOT, DeterministicWriteError
from gmap_geometry import contact, polygon_rect
from gmap_validate import validate_document
from library_index import load_json
from shape_room_checks import ShapeRoomError
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
CATALOG = ROOT / "godot_walk/room_catalog"
MAP_DIR = CATALOG / "generative_maps"
V2 = "gmap-0.2.0"
SEEDS = range(1, 31)


@pytest.fixture(scope="module")
def lib() -> library.Library:
    return library.load_library(INDEX)


@pytest.fixture(scope="module")
def maps(lib) -> dict[int, dict]:
    return {seed: build.build_map(seed, lib, version=V2) for seed in SEEDS}


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


def rects_of(document: dict) -> dict[str, tuple]:
    return {c["cell_id"]: polygon_rect(c["envelope_xz"]) for c in document["cells"]}


def port_table(document: dict) -> dict[str, tuple[str, dict]]:
    return {p["port_id"]: (c["cell_id"], p) for c in document["cells"] for p in c["required_ports"]}


def along(port: dict) -> float:
    return port["pos_xz"][1] if port["normal"][0] else port["pos_xz"][0]


def first_degenerate(maps: dict[int, dict]) -> dict:
    return next(d for d in maps.values() if d["degenerate_budget"]["used"])


def seed_with_degenerate(maps: dict[int, dict]) -> int:
    return next(s for s, d in maps.items() if d["degenerate_budget"]["used"])


# --- standard margins ----------------------------------------------------------


def test_every_v2_map_validates_and_records_its_rules(maps) -> None:
    for seed, document in maps.items():
        assert validate_document(document) == [], seed
        assert document["generator_version"] == V2 and document["map_id"] == f"gmap-{seed}-{V2}"
        assert {"standard_doorway_margin", "degenerate_only_in_degenerate_cells"} <= set(document["rules"])
        assert document["rules"] == sorted(document["rules"])


def side_ends(rect: tuple, port: dict) -> tuple[float, float]:
    return (rect[1], rect[3]) if port["normal"][0] else (rect[0], rect[2])


def test_standard_ports_keep_1_5_m_from_overlap_ends_and_envelope_corners(maps) -> None:
    standard_ports = clean_edges = 0
    for document in maps.values():
        rects, ports = rects_of(document), port_table(document)
        for cell_id, port in ports.values():
            if port["placement"] == "standard":
                standard_ports += 1
                low, high = side_ends(rects[cell_id], port)
                assert along(port) - low >= 1.5 and high - along(port) >= 1.5, port["port_id"]
        for edge in document["edges"]:
            (cell_a, port_a), (cell_b, port_b) = ports[edge["from"]], ports[edge["to"]]
            shared = contact(rects[cell_a], rects[cell_b])
            assert shared is not None and shared[3] - shared[2] >= 3
            if port_a["placement"] == port_b["placement"] == "standard":
                clean_edges += 1
                assert along(port_a) - shared[2] >= 1.5 and shared[3] - along(port_a) >= 1.5
    assert standard_ports > 200 and clean_edges > 100


def test_ports_sit_on_the_half_metre_grid_and_lattice_declares_it(maps) -> None:
    document = maps[1]
    assert document["lattice"] == {"kind": "square", "unit_m": 1.0, "port_unit": "level_doorway_2m_v1", "port_step_m": 0.5}
    halves = [v for d in maps.values() for _, p in port_table(d).values() for v in p["pos_xz"] if v != int(v)]
    assert halves and all(v * 2 == int(v * 2) for v in halves)


# --- degenerate cells ------------------------------------------------------------


def test_degenerate_ports_only_in_degenerate_cells_and_within_budget(maps) -> None:
    degenerate_maps = 0
    for document in maps.values():
        modes = {c["cell_id"]: c["mode"] for c in document["cells"]}
        used = sorted(c for c, mode in modes.items() if mode == "degenerate")
        assert len(used) == document["degenerate_budget"]["used"] <= document["degenerate_budget"]["max"] == 1
        degenerate_maps += bool(used)
        for cell in document["cells"]:
            for port in cell["required_ports"]:
                if port["placement"] == "degenerate":
                    assert modes[cell["cell_id"]] == "degenerate"
        for cell_id in used:
            cell = next(c for c in document["cells"] if c["cell_id"] == cell_id)
            assert cell["role"] in ("ground", "threshold") and cell_id != "c00"
            assert any(p["placement"] == "degenerate" for p in cell["required_ports"])
    assert 0 < degenerate_maps < len(maps)  # rare, but present


def test_degenerate_max_zero_disables_and_larger_budgets_are_respected(lib) -> None:
    for seed in range(1, 21):
        off = build.build_map(seed, lib, version=V2, degenerate_max=0)
        assert off["degenerate_budget"] == {"max": 0, "used": 0}
        assert all(c["mode"] == "standard" for c in off["cells"])
        assert validate_document(off) == []
        wide = build.build_map(seed, lib, version=V2, degenerate_max=3)
        assert validate_document(wide) == []
        assert wide["degenerate_budget"]["used"] <= 3
    with pytest.raises(Exception, match="degenerate-max"):
        build.build_map(1, lib, version=V2, degenerate_max=-1)


def test_degenerate_selection_is_deterministic_and_a_separate_stream(lib, maps) -> None:
    for seed in (3, 8, 14):
        assert build.build_map(seed, lib, version=V2) == maps.get(seed, build.build_map(seed, lib, version=V2))
    on, off = build.build_map(3, lib, version=V2), build.build_map(3, lib, version=V2, degenerate_max=0)
    # The structure (cells, edges) is the same; only degenerate ports moved.
    assert [c["envelope_xz"] for c in on["cells"]] == [c["envelope_xz"] for c in off["cells"]]
    assert on["edges"] == off["edges"]


def test_degenerate_port_really_touches_an_envelope_corner(maps) -> None:
    document = first_degenerate(maps)
    rects, ports = rects_of(document), port_table(document)
    modes = {c["cell_id"]: c["mode"] for c in document["cells"]}
    found = 0
    for cell_id, port in ports.values():
        low, high = side_ends(rects[cell_id], port)
        near_corner = along(port) - low < 1.5 or high - along(port) < 1.5
        assert near_corner == (port["placement"] == "degenerate")
        if near_corner:
            found += 1
            assert modes[cell_id] == "degenerate"
    assert found >= 1


def test_neighbour_of_a_corner_doorway_keeps_a_standard_port(maps) -> None:
    document = first_degenerate(maps)  # budget 1: only one cell can own the corner
    ports = port_table(document)
    mixed = [
        e for e in document["edges"]
        if "degenerate" in {ports[e["from"]][1]["placement"], ports[e["to"]][1]["placement"]}
    ]
    assert mixed
    for edge in mixed:
        assert {ports[edge["from"]][1]["placement"], ports[edge["to"]][1]["placement"]} == {"degenerate", "standard"}


# --- validator negative controls ---------------------------------------------------


def move_to_corner(document: dict, port_id: str) -> None:
    """Slide both ends of an edge so the doorway touches the low end of its overlap."""
    rects, ports = rects_of(document), port_table(document)
    edge = next(e for e in document["edges"] if port_id in (e["from"], e["to"]))
    cell_a, port_a = ports[edge["from"]]
    cell_b, port_b = ports[edge["to"]]
    low = contact(rects[cell_a], rects[cell_b])[2]
    for port in (port_a, port_b):
        index = 1 if port["normal"][0] else 0
        port["pos_xz"][index] = low + 1


def a_standard_edge(document: dict) -> dict:
    return next(
        e for e in document["edges"]
        if port_table(document)[e["from"]][1]["placement"] == "standard"
        and rects_of(document)[e["from"].split(":")[0]] is not None
        and contact(rects_of(document)[e["from"].split(":")[0]], rects_of(document)[e["to"].split(":")[0]])[3]
        - contact(rects_of(document)[e["from"].split(":")[0]], rects_of(document)[e["to"].split(":")[0]])[2] == 3
    )


def test_control_standard_port_hugging_a_corner_is_rejected(maps) -> None:
    document = copy.deepcopy(maps[1])
    edge = a_standard_edge(document)
    move_to_corner(document, edge["from"])
    assert "standard_port_margin" in codes(document)


def test_control_degenerate_label_in_a_standard_cell_is_rejected(maps) -> None:
    document = copy.deepcopy(maps[1])
    edge = a_standard_edge(document)
    move_to_corner(document, edge["from"])
    for end in (edge["from"], edge["to"]):
        port_table(document)[end][1]["placement"] = "degenerate"
    assert "degenerate_in_standard_cell" in codes(document)


def test_control_degenerate_label_without_a_corner_is_rejected(maps) -> None:
    document = copy.deepcopy(maps[1])
    edge = a_standard_edge(document)
    port_table(document)[edge["from"]][1]["placement"] = "degenerate"
    assert "degenerate_label_unneeded" in codes(document)


def test_control_budget_and_cell_restrictions(maps) -> None:
    document = copy.deepcopy(maps[1])
    document["cells"][0]["mode"] = "degenerate"
    found = codes(document)
    assert {"degenerate_budget_used", "degenerate_cell_not_allowed"} <= found
    document["degenerate_budget"] = {"max": 0, "used": 1}
    assert "degenerate_budget_exceeded" in codes(document)
    missing = copy.deepcopy(maps[1])
    del missing["degenerate_budget"]
    assert "degenerate_budget_missing" in codes(missing)


def test_control_off_step_ports_and_incomplete_rules(maps) -> None:
    document = copy.deepcopy(maps[1])
    port_table(document)[document["edges"][0]["from"]][1]["pos_xz"][0] += 0.25
    assert "port_off_step" in codes(document)
    rules = copy.deepcopy(maps[1])
    rules["rules"].remove("standard_doorway_margin")
    assert "rules_incomplete" in codes(rules)


# --- determinism, committed outputs, back-compat ------------------------------------


def test_v2_outputs_are_byte_identical_and_refuse_to_overwrite(tmp_path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    gm.generate(3, INDEX, svg=True, out_dir=first, version=V2)
    gm.generate(3, INDEX, svg=True, out_dir=second, version=V2)
    names = sorted(p.name for p in first.iterdir())
    assert names == [f"gmap-3-{V2}.fill.json", f"gmap-3-{V2}.json", f"gmap-3-{V2}.svg"]
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    (first / names[0]).write_text("{}\n", encoding="utf-8")
    with pytest.raises(DeterministicWriteError):
        gm.generate(3, INDEX, svg=True, out_dir=first, version=V2)


def test_degenerate_cells_are_marked_in_the_svg(tmp_path) -> None:
    gm.generate(3, INDEX, svg=True, out_dir=tmp_path, version=V2)
    svg = (tmp_path / f"gmap-3-{V2}.svg").read_text(encoding="utf-8")
    assert "degenerate" in svg and 'stroke-dasharray="8 3 2 3"' in svg
    plain = tmp_path / "plain"
    gm.generate(1, INDEX, svg=True, out_dir=plain, version=V2)
    assert "degenerate" not in (plain / f"gmap-1-{V2}.svg").read_text(encoding="utf-8")


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_committed_v2_outputs_are_current_and_valid(seed, tmp_path) -> None:
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=V2)
    stem = f"gmap-{seed}-{V2}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_v1_artifacts_are_unchanged_and_still_validate(seed, tmp_path, lib) -> None:
    document = load_json(MAP_DIR / f"gmap-{seed}-gmap-0.1.0.json")
    assert "degenerate_budget" not in document and "port_step_m" not in document["lattice"]
    for cell in document["cells"]:
        assert "mode" not in cell and all("placement" not in p for p in cell["required_ports"])
        assert all(v == int(v) for p in cell["required_ports"] for v in p["pos_xz"])
    assert build.build_map(seed, lib) == document
    assert gm.validate_path(MAP_DIR / f"gmap-{seed}-gmap-0.1.0.json") == []
    sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in MAP_DIR.glob(f"gmap-{seed}-gmap-0.1.0*")}
    assert len(sums) == 3
    for seed_dir in (CATALOG / "shape_rooms" / f"gmap-{seed}-gmap-0.1.0",):
        assert sr.validate(MAP_DIR / f"gmap-{seed}-gmap-0.1.0.json", "all_walkable") == []
        assert load_json(seed_dir / "index.json")["generator_version"] == "shape-room-0.1.0"


def test_v1_maps_still_require_only_the_v1_rule_ids(lib) -> None:
    document = build.build_map(1, lib)
    assert document["rules"] == sorted(build.RULE_IDS)
    assert validate_document(document) == []


def test_cli_defaults_to_v2_and_accepts_degenerate_max(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(gm, "OUT_DIR", tmp_path)
    monkeypatch.setattr(gm, "ROOT", tmp_path)
    assert gm.main(["generate", "--seed", "3", "--index", str(INDEX), "--degenerate-max", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["map_id"] == f"gmap-3-{V2}"


# --- shape rooms: strict margins ----------------------------------------------------


def specs_for(seed: int) -> dict[str, dict]:
    files = sr.derive(MAP_DIR / f"gmap-{seed}-{V2}.json", "all_walkable")
    return {n[:-5]: json.loads(d) for n, d in files.items() if n != "index.json"}


def margin(spec: dict, doorway: dict) -> float:
    envelope = spec["envelope_xz"]
    x_wall = bool(doorway["normal"][0])
    low, high = (envelope[0][1], envelope[2][1]) if x_wall else (envelope[0][0], envelope[2][0])
    centre = doorway["pos_xz"][1] if x_wall else doorway["pos_xz"][0]
    return min(centre - 1 - low, high - (centre + 1))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_v2_shape_rooms_keep_the_full_margin_unless_degenerate(seed) -> None:
    specs = specs_for(seed)
    for spec in specs.values():
        assert spec["generator_version"] == "shape-room-0.2.0"
        corner = sorted(d["port_id"] for d in spec["doorways"] if margin(spec, d) < 0.5)
        if spec["mode"] == "standard":
            assert corner == [] and spec["degenerate_features"] == [] and spec["degenerate_port_ids"] == []
        else:
            assert corner == spec["degenerate_port_ids"] and spec["degenerate_features"] == ["corner_doorway"]
        assert all(f["sign"] == "symbol" for f in spec["features"])
    schema = load_json(CATALOG / "shape_room.schema.json")
    for spec in specs.values():
        assert list(Draft202012Validator(schema).iter_errors(spec)) == []


def test_a_degenerate_shape_room_exists_with_its_port_ids(maps) -> None:
    seed = seed_with_degenerate(maps)
    degenerate = [s for s in (specs_for(seed) if seed <= 3 else {}).values() if s["mode"] == "degenerate"]
    if seed <= 3:
        assert degenerate and degenerate[0]["degenerate_port_ids"]
    document = maps[seed]
    links = sr.edge_links(document)
    cell = next(c for c in document["cells"] if c["mode"] == "degenerate")
    spec = build_spec(document, "0" * 64, cell, "shape_room_pending", links)
    assert spec["mode"] == "degenerate" and spec["degenerate_features"] == ["corner_doorway"]
    assert spec["degenerate_port_ids"] == sorted(p["port_id"] for p in cell["required_ports"] if p["placement"] == "degenerate")


def test_control_standard_cell_with_a_corner_doorway_fails_closed(maps) -> None:
    seed = seed_with_degenerate(maps)
    document = copy.deepcopy(maps[seed])
    cell = next(c for c in document["cells"] if c["mode"] == "degenerate")
    links = sr.edge_links(document)
    cell["mode"] = "standard"  # same hugging ports, but the waiver is no longer granted
    with pytest.raises(ShapeRoomError, match="wall margin"):
        build_spec(document, "0" * 64, cell, "shape_room_pending", links)


def test_v1_shape_rooms_keep_the_corner_waiver(lib) -> None:
    document = build.build_map(1, lib)
    links = sr.edge_links(document)
    for cell in document["cells"]:
        if cell["role"] != "void":
            spec = build_spec(document, "0" * 64, cell, "shape_room_pending", links)
            assert spec["generator_version"] == "shape-room-0.1.0" and "mode" not in spec
