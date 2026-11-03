"""45-degree chamfers on a rectilinear shape-room outline (shape stage 2a, issue 190).

A chamfer replaces one convex corner V of the base outline by the two points `c` metres
back along the incoming edge and `c` metres on along the outgoing edge. Every chamfer
leaves its two edges' straight remainders and every doorway on an axis-aligned face.
"""

from __future__ import annotations

import math
from typing import Any

from doorway_sizes import DEFAULT_TYPE, doorway_size
from poetics_geometry import Point, TOLERANCE_M, edge_vectors, segment_distance, signed_area
from shape_room_raster import Cell, Rect, decompose

CHAMFER_LENGTHS = (1.0, 1.5, 2.0, 2.5, 3.0)
MIN_FACE_M = 1.5  # a straight face beside a chamfer, so the cut never eats a whole wall
WALL_MARGIN_M = 0.5
PORT_CLEAR_M = 0.6  # a capsule (0.3 m) beside a 0.16 m wall, with slack, along the line in from every doorway
PORT_CLEAR_DEPTHS = (1.0, 1.5)
ERODE_M = 1.0  # the room keeps a connected spine this far from every wall (stage-1 arms are >= 3 m wide)
GRID_M = 0.5
EPS = 1e-9
Cuts = dict[int, float]


def unit(a: Point, b: Point) -> Point:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    return (b[0] - a[0]) / length, (b[1] - a[1]) / length


def convex_vertices(ring: list[Point]) -> list[int]:
    """Indices of the left-turning (convex, counter-clockwise ring) vertices."""
    count = len(ring)
    found = []
    for i in range(count):
        a, b, c = ring[i - 1], ring[i], ring[(i + 1) % count]
        if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) > EPS:
            found.append(i)
    return found


def apply_cuts(ring: list[Point], cuts: Cuts) -> list[Point]:
    """The outline with each cut vertex replaced by its two chamfer end points."""
    count = len(ring)
    points: list[Point] = []
    for i, vertex in enumerate(ring):
        c = cuts.get(i)
        if not c:
            points.append(vertex)
            continue
        back = unit(vertex, ring[i - 1])  # toward the previous vertex
        onward = unit(vertex, ring[(i + 1) % count])
        points.append((vertex[0] + back[0] * c, vertex[1] + back[1] * c))
        points.append((vertex[0] + onward[0] * c, vertex[1] + onward[1] * c))
    kept = [p for i, p in enumerate(points) if math.dist(p, points[i - 1]) > TOLERANCE_M]
    return [(round(x, 6) + 0.0, round(z, 6) + 0.0) for x, z in kept]


def port_edge(ring: list[Point], port: dict[str, Any]) -> int | None:
    """Index of the outline edge that carries the port's doorway (outward normal and line match)."""
    pos, normal = port["pos_xz"], port["normal"]
    for i, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1])):
        d = unit(a, b)
        if abs(normal[0] - d[1]) > EPS or abs(normal[1] + d[0]) > EPS:
            continue  # counter-clockwise ring: the outward normal of direction d is (d.z, -d.x)
        if segment_distance((pos[0], pos[1]), a, b) <= TOLERANCE_M:
            return i
    return None


def cut_issues(ring: list[Point], ports: list[dict[str, Any]], cuts: Cuts, wedge: bool = False) -> list[str]:
    """Reasons the chamfers break the margin, face, convexity or degenerate-port rules."""
    issues = []
    count = len(ring)
    convex = set(convex_vertices(ring))
    for i, c in cuts.items():
        if i not in convex:
            issues.append(f"vertex {i} is not a convex corner")
        if abs(c * 2 - round(c * 2)) > EPS or c < CHAMFER_LENGTHS[0]:
            issues.append(f"chamfer {c} m is off the 0.5 m lattice or under {CHAMFER_LENGTHS[0]} m")
    for j in range(count):
        a, b = ring[j], ring[(j + 1) % count]
        start, end = cuts.get(j, 0.0), cuts.get((j + 1) % count, 0.0)
        left = math.dist(a, b) - start - end
        if (start or end) and not (left >= MIN_FACE_M - EPS or (wedge and abs(left) <= EPS)):
            issues.append(f"edge {j} keeps only {left:.2f} m of straight face")
    for port in ports:
        j = port_edge(ring, port)
        if j is None:
            if cuts:
                issues.append(f"{port['port_id']}: no outline edge carries the doorway")
            continue
        start, end = cuts.get(j, 0.0), cuts.get((j + 1) % count, 0.0)
        if port.get("placement", "standard") == "degenerate" and (start or end):
            issues.append(f"{port['port_id']}: a degenerate doorway blocks chamfering its corner")
        half = doorway_size(port.get("compatibility_type", DEFAULT_TYPE))[0] / 2 + WALL_MARGIN_M
        a, b = ring[j], ring[(j + 1) % count]
        pos = (port["pos_xz"][0], port["pos_xz"][1])
        for chamfer, distance in ((start, math.dist(pos, a)), (end, math.dist(pos, b))):
            if chamfer and distance - chamfer < half - EPS:
                issues.append(f"{port['port_id']}: chamfer {chamfer} m leaves {distance - chamfer:.2f} m < {half} m to the doorway")
    if cuts:
        issues.extend(approach_issues(apply_cuts(ring, cuts), ports))
    return issues


def approach_issues(final: list[Point], ports: list[dict[str, Any]]) -> list[str]:
    """The line in from each doorway keeps PORT_CLEAR_M from every wall of the cut outline (a doorway
    opening onto the thin tip of a wedge could not be walked through)."""
    issues = []
    for port in ports:
        for depth in PORT_CLEAR_DEPTHS:
            point = (port["pos_xz"][0] - port["normal"][0] * depth, port["pos_xz"][1] - port["normal"][1] * depth)
            if wall_distance(point, final) < PORT_CLEAR_M - EPS:
                issues.append(f"{port['port_id']}: a wall comes within {PORT_CLEAR_M} m of the line in from the doorway at {depth} m")
                break
    return issues


def inside_polygon(point: Point, ring: list[Point]) -> bool:
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > point[1]) != (b[1] > point[1]) and point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def wall_distance(point: Point, ring: list[Point]) -> float:
    return min(segment_distance(point, a, b) for a, b in zip(ring, ring[1:] + ring[:1]))


def clearance_ok(ring: list[Point]) -> bool:
    """Minimum corridor clearance: points 1 m from every wall form one connected, non-empty spine."""
    xs, zs = [p[0] for p in ring], [p[1] for p in ring]
    spine = set()
    for i in range(int((max(xs) - min(xs)) / GRID_M)):
        for j in range(int((max(zs) - min(zs)) / GRID_M)):
            p = (min(xs) + (i + 0.5) * GRID_M, min(zs) + (j + 0.5) * GRID_M)
            if inside_polygon(p, ring) and wall_distance(p, ring) >= ERODE_M - EPS:
                spine.add((i, j))
    if not spine:
        return False
    seen, pending = set(), [min(spine)]
    while pending:
        i, j = pending.pop()
        if (i, j) not in seen:
            seen.add((i, j))
            pending.extend(n for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)) if n in spine)
    return len(seen) == len(spine)


def cut_cell_free(ring: list[Point], cuts: Cuts, cell: tuple[float, float, float, float]) -> bool:
    """True when the axis-aligned cell lies on the kept side of every chamfer line."""
    count = len(ring)
    for i, c in cuts.items():
        v = ring[i]
        e1, e2 = unit(v, ring[i - 1]), unit(v, ring[(i + 1) % count])
        s = [(cell[0] - v[0]) * e1[0] + (cell[1] - v[1]) * e1[1], (cell[2] - v[0]) * e1[0] + (cell[3] - v[1]) * e1[1]]
        t = [(cell[0] - v[0]) * e2[0] + (cell[1] - v[1]) * e2[1], (cell[2] - v[0]) * e2[0] + (cell[3] - v[1]) * e2[1]]
        s0, s1, t0, t1 = min(s), max(s), min(t), max(t)
        if s1 > EPS and t1 > EPS and max(s0, 0.0) + max(t0, 0.0) < c - EPS:
            return False
    return True


def outline_area(ring: list[Point]) -> float:
    return abs(signed_area(ring))


def is_axis_or_diagonal(ring: list[Point]) -> bool:
    return all(min(abs(dx), abs(dz)) <= TOLERANCE_M or abs(abs(dx) - abs(dz)) <= TOLERANCE_M for dx, dz in edge_vectors(ring))


def inscribed_rects(cells: set[Cell], ring: list[Point], cuts: Cuts) -> list[Rect]:
    """Disjoint rectangles of the 0.5 m raster cells that lie wholly inside the chamfered outline."""
    kept = {(i, j) for i, j in cells if cut_cell_free(ring, cuts, (i / 2, j / 2, (i + 1) / 2, (j + 1) / 2))}
    return decompose(kept) if kept else []


def lamp_points_polygon(ring: list[Point], pitch: float, anchor: float, inset: float) -> list[list[float]]:
    """Ceiling panels on the stage-1 grid, kept `inset` metres (Euclidean) from every wall, diagonals included.
    When none fit, the lattice point farthest from every wall."""
    xs, zs = [p[0] for p in ring], [p[1] for p in ring]
    points = []
    x = min(xs) + anchor
    while x <= max(xs):
        z = min(zs) + anchor
        while z <= max(zs):
            if inside_polygon((x, z), ring) and wall_distance((x, z), ring) >= inset - EPS:
                points.append([round(x, 6) + 0.0, round(z, 6) + 0.0])
            z += pitch
        x += pitch
    if points:
        return points
    best = max(
        ((wall_distance((x / 2, z / 2), ring), -z, -x) for x in range(int(min(xs) * 2), int(max(xs) * 2) + 1)
         for z in range(int(min(zs) * 2), int(max(zs) * 2) + 1) if inside_polygon((x / 2, z / 2), ring)),
    )
    return [[-best[2] / 2 + 0.0, -best[1] / 2 + 0.0]]
