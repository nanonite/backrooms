"""Integer-lattice rectangle geometry shared by the generative map stages."""

from __future__ import annotations

from collections.abc import Iterator

Rect = tuple[int, int, int, int]
Vec = tuple[int, int]

MIN_OVERLAP_M = 2.4
DOORWAY_HALF_M = 1.0
MIN_PORT_SEPARATION_M = 2.0
EPS = 1e-9
SIDES: tuple[Vec, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


def rect_polygon(rect: Rect) -> list[list[int]]:
    x0, z0, x1, z1 = rect
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


def polygon_rect(polygon: list[list[float]]) -> Rect | None:
    """The rectangle a 4-point axis-aligned polygon describes, else None."""
    if len(polygon) != 4:
        return None
    xs = sorted({point[0] for point in polygon})
    zs = sorted({point[1] for point in polygon})
    if len(xs) != 2 or len(zs) != 2:
        return None
    if {tuple(point) for point in polygon} != {(x, z) for x in xs for z in zs}:
        return None
    return xs[0], zs[0], xs[1], zs[1]  # type: ignore[return-value]


def size_of(rect: Rect) -> tuple[int, int]:
    return rect[2] - rect[0], rect[3] - rect[1]


def aspect(rect: Rect) -> float:
    width, depth = size_of(rect)
    return max(width, depth) / min(width, depth)


def overlaps(a: Rect, b: Rect) -> bool:
    """True when the interiors share positive area (touching is allowed)."""
    return (
        min(a[2], b[2]) - max(a[0], b[0]) > EPS and min(a[3], b[3]) - max(a[1], b[1]) > EPS
    )


def contact(a: Rect, b: Rect) -> tuple[Vec, float, float, float] | None:
    """Shared boundary of two touching rectangles as (normal_of_a, coord, lo, hi)."""
    if abs(a[2] - b[0]) <= EPS:
        side: Vec = (1, 0)
    elif abs(a[0] - b[2]) <= EPS:
        side = (-1, 0)
    elif abs(a[3] - b[1]) <= EPS:
        side = (0, 1)
    elif abs(a[1] - b[3]) <= EPS:
        side = (0, -1)
    else:
        return None
    if side[0]:
        coord = a[2] if side[0] > 0 else a[0]
        lo, hi = max(a[1], b[1]), min(a[3], b[3])
    else:
        coord = a[3] if side[1] > 0 else a[1]
        lo, hi = max(a[0], b[0]), min(a[2], b[2])
    return (side, coord, lo, hi) if hi - lo > EPS else None


def adjacent(a: Rect, b: Rect) -> bool:
    return contact(a, b) is not None


def along(pos: tuple[float, float], normal: Vec) -> float:
    """Coordinate of a port along its wall (z for east/west walls, x otherwise)."""
    return pos[1] if normal[0] else pos[0]


def port_position(normal: Vec, coord: float, offset: float) -> Vec:
    return (int(coord), int(offset)) if normal[0] else (int(offset), int(coord))


def contact_port(a: Rect, b: Rect) -> tuple[Vec, Vec] | None:
    """Snapped centre of the overlap segment and a's outward normal, or None."""
    shared = contact(a, b)
    if shared is None or shared[3] - shared[2] + EPS < MIN_OVERLAP_M:
        return None
    normal, coord, lo, hi = shared
    return port_position(normal, coord, lo + int((hi - lo) // 2)), normal


def check_port_on_contact(
    rect: Rect, pos: tuple[float, float], normal: Vec, other: Rect
) -> str | None:
    """Error code if `pos` is not a valid doorway between `rect` and `other`."""
    shared = contact(rect, other)
    if shared is None:
        return "no_contact"
    side, coord, lo, hi = shared
    if side != tuple(normal):
        return "normal_not_outward"
    if hi - lo + EPS < MIN_OVERLAP_M:
        return "overlap_too_short"
    on_wall = pos[0] if normal[0] else pos[1]
    if abs(on_wall - coord) > EPS:
        return "port_off_boundary"
    where = along(pos, normal)
    if where < lo + DOORWAY_HALF_M - EPS or where > hi - DOORWAY_HALF_M + EPS:
        return "port_outside_overlap"
    return None


def flush_rects(parent: Rect, normal: Vec, width: int, depth: int) -> Iterator[Rect]:
    """Every rectangle flush against `parent` on one side with >= 3 m overlap."""
    px0, pz0, px1, pz1 = parent
    if normal[0]:
        x0 = px1 if normal[0] > 0 else px0 - width
        for z0 in range(pz0 - depth + 3, pz1 - 3 + 1):
            yield (x0, z0, x0 + width, z0 + depth)
    else:
        z0 = pz1 if normal[1] > 0 else pz0 - depth
        for x0 in range(px0 - width + 3, px1 - 3 + 1):
            yield (x0, z0, x0 + width, z0 + depth)


def oriented_sizes(size: tuple[int, int]) -> list[tuple[int, int]]:
    """The 0 and 90 degree orientations of a (width, depth) class, sorted."""
    return sorted({size, (size[1], size[0])})


def far_enough(pos: Vec, others: list[Vec]) -> bool:
    return all(
        (pos[0] - o[0]) ** 2 + (pos[1] - o[1]) ** 2 >= MIN_PORT_SEPARATION_M**2 - EPS
        for o in others
    )
