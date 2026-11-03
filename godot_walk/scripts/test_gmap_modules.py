"""Tests for gmap-0.3.0 library modules as proposed, untested leaf cells (issue 188)."""

from __future__ import annotations

import copy
import json
import math
import random
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_fill as fill
import gmap_library as library
import gmap_modules as modules
import shape_room as sr
from deterministic_json import ROOT, sha256_file
from doorway_sizes import DEFAULT_TYPE, DOORWAY_SIZES, WIDE_TYPE, doorway_size, port_margin_m
from gmap_geometry import contact, polygon_rect
from gmap_grow import Cell, Draft, RetryAttempt
from gmap_transform import rotate_vector, world_point
from gmap_validate import validate_document
from library_index import load_json
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
CATALOG = ROOT / "godot_walk/room_catalog"
MAP_DIR = CATALOG / "generative_maps"
V3 = "gmap-0.3.0"
USABLE = {
    "godot_early_pocket_single_west_v1": ("ground", 0, "west", DEFAULT_TYPE),
    "godot_later_bay_column_bounded_v1": ("ground", 1, "east", DEFAULT_TYPE),
    "godot_gopro_industrial_hall_south_socket_v1": ("figure", 2, "south", WIDE_TYPE),
    "video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1": ("figure", 2, "north", WIDE_TYPE),
}


@pytest.fixture(scope="module")
def lib() -> library.Library:
    return library.load_library(INDEX)


@pytest.fixture(scope="module")
def maps(lib) -> dict[int, dict]:
    return {seed: build.build_map(seed, lib, version=V3) for seed in range(1, 41)}


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


def module_cells(document: dict) -> list[dict]:
    return [c for c in document["cells"] if c.get("module")]


def by_id(document: dict) -> dict[str, dict]:
    return {c["cell_id"]: c for c in document["cells"]}


def first_map(maps, predicate) -> dict:
    return next(d for d in maps.values() if predicate(d))


# --- accepted metadata loader --------------------------------------------------------------


def test_loader_reads_accepted_records_and_marks_exactly_the_four_modules_usable(lib):
    usable = {m.module_id: m for m in lib.modules if m.layout_usable}
    assert set(usable) == set(USABLE)
    for module_id, (role, tier, socket, _) in USABLE.items():
        module = usable[module_id]
        assert (module.form_role, module.rarity_tier) == (role, tier)
        assert module.apollonian is not None and module.dionysian is not None and module.style_tags
        assert module.metadata_record is not None
        assert module.metadata_record["sha256"] == sha256_file(ROOT / module.metadata_record["path"])
        assert module.metadata_record["path"].endswith(("module_poetics_v2.json", ".accepted.json"))
        assert [s.socket_id for s in module.sockets if s.tested] == [socket]
    for module in lib.modules:
        assert module.form_role in ("ground", "figure")  # all eleven rooms are accepted


def test_loader_prefers_accepted_over_the_draft_and_falls_back_to_the_draft(tmp_path):
    entry = next(
        e for e in load_json(INDEX)["modules"] if e["module_id"] == "godot_early_pocket_single_west_v1"
    )
    poetics_dir = tmp_path / "godot_walk/room_catalog/module_poetics"
    poetics_dir.mkdir(parents=True)
    name = "godot_early_pocket_single_west_v1-v1"
    draft_file = poetics_dir / f"{name}.json"
    shutil.copy(CATALOG / "module_poetics" / f"{name}.json", draft_file)
    only_draft = library.load_module(entry, tmp_path)
    assert not only_draft.layout_usable and only_draft.form_role is None and only_draft.rarity_tier is None
    assert only_draft.style_tags == () and only_draft.metadata_record["path"].endswith(f"{name}.json")
    accepted_file = poetics_dir / f"{name}.accepted.json"
    shutil.copy(CATALOG / "module_poetics" / f"{name}.accepted.json", accepted_file)
    both = library.load_module(entry, tmp_path)
    assert both.layout_usable and both.form_role == "ground"
    assert both.metadata_record["path"].endswith(f"{name}.accepted.json")
    assert both.footprint == only_draft.footprint and both.legacy_layout_usable is False
    record = json.loads(accepted_file.read_text(encoding="utf-8"))
    record["metadata_status"] = "draft_mechanical"  # an accepted-named file that is not accepted
    accepted_file.write_text(json.dumps(record), encoding="utf-8")
    assert not library.load_module(entry, tmp_path).layout_usable
    record["metadata_status"] = "operator_accepted"
    record["eligibility"]["layout_eligible_derived"] = False  # accepted but not layout eligible
    accepted_file.write_text(json.dumps(record), encoding="utf-8")
    assert not library.load_module(entry, tmp_path).layout_usable


def test_metadata_records_are_listed_sorted_with_matching_hashes(lib, maps):
    records = maps[1]["library_index"]["metadata_records"]
    assert [r["module_id"] for r in records] == sorted(m.module_id for m in lib.modules)
    for record in records:
        assert record["sha256"] == sha256_file(ROOT / record["path"])
    assert library.metadata_records(lib) == records


# --- older generators are untouched ----------------------------------------------------------


@pytest.mark.parametrize("version", ["gmap-0.1.0", "gmap-0.2.0"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_older_versions_regenerate_byte_identically(version, seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=version)
    stem = f"gmap-{seed}-{version}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    shape_out = tmp_path / "shape_rooms"
    sr.generate(tmp_path / f"{stem}.json", "all_walkable", out_dir=shape_out)
    committed = CATALOG / "shape_rooms" / stem
    regenerated = shape_out / stem
    assert sorted(p.name for p in committed.glob("*.json")) == sorted(p.name for p in regenerated.glob("*.json"))
    for path in committed.glob("*.json"):
        assert path.read_bytes() == (regenerated / path.name).read_bytes(), path.name
    document = json.loads((tmp_path / f"{stem}.json").read_text(encoding="utf-8"))
    assert "module_budget" not in document and "metadata_records" not in document["library_index"]
    assert not any("module" in c or "connection_status" in e for c in document["cells"] for e in document["edges"])


@pytest.mark.parametrize("version", ["gmap-0.1.0", "gmap-0.2.0"])
def test_committed_older_documents_still_satisfy_the_extended_schemas(version):
    schema = Draft202012Validator(load_json(CATALOG / "generative_map.schema.json"))
    fill_schema = Draft202012Validator(load_json(CATALOG / "generative_map_fill.schema.json"))
    for seed in (1, 2, 3):
        assert list(schema.iter_errors(load_json(MAP_DIR / f"gmap-{seed}-{version}.json"))) == []
        assert list(fill_schema.iter_errors(load_json(MAP_DIR / f"gmap-{seed}-{version}.fill.json"))) == []
    # the fill's layout_usable stays the draft's (false) for the older generators
    data = load_json(MAP_DIR / f"gmap-1-{version}.fill.json")
    assert not any(c["layout_usable"] for cell in data["cells"] for c in cell["candidates"])


# --- budget, weights and draws -----------------------------------------------------------------


def test_every_map_places_one_or_two_distinct_usable_modules_and_validates(maps):
    counts = Counter()
    for seed, document in maps.items():
        assert validate_document(document) == [], seed
        placed = module_cells(document)
        assert 1 <= len(placed) <= 2 and document["module_budget"] == {"min": 1, "max": 2, "used": len(placed)}
        assert len({c["module"]["module_id"] for c in placed}) == len(placed)
        assert {c["module"]["module_id"] for c in placed} <= set(USABLE)
        counts[len(placed)] += 1
        assert document["generator_version"] == V3 and document["map_id"] == f"gmap-{seed}-{V3}"
        assert set(document["rules"]) >= set(build.RULE_IDS_V3)
    assert set(counts) == {1, 2}


def test_tier_weights_and_weighted_draws_follow_the_rarity_tiers(lib, monkeypatch):
    assert modules.TIER_WEIGHTS == {0: 4, 1: 3, 2: 2, 3: 1}
    drawn: Counter = Counter()

    def pretend(rng, draft, module):  # always succeeds; only the draw is under test
        drawn[module.module_id] += 1
        draft.cells[f"fake{len(draft.cells)}"] = Cell(f"fake{len(draft.cells)}", (0, 0, 1, 1), module={"module_id": module.module_id})
        return True

    monkeypatch.setattr(modules, "try_module", pretend)
    monkeypatch.setattr(modules, "MODULE_BUDGET", {"min": 1, "max": 1})
    for seed in range(4000):
        modules.attach_modules(random.Random(seed), Draft(), lib)
    weights = {m.module_id: modules.TIER_WEIGHTS[m.rarity_tier] for m in modules.usable_modules(lib)}
    assert sorted(weights.values()) == [2, 2, 3, 4]
    total = sum(weights.values())
    for module_id, weight in weights.items():
        assert drawn[module_id] / 4000 == pytest.approx(weight / total, abs=0.03), module_id


def test_usable_modules_are_in_module_id_order(lib):
    ids = [m.module_id for m in modules.usable_modules(lib)]
    assert ids == sorted(ids) and len(ids) == 4


def test_minimum_budget_failure_asks_for_another_attempt(lib, monkeypatch):
    monkeypatch.setattr(modules, "try_module", lambda rng, draft, module: False)
    with pytest.raises(RetryAttempt):
        modules.attach_modules(random.Random(1), Draft(), lib)


def test_module_budget_cannot_be_met_without_usable_modules(lib):
    nothing = library.Library(lib.index_ref, lib.snapshot_ref, tuple(m for m in lib.modules if not m.layout_usable))
    with pytest.raises(RetryAttempt):
        modules.attach_modules(random.Random(1), Draft(), nothing)


# --- socket landing in all four rotations -----------------------------------------------------


def parent_draft(parent: tuple = (0, 0, 40, 40)) -> tuple[Draft, Cell]:
    draft = Draft(centred=True, margin=1.5)
    cell = Cell("c00", parent)
    draft.cells["c00"] = cell
    return draft, cell


@pytest.mark.parametrize("module_id", sorted(USABLE))
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_socket_lands_on_the_port_for_every_module_and_rotation(lib, module_id, turns):
    module = next(m for m in lib.modules if m.module_id == module_id)
    layout = modules.layout_for(module, turns)
    assert layout is not None
    draft, parent = parent_draft()
    options = modules.module_options(draft, parent, layout)
    assert options, "a 40 m square parent leaves room on every side"
    socket = layout.socket
    assert socket.compatibility_type == USABLE[module_id][3]
    outward = rotate_vector(socket.normal, turns)
    assert outward == layout.outward
    for rect, port, translation in options[:: max(1, len(options) // 25)]:
        placed = world_point(socket.pos, 90 * turns, translation)
        assert math.dist(placed, port) == pytest.approx(modules.LANDING_CLEARANCE_M, abs=1e-6)
        # moved away from the parent: opposite the socket's outward normal
        assert (placed[0] - port[0], placed[1] - port[1]) == pytest.approx(
            (-outward[0] * modules.LANDING_CLEARANCE_M, -outward[1] * modules.LANDING_CLEARANCE_M), abs=1e-6
        )
        x0, z0, x1, z1 = library.bbox(tuple(world_point(p, 90 * turns, translation) for p in module.footprint))
        slack = modules.LANDING_CLEARANCE_M + 1e-6
        assert x0 >= rect[0] - slack and z0 >= rect[1] - slack and x1 <= rect[2] + slack and z1 <= rect[3] + slack
        assert rect[2] - rect[0] == math.ceil(layout.bbox_size[0] - 1e-9) and rect[3] - rect[1] == math.ceil(layout.bbox_size[1] - 1e-9)
        assert port[0] * 2 == int(port[0] * 2) and port[1] * 2 == int(port[1] * 2)  # 0.5 m port lattice
        shared = contact(parent.rect, rect)
        assert shared is not None and shared[0] == (-outward[0], -outward[1])


def test_known_placements_match_hand_computation(lib):
    pocket = next(m for m in lib.modules if m.module_id == "godot_early_pocket_single_west_v1")
    layout = modules.layout_for(pocket, 0)
    assert layout.size == (6, 14) and layout.outward == (-1, 0)
    port, translation = modules.landing(layout, (6, 0, 12, 14), 7.0)
    assert port == (6, 7) and translation == pytest.approx((6.02, 0.1))
    hall = next(m for m in lib.modules if m.module_id == "godot_gopro_industrial_hall_south_socket_v1")
    layout = modules.layout_for(hall, 1)
    assert layout.size == (13, 16) and layout.outward == (-1, 0)
    port, translation = modules.landing(layout, (0, 0, 13, 16), 8.0)
    assert port == (0, 8)
    assert world_point(hall.sockets[0].pos, 90, translation) == pytest.approx((0.02, 8.0))
    column = next(m for m in lib.modules if m.module_id == "godot_later_bay_column_bounded_v1")
    layout = modules.layout_for(column, 0)
    assert layout.size == (8, 7) and layout.outward == (1, 0)
    assert modules.along_candidates(layout, (0, 0, 8, 7)) == [4.5]  # 4.3 .. 4.5 holds one lattice value


def test_wide_doorways_need_wider_margin_and_spacing(lib):
    assert doorway_size(WIDE_TYPE) == (2.4, 2.2) and doorway_size(DEFAULT_TYPE) == (2.0, 2.1)
    assert port_margin_m(DEFAULT_TYPE) == 1.5 and port_margin_m(WIDE_TYPE) == 1.7
    hall = next(m for m in lib.modules if m.module_id == "godot_gopro_industrial_hall_south_socket_v1")
    draft, parent = parent_draft((0, 0, 20, 20))
    layout = modules.layout_for(hall, 0)
    for rect, port, _ in modules.module_options(draft, parent, layout):
        assert 1.7 - 1e-9 <= port[0] - max(rect[0], parent.rect[0]) and port[0] <= min(rect[2], parent.rect[2]) - 1.7 + 1e-9


def test_figure_module_never_hangs_off_a_figure_parent(lib):
    hall = next(m for m in lib.modules if m.module_id == "godot_gopro_industrial_hall_south_socket_v1")
    draft, parent = parent_draft()
    parent.role = "figure"
    assert modules.module_options(draft, parent, modules.layout_for(hall, 0)) == []
    parent.role = "ground"
    assert modules.module_options(draft, parent, modules.layout_for(hall, 0))


def test_modules_keep_off_every_walkable_cell_but_their_parent(lib):
    pocket = next(m for m in lib.modules if m.module_id == "godot_early_pocket_single_west_v1")
    layout = modules.layout_for(pocket, 0)  # cell 6 x 14, parent on its west side
    draft, parent = parent_draft((0, 0, 8, 14))
    base = modules.module_options(draft, parent, layout)
    assert base
    neighbour = Cell("c01", (8, 14, 14, 20))  # touches the module cells that sit at z <= 14 along x 8..14
    draft.cells["c01"] = neighbour
    assert len(modules.module_options(draft, parent, layout)) < len(base)
    for rect, _, _ in modules.module_options(draft, parent, layout):
        assert contact(rect, neighbour.rect) is None


# --- map content ---------------------------------------------------------------------------------


def test_module_cells_are_leaves_with_proposed_untested_edges(maps):
    for document in maps.values():
        cells, edges = by_id(document), document["edges"]
        proposed = [e for e in edges if e.get("connection_status") == "proposed_untested"]
        placed = module_cells(document)
        assert len(proposed) == len(placed)
        for cell in placed:
            assert len(cell["required_ports"]) == 1 and cell["mode"] == "standard"
            module = cell["module"]
            role, tier, socket, compat = USABLE[module["module_id"]]
            assert (cell["role"], cell["rarity_tier"], module["socket_id"]) == (role, tier, socket)
            assert cell["required_ports"][0]["compatibility_type"] == compat
            assert module["metadata_record"]["sha256"] == sha256_file(ROOT / module["metadata_record"]["path"])
            edge = next(e for e in proposed if cell["cell_id"] in (e["from"].split(":")[0], e["to"].split(":")[0]))
            assert edge["connector"] == "direct"
            parent = cells[edge["from"].split(":")[0]]
            assert parent["role"] != "void" and parent["role"] != "threshold" and "module" not in parent
            if role == "figure":
                assert parent["role"] != "figure"
        assert all("connection_status" not in e for e in edges if e not in proposed)


def test_voids_and_degenerate_corners_never_touch_module_cells(maps):
    for document in maps.values():
        placed = {c["cell_id"] for c in module_cells(document)}
        for edge in document["edges"]:
            ends = {edge["from"].split(":")[0], edge["to"].split(":")[0]}
            if edge["connector"] == "closed_visible":
                assert not ends & placed
        for cell in module_cells(document):
            assert cell["required_ports"][0]["placement"] == "standard"


def test_module_ports_keep_the_wall_margin_on_the_parent_side(maps):
    for document in maps.values():
        rects = {c["cell_id"]: polygon_rect(c["envelope_xz"]) for c in document["cells"]}
        for cell in module_cells(document):
            port = cell["required_ports"][0]
            margin = port_margin_m(port["compatibility_type"])
            edge = next(e for e in document["edges"] if e["from"] == port["port_id"] or e["to"] == port["port_id"])
            other = (edge["to"] if edge["from"] == port["port_id"] else edge["from"]).split(":")[0]
            for rect in (rects[cell["cell_id"]], rects[other]):
                low, high = (rect[1], rect[3]) if port["normal"][0] else (rect[0], rect[2])
                where = port["pos_xz"][1] if port["normal"][0] else port["pos_xz"][0]
                assert where - low >= margin - 1e-9 and high - where >= margin - 1e-9


def test_generation_is_deterministic_and_seed_sensitive(lib):
    assert build.build_map(7, lib, version=V3) == build.build_map(7, lib, version=V3)
    placements = {
        json.dumps([c["module"] for c in module_cells(build.build_map(seed, lib, version=V3))], sort_keys=True)
        for seed in range(1, 16)
    }
    assert len(placements) > 8


def test_seeds_1_to_3_place_a_figure_module_and_a_kit_module():
    roles, ids = set(), set()
    for seed in (1, 2, 3):
        document = load_json(MAP_DIR / f"gmap-{seed}-{V3}.json")
        for cell in module_cells(document):
            roles.add(cell["role"])
            ids.add(cell["module"]["module_id"])
    assert "figure" in roles and "ground" in roles
    assert ids & {"godot_gopro_industrial_hall_south_socket_v1", "video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1"}
    assert ids & {"godot_later_bay_column_bounded_v1", "godot_early_pocket_single_west_v1"}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_committed_v3_outputs_are_current_and_valid(seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=V3)
    stem = f"gmap-{seed}-{V3}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []
    assert sr.validate(MAP_DIR / f"{stem}.json", "all_walkable") == []
    svg = (MAP_DIR / f"{stem}.svg").read_text(encoding="utf-8")
    document = load_json(MAP_DIR / f"{stem}.json")
    for cell in module_cells(document):
        assert cell["module"]["module_id"] in svg and "module" in svg
    assert "proposed_untested" not in svg and "e67e22" in svg  # untested joints are drawn in their own colour


def test_cli_generates_v3_and_the_default_stays_v2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gm, "OUT_DIR", tmp_path)
    monkeypatch.setattr(gm, "ROOT", tmp_path)  # outputs land below tmp_path
    assert build.GENERATOR_VERSION_V3 in build.VERSIONS
    seen = {}
    monkeypatch.setattr(gm, "generate", lambda *args, **kwargs: seen.update(version=kwargs["version"]) or {"files": []})
    assert gm.main(["generate", "--seed", "5", "--index", str(INDEX)]) == 0
    assert seen["version"] == build.GENERATOR_VERSION_V2
    assert gm.main(["generate", "--seed", "5", "--index", str(INDEX), "--generator-version", V3]) == 0
    assert seen["version"] == V3
    capsys.readouterr()


# --- fill ---------------------------------------------------------------------------------------


def test_fill_marks_module_cells_placed_with_their_placement(lib, maps):
    schema = Draft202012Validator(load_json(CATALOG / "generative_map_fill.schema.json"))
    for document in list(maps.values())[:10]:
        data = fill.build_fill(document, "0" * 64, lib)
        assert list(schema.iter_errors(data)) == []
        by_cell = {c["cell_id"]: c for c in data["cells"]}
        for cell in document["cells"]:
            entry = by_cell[cell["cell_id"]]
            if cell.get("module"):
                assert entry["cell_status"] == "module_placed" and entry["candidates"] == []
                placement = entry["placement"]
                assert placement["module_id"] == cell["module"]["module_id"]
                assert placement["translation_xz"] == cell["module"]["translation_xz"]
                assert placement["port_id"] == cell["required_ports"][0]["port_id"]
            else:
                assert "placement" not in entry and entry["cell_status"] != "module_placed"
        usable_flags = {c["layout_usable"] for e in data["cells"] for c in e["candidates"]}
        assert True in usable_flags  # 0.3.0 reports the accepted metadata's layout_usable
        assert data["library_index"]["metadata_records"] == document["library_index"]["metadata_records"]
        assert data["playable"] is False


def test_fill_validation_ties_the_fill_to_the_map(tmp_path):
    gm.generate(2, INDEX, out_dir=tmp_path, version=V3)
    path = tmp_path / f"gmap-2-{V3}.json"
    assert gm.validate_path(path) == []
    fill_path = tmp_path / f"gmap-2-{V3}.fill.json"
    data = load_json(fill_path)
    data["cells"][0]["cell_status"] = "void"
    fill_path.write_text(json.dumps(data), encoding="utf-8")
    assert [e["code"] for e in gm.validate_path(path)][0] in ("fill_cells_mismatch", "fill_stale_map_hash")


# --- validator controls ---------------------------------------------------------------------------


@pytest.fixture()
def good(maps) -> dict:
    return copy.deepcopy(first_map(maps, lambda d: len(module_cells(d)) == 2))


def test_validator_accepts_the_generated_maps(good):
    assert validate_document(good) == []


def test_control_socket_misses_port(good):
    module_cells(good)[0]["module"]["translation_xz"][0] += 1.0
    assert {"socket_misses_port"} <= codes(good)


def test_control_wrong_rotation_breaks_normal_or_landing(good):
    cell = module_cells(good)[0]
    cell["module"]["rotation_deg"] = (cell["module"]["rotation_deg"] + 90) % 360
    assert codes(good) & {"socket_normal_mismatch", "socket_misses_port"}


def test_control_footprint_outside_cell(good):
    module = module_cells(good)[0]["module"]
    module["translation_xz"][1] += 0.4
    module["translation_xz"][0] += 0.4
    assert codes(good) & {"footprint_outside_cell", "socket_misses_port"}


def test_control_module_twice(good):
    a, b = module_cells(good)
    b["module"] = copy.deepcopy(a["module"])
    assert "module_placed_twice" in codes(good)


def test_control_unknown_module_and_unusable_module(good):
    module_cells(good)[0]["module"]["module_id"] = "no_such_module"
    assert "module_unknown" in codes(good)
    other = copy.deepcopy(good)
    cell = module_cells(other)[0]
    cell["module"].update(module_id="godot_early_pocket_pass_through_v1", socket_id="east")
    assert "module_not_layout_usable" in codes(other)


def test_control_stale_metadata_record(good):
    module_cells(good)[0]["module"]["metadata_record"]["sha256"] = "0" * 64
    assert "stale_metadata_record" in codes(good)
    other = copy.deepcopy(good)
    other["library_index"]["metadata_records"][0]["sha256"] = "1" * 64
    assert "stale_metadata_record" in codes(other)


def test_control_edge_status_must_be_proposed_untested(good):
    edge = next(e for e in good["edges"] if e.get("connection_status"))
    del edge["connection_status"]
    assert "edge_not_proposed_untested" in codes(good)
    other = copy.deepcopy(good)
    generated = next(e for e in other["edges"] if not e.get("connection_status"))
    generated["connection_status"] = "proposed_untested"
    assert "connection_status_on_generated_edge" in codes(other)
    third = copy.deepcopy(good)
    next(e for e in third["edges"] if e.get("connection_status"))["connection_status"] = "tested"
    assert "schema" in codes(third)


def test_control_budget_and_role(good):
    good["module_budget"]["used"] = 7
    assert "module_budget_used" in codes(good)
    other = copy.deepcopy(good)
    module_cells(other)[0]["role"] = "threshold"
    assert "module_role_mismatch" in codes(other)
    third = copy.deepcopy(good)
    del third["module_budget"]
    assert "schema" not in codes(third) and "module_budget_missing" in codes(third)


def test_control_module_touching_another_cell(good):
    cell = module_cells(good)[0]
    rect = polygon_rect(cell["envelope_xz"])
    ids = {c["cell_id"]: polygon_rect(c["envelope_xz"]) for c in good["cells"]}
    parent_id = next(
        (e["from"] if e["to"].startswith(cell["cell_id"] + ":") else e["to"]).split(":")[0]
        for e in good["edges"]
        if cell["cell_id"] + ":" in (e["from"] + e["to"])
    )
    victim = next(c for c in good["cells"] if c["role"] != "void" and c["cell_id"] not in (cell["cell_id"], parent_id))
    width, depth = rect[2] - rect[0], rect[3] - rect[1]
    victim["envelope_xz"] = [[rect[2], rect[1]], [rect[2] + 3, rect[1]], [rect[2] + 3, rect[1] + depth], [rect[2], rect[1] + depth]]
    del ids, width
    assert "module_touches_neighbour" in codes(good)


def test_schema_rejects_unknown_module_fields(good):
    module_cells(good)[0]["module"]["extra"] = 1
    assert "schema" in codes(good)


# --- shape rooms on the parent side ----------------------------------------------------------------


def parent_specs(document: dict) -> list[tuple[dict, dict]]:
    links = sr.edge_links(document)
    result = []
    for cell in document["cells"]:
        if cell["role"] == "void" or cell.get("module"):
            continue
        if any(p["compatibility_type"] != DEFAULT_TYPE for p in cell["required_ports"]):
            spec = build_spec(document, "0" * 64, cell, "shape_room_pending", links)
            result.append((cell, spec))
    return result


def test_parent_rooms_cut_doorways_sized_by_compatibility_type(maps):
    schema = load_json(CATALOG / "shape_room.schema.json")
    validator = Draft202012Validator(schema)
    seen_wide = 0
    for document in maps.values():
        for cell, spec in parent_specs(document):
            assert spec["generator_version"] == "shape-room-0.3.0"
            assert list(validator.iter_errors(spec)) == []
            ports = {p["port_id"]: p for p in cell["required_ports"]}
            for doorway in spec["doorways"]:
                width, height = DOORWAY_SIZES[ports[doorway["port_id"]]["compatibility_type"]]
                assert (doorway["width_m"], doorway["height_m"]) == (width, height)
                assert doorway["compatibility_type"] == ports[doorway["port_id"]]["compatibility_type"]
                seen_wide += doorway["width_m"] == 2.4
            if spec["construction"] == "arms":
                assert spec["arm_width_m"] >= 4  # >= 0.5 m of wall beside a 2.4 m doorway
    assert seen_wide


def test_index_lists_no_room_for_module_cells_and_specs_stay_typed(maps, tmp_path):
    path = MAP_DIR / f"gmap-2-{V3}.json"
    files = sr.derive(path, "all_walkable")
    document = load_json(path)
    cells = {c["cell_id"] for c in document["cells"] if c["role"] != "void" and not c.get("module")}
    assert {n[:-5] for n in files if n != "index.json"} == cells
    index = json.loads(files["index.json"])
    assert index["generator_version"] == "shape-room-0.3.0" and len(index["rooms"]) == len(cells)
    for name, data in files.items():
        if name != "index.json":
            assert all("compatibility_type" in d for d in json.loads(data)["doorways"])


def test_doorway_table_is_the_same_in_python_and_gdscript():
    text = (ROOT / "godot_walk/scripts/doorway_sizes.gd").read_text(encoding="utf-8")
    block = text[text.index("const SIZES") :]
    found = {
        name: (float(w), float(h))
        for name, w, h in re.findall(r'"([^"]+)":\s*Vector2\(([\d.]+),\s*([\d.]+)\)', block)
    }
    assert found == DOORWAY_SIZES
    assert re.search(r'const DEFAULT_TYPE := "([^"]+)"', text).group(1) == DEFAULT_TYPE
    builder = (ROOT / "godot_walk/scripts/shape_room_builder.gd").read_text(encoding="utf-8")
    assert "DOOR_HEIGHT" not in builder and "doorway_sizes.gd" in builder


def test_module_joint_recess_is_wired_and_guarded_by_a_failing_check():
    """#189: the parent doorway is cut larger than the library opening, and the headless
    test fails on any coplanar reveal face and keeps a control that rebuilds the old geometry."""
    scripts = ROOT / "godot_walk/scripts"
    builder = (scripts / "shape_room_builder.gd").read_text(encoding="utf-8")
    assembly = (scripts / "generative_map_assembly.gd").read_text(encoding="utf-8")
    checks = (scripts / "issue188_module_checks.gd").read_text(encoding="utf-8")
    test = (scripts / "test_issue183_shape_rooms.gd").read_text(encoding="utf-8")
    assert re.search(r"const MODULE_JOINT_RECESS := 0\.0[1-9]", builder)
    assert "module_joints" in builder and "_module_joints(" in assembly and "recess_joints" in assembly
    assert "shares face plane" in checks
    assert "module_joint_recess_removed" in test and "recess_joints" in test
