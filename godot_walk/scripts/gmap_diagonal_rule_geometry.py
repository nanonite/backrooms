"""Polygon and endpoint helpers for the gmap-0.6.0 diagonal rule checks."""

from __future__ import annotations

import math
from typing import Any

from gmap_diagonal import (
    CLEAR_WIDTH_M,
    CLEARANCE_M,
    WALL_M,
    _passage_polygon,
    _rect_intersects_polygon,
)
from gmap_geometry import polygon_rect
from gmap_rules import Errors, err

RULE = "diagonal_links"
EPS = 1e-6


def ports_by_id(
    cells: list[dict[str, Any]],
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    return {
        port["port_id"]: (cell, port)
        for cell in cells
        for port in cell["required_ports"]
    }


def edge_groups(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for edge in document["edges"]:
        if edge.get("kind") == "diagonal":
            groups.setdefault(edge.get("diagonal_link_id", ""), []).append(edge)
    return groups


def point_matches(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) == 2 and math.dist(a, b) <= EPS


def polygon_errors(
    cell: dict[str, Any],
    cells: list[dict[str, Any]],
    source_ids: tuple[str, str],
    start: list[float],
    finish: list[float],
) -> Errors:
    meta = cell["diagonal_passage"]
    poly = meta["outline_xz"]
    errors: Errors = []
    if len(poly) != 4 or len({tuple(point) for point in poly}) != 4:
        return [err(RULE, "passage_polygon_invalid", cell["cell_id"])]
    if _area(poly) <= EPS:
        errors.append(err(RULE, "passage_polygon_degenerate", cell["cell_id"]))
    broad = _passage_polygon(start, finish, CLEAR_WIDTH_M / 2 + WALL_M + CLEARANCE_M)
    excluded = {cell["cell_id"], *source_ids}
    for other in cells:
        if other["cell_id"] in excluded:
            continue
        _check_intersection(errors, cell, other, poly, broad)
    return errors


def _area(poly: list[list[float]]) -> float:
    return (
        abs(
            sum(
                poly[index][0] * poly[(index + 1) % 4][1]
                - poly[(index + 1) % 4][0] * poly[index][1]
                for index in range(4)
            )
        )
        / 2
    )


def _check_intersection(
    errors: Errors,
    passage: dict[str, Any],
    other: dict[str, Any],
    polygon: list[list[float]],
    broad: list[list[float]],
) -> None:
    rect = polygon_rect(other["envelope_xz"])
    if rect is None:
        return
    if _rect_intersects_polygon(rect, polygon):
        errors.append(
            err(
                RULE,
                "passage_footprint_overlap",
                f"{passage['cell_id']} intersects {other['cell_id']}",
            )
        )
    if _rect_intersects_polygon(rect, broad):
        errors.append(
            err(
                RULE,
                "passage_clearance_blocked",
                f"{passage['cell_id']} approaches {other['cell_id']} within 0.5 m",
            )
        )
