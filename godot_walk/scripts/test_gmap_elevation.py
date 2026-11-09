"""Tests for gmap-0.10.0 elevation (#201): levels, ramps, drops and connectivity."""

from __future__ import annotations

import copy
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gmap_build as build
from deterministic_json import ROOT, canonical_bytes
from gmap_elevation import (
    CLEARANCE_M,
    DROP_PROBABILITY,
    LEVELS,
    RAMP_MAX_ANGLE_DEG,
    RAMP_MIN_RUN_M,
    directed_edges,
    distribution,
    strongly_connected,
    walkable_ids,
)
from gmap_library import load_library
from gmap_validate import validate_document
from shape_room import edge_links
from shape_room_spec import build_spec

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
MAP_DIR = ROOT / "godot_walk/room_catalog/generative_maps"
LEGACY_VERSIONS = (
    build.GENERATOR_VERSION,
    build.GENERATOR_VERSION_V2,
    build.GENERATOR_VERSION_V3,
    build.GENERATOR_VERSION_V4,
    build.GENERATOR_VERSION_V5,
    build.GENERATOR_VERSION_V6,
    build.GENERATOR_VERSION_V61,
    build.GENERATOR_VERSION_V7,
    build.GENERATOR_VERSION_V8,
    build.GENERATOR_VERSION_V9,
)


@pytest.fixture(scope="module")
def library():
    return load_library(INDEX)


def codes(document: dict) -> set[str]:
    return {error["code"] for error in validate_document(document)}


def cells(document: dict) -> dict[str, dict]:
    return {cell["cell_id"]: cell for cell in document["cells"]}


def changed_edges(document: dict) -> list[dict]:
    return [
        edge
        for edge in document["edges"]
        if edge.get("connector") == "direct"
        and edge.get("vertical") in ("ramp", "drop")
    ]


def test_old_versions_are_byte_identical(library):
    """0.1.0-0.9.0 keep their committed bytes after the 0.10.0 layer exists."""
    for seed in (1, 2, 3):
        for version in LEGACY_VERSIONS:
            document = build.build_map(seed, library, cells=12, version=version)
            path = MAP_DIR / f"gmap-{seed}-{version}.json"
            assert canonical_bytes(document) == path.read_bytes(), (seed, version)


def test_strong_connectivity_is_reusable_and_detects_a_missing_return():
    assert strongly_connected(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    assert not strongly_connected(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert strongly_connected(
        ["a", "b", "c"],
        [("a", "b"), ("b", "a"), ("b", "c"), ("c", "b"), ("c", "a"), ("a", "c")],
    )
    assert not strongly_connected(["a", "b"], [("a", "b"), ("a", "b")])


def test_v100_maps_are_deterministic_and_valid(library):
    for seed in (1, 2, 3, 279):
        first = build.build_map(seed, library, cells=12, version=build.GENERATOR_VERSION_V10)
        second = build.build_map(seed, library, cells=12, version=build.GENERATOR_VERSION_V10)
        assert canonical_bytes(first) == canonical_bytes(second)
        assert validate_document(first) == [], seed
        assert first["elevation"]["stream"] == "elevation:gmap-0.10.0"
        assert first["elevation"]["drop_probability"] == DROP_PROBABILITY
        assert first["elevation"]["levels_m"] == list(LEVELS)
        assert all(cell["floor_y"] in LEVELS for cell in first["cells"])
        assert first["cells"][0]["floor_y"] == 0.0
        for edge in first["edges"]:
            assert edge["vertical"] in {"level", "ramp", "drop"}


def test_v100_directed_graph_is_strongly_connected(library):
    for seed in (1, 2, 3, 279):
        document = build.build_map(seed, library, cells=12, version=build.GENERATOR_VERSION_V10)
        assert strongly_connected(walkable_ids(document), directed_edges(document)), seed


def test_drop_without_a_return_route_is_rejected(library):
    document = build.build_map(279, library, cells=12, version=build.GENERATOR_VERSION_V10)
    altered = copy.deepcopy(document)
    picked = None
    for edge in altered["edges"]:
        if edge.get("vertical") != "ramp":
            continue
        ramp = edge["ramp"]
        edge["vertical"] = "drop"
        del edge["ramp"]
        edge["drop"] = {
            "upper_cell_id": ramp["upper_cell_id"],
            "lower_cell_id": ramp["lower_cell_id"],
            "drop_m": abs(
                cells(altered)[ramp["upper_cell_id"]]["floor_y"]
                - cells(altered)[ramp["lower_cell_id"]]["floor_y"]
            ),
        }
        if not strongly_connected(walkable_ids(altered), directed_edges(altered)):
            picked = edge
            break
    assert picked is not None, "seed 279 has no one-way ramp whose removal breaks the graph"
    assert "elevation_graph_not_strongly_connected" in codes(altered)


def test_ramps_fit_their_lower_cell_and_keep_ceiling_clearance(library):
    document = build.build_map(279, library, cells=12, version=build.GENERATOR_VERSION_V10)
    by_id = cells(document)
    ramps = 0
    for edge in changed_edges(document):
        if edge["vertical"] != "ramp":
            continue
        ramps += 1
        ramp = edge["ramp"]
        lower = by_id[ramp["lower_cell_id"]]
        upper = by_id[ramp["upper_cell_id"]]
        assert ramp["rise_m"] == pytest.approx(1.5)
        assert ramp["run_m"] >= RAMP_MIN_RUN_M
        assert ramp["angle_deg"] <= RAMP_MAX_ANGLE_DEG
        assert upper["floor_y"] - lower["floor_y"] == pytest.approx(1.5)
        points = lower["envelope_xz"]
        xs = [point[0] for point in points]
        zs = [point[1] for point in points]
        lower_port = next(
            port
            for port in lower["required_ports"]
            if port["port_id"] in (edge["from"], edge["to"])
        )
        normal = lower_port["normal"]
        depth = (max(xs) - min(xs)) if abs(normal[0]) > 0.5 else (max(zs) - min(zs))
        assert depth >= ramp["run_m"]
        assert lower["ceiling_range_m"][1] >= ramp["rise_m"] + CLEARANCE_M
        assert lower["ceiling_range_m"][0] >= CLEARANCE_M
    assert ramps >= 2


def test_drops_are_one_way_and_clear_the_lower_ceiling(library):
    document = build.build_map(279, library, cells=12, version=build.GENERATOR_VERSION_V10)
    by_id = cells(document)
    drops = 0
    for edge in changed_edges(document):
        if edge["vertical"] != "drop":
            continue
        drops += 1
        drop = edge["drop"]
        lower = by_id[drop["lower_cell_id"]]
        upper = by_id[drop["upper_cell_id"]]
        assert 1.5 <= drop["drop_m"] <= 4.5
        assert upper["floor_y"] - lower["floor_y"] == pytest.approx(drop["drop_m"])
        assert lower["ceiling_range_m"][1] >= drop["drop_m"] + CLEARANCE_M
        assert drop["upper_cell_id"] != drop["lower_cell_id"]
    assert drops >= 2


def test_shape_specs_carry_floors_sills_and_ramps(library):
    document = build.build_map(279, library, cells=12, version=build.GENERATOR_VERSION_V10)
    by_id = cells(document)
    links = edge_links(document)
    for cell in document["cells"]:
        if cell["role"] == "void" or cell.get("module"):
            continue
        spec = build_spec(document, "a" * 64, cell, "shape_room_pending", links)
        assert spec["generator_version"] == "shape-room-0.10.0"
        assert spec["floor_y"] == cell["floor_y"]
        for doorway in spec["doorways"]:
            own = by_id[cell["cell_id"]]
            other = by_id[doorway["to_cell_id"]]
            edge = next(
                item
                for item in document["edges"]
                if doorway["port_id"] in (item["from"], item["to"])
            )
            if edge["vertical"] in ("ramp", "drop") and own["floor_y"] < other["floor_y"]:
                assert doorway["sill_height_m"] == pytest.approx(
                    other["floor_y"] - own["floor_y"]
                )
            else:
                assert doorway["sill_height_m"] == 0.0
        ramps = spec.get("ramps", [])
        for ramp in ramps:
            assert ramp["rise_m"] == pytest.approx(1.5)
            assert ramp["run_m"] >= RAMP_MIN_RUN_M
            assert ramp["angle_deg"] <= RAMP_MAX_ANGLE_DEG


def test_seeds_1_to_300_validate_and_report_distribution(library):
    levels: Counter[str] = Counter()
    verticals: Counter[str] = Counter()
    examples = []
    for seed in range(1, 301):
        document = build.build_map(seed, library, cells=12, version=build.GENERATOR_VERSION_V10)
        errors = validate_document(document)
        assert errors == [], (seed, errors)
        report = distribution(document)
        levels.update(report["levels"])
        verticals.update(report["edges"])
        if report["edges"]["drop"] >= 2 and report["edges"]["ramp"] >= 2:
            examples.append(seed)
    assert verticals["ramp"] > 0 and verticals["drop"] > 0
    assert len(levels) >= 3
    assert examples, "no seed in 1..300 has two drops and two ramps"
    assert 279 in examples
