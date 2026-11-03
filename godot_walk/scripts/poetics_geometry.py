"""Mechanical footprint analysis for module_poetics (shape, symmetry, port slots)."""

from __future__ import annotations

import math
from typing import Any, Callable

TOLERANCE_M = 1e-3
PORT_SLOT_MIN_LENGTH_M = 2.4
SOCKET_HOST_DISTANCE_M = 0.5
DECIMALS = 6
LENGTH_EPSILON_M = 1e-9
WEDGE_MIN_LEG_M = 3.0  # a single chamfer with a longer leg is a wedge

Point = tuple[float, float]


def num(value: float) -> float:
    """Round for stable output; the +0.0 turns -0.0 into 0.0."""
    return round(float(value), DECIMALS) + 0.0


def point_json(point: Point) -> list[float]:
    return [num(point[0]), num(point[1])]


def close(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) <= TOLERANCE_M and abs(a[1] - b[1]) <= TOLERANCE_M


def open_ring(footprint: list[list[float]]) -> list[Point]:
    """Footprint vertices without a duplicate closing vertex."""
    ring = [(float(x), float(z)) for x, z in footprint]
    if len(ring) > 1 and close(ring[0], ring[-1]):
        ring = ring[:-1]
    if len(ring) < 3:
        raise ValueError("A footprint needs at least three distinct vertices")
    return ring


def signed_area(ring: list[Point]) -> float:
    total = 0.0
    for index, (x1, z1) in enumerate(ring):
        x2, z2 = ring[(index + 1) % len(ring)]
        total += x1 * z2 - x2 * z1
    return total / 2.0


def convex_hull(points: list[Point]) -> list[Point]:
    ordered = sorted(set(points))
    if len(ordered) < 3:
        return ordered

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(sequence: list[Point]) -> list[Point]:
        chain: list[Point] = []
        for point in sequence:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain[:-1]

    return half(ordered) + half(ordered[::-1])


def edge_vectors(ring: list[Point]) -> list[Point]:
    return [
        (ring[(i + 1) % len(ring)][0] - x, ring[(i + 1) % len(ring)][1] - z)
        for i, (x, z) in enumerate(ring)
    ]


def is_rectilinear(ring: list[Point]) -> bool:
    return all(
        min(abs(dx), abs(dz)) <= TOLERANCE_M for dx, dz in edge_vectors(ring)
    )


def is_chamfered(ring: list[Point]) -> bool:
    """Every edge is axis-aligned or at 45 degrees."""
    return all(
        min(abs(dx), abs(dz)) <= TOLERANCE_M or abs(abs(dx) - abs(dz)) <= TOLERANCE_M
        for dx, dz in edge_vectors(ring)
    )


def chamfer_base(ring: list[Point]) -> tuple[list[Point], list[float]] | None:
    """Counter-clockwise rectilinear outline with every 45-degree chamfer edge un-cut, and the legs.

    Each diagonal edge P -> Q gets the one right-angle corner C on its outer (right-hand) side
    inserted between P and Q; points that become collinear are then dropped. That also covers a
    chamfer that eats a whole side (a wedge). None when a diagonal has no single outer corner."""
    if signed_area(ring) < 0:
        ring = ring[::-1]
    edges = edge_vectors(ring)
    points: list[Point] = []
    legs: list[float] = []
    for i, (dx, dz) in enumerate(edges):
        points.append(ring[i])
        if min(abs(dx), abs(dz)) > TOLERANCE_M:
            p, q = ring[i], ring[(i + 1) % len(ring)]
            outer = [c for c in ((q[0], p[1]), (p[0], q[1])) if dx * (c[1] - p[1]) - dz * (c[0] - p[0]) < -TOLERANCE_M]
            if len(outer) != 1:
                return None
            points.append(outer[0])
            legs.append(abs(dx))
    changed = True
    while changed and len(points) > 3:
        changed = False
        for i, v in enumerate(points):
            a, b = points[i - 1], points[(i + 1) % len(points)]
            if close(a, v) or abs((v[0] - a[0]) * (b[1] - v[1]) - (v[1] - a[1]) * (b[0] - v[0])) <= TOLERANCE_M:
                del points[i]
                changed = True
                break
    return points, legs


def classify_chamfered(ring: list[Point]) -> str:
    """Stage-2 class of a ring whose edges are axis-aligned or at 45 degrees."""
    cut = chamfer_base(ring)
    if cut is None:
        return "chamfered_polygon"
    base, legs = cut
    if not is_rectilinear(base):
        return "chamfered_polygon"
    if len(base) != 4:
        return "chamfered_polyomino"
    if len(legs) == 4 and max(legs) - min(legs) <= TOLERANCE_M:
        return "octagon"
    if len(legs) == 1 and legs[0] > WEDGE_MIN_LEG_M:
        return "wedge"
    return "chamfered_box"


def classify_primitive(ring: list[Point], detailed: bool = True) -> tuple[str, int | None]:
    """Primitive name and shape stage per proposal section 5.

    `detailed` splits stage 2 into chamfered_box / octagon / wedge / chamfered_polyomino
    (shape rooms, #190); module poetics keeps the single `chamfered_polygon` label."""
    if is_rectilinear(ring):
        if len(ring) == 4:
            return "box", 0
        if len(ring) == 6:
            return "l_shape", 1
        return "rectilinear_polygon", 1
    if is_chamfered(ring):
        return (classify_chamfered(ring) if detailed else "chamfered_polygon"), 2
    return "polygon", None


def bbox_of(ring: list[Point]) -> tuple[float, float, float, float]:
    xs = [x for x, _ in ring]
    zs = [z for _, z in ring]
    return min(xs), min(zs), max(xs), max(zs)


def same_ring(a: list[Point], b: list[Point]) -> bool:
    """Equal as closed polygons, ignoring start vertex and winding."""
    if len(a) != len(b):
        return False
    count = len(a)
    for sequence in (b, b[::-1]):
        for shift in range(count):
            if all(close(a[i], sequence[(i + shift) % count]) for i in range(count)):
                return True
    return False


def symmetry_class(ring: list[Point]) -> str:
    """C1, D1, C2, D2, C4 or D4 about the bounding-box centre."""
    min_x, min_z, max_x, max_z = bbox_of(ring)
    cx, cz = (min_x + max_x) / 2.0, (min_z + max_z) / 2.0
    moves: dict[str, Callable[[Point], Point]] = {
        "mirror_x": lambda p: (2 * cx - p[0], p[1]),
        "mirror_z": lambda p: (p[0], 2 * cz - p[1]),
        "rot180": lambda p: (2 * cx - p[0], 2 * cz - p[1]),
        "rot90": lambda p: (cx - (p[1] - cz), cz + (p[0] - cx)),
    }
    held = {name for name, move in moves.items() if same_ring(ring, [move(p) for p in ring])}
    mirrors = held & {"mirror_x", "mirror_z"}
    if "rot90" in held:
        return "D4" if mirrors else "C4"
    if "rot180" in held:
        return "D2" if mirrors else "C2"
    return "D1" if mirrors else "C1"


def analyze_shape(footprint: list[list[float]]) -> dict[str, Any]:
    ring = open_ring(footprint)
    area = abs(signed_area(ring))
    if area <= TOLERANCE_M:
        raise ValueError("Footprint has zero area")
    min_x, min_z, max_x, max_z = bbox_of(ring)
    sides = sorted([max_x - min_x, max_z - min_z])
    primitive, stage = classify_primitive(ring, detailed=False)
    return {
        "footprint_xz": [point_json(p) for p in ring],
        "vertex_count": len(ring),
        "area_m2": num(area),
        "bbox_xz": {"min": [num(min_x), num(min_z)], "max": [num(max_x), num(max_z)]},
        "aspect": num(sides[1] / sides[0]),
        "convexity": num(area / abs(signed_area(convex_hull(ring)))),
        "rectilinear": is_rectilinear(ring),
        "primitive": primitive,
        "shape_stage": stage,
        "symmetry": symmetry_class(ring),
    }


def segment_distance(point: Point, a: Point, b: Point) -> float:
    dx, dz = b[0] - a[0], b[1] - a[1]
    length_squared = dx * dx + dz * dz
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dz) / length_squared
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dz))


def hosts_socket(a: Point, b: Point, sockets: list[dict[str, Any]]) -> bool:
    for socket in sockets:
        centre = socket["local_floor_center"]
        if segment_distance((centre[0], centre[2]), a, b) <= SOCKET_HOST_DISTANCE_M:
            return True
    return False


def outward_normal(edge: Point, counter_clockwise: bool) -> Point:
    length = math.hypot(*edge)
    dx, dz = edge[0] / length, edge[1] / length
    return (dz, -dx) if counter_clockwise else (-dz, dx)


def port_slots(
    footprint: list[list[float]], sockets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Long footprint edges that host no socket. Proposal-only, never usable by layout."""
    ring = open_ring(footprint)
    counter_clockwise = signed_area(ring) > 0
    slots = []
    for index, edge in enumerate(edge_vectors(ring)):
        a, b = ring[index], ring[(index + 1) % len(ring)]
        length = math.hypot(*edge)
        if length + LENGTH_EPSILON_M < PORT_SLOT_MIN_LENGTH_M or hosts_socket(a, b, sockets):
            continue
        slots.append(
            {
                "slot_id": f"edge-{index}",
                "edge_index": index,
                "from_xz": point_json(a),
                "to_xz": point_json(b),
                "midpoint_xz": point_json(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)),
                "length_m": num(length),
                "outward_normal_xz": point_json(outward_normal(edge, counter_clockwise)),
            }
        )
    return slots
