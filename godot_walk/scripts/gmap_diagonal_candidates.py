"""Eligible corner pairs and safe one-metre leaf adjustments for gmap-0.6.0."""

from __future__ import annotations

import itertools
import math
from typing import Any

from gmap_diagonal import (
    CHAMFER_M,
    CLEAR_WIDTH_M,
    CLEARANCE_M,
    DIAG,
    WALL_M,
    _passage_polygon,
    _point_on_cut,
    _rect_intersects_polygon,
)
from gmap_geometry import polygon_rect, rect_polygon
from shape_room_chamfer import (
    apply_cuts,
    approach_issues,
    clearance_ok,
    cut_issues,
    port_edge,
)


def _source_cut_ok(cell: dict[str, Any], corner_index: int, sx: int, sz: int) -> bool:
    rect = polygon_rect(cell["envelope_xz"])
    if rect is None:
        return False
    ring = [(float(x), float(z)) for x, z in rect_polygon(rect)]
    corner = ring[corner_index]
    pos = _point_on_cut(cell, list(corner), sx, sz)
    port = {
        "port_id": "candidate",
        "pos_xz": pos,
        "normal": [sx * DIAG, sz * DIAG],
        "compatibility_type": "level_doorway_2m_v1",
    }
    if any(math.dist(pos, p["pos_xz"]) < 2.0 - 1e-7 for p in cell["required_ports"]):
        return False
    cuts = {corner_index: CHAMFER_M}
    final = apply_cuts(ring, cuts)
    edge = port_edge(final, port)
    return (
        not cut_issues(ring, cell["required_ports"], cuts)
        and edge is not None
        and math.dist(final[edge], final[(edge + 1) % len(final)])
        >= CLEAR_WIDTH_M + 1.0
        and not approach_issues(final, [port])
        and clearance_ok(final)
    )


def _corners(rect: tuple[float, float, float, float]) -> list[list[float]]:
    x0, z0, x1, z1 = rect
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


def candidate_pairs(document: dict[str, Any]) -> list[dict[str, Any]]:
    cells = [
        c
        for c in document["cells"]
        if c["role"] in ("ground", "figure") and not c.get("module")
    ]
    found = []
    for a, b in itertools.combinations(sorted(cells, key=lambda c: c["cell_id"]), 2):
        ra, rb = polygon_rect(a["envelope_xz"]), polygon_rect(b["envelope_xz"])
        if (
            ra is None
            or rb is None
            or min(ra[2] - ra[0], ra[3] - ra[1], rb[2] - rb[0], rb[3] - rb[1]) < 4.0
        ):
            continue
        for ia, ca in enumerate(_corners(ra)):
            for ib, cb in enumerate(_corners(rb)):
                dx, dz = cb[0] - ca[0], cb[1] - ca[1]
                if abs(dx) != 1 or abs(dz) != 1:
                    continue
                sx, sz = int(dx), int(dz)
                if not _source_cut_ok(a, ia, sx, sz) or not _source_cut_ok(
                    b, ib, -sx, -sz
                ):
                    continue
                start, finish = (
                    _point_on_cut(a, ca, sx, sz),
                    _point_on_cut(b, cb, -sx, -sz),
                )
                if math.dist(start, finish) < 2.0:
                    continue
                broad = _passage_polygon(
                    start, finish, CLEAR_WIDTH_M / 2 + WALL_M + CLEARANCE_M
                )
                blocked = any(
                    _rect_intersects_polygon(polygon_rect(c["envelope_xz"]), broad)
                    for c in document["cells"]
                    if c["cell_id"] not in (a["cell_id"], b["cell_id"])
                    and polygon_rect(c["envelope_xz"]) is not None
                )
                if not blocked:
                    found.append(
                        {
                            "a": a,
                            "b": b,
                            "corner_a": ia,
                            "corner_b": ib,
                            "corner_a_xz": ca,
                            "corner_b_xz": cb,
                            "sx": sx,
                            "sz": sz,
                            "start": start,
                            "finish": finish,
                        }
                    )
    return found


def _pair_capacity(pairs: list[dict[str, Any]]) -> int:
    identities = [({pair["a"]["cell_id"], pair["b"]["cell_id"]}) for pair in pairs]
    if any(
        left.isdisjoint(right)
        for i, left in enumerate(identities)
        for right in identities[i + 1 :]
    ):
        return 2
    return int(bool(identities))


def select_pairs(
    pairs: list[dict[str, Any]], budget: int, rng: Any
) -> list[dict[str, Any]]:
    rng.shuffle(pairs)
    best: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []

    def search(start: int, used: set[str]) -> bool:
        nonlocal best
        if len(selected) > len(best):
            best = selected.copy()
        if len(selected) >= budget:
            return True
        for index in range(start, len(pairs)):
            pair = pairs[index]
            ids = {pair["a"]["cell_id"], pair["b"]["cell_id"]}
            if ids.isdisjoint(used):
                selected.append(pair)
                if search(index + 1, used | ids):
                    return True
                selected.pop()
        return False

    search(0, set())
    return best
