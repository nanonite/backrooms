"""Half-metre raster of a union of axis-aligned rectangles: outline, decomposition, queries.

Raster cell (i, j) covers [i/2, (i+1)/2] x [j/2, (j+1)/2] metres. The design traces on a
1 m raster, but 3 m arms centred on integer ports have half-metre edges, so the raster
resolution is 0.5 m.
"""

from __future__ import annotations

import math

from poetics_geometry import Point

STEPS_PER_M = 2
Rect = tuple[float, float, float, float]
Cell = tuple[int, int]
Vertex = tuple[int, int]


class RasterError(ValueError):
    """The union is not one simple rectilinear polygon on the raster."""


def to_units(value: float) -> int:
    scaled = value * STEPS_PER_M
    if abs(scaled - round(scaled)) > 1e-9:
        raise RasterError(f"{value} m is not on the 0.5 m raster")
    return round(scaled)


def occupied_cells(rects: list[Rect]) -> set[Cell]:
    cells: set[Cell] = set()
    for x0, z0, x1, z1 in rects:
        u0, v0, u1, v1 = to_units(x0), to_units(z0), to_units(x1), to_units(z1)
        if u1 <= u0 or v1 <= v0:
            raise RasterError(f"degenerate rectangle {(x0, z0, x1, z1)}")
        cells.update((i, j) for i in range(u0, u1) for j in range(v0, v1))
    return cells


def boundary_edges(cells: set[Cell]) -> dict[Vertex, list[Vertex]]:
    """Directed boundary edges, interior on the left (counter-clockwise)."""
    edges: dict[Vertex, list[Vertex]] = {}
    for i, j in sorted(cells):
        sides = (
            ((i, j - 1), (i, j), (i + 1, j)),
            ((i + 1, j), (i + 1, j), (i + 1, j + 1)),
            ((i, j + 1), (i + 1, j + 1), (i, j + 1)),
            ((i - 1, j), (i, j + 1), (i, j)),
        )
        for neighbour, start, end in sides:
            if neighbour not in cells:
                edges.setdefault(start, []).append(end)
    return edges


def trace_loop(edges: dict[Vertex, list[Vertex]]) -> list[Vertex]:
    if any(len(ends) > 1 for ends in edges.values()):
        raise RasterError("outline pinches (rectangles touch only at a corner)")
    start = min(edges)
    loop, current = [start], edges[start][0]
    while current != start:
        loop.append(current)
        current = edges[current][0]
    if len(loop) != sum(len(ends) for ends in edges.values()):
        raise RasterError("union has more than one boundary loop (hole or split)")
    return loop


def drop_collinear(loop: list[Vertex]) -> list[Vertex]:
    kept = []
    count = len(loop)
    for index, vertex in enumerate(loop):
        before, after = loop[index - 1], loop[(index + 1) % count]
        same_row = before[1] == vertex[1] == after[1]
        same_column = before[0] == vertex[0] == after[0]
        if not (same_row or same_column):
            kept.append(vertex)
    return kept


def outline_of(cells: set[Cell]) -> list[Point]:
    """Counter-clockwise outline of the union in metres, no collinear vertices."""
    if not cells:
        raise RasterError("empty union")
    loop = drop_collinear(trace_loop(boundary_edges(cells)))
    return [(u / STEPS_PER_M, v / STEPS_PER_M) for u, v in loop]


def is_connected(cells: set[Cell]) -> bool:
    if not cells:
        return False
    seen, pending = set(), [min(cells)]
    while pending:
        i, j = pending.pop()
        if (i, j) in seen:
            continue
        seen.add((i, j))
        pending.extend(n for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)) if n in cells)
    return len(seen) == len(cells)


def decompose(cells: set[Cell]) -> list[Rect]:
    """Disjoint rectangles covering the cells: horizontal runs merged across equal rows."""
    runs: dict[int, list[list[int]]] = {}
    for i, j in sorted(cells, key=lambda c: (c[1], c[0])):
        row = runs.setdefault(j, [])
        if row and row[-1][1] == i:
            row[-1][1] = i + 1
        else:
            row.append([i, i + 1])
    return merge_rows(runs)


def merge_rows(runs: dict[int, list[list[int]]]) -> list[Rect]:
    started: dict[tuple[int, int], int] = {}
    done: list[Rect] = []
    for j in range(min(runs), max(runs) + 2):
        current = {(a, b) for a, b in runs.get(j, [])}
        for key in sorted(set(started) - current):
            done.append(rect_from_units(key, (started.pop(key), j)))
        for key in sorted(current - set(started)):
            started[key] = j
    return sorted(done, key=lambda r: (r[1], r[0]))


def rect_from_units(columns: tuple[int, int], rows: tuple[int, int]) -> Rect:
    return (
        columns[0] / STEPS_PER_M,
        rows[0] / STEPS_PER_M,
        columns[1] / STEPS_PER_M,
        rows[1] / STEPS_PER_M,
    )


def solid_at(cells: set[Cell], x: float, z: float) -> bool:
    """True when the raster cell containing (x, z) is occupied."""
    return (math.floor(x * STEPS_PER_M), math.floor(z * STEPS_PER_M)) in cells
