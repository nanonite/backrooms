"""Tests for fill candidates (issue 182): rotation fit, port alignment, status."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_fill as fill
import gmap_library as library
from deterministic_json import ROOT

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
SCHEMA = ROOT / "godot_walk/room_catalog/generative_map_fill.schema.json"
TYPE = "level_doorway_2m_v1"


def module(footprint, sockets=(), usable=False) -> library.LibraryModule:
    return library.LibraryModule("m", 1, None, tuple(footprint), tuple(sockets), usable)


def rect_footprint(width: float, depth: float):
    return [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]


def rotations_that_fit(mod, rect) -> list[int]:
    lib = library.Library({}, {}, (mod,))
    return [c["rotation_deg"] for c in fill.cell_candidates(lib, rect, [])]


def test_known_footprint_fits_only_at_matching_rotations():
    mod = module(rect_footprint(6.0, 13.8))
    assert rotations_that_fit(mod, (10, 20, 16, 34)) == [0, 180]  # 6 x 14 envelope
    assert rotations_that_fit(mod, (0, 0, 14, 6)) == [90, 270]  # 14 x 6 envelope
    assert rotations_that_fit(mod, (0, 0, 14, 14)) == [0, 90, 180, 270]
    assert rotations_that_fit(mod, (0, 0, 6, 13)) == []  # 13 m is too short


def test_l_shape_fit_uses_its_bounding_box_but_rotation_moves_the_notch():
    ell = module([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])
    placed, shift = fill.place_footprint(ell, 90, (10, 10, 14, 14))
    assert min(x for x, _ in placed) == 10 and min(z for _, z in placed) == 10
    assert set(placed) != {(x + shift[0], z + shift[1]) for x, z in ell.footprint}


def test_ports_alignable_needs_a_tested_socket_that_lands_on_the_port():
    socket = library.Socket("east", (6.0, 6.9), (1.0, 0.0), TYPE, True)
    mod = module(rect_footprint(6.0, 13.8), [socket])
    port = {"pos_xz": [16, 27], "normal": [1, 0], "compatibility_type": TYPE}
    assert fill.alignable(mod, 0, (10, 20, 16, 34), [port])
    assert not fill.alignable(mod, 0, (10, 20, 16, 34), [dict(port, normal=[-1, 0])])
    assert not fill.alignable(mod, 0, (10, 20, 16, 34), [dict(port, compatibility_type="other")])
    wide = (10, 20, 18, 36)  # 2 m of slack: a lattice translation reaches a shifted port
    assert fill.alignable(mod, 0, wide, [dict(port, pos_xz=[18, 29])])
    assert not fill.alignable(mod, 0, wide, [dict(port, pos_xz=[18, 31])])
    assert fill.alignable(mod, 2, (10, 20, 16, 34), [dict(port, normal=[-1, 0], pos_xz=[10, 27])])
    untested = library.Socket("east", (6.0, 6.9), (1.0, 0.0), TYPE, False)
    assert not fill.alignable(module(rect_footprint(6.0, 13.8), [untested]), 0, (10, 20, 16, 34), [port])


def test_real_index_never_offers_layout_usable_candidates(tmp_path):
    for seed in (1, 2, 3):
        gm.generate(seed, INDEX, out_dir=tmp_path)
        data = json.loads((tmp_path / f"gmap-{seed}-gmap-0.1.0.fill.json").read_text(encoding="utf-8"))
        candidates = [c for cell in data["cells"] for c in cell["candidates"]]
        assert candidates and not any(c["layout_usable"] for c in candidates)
        assert all(c["footprint_fits"] for c in candidates)


def test_cell_status_and_schema(tmp_path):
    gm.generate(2, INDEX, out_dir=tmp_path)
    data = json.loads((tmp_path / "gmap-2-gmap-0.1.0.fill.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(data)) == []
    document = json.loads((tmp_path / "gmap-2-gmap-0.1.0.json").read_text(encoding="utf-8"))
    roles = {c["cell_id"]: c["role"] for c in document["cells"]}
    for cell in data["cells"]:
        if roles[cell["cell_id"]] == "void":
            assert cell["cell_status"] == "void" and cell["candidates"] == []
        elif cell["candidates"]:
            assert cell["cell_status"] == "module_candidates"
        else:
            assert cell["cell_status"] == "shape_room_pending"
    assert data["note"] == fill.NOTE and data["playable"] is False


def test_fill_candidate_required_port_counts_match_the_map():
    lib = library.load_library(INDEX)
    document = build.build_map(5, lib)
    data = fill.build_fill(document, "0" * 64, lib)
    ports = {c["cell_id"]: len(c["required_ports"]) for c in document["cells"]}
    for cell in data["cells"]:
        assert {c["required_port_count"] for c in cell["candidates"]} <= {ports[cell["cell_id"]]}


def test_validate_checks_sibling_fill_file(tmp_path):
    gm.generate(4, INDEX, out_dir=tmp_path)
    path = tmp_path / "gmap-4-gmap-0.1.0.json"
    assert gm.validate_path(path) == []
    fill_path = tmp_path / "gmap-4-gmap-0.1.0.fill.json"
    data = json.loads(fill_path.read_text(encoding="utf-8"))
    data["map_file"]["sha256"] = "0" * 64
    fill_path.write_text(json.dumps(data), encoding="utf-8")
    assert [e["code"] for e in gm.validate_path(path)] == ["fill_stale_map_hash"]
    data["playable"] = True
    fill_path.write_text(json.dumps(data), encoding="utf-8")
    assert [e["code"] for e in gm.validate_path(path)] == ["fill_schema"]


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_rotation_round_trips(turns):
    point = (2.0, 5.0)
    centre = (3.0, 7.0)
    moved = fill.rotate_point(point, centre, turns)
    assert fill.rotate_point(moved, centre, 4 - turns) == pytest.approx(point)
