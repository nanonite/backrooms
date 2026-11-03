"""Fail-closed invariants for a generated shape room."""

from __future__ import annotations

from typing import Any

from poetics_geometry import is_rectilinear
from shape_room_raster import Cell, Rect, is_connected, solid_at

DOORWAY_WIDTH_M = 2.0
DOORWAY_HEIGHT_M = 2.1
WALL_MARGIN_M = 0.5
PROBE_M = 0.25  # half a raster cell: the centre of the cell just inside a wall


class ShapeRoomError(ValueError):
    """A shape room violates an invariant; nothing is written."""


def rect_inside(rect: Rect, envelope: Rect) -> bool:
    return (
        rect[0] >= envelope[0] and rect[1] >= envelope[1]
        and rect[2] <= envelope[2] and rect[3] <= envelope[3]
    )


def probe_point(port: dict[str, Any], along: float) -> tuple[float, float]:
    """Centre of the raster cell just inside the port's wall at `along` the wall."""
    x, z = port["pos_xz"]
    nx, nz = port["normal"]
    if nx:
        return x - nx * PROBE_M, along
    return along, z - nz * PROBE_M


def wall_span(envelope: Rect, port: dict[str, Any]) -> tuple[float, float, float]:
    """(port coordinate along the wall, envelope low end, envelope high end)."""
    if port["normal"][0]:
        return port["pos_xz"][1], envelope[1], envelope[3]
    return port["pos_xz"][0], envelope[0], envelope[2]


def port_on_envelope(envelope: Rect, port: dict[str, Any]) -> bool:
    x, z = port["pos_xz"]
    nx, nz = port["normal"]
    wall = {(1, 0): envelope[2], (-1, 0): envelope[0], (0, 1): envelope[3], (0, -1): envelope[1]}
    return (x if nx else z) == wall[(nx, nz)]


def port_issues(cells: set[Cell], envelope: Rect, port: dict[str, Any]) -> list[str]:
    name = port["port_id"]
    if not port_on_envelope(envelope, port):
        return [f"{name}: port is not on its envelope side"]
    centre, low, high = wall_span(envelope, port)
    start, end = centre - DOORWAY_WIDTH_M / 2, centre + DOORWAY_WIDTH_M / 2
    if start < low or end > high:
        return [f"{name}: doorway leaves the envelope side"]
    issues = []
    along = start + PROBE_M
    while along < end:
        if not solid_at(cells, *probe_point(port, along)):
            issues.append(f"{name}: doorway span is not on the polygon boundary at {along}")
            break
        along += PROBE_M * 2
    issues.extend(margin_issues(cells, port, (start, low), (end, high)))
    return issues


def margin_issues(
    cells: set[Cell], port: dict[str, Any], low_side: tuple[float, float], high_side: tuple[float, float]
) -> list[str]:
    """>= 0.5 m of solid wall beside the doorway, unless the envelope side ends first."""
    issues = []
    for label, edge, limit, direction in (("low", *low_side, -1), ("high", *high_side, 1)):
        if abs(edge - limit) < WALL_MARGIN_M:
            continue
        probe = edge + direction * PROBE_M
        if not solid_at(cells, *probe_point(port, probe)):
            issues.append(f"{port['port_id']}: no {WALL_MARGIN_M} m wall margin on the {label} side")
    return issues


def check_room(
    envelope: Rect,
    ports: list[dict[str, Any]],
    rects: list[Rect],
    cells: set[Cell],
    outline: list[tuple[float, float]],
) -> list[str]:
    issues = [f"rectangle {r} leaves the envelope" for r in rects if not rect_inside(r, envelope)]
    if not is_connected(cells):
        issues.append("polygon is not connected")
    if not is_rectilinear(outline):
        issues.append("outline is not rectilinear")
    for port in ports:
        issues.extend(port_issues(cells, envelope, port))
    return issues


def require_valid(cell_id: str, issues: list[str]) -> None:
    if issues:
        raise ShapeRoomError(f"{cell_id}: " + "; ".join(issues))
