"""Static geometry checks for the supported orthogonal room footprint."""

from __future__ import annotations

import math
from collections.abc import Sequence

from video_adaptation_errors import AdaptationValidationError

TOLERANCE = 1e-9


def validate_orthogonal_polygon(
    vertices: object, label: str
) -> list[tuple[float, float]]:
    points = _read_vertices(vertices, label)
    if len(points) < 4:
        raise AdaptationValidationError(f"{label} needs at least four vertices")
    _validate_edges(points, label)
    _validate_intersections(points, label)
    area = abs(_signed_area(points))
    if not math.isfinite(area) or area <= TOLERANCE:
        raise AdaptationValidationError(f"{label} has zero area")
    return points


def point_location(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> str:
    inside = False
    x, z = point
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if _point_on_segment(point, start, end):
            return "boundary"
        x1, z1 = start
        x2, z2 = end
        crosses = (z1 > z) != (z2 > z)
        if crosses and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            inside = not inside
    return "inside" if inside else "outside"


def distance_to_boundary(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> float:
    distances = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        distances.append(_point_segment_distance(point, start, end))
    return min(distances)


def ensure_polygon_inside(
    inner: Sequence[tuple[float, float]],
    outer: Sequence[tuple[float, float]],
    label: str,
) -> None:
    if any(point_location(point, outer) != "inside" for point in inner):
        raise AdaptationValidationError(f"{label} leaves its supporting footprint")
    for start, end in _polygon_edges(inner):
        for edge_start, edge_end in _polygon_edges(outer):
            if _segments_intersect(start, end, edge_start, edge_end):
                raise AdaptationValidationError(
                    f"{label} crosses or touches its supporting boundary"
                )


def minimum_boundary_separation(
    first: Sequence[tuple[float, float]], second: Sequence[tuple[float, float]]
) -> float:
    distances = []
    for first_start, first_end in _polygon_edges(first):
        for second_start, second_end in _polygon_edges(second):
            if _segments_intersect(first_start, first_end, second_start, second_end):
                return 0.0
            distances.extend(
                (
                    _point_segment_distance(first_start, second_start, second_end),
                    _point_segment_distance(first_end, second_start, second_end),
                    _point_segment_distance(second_start, first_start, first_end),
                    _point_segment_distance(second_end, first_start, first_end),
                )
            )
    return min(distances)


def signed_area(points: Sequence[tuple[float, float]]) -> float:
    return _signed_area(points)


def _polygon_edges(
    points: Sequence[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [
        (start, points[(index + 1) % len(points)]) for index, start in enumerate(points)
    ]


def _read_vertices(value: object, label: str) -> list[tuple[float, float]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AdaptationValidationError(
            f"{label} vertices must be a coordinate sequence"
        )
    points = []
    for vertex in value:
        if not isinstance(vertex, Sequence) or len(vertex) != 2:
            raise AdaptationValidationError(f"{label} vertices must be X/Z pairs")
        if any(
            isinstance(axis, bool) or not isinstance(axis, (int, float))
            for axis in vertex
        ):
            raise AdaptationValidationError(
                f"{label} coordinates must be finite numbers"
            )
        point = (float(vertex[0]), float(vertex[1]))
        if not all(math.isfinite(axis) for axis in point):
            raise AdaptationValidationError(
                f"{label} coordinates must be finite numbers"
            )
        points.append(point)
    if len(set(points)) != len(points):
        raise AdaptationValidationError(f"{label} repeats a polygon vertex")
    return points


def _validate_edges(points: list[tuple[float, float]], label: str) -> None:
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        dx, dz = end[0] - start[0], end[1] - start[1]
        horizontal = abs(dz) <= TOLERANCE
        vertical = abs(dx) <= TOLERANCE
        if horizontal == vertical:
            raise AdaptationValidationError(
                f"{label} contains a zero-length or nonorthogonal edge"
            )
    for index, point in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % len(points)]
        incoming = (point[0] - previous[0], point[1] - previous[1])
        outgoing = (following[0] - point[0], following[1] - point[1])
        dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        if abs(_cross(incoming, outgoing)) <= TOLERANCE and dot < 0:
            raise AdaptationValidationError(
                f"{label} doubles back over an adjacent edge"
            )


def _validate_intersections(points: list[tuple[float, float]], label: str) -> None:
    count = len(points)
    for first in range(count):
        a, b = points[first], points[(first + 1) % count]
        for second in range(first + 1, count):
            if second == first + 1 or (first == 0 and second == count - 1):
                continue
            c, d = points[second], points[(second + 1) % count]
            if _segments_intersect(a, b, c, d):
                raise AdaptationValidationError(
                    f"{label} self-intersects or touches itself"
                )


def _signed_area(points: Sequence[tuple[float, float]]) -> float:
    return (
        sum(
            start[0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * start[1]
            for i, start in enumerate(points)
        )
        / 2.0
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    return _orientation_intersects(a, b, c, d) and _orientation_intersects(c, d, a, b)


def _orientation_intersects(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    o1, o2 = _cross_diff(a, b, c), _cross_diff(a, b, d)
    o3, o4 = _cross_diff(c, d, a), _cross_diff(c, d, b)
    if (
        (o1 > TOLERANCE and o2 < -TOLERANCE) or (o1 < -TOLERANCE and o2 > TOLERANCE)
    ) and (
        (o3 > TOLERANCE and o4 < -TOLERANCE) or (o3 < -TOLERANCE and o4 > TOLERANCE)
    ):
        return True
    return any(
        (abs(value) <= TOLERANCE and _point_on_segment(point, start, end))
        for value, point, start, end in (
            (o1, c, a, b),
            (o2, d, a, b),
            (o3, a, c, d),
            (o4, b, c, d),
        )
    )


def _cross_diff(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> float:
    return _cross((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1]))


def _cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _point_on_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> bool:
    if abs(_cross_diff(start, end, point)) > TOLERANCE:
        return False
    return (
        min(start[0], end[0]) - TOLERANCE
        <= point[0]
        <= max(start[0], end[0]) + TOLERANCE
        and min(start[1], end[1]) - TOLERANCE
        <= point[1]
        <= max(start[1], end[1]) + TOLERANCE
    )


def _point_segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dz = end[0] - start[0], end[1] - start[1]
    denominator = dx * dx + dz * dz
    projection = max(
        0.0,
        min(
            1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dz) / denominator
        ),
    )
    nearest = (start[0] + projection * dx, start[1] + projection * dz)
    return math.hypot(point[0] - nearest[0], point[1] - nearest[1])
