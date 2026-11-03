"""Seeded diagonal links for gmap-0.6.0; earlier map versions never call this module."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from gmap_geometry import rect_polygon
from poetics_geometry import signed_area

VERSION = "gmap-0.6.0"
CHAMFER_M = 2.5
CLEAR_WIDTH_M = 2.0
WALL_M = 0.16
CLEARANCE_M = 0.5
RULE = "diagonal_links"
DIAG = math.sqrt(0.5)


def rng_for(seed: int, attempt: int) -> random.Random:
    key = hashlib.sha256(f"{seed}:{attempt}:diagonal-links:{VERSION}".encode()).digest()
    return random.Random(int.from_bytes(key, "big"))


def sampled_budget(rng: random.Random) -> int:
    return rng.choices((0, 1, 2), weights=(3, 5, 2), k=1)[0]


def _point_on_cut(
    cell: dict[str, Any], corner: list[float], sx: int, sz: int
) -> list[float]:
    return [corner[0] - sx * CHAMFER_M / 2, corner[1] - sz * CHAMFER_M / 2]


def _rect_intersects_polygon(
    rect: tuple[float, float, float, float], poly: list[list[float]]
) -> bool:
    x0, z0, x1, z1 = rect
    corners = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]
    axes = [(1.0, 0.0), (0.0, 1.0)]
    axes += [(-(b[1] - a[1]), b[0] - a[0]) for a, b in zip(poly, poly[1:] + poly[:1])]
    for ax, az in axes:
        a = [p[0] * ax + p[1] * az for p in corners]
        b = [p[0] * ax + p[1] * az for p in poly]
        if min(max(a), max(b)) - max(min(a), min(b)) <= 1e-7:
            return False
    return True


def _passage_polygon(
    start: list[float], end: list[float], half_width: float
) -> list[list[float]]:
    dx, dz = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dz)
    tx, tz = -dz / length, dx / length
    return [
        [start[0] + tx * half_width, start[1] + tz * half_width],
        [end[0] + tx * half_width, end[1] + tz * half_width],
        [end[0] - tx * half_width, end[1] - tz * half_width],
        [start[0] - tx * half_width, start[1] - tz * half_width],
    ]


def _port(port_id: str, pos: list[float], normal: list[float]) -> dict[str, Any]:
    return {
        "port_id": port_id,
        "pos_xz": [round(v, 9) for v in pos],
        "normal": [float(v) for v in normal],
        "compatibility_type": "level_doorway_2m_v1",
        "placement": "standard",
    }


def _add_one(document: dict[str, Any], pair: dict[str, Any], number: int) -> None:
    a, b = pair["a"], pair["b"]
    link_id, passage_id = f"dl{number:02d}", f"dp{number:02d}"
    sx, sz = pair["sx"], pair["sz"]
    normal = [sx * DIAG, sz * DIAG]
    a_id, b_id = f"{a['cell_id']}:d{number}", f"{b['cell_id']}:d{number}"
    a_port, b_port = (
        _port(a_id, pair["start"], normal),
        _port(b_id, pair["finish"], [-normal[0], -normal[1]]),
    )
    for cell, corner, port in (
        (a, pair["corner_a_xz"], a_port),
        (b, pair["corner_b_xz"], b_port),
    ):
        cell["required_ports"].append(port)
        cell["diagonal_link_chamfer"] = {
            "corner_xz": corner,
            "length_m": CHAMFER_M,
            "port_id": port["port_id"],
        }
        cell["allowed_primitives"] = sorted(
            set(cell["allowed_primitives"]) | {"chamfered_box"}
        )
        cell["shape_stage_target"], cell["shape_class_target"] = 2, "chamfered_box"
    passage = _passage_polygon(
        pair["start"], pair["finish"], CLEAR_WIDTH_M / 2 + WALL_M
    )
    xs, zs = [p[0] for p in passage], [p[1] for p in passage]
    rect = (min(xs), min(zs), max(xs), max(zs))
    length = math.dist(pair["start"], pair["finish"])
    passage_cell = {
        "cell_id": passage_id,
        "envelope_xz": rect_polygon(rect),
        "ceiling_range_m": [2.6, 4.8],
        "allowed_primitives": ["diagonal_passage"],
        "required_ports": [
            _port(f"{passage_id}:a", pair["start"], [-normal[0], -normal[1]]),
            _port(f"{passage_id}:b", pair["finish"], normal),
        ],
        "role": "threshold",
        "rarity_tier": 0,
        "mode": "standard",
        "shape_stage_target": 2,
        "shape_class_target": "diagonal_passage",
        "diagonal_passage": {
            "link_id": link_id,
            "from_cell_id": a["cell_id"],
            "to_cell_id": b["cell_id"],
            "from_port_id": a_id,
            "to_port_id": b_id,
            "clear_width_m": CLEAR_WIDTH_M,
            "wall_thickness_m": WALL_M,
            "length_m": round(length, 9),
            "outline_xz": passage,
            "palette_source_cell_id": min(a["cell_id"], b["cell_id"]),
        },
    }
    document["cells"].append(passage_cell)
    document["edges"].extend(
        [
            {
                "from": a_id,
                "to": f"{passage_id}:a",
                "connector": "direct",
                "kind": "diagonal",
                "diagonal_link_id": link_id,
            },
            {
                "from": f"{passage_id}:b",
                "to": b_id,
                "connector": "direct",
                "kind": "diagonal",
                "diagonal_link_id": link_id,
            },
        ]
    )


def apply_links(document: dict[str, Any]) -> None:
    """Post-pass over the frozen 0.5 layout stream; source rooms and spanning tree are retained."""
    from gmap_diagonal_candidates import candidate_pairs, select_pairs
    from gmap_diagonal_nudge import nudge_to_budget

    rng = rng_for(document["seed"], document["attempt"])
    budget = sampled_budget(rng)
    nudged = nudge_to_budget(document, budget) if budget else []
    chosen = select_pairs(candidate_pairs(document), budget, rng)
    for index, pair in enumerate(chosen):
        _add_one(document, pair, index)
    document["edges"].sort(key=lambda e: (e["from"], e["to"]))
    document["diagonal_links"] = {
        "budget": budget,
        "used": len(chosen),
        "selection_rule": "seeded weighted draw 0:3, 1:5, 2:2; eligible pairs sorted then seeded shuffle",
        "nudged_cells": nudged,
    }


def polygon_area(points: list[list[float]]) -> float:
    return abs(signed_area([(float(x), float(z)) for x, z in points]))
