"""gmap-0.6.0 diagonal-link generation, static checks and fail-closed controls (#193)."""

from __future__ import annotations

import copy
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gmap_build as build
import gmap_diagonal_candidates as candidates
import gmap_library as library
from deterministic_json import ROOT, canonical_bytes
from gmap_library import Library
from gmap_validate import validate_document

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
V6 = "gmap-0.6.0"


@pytest.fixture(scope="module")
def lib() -> Library:
    return library.load_library(INDEX)


@pytest.fixture(scope="module")
def linked_map(lib: Library) -> dict:
    document = build.build_map(36, lib, cells=12, stage_max=2, version=V6)
    assert document["diagonal_links"]["used"] == 1
    return document


def test_gmap_06_is_a_distinct_opt_in_generator_and_seeded_draw_is_stable(lib: Library):
    assert build.GENERATOR_VERSION_V6 in build.VERSIONS
    assert build.GENERATOR_VERSION_V2 == "gmap-0.2.0"
    one = build.build_map(36, lib, cells=12, stage_max=2, version=V6)
    two = build.build_map(36, lib, cells=12, stage_max=2, version=V6)
    assert canonical_bytes(one) == canonical_bytes(two)
    assert one["diagonal_links"]["budget"] == 1
    assert one["diagonal_links"]["used"] == 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_required_first_seeds_remain_valid_even_when_no_pair_is_eligible(
    lib: Library, seed: int
):
    document = build.build_map(seed, lib, cells=12, stage_max=2, version=V6)
    assert validate_document(document) == []
    assert document["diagonal_links"]["used"] <= document["diagonal_links"]["budget"]


def test_linked_map_has_chamfered_sources_passage_and_zero_validation_errors(
    linked_map: dict,
):
    assert validate_document(linked_map) == []
    passage = next(c for c in linked_map["cells"] if c.get("diagonal_passage"))
    assert passage["shape_class_target"] == "diagonal_passage"
    assert len(passage["required_ports"]) == 2
    assert all(
        abs(abs(n) - 2**-0.5) < 1e-12
        for port in passage["required_ports"]
        for n in port["normal"]
    )
    sources = [c for c in linked_map["cells"] if c.get("diagonal_link_chamfer")]
    assert len(sources) == 2
    assert all(c["shape_class_target"] == "chamfered_box" for c in sources)


def test_seeded_diagonal_map_mutations_fail_the_specific_static_checks(
    linked_map: dict,
):
    changed = copy.deepcopy(linked_map)
    changed["diagonal_links"]["budget"] = 0
    assert "link_budget_draw_mismatch" in {
        e["code"] for e in validate_document(changed)
    }

    changed = copy.deepcopy(linked_map)
    changed["edges"] = [e for e in changed["edges"] if e.get("kind") != "diagonal"]
    codes = {e["code"] for e in validate_document(changed)}
    assert "link_edges_missing" in codes or "port_unused" in codes

    changed = copy.deepcopy(linked_map)
    passage = next(c for c in changed["cells"] if c.get("diagonal_passage"))
    passage["diagonal_passage"]["clear_width_m"] = 1.0
    assert "schema" in {e["code"] for e in validate_document(changed)}

    changed = copy.deepcopy(linked_map)
    source = next(c for c in changed["cells"] if c.get("diagonal_link_chamfer"))
    source["diagonal_link_chamfer"]["corner_xz"][0] += 1
    assert {
        "from_chamfer_port_mismatch",
        "to_chamfer_port_mismatch",
        "source_corners_not_one_metre_apart",
    } & {e["code"] for e in validate_document(changed)}


def test_module_catalog_and_palette_provenance_stays_in_the_linked_seed(lib: Library):
    document = build.build_map(36, lib, cells=12, stage_max=2, version=V6)
    assert any(c.get("module") for c in document["cells"])
    assert any(
        c.get("palette", {}).get("palette_id") != "default"
        for c in document["cells"]
        if c.get("palette")
    )
    passage = next(c for c in document["cells"] if c.get("diagonal_passage"))
    assert passage["palette"]["palette_id"] == next(
        c["palette"]["palette_id"]
        for c in document["cells"]
        if c["cell_id"] == passage["diagonal_passage"]["palette_source_cell_id"]
    )


def test_two_link_budget_requires_two_independent_pairs_and_selects_them():
    def pair(left: str, right: str) -> dict:
        return {"a": {"cell_id": left}, "b": {"cell_id": right}}

    shared = pair("a", "b")
    overlapping = pair("a", "c")
    independent = pair("d", "e")
    assert candidates._pair_capacity([shared, overlapping]) == 1
    selected = candidates.select_pairs(
        [shared, overlapping, independent], 2, random.Random(7)
    )
    assert len(selected) == 2
    used = [{item["a"]["cell_id"], item["b"]["cell_id"]} for item in selected]
    assert used[0].isdisjoint(used[1])
