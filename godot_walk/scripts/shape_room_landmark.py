"""Regular-polygon shape-room spec construction for gmap-0.7.0."""

from __future__ import annotations

import math
from typing import Any

from gmap_landmark import LANDMARKS, regular_polygon
from poetics_geometry import num, signed_area
from shape_room_raster import Cell, Rect, decompose

GRID = 0.5
EPS = 1e-7


def _inside(point: tuple[float, float], ring: list[list[float]]) -> bool:
    x, z = point
    inside = False
    for index, a in enumerate(ring):
        b = ring[(index + 1) % len(ring)]
        dx, dz = b[0] - a[0], b[1] - a[1]
        cross = (x - a[0]) * dz - (z - a[1]) * dx
        if (
            abs(cross) <= EPS
            and min(a[0], b[0]) - EPS <= x <= max(a[0], b[0]) + EPS
            and min(a[1], b[1]) - EPS <= z <= max(a[1], b[1]) + EPS
        ):
            return True
        if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / dz + a[0]:
            inside = not inside
    return inside


def _raster_rects(ring: list[list[float]]) -> list[Rect]:
    low_x, high_x = min(p[0] for p in ring), max(p[0] for p in ring)
    low_z, high_z = min(p[1] for p in ring), max(p[1] for p in ring)
    cells: set[Cell] = set()
    for i in range(math.floor(low_x / GRID), math.ceil(high_x / GRID)):
        for j in range(math.floor(low_z / GRID), math.ceil(high_z / GRID)):
            corners = [
                (i * GRID, j * GRID),
                ((i + 1) * GRID, j * GRID),
                ((i + 1) * GRID, (j + 1) * GRID),
                (i * GRID, (j + 1) * GRID),
            ]
            if all(_inside(point, ring) for point in corners):
                cells.add((i, j))
    return decompose(cells)


def spec_fields(cell: dict[str, Any]) -> dict[str, Any]:
    """Return exact polygon outline, an interior 0.5 m support raster, and reported area."""
    landmark = cell["landmark"]
    base = float(LANDMARKS[landmark["class"]]["rotation"])
    rotation_offset = (float(landmark["rotation_deg"]) - base) % 360.0
    rect = (
        min(p[0] for p in cell["envelope_xz"]),
        min(p[1] for p in cell["envelope_xz"]),
        max(p[0] for p in cell["envelope_xz"]),
        max(p[1] for p in cell["envelope_xz"]),
    )
    plan = {"class": landmark["class"], "rotation_deg": rotation_offset}
    center = ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    outline = regular_polygon(center, plan)
    rects = _raster_rects(outline)
    if not rects:
        raise ValueError(f"{cell['cell_id']}: landmark has no interior raster cells")
    area = abs(signed_area([(p[0], p[1]) for p in outline]))
    return {"outline": outline, "rects": rects, "area_m2": num(area), "center": center}
