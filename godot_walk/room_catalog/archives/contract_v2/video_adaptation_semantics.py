"""Static geometry and scene-manifest consistency checks for adaptations."""

from __future__ import annotations

import math
from typing import Any

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_polygon import (
    distance_to_boundary,
    point_location,
    validate_orthogonal_polygon,
)

TOLERANCE = 1e-6


def validate_static_spatial_contract(record: dict[str, Any]) -> None:
    walkable_polygon, render_polygon, floor_y, minimum, maximum = (
        _read_spatial_declarations(record["resolved_adaptation"])
    )
    _validate_render_bounds(minimum, maximum, render_polygon, walkable_polygon, floor_y)
    _validate_collision_declarations(
        record["resolved_adaptation"]["boundary_and_obstacle_collision"]
    )
    _validate_spawn(record, walkable_polygon, floor_y, maximum[1])
    _validate_record_sockets(record, walkable_polygon, floor_y)


def _read_spatial_declarations(
    resolved: dict[str, Any],
) -> tuple[
    list[tuple[float, float]],
    list[tuple[float, float]],
    float,
    list[float],
    list[float],
]:
    walkable = resolved["walkable_space"]
    walkable_polygon = validate_orthogonal_polygon(
        walkable["footprint"]["vertices_xz"], "Walkable footprint"
    )
    envelope = resolved["rendered_placement_envelope"]
    render_polygon = validate_orthogonal_polygon(
        envelope["footprint"]["vertices_xz"], "Render envelope footprint"
    )
    floor_y = _finite_number(walkable["floor_elevation"], "floor elevation")
    bounds = envelope["bounds_xyz"]
    minimum = _vector(bounds["min"], 3, "render bounds minimum")
    maximum = _vector(bounds["max"], 3, "render bounds maximum")
    return walkable_polygon, render_polygon, floor_y, minimum, maximum


def _validate_render_bounds(
    minimum: list[float],
    maximum: list[float],
    render_polygon: list[tuple[float, float]],
    walkable_polygon: list[tuple[float, float]],
    floor_y: float,
) -> None:
    if any(low >= high for low, high in zip(minimum, maximum)):
        raise AdaptationValidationError("Render bounds are inverted or degenerate")
    _validate_bounds_enclose_polygon(minimum, maximum, render_polygon)
    _validate_bounds_enclose_polygon(minimum, maximum, walkable_polygon)
    if not minimum[1] <= floor_y <= maximum[1]:
        raise AdaptationValidationError(
            "Render bounds do not include the walkable floor elevation"
        )


def _validate_record_sockets(
    record: dict[str, Any], polygon: list[tuple[float, float]], floor_y: float
) -> None:
    player = record["reusable_requirements"]["player"]
    _validate_sockets(
        record["resolved_adaptation"].get("sockets", []),
        polygon,
        floor_y,
        _positive_number(player["capsule_radius"], "capsule radius"),
        _positive_number(player["capsule_height"], "capsule height"),
    )


def _validate_collision_declarations(collision: dict[str, Any]) -> None:
    for field in ("floor_bodies", "boundaries", "obstacles"):
        names = collision[field]
        if not isinstance(names, list) or any(
            not isinstance(name, str) or not name for name in names
        ):
            raise AdaptationValidationError(
                f"Collision {field} must contain nonempty node paths"
            )
        if len(names) != len(set(names)):
            raise AdaptationValidationError(
                f"Collision {field} contains duplicate node paths"
            )
        if field != "obstacles" and not names:
            raise AdaptationValidationError(
                f"Collision contract requires at least one {field[:-1]}"
            )


def _validate_spawn(
    record: dict[str, Any],
    polygon: list[tuple[float, float]],
    floor_y: float,
    render_ceiling: float,
) -> None:
    walkable = record["resolved_adaptation"]["walkable_space"]
    spawn = _vector(walkable["safe_spawn_xyz"], 3, "safe spawn")
    player = record["reusable_requirements"]["player"]
    radius = _positive_number(player["capsule_radius"], "capsule radius")
    height = _positive_number(player["capsule_height"], "capsule height")
    _validate_spawn_footprint(spawn, polygon, radius)
    _validate_spawn_height(spawn[1], floor_y, render_ceiling, height)


def _validate_spawn_footprint(
    spawn: list[float], polygon: list[tuple[float, float]], radius: float
) -> None:
    location = point_location((spawn[0], spawn[2]), polygon)
    if (
        location != "inside"
        or distance_to_boundary((spawn[0], spawn[2]), polygon) + TOLERANCE < radius
    ):
        raise AdaptationValidationError(
            "Safe spawn is outside the walkable polygon or capsule margin"
        )


def _validate_spawn_height(
    spawn_y: float, floor_y: float, render_ceiling: float, height: float
) -> None:
    if abs(spawn_y - floor_y - height / 2.0) > 1e-4:
        raise AdaptationValidationError(
            "Safe spawn height does not match the capsule standing on the floor"
        )
    if spawn_y + height / 2.0 > render_ceiling + TOLERANCE:
        raise AdaptationValidationError(
            "Safe spawn capsule exceeds the declared render envelope height"
        )


def _validate_sockets(
    sockets: list[dict[str, Any]],
    polygon: list[tuple[float, float]],
    floor_y: float,
    capsule_radius: float,
    capsule_height: float,
) -> None:
    identifiers: set[str] = set()
    for socket in sockets:
        socket_id = socket["id"]
        if socket_id in identifiers:
            raise AdaptationValidationError(f"Duplicate socket ID: {socket_id}")
        identifiers.add(socket_id)
        if socket["kind"] == "observed_opening":
            _validate_observed_opening(socket)
            continue
        _validate_authored_socket(
            socket, polygon, floor_y, capsule_radius, capsule_height
        )


def _validate_observed_opening(socket: dict[str, Any]) -> None:
    if socket["status"] != "source_observation_only":
        raise AdaptationValidationError(
            "Observed openings must remain source_observation_only"
        )


def _validate_authored_socket(
    socket: dict[str, Any],
    polygon: list[tuple[float, float]],
    floor_y: float,
    capsule_radius: float,
    capsule_height: float,
) -> None:
    socket_id = socket["id"]
    if socket["status"] == "source_observation_only":
        raise AdaptationValidationError(
            "Authored sockets cannot use source_observation_only status"
        )
    center, normal = _socket_frame(socket)
    _validate_socket_clearance(socket, capsule_radius, capsule_height)
    _validate_socket_floor(socket, center, floor_y)
    _validate_socket_approach(socket, center, normal, polygon, capsule_radius)
    if socket["status"] == "tested_connector" and not socket.get(
        "tested_connection_ref"
    ):
        raise AdaptationValidationError(
            f"Tested socket {socket_id} is missing its traversal evidence reference"
        )


def _socket_frame(socket: dict[str, Any]) -> tuple[list[float], list[float]]:
    socket_id = socket["id"]
    center = _vector(socket["local_floor_center_xyz"], 3, f"socket {socket_id} center")
    normal = _vector(socket["outward_normal_xyz"], 3, f"socket {socket_id} normal")
    if (
        abs(normal[1]) > TOLERANCE
        or abs(math.hypot(normal[0], normal[2]) - 1.0) > TOLERANCE
    ):
        raise AdaptationValidationError(
            f"Socket {socket_id} needs a normalized horizontal outward normal"
        )
    return center, normal


def _validate_socket_clearance(
    socket: dict[str, Any], capsule_radius: float, capsule_height: float
) -> None:
    socket_id = socket["id"]
    width, height = _vector(socket["clear_size"], 2, f"socket {socket_id} clear size")
    _positive_number(width, f"socket {socket_id} clear width")
    _positive_number(height, f"socket {socket_id} clear height")
    if width < 2 * capsule_radius or height < capsule_height:
        raise AdaptationValidationError(
            f"Socket {socket_id} is smaller than the declared player capsule"
        )


def _validate_socket_floor(
    socket: dict[str, Any], center: list[float], floor_y: float
) -> None:
    socket_floor = _finite_number(
        socket.get("floor_elevation", socket.get("floor_elevation_m", center[1])),
        f"socket {socket['id']} floor elevation",
    )
    if abs(center[1] - floor_y) > TOLERANCE or abs(socket_floor - floor_y) > TOLERANCE:
        raise AdaptationValidationError(
            f"Socket {socket['id']} floor elevation differs from the room floor"
        )


def _validate_socket_approach(
    socket: dict[str, Any],
    center: list[float],
    normal: list[float],
    polygon: list[tuple[float, float]],
    capsule_radius: float,
) -> None:
    approach = _positive_number(
        socket["approach_clearance"], f"socket {socket['id']} approach clearance"
    )
    point = (center[0] - normal[0] * approach, center[2] - normal[2] * approach)
    if point_location(point, polygon) != "inside":
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach is outside the supported footprint"
        )
    if distance_to_boundary(point, polygon) + TOLERANCE < capsule_radius:
        raise AdaptationValidationError(
            f"Socket {socket['id']} approach lacks capsule clearance"
        )


def _validate_bounds_enclose_polygon(
    minimum: list[float], maximum: list[float], polygon: list[tuple[float, float]]
) -> None:
    for x, z in polygon:
        if x < minimum[0] - TOLERANCE or x > maximum[0] + TOLERANCE:
            raise AdaptationValidationError(
                "Render bounds do not enclose a declared X extent"
            )
        if z < minimum[2] - TOLERANCE or z > maximum[2] + TOLERANCE:
            raise AdaptationValidationError(
                "Render bounds do not enclose a declared Z extent"
            )


def _vector(value: object, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise AdaptationValidationError(f"{label} must contain {length} numeric values")
    return [_finite_number(item, label) for item in value]


def _positive_number(value: object, label: str) -> float:
    number = _finite_number(value, label)
    if number <= 0:
        raise AdaptationValidationError(f"{label} must be positive")
    return number


def _finite_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise AdaptationValidationError(f"{label} must be a finite number")
    return float(value)
