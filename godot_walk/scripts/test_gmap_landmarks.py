"""Map-first regular polygon landmarks for gmap-0.7.0 (#194)."""

from __future__ import annotations

import copy
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gmap_diagonal_growth as diagonal_growth
from deterministic_json import ROOT
from gmap_build import GENERATOR_VERSION_V7, build_map
from gmap_geometry import polygon_rect
from gmap_grow import Cell, Draft, _landmark_port_is_midpoint, connect, placements
from gmap_landmark import (
    LANDMARKS,
    facet_length,
    normal_for_facet,
    port_facet_indices,
    port_normals,
    regular_polygon,
)
from gmap_landmark_rules import landmark_errors
from gmap_library import load_library
from gmap_validate import validate_document
from poetics_geometry import classify_primitive

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
EXPECTED_FACETS = {
    "octagon_regular": 3.3137,
    "dodecagon": 3.2154,
    "rotunda16": 3.1826,
    "hexagon": 4.6188,
}


@pytest.fixture(scope="module")
def library():
    return load_library(INDEX)


def _plan(landmark_class: str, rotation_deg: float = 0.0) -> dict:
    return {"class": landmark_class, "rotation_deg": rotation_deg}


def test_facet_lengths_and_port_facets_match_envelope_contract():
    for landmark_class, expected in EXPECTED_FACETS.items():
        plan = _plan(landmark_class)
        assert facet_length(plan) == pytest.approx(expected, abs=0.001)
        ring = regular_polygon((0.0, 0.0), plan)
        assert classify_primitive([(x, z) for x, z in ring]) == (landmark_class, 3)
        indices = port_facet_indices(plan)
        assert len(indices) == (2 if landmark_class == "hexagon" else 4)
        assert all(facet_length(plan) >= 3.0 for _ in indices)
        assert all(
            abs(normal_for_facet(index, plan)[0]) < 1e-6
            or abs(normal_for_facet(index, plan)[1]) < 1e-6
            for index in indices
        )
        for index in indices:
            start = ring[index]
            finish = ring[(index + 1) % len(ring)]
            edge = (finish[0] - start[0], finish[1] - start[1])
            length = math.hypot(*edge)
            actual_normal = (edge[1] / length, -edge[0] / length)
            assert actual_normal == pytest.approx(
                normal_for_facet(index, plan), abs=1e-6
            )
            midpoint = ((start[0] + finish[0]) / 2, (start[1] + finish[1]) / 2)
            assert midpoint[0] * actual_normal[0] + midpoint[1] * actual_normal[
                1
            ] == pytest.approx(LANDMARKS[landmark_class]["inradius"], abs=1e-5)
    rotated = _plan("hexagon", 90.0)
    assert [
        normal_for_facet(index, rotated) for index in port_facet_indices(rotated)
    ] != [
        normal_for_facet(index, _plan("hexagon"))
        for index in port_facet_indices(_plan("hexagon"))
    ]


def _placed_document(library):
    for seed in range(1, 20):
        document = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V7)
        if document.get("landmark", {}).get("status") == "placed":
            return document
    raise AssertionError("expected a placed landmark in seeds 1..19")


def test_v70_landmark_has_midpoint_ports_and_passes_all_map_rules(library):
    document = _placed_document(library)
    assert validate_document(document) == []
    landmark = next(cell for cell in document["cells"] if cell.get("landmark"))
    assert landmark["shape_stage_target"] == 3
    assert landmark["role"] != "void" and "module" not in landmark
    assert len([cell for cell in document["cells"] if cell.get("landmark")]) == 1


def test_landmark_uses_first_legal_target_step_before_reserved_site(monkeypatch):
    plan = {"class": "octagon_regular", "rotation_deg": 0.0, "target_step": 1}
    draft = Draft(centred=True, margin=1.0, landmark_plan=plan)
    draft.cells["c00"] = Cell("c00", (0, 0, 6, 6))
    site_placement_calls = []
    monkeypatch.setattr(
        diagonal_growth,
        "_all_site_options",
        lambda *_args: [((0, 0, 1, 1), {})],
    )
    monkeypatch.setattr(
        diagonal_growth,
        "_place_site",
        lambda *_args: site_placement_calls.append(True),
    )
    diagonal_growth.grow_step_v61(
        random.Random(4),
        random.Random(1),
        draft,
        site_budget=1,
        landmark_plan=plan,
        landmark_rng=random.Random(3),
        growth_step=1,
    )
    assert draft.landmark_cell_id is not None
    assert site_placement_calls == []


@pytest.mark.parametrize(
    "seed,landmark_class",
    [
        (2, "dodecagon"),
        (4, "rotunda16"),
        (40, "octagon_regular"),
        (52, "hexagon"),
    ],
)
def test_growth_filter_and_validator_agree_on_each_landmark_side(
    library, seed, landmark_class
):
    document = build_map(seed, library, cells=12, version=GENERATOR_VERSION_V7)
    landmark = next(cell for cell in document["cells"] if cell.get("landmark"))
    assert landmark["landmark"]["class"] == landmark_class
    for side in port_normals(landmark["landmark"]):
        _assert_growth_port_matches_validator(document, landmark, side)


def _assert_growth_port_matches_validator(document, landmark, side):
    rect = polygon_rect(landmark["envelope_xz"])
    assert rect is not None
    parent = Cell(landmark["cell_id"], rect, landmark=landmark["landmark"])
    draft = Draft(centred=True, margin=1.5)
    draft.cells[parent.cell_id] = parent
    options = placements(draft, parent, side, (6, 6))
    assert options
    child = Cell(f"child_{side[0]}_{side[1]}", options[0])
    connect(draft, parent, child, "direct")
    port = parent.ports[0]
    assert port.normal == side
    assert _landmark_port_is_midpoint(parent, port.pos)
    candidate = _map_with_only_port(document, parent, port, child)
    assert landmark_errors(candidate) == []
    _assert_off_midpoint_is_rejected(candidate, parent, port)


def _map_with_only_port(document, parent, port, child):
    candidate = copy.deepcopy(document)
    cell = next(
        item for item in candidate["cells"] if item["cell_id"] == parent.cell_id
    )
    cell["required_ports"] = [
        {
            "port_id": port.port_id,
            "pos_xz": list(port.pos),
            "normal": list(port.normal),
            "placement": port.placement,
            "compatibility_type": port.compatibility_type,
        }
    ]
    candidate["edges"] = [
        edge
        for edge in candidate["edges"]
        if parent.cell_id not in (edge["from"].split(":")[0], edge["to"].split(":")[0])
    ]
    candidate["edges"].append(
        {"from": port.port_id, "to": f"{child.cell_id}:p0", "connector": "direct"}
    )
    return candidate


def _assert_off_midpoint_is_rejected(candidate, parent, port):
    tangent_axis = 1 if port.normal[0] else 0
    moved = list(port.pos)
    moved[tangent_axis] += 0.5
    assert not _landmark_port_is_midpoint(parent, tuple(moved))
    altered = copy.deepcopy(candidate)
    cell = next(item for item in altered["cells"] if item["cell_id"] == parent.cell_id)
    cell["required_ports"][0]["pos_xz"] = moved
    assert any(
        error["code"] == "landmark_port_not_facet_midpoint"
        for error in landmark_errors(altered)
    )


@pytest.mark.parametrize(
    "violation",
    [
        "module",
        "degenerate",
        "reserved_diagonal",
        "diagonal_endpoint",
        "off_midpoint",
        "multiple",
    ],
)
def test_landmark_exclusions_are_rejected(library, violation):
    document = copy.deepcopy(_placed_document(library))
    landmark = next(cell for cell in document["cells"] if cell.get("landmark"))
    if violation == "module":
        landmark["module"] = {"module_id": "forbidden"}
    elif violation == "degenerate":
        landmark["mode"] = "degenerate"
    elif violation == "reserved_diagonal":
        document.setdefault("diagonal_links", {})["reserved_diagonal_zones"] = [
            {"endpoint_ids": [landmark["cell_id"]]}
        ]
    elif violation == "diagonal_endpoint":
        document["edges"].append(
            {"kind": "diagonal", "from": f"{landmark['cell_id']}:p0", "to": "c00:p0"}
        )
    elif violation == "multiple":
        other = next(cell for cell in document["cells"] if cell is not landmark)
        other["landmark"] = copy.deepcopy(landmark["landmark"])
        other["shape_stage_target"] = 3
    else:
        landmark["required_ports"][0]["pos_xz"][1] += 0.5
    assert landmark_errors(document)


def _sweep(library, cells: int) -> dict:
    drawn = placed = unplaced = 0
    reasons: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    door_counts: dict[str, Counter[int]] = {}
    invalid = []
    for seed in range(1, 301):
        document = build_map(seed, library, cells=cells, version=GENERATOR_VERSION_V7)
        errors = validate_document(document)
        if errors:
            invalid.append((seed, errors[0]))
        record = document.get("landmark")
        if record is None:
            continue
        drawn += 1
        if record["status"] == "placed":
            placed += 1
            classes[record["class"]] += 1
            landmark = next(cell for cell in document["cells"] if cell.get("landmark"))
            door_counts.setdefault(record["class"], Counter())[
                len(landmark["required_ports"])
            ] += 1
        else:
            unplaced += 1
            reasons[record["reason"]] += 1
    return {
        "drawn": drawn,
        "placed": placed,
        "unplaced": unplaced,
        "reasons": reasons,
        "classes": classes,
        "door_counts": door_counts,
        "invalid": invalid,
    }


@pytest.mark.skipif(
    os.environ.get("GMAP_LANDMARK_SWEEP") != "1",
    reason="600-map sweep; run with GMAP_LANDMARK_SWEEP=1",
)
def test_v70_seed_sweep_at_12_and_20_cells(library):
    twelve, twenty = _sweep(library, 12), _sweep(library, 20)
    print(f"gmap-0.7.0 cells=12 {_sweep_summary(twelve)}")
    print(f"gmap-0.7.0 cells=20 {_sweep_summary(twenty)}")
    assert not twelve["invalid"] and not twenty["invalid"]
    assert twelve["placed"] / 300 >= 0.40
    two_or_more = sum(
        count
        for distribution in twelve["door_counts"].values()
        for doors, count in distribution.items()
        if doors >= 2
    )
    assert two_or_more / twelve["placed"] >= 0.50
    for counts in (twelve["classes"], twenty["classes"]):
        assert all(counts[landmark_class] >= 10 for landmark_class in LANDMARKS)


def _sweep_summary(result: dict) -> dict:
    return {
        "drawn": result["drawn"],
        "placed": result["placed"],
        "unplaced": result["unplaced"],
        "unplaced_reasons": dict(result["reasons"]),
        "classes": dict(result["classes"]),
        "class_by_door_count": {
            landmark_class: dict(sorted(counts.items()))
            for landmark_class, counts in sorted(result["door_counts"].items())
        },
        "invalid": result["invalid"],
    }
