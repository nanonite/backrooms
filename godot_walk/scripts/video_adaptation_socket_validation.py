"""Static checks for authored boundary sockets and historical socket records."""

from __future__ import annotations

import math
from typing import Any

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_polygon import (
    distance_to_boundary,
    ensure_polygon_inside,
    minimum_boundary_separation,
    point_location,
    signed_area,
    validate_orthogonal_polygon,
)

TOLERANCE = 1e-6


def validate_socket_declarations(
    record: dict[str, Any],
    polygon: list[tuple[float, float]],
    floor_y: float,
    capsule_radius: float,
    capsule_height: float,
    *,
    contract_version: int,
) -> None:
    resolved = record["resolved_adaptation"]
    room_clearance = (
        _room_clearance(resolved, floor_y, capsule_height)
        if contract_version >= 3
        else None
    )
    identifiers: set[str] = set()
    for socket in resolved.get("sockets", []):
        _validate_socket_id(socket, identifiers)
        if socket["kind"] == "observed_opening":
            _validate_observed_opening(socket)
            continue
        if contract_version >= 2:
            if room_clearance is None:
                raise AdaptationValidationError(
                    "Authored sockets require the v3 declared room-clearance contract; migrate the record"
                )
            _validate_authored_boundary_socket(
                socket, polygon, floor_y, room_clearance, capsule_radius, capsule_height
            )
        else:
            _validate_legacy_authored_socket(
                socket, polygon, floor_y, capsule_radius, capsule_height
            )


def _room_clearance(
    resolved: dict[str, Any], floor_y: float, capsule_height: float
) -> tuple[float, float]:
    clearance = resolved.get("room_clearance")
    if not isinstance(clearance, dict):
        raise AdaptationValidationError("Contract v3 requires declared room clearance")
    floor = _finite(clearance.get("floor_elevation"), "room-clearance floor")
    ceiling = _finite(clearance.get("ceiling_elevation"), "room-clearance ceiling")
    if abs(floor - floor_y) > TOLERANCE or ceiling <= floor:
        raise AdaptationValidationError("Declared room clearance is invalid")
    if ceiling - floor + TOLERANCE < capsule_height:
        raise AdaptationValidationError(
            "Declared room clearance is below capsule height"
        )
    if clearance.get("basis") not in {"measured", "estimated", "authored"}:
        raise AdaptationValidationError(
            "Room clearance requires an explicit evidence basis"
        )
    return floor, ceiling


def _validate_socket_id(socket: dict[str, Any], identifiers: set[str]) -> None:
    socket_id = socket["id"]
    if socket_id in identifiers:
        raise AdaptationValidationError(f"Duplicate socket ID: {socket_id}")
    identifiers.add(socket_id)


def _validate_observed_opening(socket: dict[str, Any]) -> None:
    if socket["status"] != "source_observation_only":
        raise AdaptationValidationError(
            "Observed openings must remain source_observation_only"
        )
    if socket.get("tested_connection_ref") or socket.get("compatibility_type"):
        raise AdaptationValidationError(
            "Observed source openings cannot declare a gameplay connector"
        )


def _validate_authored_boundary_socket(
    socket: dict[str, Any],
    polygon: list[tuple[float, float]],
    floor_y: float,
    room_clearance: tuple[float, float],
    capsule_radius: float,
    capsule_height: float,
) -> None:
    if socket["status"] == "source_observation_only":
        raise AdaptationValidationError(
            "Authored sockets cannot be source-only openings"
        )
    center, normal = _socket_frame(socket)
    width, height = _socket_size(socket, capsule_radius, capsule_height)
    tangent = _validate_boundary_edge(center, normal, width, polygon, socket["id"])
    _validate_socket_height(socket, center, floor_y, height, room_clearance)
    _validate_approach_region(
        socket, center, normal, tangent, width, polygon, capsule_radius
    )
    _validate_tested_reference(socket)


def _socket_frame(
    socket: dict[str, Any],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    center = _vector(
        socket.get("local_floor_center_xyz"), 3, f"socket {socket['id']} center"
    )
    normal = _vector(
        socket.get("outward_normal_xyz"), 3, f"socket {socket['id']} normal"
    )
    if (
        abs(normal[1]) > TOLERANCE
        or abs(math.hypot(normal[0], normal[2]) - 1.0) > TOLERANCE
    ):
        raise AdaptationValidationError(
            f"Socket {socket['id']} needs a normalized horizontal normal"
        )
    return tuple(center), tuple(normal)


def _socket_size(
    socket: dict[str, Any], capsule_radius: float, capsule_height: float
) -> tuple[float, float]:
    width, height = _vector(
        socket.get("clear_size"), 2, f"socket {socket['id']} clear size"
    )
    if width < 2 * capsule_radius or height < capsule_height:
        raise AdaptationValidationError(
            f"Socket {socket['id']} is smaller than the player capsule"
        )
    return width, height


def _validate_boundary_edge(
    center: tuple[float, float, float],
    normal: tuple[float, float, float],
    width: float,
    polygon: list[tuple[float, float]],
    socket_id: str,
) -> tuple[float, float]:
    candidates = _boundary_edge_candidates(center, polygon)
    if len(candidates) != 1:
        raise AdaptationValidationError(
            f"Socket {socket_id} must lie on exactly one supported perimeter edge"
        )
    start, end, outward, tangent = candidates[0]
    if math.hypot(normal[0] - outward[0], normal[2] - outward[1]) > TOLERANCE:
        raise AdaptationValidationError(
            f"Socket {socket_id} normal does not point outward"
        )
    _validate_opening_fit(center, width, start, end, tangent, socket_id)
    return tangent


def _boundary_edge_candidates(
    center: tuple[float, float, float], polygon: list[tuple[float, float]]
) -> list[
    tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]
]:
    candidates = []
    orientation = 1.0 if signed_area(polygon) > 0 else -1.0
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        tangent = _unit_vector(start, end)
        if not _point_on_edge((center[0], center[2]), start, end):
            continue
        outward = (orientation * tangent[1], -orientation * tangent[0])
        candidates.append((start, end, outward, tangent))
    return candidates


def _validate_opening_fit(
    center: tuple[float, float, float],
    width: float,
    start: tuple[float, float],
    end: tuple[float, float],
    tangent: tuple[float, float],
    socket_id: str,
) -> None:
    center_axis = center[0] * tangent[0] + center[2] * tangent[1]
    edge_axis = [
        point[0] * tangent[0] + point[1] * tangent[1] for point in (start, end)
    ]
    lower, upper = min(edge_axis), max(edge_axis)
    if (
        center_axis - width / 2 <= lower + TOLERANCE
        or center_axis + width / 2 >= upper - TOLERANCE
    ):
        raise AdaptationValidationError(
            f"Socket {socket_id} opening crosses or touches a perimeter corner"
        )


def _validate_socket_height(
    socket: dict[str, Any],
    center: tuple[float, float, float],
    floor_y: float,
    opening_height: float,
    room_clearance: tuple[float, float],
) -> None:
    socket_floor = _finite(
        socket.get("floor_elevation"), f"socket {socket['id']} floor"
    )
    room_floor, ceiling = room_clearance
    if (
        abs(center[1] - floor_y) > TOLERANCE
        or abs(socket_floor - room_floor) > TOLERANCE
    ):
        raise AdaptationValidationError(
            f"Socket {socket['id']} floor differs from room floor"
        )
    if center[1] + opening_height > ceiling + TOLERANCE:
        raise AdaptationValidationError(
            f"Socket {socket['id']} height exceeds declared room clearance"
        )


def _validate_approach_region(
    socket: dict[str, Any],
    center: tuple[float, float, float],
    normal: tuple[float, float, float],
    tangent: tuple[float, float],
    width: float,
    polygon: list[tuple[float, float]],
    capsule_radius: float,
) -> None:
    region = socket.get("approach_region_xz")
    if not isinstance(region, dict):
        raise AdaptationValidationError(
            f"Socket {socket['id']} needs an explicit approach region"
        )
    points = validate_orthogonal_polygon(
        region.get("vertices_xz"), f"Socket {socket['id']} approach region"
    )
    ensure_polygon_inside(points, polygon, f"Socket {socket['id']} approach region")
    separation = minimum_boundary_separation(points, polygon)
    if separation + TOLERANCE < capsule_radius:
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach lacks full capsule clearance"
        )
    _validate_approach_orientation(
        socket, points, center, normal, tangent, width, capsule_radius
    )


def _validate_approach_orientation(
    socket: dict[str, Any],
    points: list[tuple[float, float]],
    center: tuple[float, float, float],
    normal: tuple[float, float, float],
    tangent: tuple[float, float],
    width: float,
    capsule_radius: float,
) -> None:
    depths = [
        -(point[0] - center[0]) * normal[0] - (point[1] - center[2]) * normal[2]
        for point in points
    ]
    if min(depths) < -TOLERANCE:
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach extends outside the room"
        )
    if min(depths) > capsule_radius + TOLERANCE:
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach region does not reach its capsule-clearance band"
        )
    declared_depth = _positive(
        socket.get("approach_clearance"), f"Socket {socket['id']} approach clearance"
    )
    if max(depths) + TOLERANCE < declared_depth:
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach region is shorter than declared"
        )
    offsets = [
        point[0] * tangent[0]
        + point[1] * tangent[1]
        - (center[0] * tangent[0] + center[2] * tangent[1])
        for point in points
    ]
    usable_half_width = width / 2 - capsule_radius
    if (
        min(offsets) > -usable_half_width + TOLERANCE
        or max(offsets) < usable_half_width - TOLERANCE
    ):
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach does not cover the opening"
        )


def _validate_tested_reference(socket: dict[str, Any]) -> None:
    if socket["status"] == "tested_connector" and not socket.get(
        "tested_connection_ref"
    ):
        raise AdaptationValidationError(
            f"Tested socket {socket['id']} is missing traversal evidence"
        )


def _validate_legacy_authored_socket(
    socket: dict[str, Any],
    polygon: list[tuple[float, float]],
    floor_y: float,
    capsule_radius: float,
    capsule_height: float,
) -> None:
    center, normal = _socket_frame(socket)
    width, height = _vector(
        socket["clear_size"], 2, f"socket {socket['id']} clear size"
    )
    if width < 2 * capsule_radius or height < capsule_height:
        raise AdaptationValidationError(
            f"Socket {socket['id']} is smaller than the player capsule"
        )
    if abs(center[1] - floor_y) > TOLERANCE:
        raise AdaptationValidationError(
            f"Socket {socket['id']} floor differs from room floor"
        )
    approach = _positive(
        socket["approach_clearance"], f"socket {socket['id']} approach clearance"
    )
    point = (center[0] - normal[0] * approach, center[2] - normal[2] * approach)
    if (
        point_location(point, polygon) != "inside"
        or distance_to_boundary(point, polygon) + TOLERANCE < capsule_radius
    ):
        raise AdaptationValidationError(
            f"Socket {socket['id']} legacy approach is invalid"
        )


def _point_on_edge(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> bool:
    dx, dz = end[0] - start[0], end[1] - start[1]
    cross = dx * (point[1] - start[1]) - dz * (point[0] - start[0])
    dot = (point[0] - start[0]) * dx + (point[1] - start[1]) * dz
    return (
        abs(cross) <= TOLERANCE and -TOLERANCE <= dot <= dx * dx + dz * dz + TOLERANCE
    )


def _unit_vector(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    return (end[0] - start[0]) / length, (end[1] - start[1]) / length


def _vector(value: object, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise AdaptationValidationError(f"{label} must contain {length} numeric values")
    return [_finite(item, label) for item in value]


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise AdaptationValidationError(f"{label} must be positive")
    return number


def _finite(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise AdaptationValidationError(f"{label} must be finite")
    return float(value)
