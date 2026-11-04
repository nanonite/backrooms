"""Growth-time diagonal-site behavior and rate gates for gmap-0.6.1 (#196)."""

from __future__ import annotations

import copy
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generative_map as gm
import gmap_build as build
import gmap_diagonal_site_rules as site_rules
import gmap_diagonal_v61 as diagonal_v61
import gmap_library as library
import shape_room as sr
from deterministic_json import ROOT, canonical_bytes
from gmap_library import Library
from gmap_validate import validate_document

INDEX = ROOT / "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
CATALOG = ROOT / "godot_walk/room_catalog"
MAP_DIR = CATALOG / "generative_maps"
V6 = "gmap-0.6.0"
V61 = "gmap-0.6.1"


@pytest.fixture(scope="module")
def lib() -> Library:
    return library.load_library(INDEX)


def test_v61_is_opt_in_deterministic_and_keeps_cli_default(lib: Library):
    assert V61 in build.VERSIONS
    assert build.GENERATOR_VERSION_V2 == "gmap-0.2.0"
    one = build.build_map(2, lib, cells=12, stage_max=2, version=V61)
    two = build.build_map(2, lib, cells=12, stage_max=2, version=V61)
    assert canonical_bytes(one) == canonical_bytes(two)
    assert 0 <= one["layout_variant"] < build.MAX_SITE_LAYOUT_VARIANTS
    assert one["diagonal_links"]["budget"] == one["diagonal_links"]["used"] == 2
    assert validate_document(one) == []
    assert (
        "choices=VERSIONS, default=GENERATOR_VERSION_V2"
        in Path(gm.__file__).read_text()
    )


def test_reserved_sites_are_clear_and_do_not_reuse_endpoints(lib: Library):
    document = build.build_map(2, lib, cells=12, stage_max=2, version=V61)
    records = document["diagonal_links"]["reserved_diagonal_zones"]
    assert len(records) == 2
    assert all(record["status"] == "realized" for record in records)
    assert len({cell for record in records for cell in record["endpoint_ids"]}) == 4
    assert site_rules.reservation_errors(document) == []
    tree_pairs = {
        frozenset((edge["from"].split(":")[0], edge["to"].split(":")[0]))
        for edge in document["edges"]
        if edge.get("kind") != "diagonal"
    }
    assert all(
        frozenset(record["endpoint_ids"]) not in tree_pairs for record in records
    )


def test_kept_palette_ring_fixture_has_a_diagonal_link_near_the_anchor(lib: Library):
    document = build.build_map(8, lib, cells=12, stage_max=2, version=V61)
    assert document["diagonal_links"]["used"] == 1
    assert _links_near_palette_anchor(document)


@pytest.mark.parametrize("occupant_role", ["ground", "void", "module"])
def test_reserved_clearance_rejects_later_growth_void_or_module_occupancy(
    lib: Library, occupant_role: str
):
    document = build.build_map(2, lib, cells=12, stage_max=2, version=V61)
    changed = copy.deepcopy(document)
    zone = changed["diagonal_links"]["reserved_diagonal_zones"][0]
    polygon = zone["clearance_polygon_xz"]
    xs, zs = [point[0] for point in polygon], [point[1] for point in polygon]
    occupant = copy.deepcopy(changed["cells"][0])
    occupant.update(
        cell_id=f"test_{occupant_role}",
        envelope_xz=[
            [min(xs), min(zs)],
            [max(xs), min(zs)],
            [max(xs), max(zs)],
            [min(xs), max(zs)],
        ],
        role=occupant_role,
    )
    if occupant_role == "module":
        occupant["module"] = {"module_id": "test", "version": 1}
    changed["cells"].append(occupant)
    codes = {item["code"] for item in site_rules.reservation_errors(changed)}
    assert "reserved_zone_occupied" in codes


def test_exhausted_site_budget_releases_unmatched_reservation():
    chosen, records = diagonal_v61._reserved_pairs(
        [],
        [
            {
                "site_id": "ds00",
                "endpoint_ids": ["c01", "c02"],
                "corner_xz": [[0, 0], [1, 1]],
            }
        ],
        1,
    )
    assert chosen == []
    assert records[0]["status"] == "released"
    assert records[0]["release_reason"] == "not_eligible_after_final_stages"


def _sweep(
    lib: Library, cells: int
) -> tuple[Counter[tuple[int, int]], int, int, int, int, list[int]]:
    distribution: Counter[tuple[int, int]] = Counter()
    positive = full = two = 0
    palette_adjacent = []
    for seed in range(1, 301):
        document = build.build_map(seed, lib, cells=cells, stage_max=2, version=V61)
        budget, used = (
            document["diagonal_links"]["budget"],
            document["diagonal_links"]["used"],
        )
        distribution[(budget, used)] += 1
        positive += budget >= 1
        full += budget >= 1 and used == budget
        two += used == 2
        if _links_near_palette_anchor(document):
            palette_adjacent.append(seed)
    return distribution, positive, full, two, 300, palette_adjacent


def _links_near_palette_anchor(document: dict) -> bool:
    cells = {cell["cell_id"]: cell for cell in document["cells"]}
    neighbours: dict[str, set[str]] = defaultdict(set)
    link_endpoints: dict[str, set[str]] = defaultdict(set)
    for edge in document["edges"]:
        left, right = edge["from"].split(":")[0], edge["to"].split(":")[0]
        if edge.get("kind") != "diagonal":
            neighbours[left].add(right)
            neighbours[right].add(left)
            continue
        link_endpoints[edge["diagonal_link_id"]].update(
            cell_id for cell_id in (left, right) if not cell_id.startswith("dp")
        )
    for endpoints in link_endpoints.values():
        nearby = set(endpoints)
        for endpoint in endpoints:
            nearby.update(neighbours[endpoint])
        if any(
            cells[cell_id].get("palette", {}).get("anchor_module_id")
            for cell_id in nearby
        ):
            return True
    return False


@pytest.mark.skipif(
    os.environ.get("GMAP_RATE_SWEEP") != "1",
    reason="300-seed sweep (~10 min); run with GMAP_RATE_SWEEP=1",
)
def test_seed_rate_targets_and_used_vs_budget_distribution_at_12_and_20_cells(
    lib: Library,
):
    twelve, positive, full, two, total, palette_twelve = _sweep(lib, 12)
    twenty, _, _, _, _, palette_twenty = _sweep(lib, 20)
    print(
        f"gmap-0.6.1 cells=12 used_budget={dict(sorted(twelve.items()))} "
        f"full={full}/{positive} two={two}/{total}"
    )
    print(f"gmap-0.6.1 cells=20 used_budget={dict(sorted(twenty.items()))}")
    print(
        f"gmap-0.6.1 palette_anchor_adjacent_seeds="
        f"12:{palette_twelve} 20:{palette_twenty}"
    )
    assert full / positive >= 0.60
    assert two / total >= 0.15
    assert sum(twelve.values()) == sum(twenty.values()) == 300


@pytest.mark.parametrize("seed", [1, 2, 3, 36, 64])
def test_committed_v6_outputs_remain_byte_identical(
    lib: Library, seed: int, tmp_path: Path
):
    cells = 20 if seed == 64 else 12
    gm.generate(seed, INDEX, cells=cells, svg=True, out_dir=tmp_path, version=V6)
    stem = f"gmap-{seed}-{V6}"
    for suffix in (".json", ".fill.json", ".svg"):
        assert (MAP_DIR / f"{stem}{suffix}").read_bytes() == (
            tmp_path / f"{stem}{suffix}"
        ).read_bytes()
    sr.generate(tmp_path / f"{stem}.json", "all_walkable", out_dir=tmp_path / "rooms")
    committed = CATALOG / "shape_rooms" / stem
    regenerated = tmp_path / "rooms" / stem
    assert sorted(path.name for path in committed.glob("*.json")) == sorted(
        path.name for path in regenerated.glob("*.json")
    )
    for path in committed.glob("*.json"):
        assert path.read_bytes() == (regenerated / path.name).read_bytes()
