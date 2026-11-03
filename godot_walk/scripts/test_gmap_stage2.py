"""Tests for shape stage 2a (issue 190): 45-degree classes, chamfer rules, gmap-0.4.0 maps and rooms."""

from __future__ import annotations

import copy
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_library as library
import shape_room as sr
from deterministic_json import ROOT
from gmap_geometry import polygon_rect
from gmap_stage2 import stage2_errors
from gmap_validate import validate_document
from library_index import load_json
from poetics_geometry import analyze_shape, classify_primitive, segment_distance
from shape_room_module_clear import module_sides, module_top_planes, outline_conflicts
from shape_room_chamfer import apply_cuts, clearance_ok, convex_vertices, cut_issues, lamp_points_polygon
from shape_room_stage2 import STAGE2_CLASSES, box_ring, eligible_classes, plan_cuts, wedge_lengths

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAP_DIR = ROOT / "godot_walk/room_catalog/generative_maps"
V4 = "gmap-0.4.0"
DEFAULT, WIDE = "level_doorway_2m_v1", "authored_direct_doorway_2.4x2.2_v1"
OCTAGON = [(2, 0), (6, 0), (8, 2), (8, 6), (6, 8), (2, 8), (0, 6), (0, 2)]


def port(pid: str, pos: tuple[float, float], normal: tuple[int, int], kind: str = DEFAULT, placement: str = "standard") -> dict:
    return {"port_id": pid, "pos_xz": list(pos), "normal": list(normal), "compatibility_type": kind, "placement": placement}


SOUTH = port("c00:p0", (4, 0), (0, -1))


@pytest.fixture(scope="module")
def lib() -> library.Library:
    return library.load_library(INDEX)


@pytest.fixture(scope="module")
def maps(lib) -> dict[int, dict]:
    return {seed: build.build_map(seed, lib, version=V4) for seed in range(1, 61)}


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


# --- classification ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ring", "expected"),
    [
        (OCTAGON, "octagon"),
        ([(3, 0), (8, 0), (8, 8), (0, 8), (0, 3)], "chamfered_box"),
        ([(0, 0), (8, 0), (8, 8), (2, 8), (0, 6)], "chamfered_box"),
        ([(5, 0), (8, 0), (8, 8), (0, 8), (0, 5)], "wedge"),  # one 5 m chamfer
        ([(0, 6), (0, 14), (-4, 14), (-12, 6)], "wedge"),  # a chamfer that eats the whole short side
        ([(-2, -8), (-2, -2), (-8, -8)], "wedge"),  # right triangle
        ([(0, 0), (8, 0), (8, 4), (4, 4), (4, 8), (1, 8), (0, 7)], "chamfered_polyomino"),
        ([(0, 0), (8, 0), (8, 8), (0, 8), (0, 0)][:4], "box"),
    ],
)
def test_stage_two_classes(ring, expected):
    name, stage = classify_primitive([(float(x), float(z)) for x, z in ring])
    assert name == expected
    assert stage == (0 if expected == "box" else 2)


def test_classification_ignores_winding_and_start_vertex():
    ring = [(float(x), float(z)) for x, z in OCTAGON]
    assert classify_primitive(ring[::-1])[0] == "octagon"
    assert classify_primitive(ring[3:] + ring[:3])[0] == "octagon"


def test_stage_zero_and_one_results_are_unchanged():
    assert classify_primitive([(0, 0), (4, 0), (4, 4), (0, 4)]) == ("box", 0)
    assert classify_primitive([(0, 0), (8, 0), (8, 4), (4, 4), (4, 8), (0, 8)]) == ("l_shape", 1)
    assert classify_primitive([(0, 0), (4, 0), (3.5, 2.4), (0, 3)]) == ("polygon", None)
    assert analyze_shape([[float(x), float(z)] for x, z in OCTAGON])["primitive"] == "chamfered_polygon"  # module poetics


# --- chamfer rules ---------------------------------------------------------------------------------


def test_port_keeps_half_the_doorway_plus_half_a_metre_to_the_chamfer_start():
    ring = box_ring((0, 0, 8, 8))
    assert cut_issues(ring, [SOUTH], {0: 2.5}) == []  # 4 - 2.5 = 1.5 m, exactly the margin
    assert cut_issues(ring, [SOUTH], {0: 3.0})
    assert cut_issues(ring, [port("p", (4, 0), (0, -1), WIDE)], {0: 2.5})  # a 2.4 m door needs 1.7 m
    assert cut_issues(ring, [port("p", (4, 0), (0, -1), WIDE)], {0: 2.0}) == []


def test_a_doorway_may_not_open_onto_the_thin_tip_of_a_wedge():
    ring = box_ring((0, 0, 6, 6))
    tip = port("c00:p0", (0, 1.5), (-1, 0))  # 1.5 m from the 45 degree tip the hypotenuse makes at (0, 0)
    assert any("line in from the doorway" in issue for issue in cut_issues(ring, [tip], {1: 6.0}, wedge=True))
    assert cut_issues(ring, [port("c00:p0", (0, 4.5), (-1, 0))], {1: 6.0}, wedge=True) == []  # the wide end of the wedge


def test_a_degenerate_port_blocks_chamfering_the_corner_it_hugs():
    ring = box_ring((0, 0, 8, 8))
    hugging = port("c00:p0", (1, 0), (0, -1), placement="degenerate")
    assert any("degenerate" in issue for issue in cut_issues(ring, [hugging], {0: 1.0}))
    far = port("c00:p0", (4, 0), (0, -1), placement="degenerate")
    assert cut_issues(ring, [far], {2: 1.0}) == []  # the opposite corner is not on that edge


def test_chamfers_stay_on_the_lattice_on_convex_corners_and_leave_a_face():
    ring = box_ring((0, 0, 6, 6))
    assert cut_issues(ring, [], {0: 1.25}) and cut_issues(ring, [], {0: 0.5})
    assert cut_issues(ring, [], {0: 2.5, 1: 2.5})  # only 1 m of straight face left
    assert cut_issues(ring, [], {0: 2.0, 1: 2.0}) == []
    assert cut_issues(ring, [], {0: 6.0}, wedge=True) == []  # a wedge may eat a whole side
    l_ring = [(0.0, 0.0), (8.0, 0.0), (8.0, 4.0), (4.0, 4.0), (4.0, 8.0), (0.0, 8.0)]
    assert convex_vertices(l_ring) == [0, 1, 2, 4, 5]
    assert any("not a convex" in issue for issue in cut_issues(l_ring, [], {3: 1.0}))  # the inner corner stays square


def test_clearance_keeps_a_connected_spine():
    assert clearance_ok(apply_cuts(box_ring((0, 0, 3, 6)), {0: 1.0}))
    assert not clearance_ok([(0.0, 0.0), (1.5, 0.0), (1.5, 1.5), (0.0, 1.5)])


def test_wedge_lengths_are_large_and_reach_the_short_side():
    assert wedge_lengths(5)[0] == 3.5 and wedge_lengths(5)[-1] == 5
    assert wedge_lengths(8) == [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]


# --- eligibility ---------------------------------------------------------------------------------------


def test_wedge_needs_a_leaf_and_an_envelope_of_at_least_5_by_5():
    leaf = [SOUTH]
    two = [SOUTH, port("c00:p1", (8, 4), (1, 0))]
    assert "wedge" in eligible_classes((0, 0, 8, 8), leaf, "ground")
    assert "wedge" in eligible_classes((0, 0, 5, 5), [port("p", (2.5, 0), (0, -1))], "figure")
    assert "wedge" not in eligible_classes((0, 0, 8, 8), two, "ground")
    assert "wedge" not in eligible_classes((0, 0, 4, 8), [port("p", (2, 0), (0, -1))], "ground")


def test_octagon_needs_a_squarish_envelope_with_a_short_side_of_6_m():
    assert "octagon" in eligible_classes((0, 0, 6, 6), [port("p", (3, 0), (0, -1))], "ground")
    assert "octagon" in eligible_classes((0, 0, 8, 10), [port("p", (4, 0), (0, -1))], "ground")  # aspect 1.25
    assert "octagon" not in eligible_classes((0, 0, 8, 12), [port("p", (4, 0), (0, -1))], "ground")
    assert "octagon" not in eligible_classes((0, 0, 5, 5), [port("p", (2.5, 0), (0, -1))], "ground")


def test_only_ground_and_figure_cells_with_room_beside_their_doorways_are_eligible():
    assert eligible_classes((0, 0, 8, 8), [SOUTH], "threshold") == []
    assert eligible_classes((0, 0, 8, 8), [SOUTH], "void") == []
    assert eligible_classes((0, 0, 3, 6), [port("p", (1.5, 0), (0, -1))], "ground") == ["chamfered_box"]  # the far corners
    every_side = [port("n", (1.5, 3), (0, 1)), port("s", (1.5, 0), (0, -1)), port("e", (3, 1.5), (1, 0)), port("w", (0, 1.5), (-1, 0))]
    assert eligible_classes((0, 0, 3, 3), every_side, "ground") == []  # every corner is within a doorway margin


def test_plan_cuts_realises_each_class_deterministically():
    import random

    env = (0, 0, 8, 8)
    ring = box_ring(env)
    for klass in ("chamfered_box", "octagon", "wedge"):
        first = plan_cuts(klass, ring, [SOUTH], env, random.Random(5))
        assert first == plan_cuts(klass, ring, [SOUTH], env, random.Random(5))
        assert classify_primitive(apply_cuts(ring, first))[0] == klass and not cut_issues(ring, [SOUTH], first, klass == "wedge")


# --- gmap-0.4.0 maps -------------------------------------------------------------------------------------


def test_maps_validate_and_record_the_stage_choice(maps):
    for seed, document in maps.items():
        assert validate_document(document) == [], seed
        assert document["generator_version"] == V4 and document["shape_stage_max"] == 2
        assert "shape_stage2_eligibility" in document["rules"]
        for cell in document["cells"]:
            listed = set(cell["allowed_primitives"]) & set(STAGE2_CLASSES)
            if cell["role"] in ("void", "threshold") or cell.get("module"):
                assert not listed
            if cell["role"] == "void" or cell.get("module"):
                assert "shape_stage_target" not in cell
            elif cell["shape_stage_target"] == 2:
                assert cell["shape_class_target"] in listed and cell["role"] in ("ground", "figure")
            else:
                assert cell["shape_stage_target"] == 1 and "shape_class_target" not in cell


def test_two_in_five_eligible_cells_draw_stage_two_with_the_class_weights(lib):
    drawn, eligible, classes = 0, 0, Counter()
    for seed in range(1, 301):
        for cell in build.build_map(seed, lib, version=V4)["cells"]:
            if cell["role"] in ("ground", "figure") and not cell.get("module") and set(cell["allowed_primitives"]) & set(STAGE2_CLASSES):
                eligible += 1
                if cell["shape_stage_target"] == 2:
                    drawn += 1
                    classes[cell["shape_class_target"]] += 1
    assert 0.35 <= drawn / eligible <= 0.45
    assert classes["chamfered_box"] > classes["octagon"] > classes["wedge"] > 0 and classes["chamfered_polyomino"] > classes["octagon"]


def test_older_generators_gain_no_stage_two_fields(lib):
    for version in ("gmap-0.1.0", "gmap-0.2.0", "gmap-0.3.0"):
        document = build.build_map(2, lib, version=version)
        assert document["shape_stage_max"] == 1 and "shape_stage2_eligibility" not in document["rules"]
        assert all("shape_stage_target" not in c and not set(c["allowed_primitives"]) & set(STAGE2_CLASSES) for c in document["cells"])


def test_stage_max_zero_and_one_in_gmap_040_allow_no_chamfer(lib):
    for stage_max in (0, 1):
        document = build.build_map(3, lib, stage_max=stage_max, version=V4)
        assert validate_document(document) == []
        assert not any(set(c["allowed_primitives"]) & set(STAGE2_CLASSES) for c in document["cells"])
    with pytest.raises(build.GenerationError):
        build.build_map(3, lib, stage_max=2, version="gmap-0.3.0")


def test_validator_controls_for_the_stage_two_rules(maps):
    document = copy.deepcopy(maps[2])
    cell = next(c for c in document["cells"] if c.get("shape_stage_target") == 2)
    other = copy.deepcopy(document)
    next(c for c in other["cells"] if c["cell_id"] == cell["cell_id"])["shape_class_target"] = "octagon" if cell["shape_class_target"] != "octagon" else "wedge"
    assert {"shape_class_target_not_allowed", "stage2_classes_not_eligible"} & codes(other)
    threshold_or_void = next(c for c in document["cells"] if c["role"] in ("void", "threshold"))
    threshold_or_void["allowed_primitives"].append("octagon")
    assert "stage2_classes_not_eligible" in codes(document)
    missing = copy.deepcopy(maps[2])
    del next(c for c in missing["cells"] if "shape_stage_target" in c)["shape_stage_target"]
    assert "shape_stage_target_missing" in {e["code"] for e in stage2_errors(missing)}


# --- module overhang placement rule ---------------------------------------------------------------------


def gap(a: list[list[float]], b: list[list[float]]) -> float:
    ra, rb = polygon_rect(a), polygon_rect(b)
    return max(rb[0] - ra[2], ra[0] - rb[2], rb[1] - ra[3], ra[1] - rb[3])


def test_module_cells_keep_the_overhang_margin_from_every_non_parent_room(maps):
    checked = 0
    for document in maps.values():
        for cell in (c for c in document["cells"] if c.get("module")):
            parent = next(
                end.split(":")[0] for e in document["edges"] for end in (e["from"], e["to"])
                if cell["required_ports"][0]["port_id"] in (e["from"], e["to"]) and not end.startswith(cell["cell_id"] + ":")
            )
            for other in document["cells"]:
                if other["cell_id"] not in (cell["cell_id"], parent) and other["role"] != "void":
                    assert gap(cell["envelope_xz"], other["envelope_xz"]) >= 0.5, (document["seed"], cell["cell_id"], other["cell_id"])
                    checked += 1
    assert checked > 100


def test_overhang_rule_rejects_a_room_near_a_module_cell_but_only_from_gmap_040(maps, lib):
    older = build.build_map(2, lib, version="gmap-0.3.0")
    cell = next(c for c in older["cells"] if c.get("module"))
    rect = polygon_rect(cell["envelope_xz"])
    victim = next(c for c in older["cells"] if c["role"] != "void" and not c.get("module") and c["cell_id"] != cell["cell_id"])
    victim["envelope_xz"] = [[rect[2], rect[3]], [rect[2] + 3, rect[3]], [rect[2] + 3, rect[3] + 3], [rect[2], rect[3] + 3]]
    assert "module_touches_neighbour" not in codes(older)  # corner contact shares no edge: fine before gmap-0.4.0
    document = copy.deepcopy(maps[2])
    cell = next(c for c in document["cells"] if c.get("module"))
    rect = polygon_rect(cell["envelope_xz"])
    victim = next(
        c for c in document["cells"]
        if c["role"] != "void" and c["cell_id"] != cell["cell_id"] and c["cell_id"] not in {e["from"].split(":")[0] for e in document["edges"] if e["to"].startswith(cell["cell_id"] + ":")} | {e["to"].split(":")[0] for e in document["edges"] if e["from"].startswith(cell["cell_id"] + ":")}
    )
    # a corner-touching neighbour: 0.0 m gap along both axes shares no edge, so only the margin sees it
    victim["envelope_xz"] = [[rect[2], rect[3]], [rect[2] + 3, rect[3]], [rect[2] + 3, rect[3] + 3], [rect[2], rect[3] + 3]]
    assert "module_touches_neighbour" in codes(document)


# --- shape rooms ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rooms300(tmp_path_factory):
    base = tmp_path_factory.mktemp("stage2")
    found = {}
    for seed in range(1, 301):
        gm.generate(seed, INDEX, out_dir=base, version=V4, stage_max=None)
        path = base / f"gmap-{seed}-{V4}.json"
        assert gm.validate_path(path) == [], seed
        document = load_json(path)
        found[seed] = (document, {n[:-5]: json.loads(d) for n, d in sr.derive(path, "all_walkable").items() if n != "index.json"})
    return found


def on_axis_edge(outline: list[list[float]], doorway: dict) -> bool:
    x, z = doorway["pos_xz"]
    for a, b in zip(outline, outline[1:] + outline[:1]):
        if (a[0] == b[0] or a[1] == b[1]) and segment_distance((x, z), tuple(a), tuple(b)) < 1e-6:
            half = doorway["width_m"] / 2
            length = math.dist(a, b)
            along = abs((x - a[0]) * (b[0] - a[0]) + (z - a[1]) * (b[1] - a[1])) / length
            return half <= along <= length - half
    return False


def test_seeds_1_to_300_make_valid_maps_and_rooms_with_every_class(rooms300):
    seen = Counter()
    for seed, (document, specs) in rooms300.items():
        for cell_id, spec in specs.items():
            cell = next(c for c in document["cells"] if c["cell_id"] == cell_id)
            assert spec["generator_version"] == "shape-room-0.4.0" and spec["primitive_class"] in cell["allowed_primitives"]
            seen[spec["primitive_class"]] += 1
            if spec["shape_stage"] == 2:
                assert spec["primitive_class"] in STAGE2_CLASSES and spec["chamfers"]
                assert cell.get("shape_stage_target") == 2
            else:
                assert "chamfers" not in spec
    assert all(seen[k] > 0 for k in STAGE2_CLASSES)
    targets = sum(1 for d, _ in rooms300.values() for c in d["cells"] if c.get("shape_stage_target") == 2)
    realised = sum(1 for _, s in rooms300.values() for sp in s.values() if sp["shape_stage"] == 2)
    assert realised >= 0.9 * targets  # a polyomino whose arms or doorways leave no valid cut falls back to stage 1


def simple(ring: list[tuple[float, float]]) -> bool:
    """No two non-adjacent edges of the closed ring cross or touch."""

    def ccw(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    edges = list(zip(ring, ring[1:] + ring[:1]))
    for i, (a, b) in enumerate(edges):
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue
            c, d = edges[j]
            collinear = ccw(a, b, c) == 0 and ccw(a, b, d) == 0
            if collinear:
                overlap = all(max(min(a[k], b[k]), min(c[k], d[k])) <= min(max(a[k], b[k]), max(c[k], d[k])) for k in (0, 1))
                if overlap:
                    return False
            elif ccw(a, b, c) * ccw(a, b, d) <= 0 and ccw(c, d, a) * ccw(c, d, b) <= 0:
                return False
    return True


def test_stage_two_rooms_keep_lattice_vertices_axis_doorways_and_lamp_insets(rooms300):
    checked = 0
    for seed, (_, specs) in rooms300.items():
        for spec in (s for s in specs.values() if s["shape_stage"] == 2):
            outline = spec["outline_xz"]
            assert all(abs(v * 2 - round(v * 2)) < 1e-9 for p in outline for v in p), (seed, spec["cell_id"])
            assert classify_primitive([tuple(p) for p in outline])[0] == spec["primitive_class"]
            assert all(on_axis_edge(outline, d) for d in spec["doorways"]), (seed, spec["cell_id"])
            ring = [tuple(p) for p in outline]
            for lamp in spec["lamps_xz"]:
                nearest = min(segment_distance(tuple(lamp), a, b) for a, b in zip(ring, ring[1:] + ring[:1]))
                assert nearest >= 1.0 - 1e-6 or len(spec["lamps_xz"]) == 1, (seed, spec["cell_id"], lamp)
            assert abs(spec["area_m2"] - abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1])) / 2)) < 1e-6
            assert all(r[0] < r[2] and r[1] < r[3] for r in spec["rects"])
            env = polygon_rect(spec["envelope_xz"])
            assert all(env[0] <= x <= env[2] and env[1] <= z <= env[3] for x, z in outline)  # inside the envelope
            assert simple(ring), (seed, spec["cell_id"])
            assert clearance_ok(ring)
            checked += 1
    assert checked > 300


def test_wedge_rooms_are_leaf_rooms_and_octagons_are_squarish(rooms300):
    wedges = octagons = 0
    for _, specs in rooms300.values():
        for spec in specs.values():
            rect = polygon_rect(spec["envelope_xz"])
            width, depth = rect[2] - rect[0], rect[3] - rect[1]
            if spec["primitive_class"] == "wedge":
                wedges += 1
                assert len(spec["doorways"]) == 1 and min(width, depth) >= 5
            if spec["primitive_class"] == "octagon":
                octagons += 1
                assert max(width, depth) / min(width, depth) <= 1.25 and min(width, depth) >= 6
    assert wedges > 5 and octagons > 5


def test_rooms_validate_against_the_extended_schema(rooms300, tmp_path):
    document = rooms300[14][0]
    gm.generate(14, INDEX, out_dir=tmp_path, version=V4, stage_max=None)
    path = tmp_path / f"gmap-14-{V4}.json"
    sr.generate(path, "all_walkable", out_dir=tmp_path / "rooms")
    assert sr.validate(path, "all_walkable", out_dir=tmp_path / "rooms") == []
    assert document["seed"] == 14


def test_lamp_fallback_is_inside_a_small_polygon():
    ring = apply_cuts(box_ring((0, 0, 3, 3)), {0: 1.0})
    points = lamp_points_polygon(ring, 4.0, 1.5, 1.0)
    assert len(points) == 1 and 0 < points[0][0] < 3 and 0 < points[0][1] < 3


# --- committed outputs, CLI and wiring ------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3, 14])
def test_committed_v4_outputs_are_current_and_valid(seed, tmp_path):
    gm.generate(seed, INDEX, svg=True, out_dir=tmp_path, version=V4, stage_max=None)
    stem = f"gmap-{seed}-{V4}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (tmp_path / f"{stem}{suffix}").read_bytes(), suffix
    assert gm.validate_path(MAP_DIR / f"{stem}.json") == []
    assert sr.validate(MAP_DIR / f"{stem}.json", "all_walkable") == []


def test_committed_v4_seeds_show_every_new_class_and_a_library_module():
    classes, modules = set(), 0
    for seed in (1, 2, 3, 14):
        index = load_json(ROOT / f"godot_walk/room_catalog/shape_rooms/gmap-{seed}-{V4}/index.json")
        classes |= {r["primitive_class"] for r in index["rooms"]}
        modules += sum(1 for c in load_json(MAP_DIR / f"gmap-{seed}-{V4}.json")["cells"] if c.get("module"))
    assert {"octagon", "chamfered_polyomino", "wedge", "chamfered_box"} <= classes and modules >= 4


def test_cli_default_stays_v2_and_gmap_040_defaults_to_stage_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gm, "OUT_DIR", tmp_path)
    monkeypatch.setattr(gm, "ROOT", tmp_path)
    assert gm.main(["generate", "--seed", "5", "--index", str(INDEX)]) == 0
    assert (tmp_path / "gmap-5-gmap-0.2.0.json").is_file()
    assert gm.main(["generate", "--seed", "5", "--index", str(INDEX), "--generator-version", V4]) == 0
    assert load_json(tmp_path / f"gmap-5-{V4}.json")["shape_stage_max"] == 2
    capsys.readouterr()


def test_the_builder_has_diagonal_walls_polygon_floors_and_failing_controls():
    scripts = ROOT / "godot_walk/scripts"
    builder = (scripts / "shape_room_builder.gd").read_text(encoding="utf-8")
    diagonal = (scripts / "shape_room_diagonal.gd").read_text(encoding="utf-8")
    test = (scripts / "test_issue183_shape_rooms.gd").read_text(encoding="utf-8")
    assert "yaw_of" in builder and "triangulate_polygon" in diagonal and "ConvexPolygonShape3D" in diagonal
    assert "diagonal_collision_removed" in test and "unmitred_joint" in test and "diagonal_pullback" in test
    assert re.search(r"coplanar_faces", (scripts / "issue190_diagonal_checks.gd").read_text(encoding="utf-8"))


# --- parents of library modules ------------------------------------------------------------------------------


def test_outline_conflict_rule_needs_the_room_beyond_the_module_side_line():
    sides = [((-25, -23, -13, -13), (0, 1))]  # module north of the parent, east side line x = -13
    notch = [(-21.0, -26.5), (-18.5, -29.0), (-9.0, -29.0), (-9.0, -23.0), (-13.0, -23.0), (-13.0, -25.0),
             (-17.0, -25.0), (-17.0, -23.0), (-21.0, -23.0)]
    assert outline_conflicts(notch, sides)  # the notch wall at x = -13 faces the library wall's inner face
    assert not outline_conflicts([(-21.0, -31.0), (-9.0, -31.0), (-9.0, -23.0), (-21.0, -23.0)], sides)  # box: no edge on the line
    assert not outline_conflicts([(-21.0, -31.0), (-13.0, -31.0), (-13.0, -23.0), (-21.0, -23.0)], sides)  # room on the module's side
    assert not outline_conflicts([(-9.0, -31.0), (-9.0, -26.0), (-13.0, -26.0), (-13.0, -31.0)], sides)  # stops 3 m short of the joint


def test_no_parent_outline_has_a_wall_facing_its_library_modules_side_line(rooms300):
    checked = 0
    for document, specs in rooms300.values():
        cells = {c["cell_id"]: c for c in document["cells"]}
        for cell_id, spec in specs.items():
            sides = module_sides(document, cells[cell_id])
            if sides:
                checked += 1
                assert not outline_conflicts([tuple(p) for p in spec["outline_xz"]], sides), (document["seed"], cell_id)
    assert checked > 300


def test_a_module_parent_never_shares_a_wall_top_plane_with_its_library_room(rooms300):
    checked = 0
    for document, specs in rooms300.values():
        cells = {c["cell_id"]: c for c in document["cells"]}
        for cell_id, spec in specs.items():
            planes = module_top_planes(document, cells[cell_id])
            checked += bool(planes)
            assert all(abs(spec["ceiling_height_m"] - plane) >= 0.02 for plane in planes), (document["seed"], cell_id)
    assert checked > 300
