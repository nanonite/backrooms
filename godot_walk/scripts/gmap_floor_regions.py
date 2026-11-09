"""Deterministic regional floor palettes for gmap-0.12.0 (#208).

The library-anchor palette rule (gmap-0.5.0) runs first. This layer then picks
one to three non-anchored seed cells and spreads each seed's floor palette to
cells within graph distance 1, so tile, metal and wood floors arrive in
coherent patches instead of per-cell noise.

Every choice is its own keyed draw over the stream ``floor_regions:gmap-0.12.0``
(seed, attempt and cell id), never a shared sequential RNG. Re-drawing one cell
therefore does not shift any other cell's result, and a later runtime pass can
re-draw a single room's floor.

Library anchors always win, and the spawn cell plus its direct neighbours are
never region seeds or region members. The region layer spends at most
``MAX_REGION_AREA_SHARE`` of the non-anchored generated envelope area and never
pushes the default carpet share below ``MIN_DEFAULT_AREA_SHARE`` of the whole
generated envelope area, so the Backrooms carpet stays the dominant floor.
"""

from __future__ import annotations

import hashlib
from typing import Any

STREAM = "floor_regions:gmap-0.12.0"
FLOOR_PALETTES = ("tiled_institutional", "metal_service", "wood_parquet")
MAX_REGION_SEEDS = 3
REGION_RADIUS = 1
MAX_REGION_AREA_SHARE = 0.15
MIN_DEFAULT_AREA_SHARE = 0.55
MIN_DEFAULT_ENVELOPE_SHARE = 0.60
EPSILON = 1e-9


def keyed_draw(seed: int, attempt: int, *parts: str) -> float:
    """Stable [0, 1) draw for one key below this layer's stream."""
    text = ":".join((str(seed), str(attempt), STREAM, *(str(part) for part in parts)))
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def seed_draw(seed: int, attempt: int, cell_id: str) -> float:
    """Draw that decides whether a candidate cell is a region seed."""
    return keyed_draw(seed, attempt, "seed", cell_id)


def palette_for_seed(seed: int, attempt: int, cell_id: str) -> str:
    """The region palette a seed cell carries; independent of cell order."""
    index = min(
        len(FLOOR_PALETTES) - 1,
        int(keyed_draw(seed, attempt, "palette", cell_id) * len(FLOOR_PALETTES)),
    )
    return FLOOR_PALETTES[index]


def envelope_area_m2(cell: dict[str, Any]) -> float:
    """Area of the cell's rectangular envelope, in square metres."""
    points = cell["envelope_xz"]
    total = 0.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        total += float(current[0]) * float(following[1]) - float(following[0]) * float(
            current[1]
        )
    return abs(total) / 2.0


def region_record(
    palette_id: str, seed_cell_id: str, distance: int
) -> dict[str, Any]:
    """The cell palette record for a region member."""
    return {
        "palette_id": palette_id,
        "anchor_module_id": None,
        "distance": None,
        "registry_version": "0.3.0",
        "region_seed_cell_id": seed_cell_id,
        "region_distance": distance,
    }


def metadata(
    seeds: list[dict[str, Any]], region_area_m2: float, base_area_m2: float
) -> dict[str, Any]:
    return {
        "stream": STREAM,
        "max_seeds": MAX_REGION_SEEDS,
        "radius": REGION_RADIUS,
        "max_region_area_share": MAX_REGION_AREA_SHARE,
        "min_default_area_share": MIN_DEFAULT_AREA_SHARE,
        "min_default_envelope_share": MIN_DEFAULT_ENVELOPE_SHARE,
        "selection": (
            "per-cell keyed seed and palette draws after library anchors; "
            "anchors win, spawn and direct neighbours excluded"
        ),
        "seed_cells": seeds,
        "region_area_m2": round(region_area_m2, 3),
        "base_area_m2": round(base_area_m2, 3),
    }


def apply_floor_regions(
    document: dict[str, Any], records: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Spread at most three keyed region patches over the anchor/default records."""
    from gmap_palette import distances, open_neighbours

    graph = open_neighbours(document)
    spawn_id = document["cells"][0]["cell_id"]
    protected = {spawn_id} | set(graph[spawn_id])
    by_id = {cell["cell_id"]: cell for cell in document["cells"]}
    candidates = [
        cell_id
        for cell_id, record in records.items()
        if record["anchor_module_id"] is None
        and cell_id not in protected
        and not by_id[cell_id].get("diagonal_passage")
    ]
    base_area = sum(
        envelope_area_m2(by_id[cell_id])
        for cell_id, record in records.items()
        if record["anchor_module_id"] is None
    )
    total_area = sum(envelope_area_m2(by_id[cell_id]) for cell_id in records)
    budget = min(
        MAX_REGION_AREA_SHARE * base_area,
        max(0.0, base_area - MIN_DEFAULT_ENVELOPE_SHARE * total_area),
    )
    seed = int(document["seed"])
    attempt = int(document.get("attempt", 0))
    scores = {cell_id: seed_draw(seed, attempt, cell_id) for cell_id in candidates}
    ordered = sorted(candidates, key=lambda cell_id: (scores[cell_id], cell_id))
    region: dict[str, dict[str, Any]] = {}
    seeds: list[dict[str, Any]] = []
    used_area = 0.0
    for cell_id in ordered:
        if len(seeds) >= MAX_REGION_SEEDS:
            break
        if cell_id in region:
            continue
        reach = distances(graph, cell_id)
        patch = [
            other
            for other in candidates
            if reach.get(other, REGION_RADIUS + 1) <= REGION_RADIUS
        ]
        new_cells = [other for other in patch if other not in region]
        patch_area = sum(envelope_area_m2(by_id[other]) for other in new_cells)
        if not new_cells or used_area + patch_area > budget + EPSILON:
            continue
        palette_id = palette_for_seed(seed, attempt, cell_id)
        for other in new_cells:
            region[other] = region_record(
                palette_id, cell_id, int(reach.get(other, 0))
            )
        used_area += patch_area
        seeds.append({"cell_id": cell_id, "palette_id": palette_id})
    records.update(region)
    return records, metadata(seeds, used_area, base_area)
