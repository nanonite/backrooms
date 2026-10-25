"""Build the fixed, auditable three-room #164 connector layout."""

from __future__ import annotations

import hashlib
from typing import Any

from issue149_layout_core import (
    _module_map,
    _validate_connections,
    _validate_footprints,
    _validate_layout_bounds,
    canonical_json,
)
from issue164_layout_geometry import build_walk_route_xz, measure_walk_envelope

COLUMN_ID = "godot_later_bay_column_bounded_v1"
POCKET_ID = "godot_early_pocket_pass_through_v1"
LARGE_ROOM_ID = "godot_source_textured_large_room_hall_end_v1"
LAYOUT_ID = "issue164_three_room_chain_seed_164"
FLOOR_Y = -1.27099049


def build_layout(
    snapshot: dict[str, Any], catalog_hash: str, snapshot_path: str
) -> dict[str, Any]:
    modules = {item["id"]: item for item in snapshot["modules"]}
    placements = [
        _placement("R000", modules[COLUMN_ID], [0.0, 0.0, 0.0], 0),
        _placement("R001", modules[POCKET_ID], [3.5, 0.0, -3.8], 0),
        _placement("R002", modules[LARGE_ROOM_ID], [22.56, 0.0, 3.1], 180),
    ]
    connections = [
        _connection("R000", "east", "R001", "west"),
        _connection("R001", "east", "R002", "hall_end"),
    ]
    placements[0]["connected_sockets"]["east"] = "R001/west"
    placements[1]["connected_sockets"].update(
        {
            "west": "R000/east",
            "east": "R002/hall_end",
        }
    )
    placements[2]["connected_sockets"]["hall_end"] = "R001/east"
    layout = {
        "schema_version": 1,
        "layout_id": LAYOUT_ID,
        "generator_version": "0.1.0",
        "catalog_id": snapshot["catalog_id"],
        "catalog_version": snapshot["catalog_version"],
        "catalog_sha256": catalog_hash,
        "catalog_snapshot_path": snapshot_path,
        "seed": 164,
        "settings": {
            "placement_count": 3,
            "branch_required": False,
            "loops": False,
            "layout_bounds_m": [-4.4, -3.8, 28.56, 10.0],
        },
        "registration_accepted": False,
        "scale_calibrated": False,
        "mechanical_status": "candidate_validation_pending",
        "operator_status": "review_pending",
        "topology": {
            "type": "three_distinct_design_chain",
            "edge_count": 2,
            "cycle_rank": 0,
            "dead_end_count": 2,
        },
        "module_counts": {COLUMN_ID: 1, POCKET_ID: 1, LARGE_ROOM_ID: 1},
        "unique_module_designs": 3,
        "repeated_instances": 0,
        "spawn": {"instance_id": "R000", "local_position": [-3.5, FLOOR_Y + 0.6, 0.0]},
        "walk_route_xz": build_walk_route_xz(),
        "placements": placements,
        "connections": connections,
        "supported_constraints": [
            "connected_three_room_chain",
            "closed_unused_openings",
            "safe_spawn_and_reset",
            "bidirectional_backtracking",
        ],
        "unsupported_constraints": [
            "source-video-proven room connectivity",
            "metric-scale calibration",
            "unbounded streaming",
        ],
    }
    errors = validate_chain_layout(layout, snapshot)
    if errors:
        raise ValueError("Issue #164 layout failed validation: " + "; ".join(errors))
    layout["walk_envelope"] = measure_walk_envelope(layout, snapshot)
    layout["layout_sha256"] = hashlib.sha256(canonical_json(layout)).hexdigest()
    return layout


def validate_chain_layout(
    layout: dict[str, Any], snapshot: dict[str, Any]
) -> list[str]:
    placements = {item["instance_id"]: item for item in layout.get("placements", [])}
    modules = _module_map(snapshot)
    errors = []
    if len(placements) != 3 or layout.get("settings", {}).get("placement_count") != 3:
        errors.append("Issue #164 requires exactly three room placements")
    if layout.get("registration_accepted") or layout.get("scale_calibrated"):
        errors.append("Registration and scale calibration must remain false")
    if layout.get("settings", {}).get("loops"):
        errors.append("Issue #164 chain layout must not contain a loop")
    if any(item.get("module_id") not in modules for item in placements.values()):
        return errors + ["Layout references an unknown catalog module"]
    errors.extend(_validate_connections(layout, placements, modules))
    errors.extend(_validate_footprints(placements, modules))
    errors.extend(_validate_layout_bounds(layout, placements, modules))
    errors.extend(_validate_chain_graph(layout, placements))
    return errors


def _validate_chain_graph(
    layout: dict[str, Any], placements: dict[str, dict[str, Any]]
) -> list[str]:
    adjacency = {instance_id: set() for instance_id in placements}
    for edge in layout.get("connections", []):
        left = edge["from"]["instance_id"]
        right = edge["to"]["instance_id"]
        if left not in adjacency or right not in adjacency:
            return ["Connection references an unknown room instance"]
        adjacency[left].add(right)
        adjacency[right].add(left)
    degrees = sorted(len(neighbors) for neighbors in adjacency.values())
    if degrees != [1, 1, 2] or len(layout.get("connections", [])) != 2:
        return ["Three modules must form a simple two-edge chain"]
    reached = set()
    pending = [next(iter(adjacency))]
    while pending:
        current = pending.pop()
        if current not in reached:
            reached.add(current)
            pending.extend(adjacency[current] - reached)
    if len(reached) != 3:
        return ["Three-room chain is disconnected"]
    return []


def _placement(
    instance_id: str, module: dict[str, Any], position: list[float], yaw: int
) -> dict[str, Any]:
    scene_path = "godot_walk/" + module["scene"].removeprefix("res://")
    scene_hash = next(
        (
            item["sha256"]
            for item in module["dependency_hashes"]
            if item["path"] == scene_path
        ),
        "",
    )
    if not scene_hash:
        raise ValueError(f"Catalog has no dependency hash for {module['scene']}")
    return {
        "instance_id": instance_id,
        "module_id": module["id"],
        "module_version": module["version"],
        "scene": module["scene"],
        "scene_sha256": scene_hash,
        "operator_status": module["variant_status"],
        "transform": {"position": position, "yaw_degrees": yaw},
        "open_sockets": [socket["id"] for socket in module["sockets"]],
        "connected_sockets": {},
    }


def _connection(
    left_id: str, left_socket: str, right_id: str, right_socket: str
) -> dict[str, Any]:
    return {
        "id": f"{left_id}.{left_socket}__{right_id}.{right_socket}",
        "from": {"instance_id": left_id, "socket_id": left_socket},
        "to": {"instance_id": right_id, "socket_id": right_socket},
        "compatibility_type": "level_doorway_2m_v1",
        "mechanical_status": "provisional_layout_candidate",
        "operator_status": "review_pending",
    }


