"""Deterministic finite layouts for the Godot room kit."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "godot_walk/room_catalog/catalog.json"
MIN_PLACEMENTS = 10
MAX_PLACEMENTS = 20
FLOOR_TOLERANCE = 1e-5
POSITION_TOLERANCE = 1e-4
NORMAL_TOLERANCE = 0.999


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_catalog_snapshot(catalog_path: Path = CATALOG_PATH) -> tuple[dict[str, Any], str, bytes]:
    config = json.loads(catalog_path.read_text())
    _validate_catalog_config(config)
    paths = _catalog_paths(config)
    file_hashes = []
    for relative in sorted(paths):
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"Catalog dependency is missing: {relative}")
        file_hashes.append({"path": relative, "sha256": _sha256(path)})
    snapshot = copy.deepcopy(config)
    snapshot["source_catalog"] = str(catalog_path.relative_to(ROOT))
    snapshot["source_catalog_sha256"] = _sha256(catalog_path)
    snapshot["file_hashes"] = file_hashes
    hash_by_path = {item["path"]: item["sha256"] for item in file_hashes}
    runtime_paths = set(config["psx_profile"]["shaders"])
    runtime_paths.update([config["psx_profile"]["preset_script"], config["psx_profile"]["controller_scene"], config["psx_profile"]["controller_script"]])
    for module in snapshot["modules"]:
        module["dependency_hashes"] = [
            {"path": path, "sha256": hash_by_path[path]}
            for path in sorted(set(module["dependencies"]))
        ]
        runtime_paths.update(module["dependencies"])
    runtime_paths.update(
        path for path in config["generation_dependencies"]
        if path.endswith((".gd", ".tscn"))
    )
    snapshot["runtime_dependencies"] = [
        {"path": path, "sha256": hash_by_path[path]} for path in sorted(runtime_paths)
    ]
    raw = canonical_json(snapshot)
    return snapshot, hashlib.sha256(raw).hexdigest(), raw


def _catalog_paths(config: dict[str, Any]) -> set[str]:
    paths = {config["psx_profile"]["preset_script"], *config["psx_profile"]["shaders"]}
    paths.update([config["psx_profile"]["controller_scene"], config["psx_profile"]["controller_script"]])
    for module in config["modules"]:
        paths.update(module["dependencies"])
        paths.update(module["source_provenance"])
        paths.update(module["visual_assets"])
    for pair in config["tested_connector_pairs"]:
        paths.update(pair["evidence"])
    paths.update(config["generation_dependencies"])
    return paths


def _validate_catalog_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != 1 or config.get("engine") != "Godot 4.6.3":
        raise ValueError("Room catalog schema or Godot engine version is unsupported")
    if config.get("registration_accepted") or config.get("scale_calibrated"):
        raise ValueError("Unaccepted registration and scale flags must remain false")
    modules = config.get("modules")
    if not isinstance(modules, list) or len(modules) < 4:
        raise ValueError("Catalog must contain the accepted pair and two topology variants")
    ids = [module.get("id") for module in modules]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("Catalog module IDs must be unique and non-empty")
    for module in modules:
        _validate_module(module)


def _validate_module(module: dict[str, Any]) -> None:
    if not module.get("scene", "").startswith("res://scenes/"):
        raise ValueError(f"Module {module.get('id')} has an invalid scene path")
    socket_ids = [socket.get("id") for socket in module.get("sockets", [])]
    if len(socket_ids) != len(set(socket_ids)) or not socket_ids:
        raise ValueError(f"Module {module.get('id')} must declare unique sockets")
    if len(module.get("placement_footprint_xz", [])) < 3:
        raise ValueError(f"Module {module.get('id')} has no polygon footprint")
    if module.get("floor_elevation_m") is None or module.get("ceiling_elevation_m") is None:
        raise ValueError(f"Module {module.get('id')} has incomplete vertical bounds")
    for socket in module["sockets"]:
        if socket["compatibility_type"] != "level_doorway_2m_v1":
            raise ValueError(f"Unsupported socket type in module {module['id']}")
        if socket["clear_size_m"] != [2.0, 2.1]:
            raise ValueError(f"Unsupported opening size in module {module['id']}")


def _module_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {module["id"]: module for module in snapshot["modules"]}


def _socket(module: dict[str, Any], socket_id: str) -> dict[str, Any]:
    for socket in module["sockets"]:
        if socket["id"] == socket_id:
            return socket
    raise ValueError(f"Module {module['id']} has no socket '{socket_id}'")


def _rotate_xz(point: list[float], yaw: int) -> list[float]:
    x, z = point
    rotation = yaw % 360
    if rotation == 0:
        return [x, z]
    if rotation == 90:
        return [z, -x]
    if rotation == 180:
        return [-x, -z]
    if rotation == 270:
        return [-z, x]
    raise ValueError("Only 90-degree rotations are supported")


def _world_socket(placement: dict[str, Any], socket: dict[str, Any]) -> tuple[list[float], list[float]]:
    position = placement["transform"]["position"]
    yaw = placement["transform"]["yaw_degrees"]
    local = socket["local_floor_center"]
    rotated = _rotate_xz([local[0], local[2]], yaw)
    normal = _rotate_xz([socket["outward_normal"][0], socket["outward_normal"][2]], yaw)
    return [position[0] + rotated[0], local[1] + position[1], position[2] + rotated[1]], [normal[0], socket["outward_normal"][1], normal[1]]


def _new_placement(instance_id: str, module: dict[str, Any], position: list[float], yaw: int) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "module_id": module["id"],
        "module_version": module["version"],
        "scene": module["scene"],
        "scene_sha256": _dependency_hash(module, "godot_walk/" + module["scene"].removeprefix("res://")),
        "operator_status": module["variant_status"],
        "transform": {"position": [round(value, 6) for value in position], "yaw_degrees": yaw},
        "open_sockets": [socket["id"] for socket in module["sockets"]],
        "connected_sockets": {},
    }


def _dependency_hash(module: dict[str, Any], relative_path: str) -> str:
    # Scene and all imported source paths are also present in the snapshot file manifest.
    snapshot_hashes = module.get("dependency_hashes", [])
    for item in snapshot_hashes:
        if item["path"] == relative_path:
            return item["sha256"]
    return ""


def _place_to_socket(
    source_placement: dict[str, Any], source_module: dict[str, Any], source_socket_id: str,
    target_module: dict[str, Any], target_socket_id: str, yaw: int,
) -> list[float]:
    source_socket = _socket(source_module, source_socket_id)
    target_socket = _socket(target_module, target_socket_id)
    source_world, source_normal = _world_socket(source_placement, source_socket)
    target_position = target_socket["local_floor_center"]
    rotated = _rotate_xz([target_position[0], target_position[2]], yaw)
    target_normal = _rotate_xz([target_socket["outward_normal"][0], target_socket["outward_normal"][2]], yaw)
    if abs(source_world[1] - target_position[1]) > FLOOR_TOLERANCE:
        raise ValueError("Connector modules have different floor elevations")
    target_normal_3d = [target_normal[0], 0.0, target_normal[1]]
    if sum(source_normal[index] * target_normal_3d[index] for index in range(3)) >= -NORMAL_TOLERANCE:
        raise ValueError("Connector socket normals do not oppose")
    if source_socket["compatibility_type"] != target_socket["compatibility_type"]:
        raise ValueError("Connector socket compatibility types differ")
    if source_socket["clear_size_m"] != target_socket["clear_size_m"]:
        raise ValueError("Connector opening dimensions differ")
    return [round(source_world[0] - rotated[0], 6), 0.0, round(source_world[2] - rotated[1], 6)]


def _connect(
    placements: list[dict[str, Any]], modules: dict[str, dict[str, Any]],
    source_id: str, source_socket: str, target_id: str, target_socket: str,
) -> dict[str, Any]:
    source = next(item for item in placements if item["instance_id"] == source_id)
    target = next(item for item in placements if item["instance_id"] == target_id)
    source_def = modules[source["module_id"]]
    target_def = modules[target["module_id"]]
    source["connected_sockets"][source_socket] = f"{target_id}/{target_socket}"
    target["connected_sockets"][target_socket] = f"{source_id}/{source_socket}"
    return {
        "id": f"{source_id}.{source_socket}__{target_id}.{target_socket}",
        "from": {"instance_id": source_id, "socket_id": source_socket},
        "to": {"instance_id": target_id, "socket_id": target_socket},
        "compatibility_type": _socket(source_def, source_socket)["compatibility_type"],
        "mechanical_status": "provisional_layout_candidate",
        "operator_status": "review_pending",
    }


def _seed_choice(seed: int) -> int:
    value = hashlib.sha256(f"issue149:{seed}".encode()).digest()
    return int.from_bytes(value[:8], "big")


def generate_layout(seed: int, placement_count: int, snapshot: dict[str, Any], catalog_hash: str,
                    bounded_streaming: bool = False) -> dict[str, Any]:
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError("Seed must be an integer from 0 through 4294967295")
    if placement_count < MIN_PLACEMENTS or placement_count > MAX_PLACEMENTS:
        raise ValueError(f"Placement count must be between {MIN_PLACEMENTS} and {MAX_PLACEMENTS}")
    modules = _module_map(snapshot)
    root = _new_placement("R000", modules["godot_later_bay_column_bounded_v1"], [0.0, 0.0, 0.0], 0)
    placements = [root]
    connections = []
    trunk_count = placement_count - 4
    before_count = 1 + _seed_choice(seed) % (trunk_count - 1)
    branch_yaw = 0 if _seed_choice(seed + 1) % 2 == 0 else 180
    previous = root
    previous_def = modules[root["module_id"]]
    for index in range(before_count):
        previous, previous_def, edge = _append_pass_through(placements, modules, previous, previous_def, index)
        connections.append(edge)
    branch, branch_def, edge, branch_output = _append_branch(
        placements, modules, previous, previous_def, branch_yaw
    )
    connections.append(edge)
    _, side_edge = _append_side_leaf(placements, modules, branch, branch_def, branch_yaw)
    connections.append(side_edge)
    previous, previous_def = branch, branch_def
    next_source_socket = branch_output
    for index in range(placement_count - 4 - before_count):
        previous, previous_def, edge = _append_pass_through(placements, modules, previous, previous_def, before_count + index, next_source_socket)
        connections.append(edge)
        next_source_socket = "east"
    terminal, edge = _append_terminal(placements, modules, previous, previous_def, next_source_socket)
    connections.append(edge)
    if len(placements) != placement_count:
        raise ValueError("Generator produced a placement count mismatch")
    layout = _layout_record(seed, placement_count, catalog_hash, branch_yaw, placements, connections, before_count)
    if bounded_streaming:
        layout["settings"]["streaming"] = {
            "mode": "bounded_graph_window",
            "graph_radius": 1,
            "max_resident_modules": 4,
            "retain_backtracking": True,
        }
    layout["walk_envelope"] = _layout_bounds(placements, modules)
    errors = validate_layout(layout, snapshot)
    if errors:
        raise ValueError("Generated layout failed validation: " + "; ".join(errors))
    payload = canonical_json(layout)
    layout["layout_sha256"] = hashlib.sha256(payload).hexdigest()
    return layout


def _append_pass_through(placements: list[dict[str, Any]], modules: dict[str, dict[str, Any]], source: dict[str, Any], source_def: dict[str, Any], index: int, source_socket: str = "east") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    module = modules["godot_early_pocket_pass_through_v1"]
    instance_id = f"R{len(placements):03d}"
    position = _place_to_socket(source, source_def, source_socket, module, "west", 0)
    placement = _new_placement(instance_id, module, position, 0)
    placements.append(placement)
    edge = _connect(placements, modules, source["instance_id"], source_socket, instance_id, "west")
    return placement, module, edge


def _append_branch(placements: list[dict[str, Any]], modules: dict[str, dict[str, Any]], source: dict[str, Any], source_def: dict[str, Any], yaw: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    module = modules["godot_early_pocket_three_way_v1"]
    input_socket = "west" if yaw == 0 else "east"
    position = _place_to_socket(source, source_def, "east", module, input_socket, yaw)
    instance_id = f"R{len(placements):03d}"
    placement = _new_placement(instance_id, module, position, yaw)
    placements.append(placement)
    edge = _connect(placements, modules, source["instance_id"], "east", instance_id, input_socket)
    output_socket = "east" if yaw == 0 else "west"
    return placement, module, edge, output_socket


def _append_side_leaf(placements: list[dict[str, Any]], modules: dict[str, dict[str, Any]], branch: dict[str, Any], branch_def: dict[str, Any], branch_yaw: int) -> tuple[dict[str, Any], dict[str, Any]]:
    module = modules["godot_early_pocket_single_west_v1"]
    leaf_yaw = 270 if branch_yaw == 0 else 90
    position = _place_to_socket(branch, branch_def, "north", module, "west", leaf_yaw)
    instance_id = f"R{len(placements):03d}"
    placement = _new_placement(instance_id, module, position, leaf_yaw)
    placements.append(placement)
    edge = _connect(placements, modules, branch["instance_id"], "north", instance_id, "west")
    return placement, edge


def _append_terminal(placements: list[dict[str, Any]], modules: dict[str, dict[str, Any]], source: dict[str, Any], source_def: dict[str, Any], source_socket: str) -> tuple[dict[str, Any], dict[str, Any]]:
    module = modules["godot_early_pocket_single_west_v1"]
    position = _place_to_socket(source, source_def, source_socket, module, "west", 0)
    instance_id = f"R{len(placements):03d}"
    placement = _new_placement(instance_id, module, position, 0)
    placements.append(placement)
    return placement, _connect(placements, modules, source["instance_id"], source_socket, instance_id, "west")


def _layout_record(seed: int, count: int, catalog_hash: str, branch_yaw: int, placements: list[dict[str, Any]], connections: list[dict[str, Any]], before_count: int) -> dict[str, Any]:
    module_counts: dict[str, int] = {}
    for placement in placements:
        module_counts[placement["module_id"]] = module_counts.get(placement["module_id"], 0) + 1
    degrees = {item["instance_id"]: len(item["connected_sockets"]) for item in placements}
    route = _walk_route(placements)
    return {
        "schema_version": 1,
        "layout_id": f"issue149_seed_{seed:010d}_n{count:02d}",
        "generator_version": "0.1.0",
        "catalog_id": "godot_psx_room_kit",
        "catalog_version": "0.1.0",
        "catalog_sha256": catalog_hash,
        "catalog_snapshot_path": "res://evidence/2026-10-22-issue-149/catalog_snapshot.json",
        "seed": seed,
        "settings": {
            "placement_count": count,
            "branch_required": True,
            "loops": False,
            "layout_bounds_m": [-160.0, -30.0, 180.0, 35.0],
            "streaming": {
                "mode": "bounded_graph_window",
                "graph_radius": 1,
                "max_resident_modules": 4,
                "retain_backtracking": True,
            },
        },
        "registration_accepted": False,
        "scale_calibrated": False,
        "mechanical_status": "candidate_validation_pending",
        "operator_status": "review_pending",
        "topology": {
            "type": "connected_tree_with_one_three_way_branch",
            "branch_instance_id": next(item["instance_id"] for item in placements if item["module_id"] == "godot_early_pocket_three_way_v1"),
            "branch_yaw_degrees": branch_yaw,
            "branch_side": "north" if branch_yaw == 0 else "south",
            "pass_throughs_before_branch": before_count,
            "edge_count": len(connections),
            "cycle_rank": 0,
            "dead_end_count": sum(1 for degree in degrees.values() if degree == 1),
        },
        "module_counts": module_counts,
        "unique_module_designs": len(module_counts),
        "repeated_instances": sum(count - 1 for count in module_counts.values()),
        "spawn": {"instance_id": "R000", "local_position": [-3.5, -0.67099049, 0.0]},
        "walk_route_xz": route,
        "placements": placements,
        "connections": connections,
        "supported_constraints": ["connected", "one_three_way_branch", "two_terminal_branches", "closed_unused_sides", "no_cycles"],
        "unsupported_constraints": ["loops", "unbounded_streaming", "arbitrary_socket_types", "unreviewed_source_connectivity"],
    }


def _walk_route(placements: list[dict[str, Any]]) -> list[list[float]]:
    points = [[-3.5, 0.0], [-3.4, 2.6], [-1.8, 2.6], [2.4, 2.6], [2.4, 3.1], [3.3, 3.1]]
    main_rooms = [item for item in placements if item["module_id"] in {
        "godot_early_pocket_pass_through_v1", "godot_early_pocket_three_way_v1"
    }]
    branch = next(item for item in main_rooms if item["module_id"] == "godot_early_pocket_three_way_v1")
    leaves = [item for item in placements if item["module_id"] == "godot_early_pocket_single_west_v1"]
    side_leaf = leaves[0]
    for room in main_rooms:
        if room["instance_id"] == branch["instance_id"]:
            entry_x, exit_x = (0.8, 5.2) if room["transform"]["yaw_degrees"] == 0 else (5.2, 0.8)
            points.extend([_world_point(room, [entry_x, 6.9]), _world_point(room, [3.0, 6.9])])
            points.extend([
                _world_point(branch, [3.0, 12.0]),
                _world_point(side_leaf, [0.8, 6.9]),
                _world_point(side_leaf, [3.0, 6.9]),
                _world_point(branch, [3.0, 12.0]),
            ])
            points.append(_world_point(room, [exit_x, 6.9]))
        else:
            points.extend([_world_point(room, [0.8, 6.9]), _world_point(room, [5.2, 6.9])])
    terminal = leaves[-1]
    points.extend([_world_point(terminal, [0.8, 6.9]), _world_point(terminal, [3.0, 6.9])])
    forward = [[round(value, 6) for value in point] for point in points]
    return forward + list(reversed(forward[:-1]))


def _world_point(placement: dict[str, Any], local_xz: list[float]) -> list[float]:
    rotated = _rotate_xz(local_xz, placement["transform"]["yaw_degrees"])
    origin = placement["transform"]["position"]
    return [origin[0] + rotated[0], origin[2] + rotated[1]]


def _bounds(placement: dict[str, Any], module: dict[str, Any]) -> tuple[float, float, float, float]:
    points = [_rotate_xz(point, placement["transform"]["yaw_degrees"]) for point in module["placement_footprint_xz"]]
    x_origin, _, z_origin = placement["transform"]["position"]
    xs = [x_origin + point[0] for point in points]
    zs = [z_origin + point[1] for point in points]
    return min(xs), min(zs), max(xs), max(zs)


def _layout_bounds(placements: list[dict[str, Any]], modules: dict[str, dict[str, Any]]) -> list[float]:
    bounds = [_bounds(item, modules[item["module_id"]]) for item in placements]
    minimum_x = min(item[0] for item in bounds)
    minimum_z = min(item[1] for item in bounds)
    maximum_x = max(item[2] for item in bounds)
    maximum_z = max(item[3] for item in bounds)
    return [minimum_x, minimum_z, maximum_x - minimum_x, maximum_z - minimum_z]


def validate_layout(layout: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    modules = _module_map(snapshot)
    placements = {item["instance_id"]: item for item in layout.get("placements", [])}
    errors = []
    if len(placements) != layout.get("settings", {}).get("placement_count"):
        errors.append("placement count does not match settings")
    if layout.get("registration_accepted") or layout.get("scale_calibrated"):
        errors.append("calibration flags must remain false")
    if layout.get("settings", {}).get("loops"):
        errors.append("loops are unsupported by this kit")
    streaming = layout.get("settings", {}).get("streaming")
    if streaming is not None and streaming != {
        "mode": "bounded_graph_window",
        "graph_radius": 1,
        "max_resident_modules": 4,
        "retain_backtracking": True,
    }:
        errors.append("streaming must use the supported radius-one, four-module window")
    unknown_modules = [item["module_id"] for item in placements.values() if item.get("module_id") not in modules]
    if unknown_modules:
        errors.append("layout references unknown module(s): " + ", ".join(sorted(set(unknown_modules))))
        return errors
    errors.extend(_validate_connections(layout, placements, modules))
    errors.extend(_validate_footprints(placements, modules))
    errors.extend(_validate_layout_bounds(layout, placements, modules))
    errors.extend(_validate_graph(layout, placements))
    return errors


def _validate_layout_bounds(
    layout: dict[str, Any], placements: dict[str, dict[str, Any]], modules: dict[str, dict[str, Any]]
) -> list[str]:
    configured = layout.get("settings", {}).get("layout_bounds_m")
    if not isinstance(configured, list) or len(configured) != 4:
        return ["layout_bounds_m must contain min_x, min_z, max_x, max_z"]
    try:
        min_x, min_z, max_x, max_z = (float(value) for value in configured)
    except (TypeError, ValueError):
        return ["layout_bounds_m must contain finite numbers"]
    if not all(math.isfinite(value) for value in (min_x, min_z, max_x, max_z)) or min_x >= max_x or min_z >= max_z:
        return ["layout_bounds_m must define finite increasing extents"]
    actual = [_bounds(item, modules[item["module_id"]]) for item in placements.values()]
    if not actual:
        return ["layout has no placement footprint to bound"]
    actual_min_x = min(item[0] for item in actual)
    actual_min_z = min(item[1] for item in actual)
    actual_max_x = max(item[2] for item in actual)
    actual_max_z = max(item[3] for item in actual)
    if actual_min_x < min_x or actual_min_z < min_z or actual_max_x > max_x or actual_max_z > max_z:
        return ["placement footprints exceed layout_bounds_m"]
    return []


def _validate_connections(layout: dict[str, Any], placements: dict[str, dict[str, Any]], modules: dict[str, dict[str, Any]]) -> list[str]:
    errors = []
    used = set()
    for edge in layout.get("connections", []):
        source = edge["from"]
        target = edge["to"]
        source_key = (source["instance_id"], source["socket_id"])
        target_key = (target["instance_id"], target["socket_id"])
        if source_key in used or target_key in used:
            errors.append("a socket is connected more than once")
        used.update([source_key, target_key])
        if source["instance_id"] not in placements or target["instance_id"] not in placements:
            errors.append("connection references a missing room")
            continue
        if not _connection_matches(placements, modules, source, target):
            errors.append(f"socket transforms or compatibility mismatch on {edge['id']}")
    for placement in placements.values():
        module = modules.get(placement["module_id"])
        if module is None:
            errors.append(f"unknown module {placement['module_id']}")
            continue
        expected_open = {socket["id"] for socket in module["sockets"]}
        if set(placement["open_sockets"]) != expected_open:
            errors.append(f"open socket list differs from catalog for {placement['instance_id']}")
        expected_scene = next(
            (item["sha256"] for item in module["dependency_hashes"] if item["path"] == "godot_walk/" + module["scene"].removeprefix("res://")),
            "",
        )
        if placement["scene"] != module["scene"] or placement["scene_sha256"] != expected_scene:
            errors.append(f"scene hash or path differs from catalog for {placement['instance_id']}")
        for socket_id in placement["open_sockets"]:
            if (placement["instance_id"], socket_id) not in used:
                errors.append(f"unclosed open socket {placement['instance_id']}/{socket_id}")
    return errors


def _connection_matches(placements: dict[str, dict[str, Any]], modules: dict[str, dict[str, Any]], source: dict[str, str], target: dict[str, str]) -> bool:
    left = placements[source["instance_id"]]
    right = placements[target["instance_id"]]
    left_socket = _socket(modules[left["module_id"]], source["socket_id"])
    right_socket = _socket(modules[right["module_id"]], target["socket_id"])
    left_position, left_normal = _world_socket(left, left_socket)
    right_position, right_normal = _world_socket(right, right_socket)
    position_error = sum((left_position[index] - right_position[index]) ** 2 for index in range(3)) ** 0.5
    normal_dot = sum(left_normal[index] * right_normal[index] for index in range(3))
    return (
        position_error <= POSITION_TOLERANCE
        and normal_dot <= -NORMAL_TOLERANCE
        and left_socket["clear_size_m"] == right_socket["clear_size_m"]
        and left_socket["floor_elevation_m"] == right_socket["floor_elevation_m"]
        and left_socket["compatibility_type"] == right_socket["compatibility_type"]
    )


def _validate_footprints(placements: dict[str, dict[str, Any]], modules: dict[str, dict[str, Any]]) -> list[str]:
    errors = []
    values = list(placements.values())
    for index, left in enumerate(values):
        left_bounds = _bounds(left, modules[left["module_id"]])
        for right in values[index + 1:]:
            right_bounds = _bounds(right, modules[right["module_id"]])
            overlap_x = min(left_bounds[2], right_bounds[2]) - max(left_bounds[0], right_bounds[0])
            overlap_z = min(left_bounds[3], right_bounds[3]) - max(left_bounds[1], right_bounds[1])
            if overlap_x > POSITION_TOLERANCE and overlap_z > POSITION_TOLERANCE:
                errors.append(f"placement footprints overlap: {left['instance_id']} and {right['instance_id']}")
    return errors


def _validate_graph(layout: dict[str, Any], placements: dict[str, dict[str, Any]]) -> list[str]:
    if not placements:
        return ["layout has no placements"]
    adjacency = {instance_id: set() for instance_id in placements}
    for edge in layout.get("connections", []):
        left, right = edge["from"]["instance_id"], edge["to"]["instance_id"]
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)
    reached = set()
    pending = [next(iter(placements))]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(adjacency[current] - reached)
    edge_count = len(layout.get("connections", []))
    cycle_rank = edge_count - len(placements) + 1
    errors = []
    if len(reached) != len(placements):
        errors.append("layout graph is disconnected")
    if cycle_rank != 0 or layout.get("topology", {}).get("cycle_rank") != 0:
        errors.append("layout cycle count is unsupported")
    if sum(len(neighbors) == 3 for neighbors in adjacency.values()) != 1:
        errors.append("layout must contain exactly one three-way branch")
    return errors
