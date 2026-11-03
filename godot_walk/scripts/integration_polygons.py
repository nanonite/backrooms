"""Plain polygon predicates for integration fitting (boundary-inclusive)."""

from __future__ import annotations

from poetics_geometry import TOLERANCE_M, segment_distance

Point = tuple[float, float]
_COS_SIN = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}


def rotate(point: Point, yaw_deg: int) -> Point:
    cos, sin = _COS_SIN[yaw_deg]
    return (point[0] * cos + point[1] * sin, -point[0] * sin + point[1] * cos)


def on_boundary(point: Point, ring: list[Point]) -> bool:
    return any(
        segment_distance(point, ring[i], ring[(i + 1) % len(ring)]) <= TOLERANCE_M
        for i in range(len(ring))
    )


def point_inside(point: Point, ring: list[Point]) -> bool:
    """Inside or on the boundary of a simple polygon."""
    if on_boundary(point, ring):
        return True
    inside = False
    for i, (x1, z1) in enumerate(ring):
        x2, z2 = ring[(i + 1) % len(ring)]
        if (z1 > point[1]) != (z2 > point[1]):
            if point[0] < x1 + (point[1] - z1) * (x2 - x1) / (z2 - z1):
                inside = not inside
    return inside


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def proper_crossing(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    return o1 * o2 < -TOLERANCE_M and o3 * o4 < -TOLERANCE_M


def polygon_within(inner: list[Point], outer: list[Point]) -> bool:
    count = len(inner)
    edges = [(inner[i], inner[(i + 1) % count]) for i in range(count)]
    if not all(point_inside(vertex, outer) for vertex in inner):
        return False
    middles = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in edges]
    if not all(point_inside(point, outer) for point in middles):
        return False
    return not any(
        proper_crossing(a, b, outer[i], outer[(i + 1) % len(outer)])
        for a, b in edges
        for i in range(len(outer))
    )
