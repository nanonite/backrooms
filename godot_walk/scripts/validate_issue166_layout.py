"""Validate the finite issue 166 chain without imposing maze-generator topology."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from issue149_layout_core import canonical_json

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DESIGNS = {
    "godot_later_bay_column_bounded_v1",
    "godot_early_pocket_pass_through_v1",
    "godot_source_textured_large_room_dual_socket_candidate_v1",
    "godot_corridor_corner_socket_candidate_v1",
}
TOLERANCE = 1e-3
HISTORICAL_LAYOUT_TOOL_ARCHIVES = {
    "godot_walk/scripts/issue149_layout_core.py": {
        "sha256": "0170c37c402018aad118894e380c681c7cdb070bb4ba9d7ba4f8908ca9e283bf",
        "archive_path": "godot_walk/scripts/archives/issue149_layout_core_before_source_scoped_catalog.py",
    }
}


def validate_bundle(layout_path: Path) -> tuple[dict[str, Any], list[str]]:
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    snapshot_path = _snapshot_path(layout)
    errors = _layout_integrity(layout, layout_path)
    if snapshot_path is None:
        return layout, errors + ["catalog snapshot path escapes the project"]
    if not snapshot_path.is_file():
        return layout, errors + ["candidate catalog snapshot is missing"]
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    if _sha256_bytes(snapshot_bytes) != layout.get("catalog_sha256"):
        errors.append("candidate snapshot hash differs from the layout binding")
    errors.extend(_snapshot_dependencies(snapshot))
    errors.extend(_placements_and_connections(layout, snapshot))
    return layout, errors


def _snapshot_path(layout: dict[str, Any]) -> Path | None:
    resource = layout.get("catalog_snapshot_path", "")
    if not isinstance(resource, str) or not resource.startswith("res://evidence/"):
        return None
    project = ROOT / "godot_walk"
    path = (project / resource.removeprefix("res://")).resolve()
    return path if path.is_relative_to(project.resolve()) else None


def _layout_integrity(layout: dict[str, Any], path: Path) -> list[str]:
    errors = []
    payload = dict(layout)
    expected = payload.pop("layout_sha256", "")
    if hashlib.sha256(canonical_json(payload)).hexdigest() != expected:
        errors.append("canonical layout hash mismatch")
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file() or sidecar.read_text(encoding="utf-8").split()[
        0
    ] != _sha256_file(path):
        errors.append("serialized layout sidecar is missing or stale")
    if layout.get("operator_status") != "review_pending":
        errors.append("candidate must remain pending operator review")
    if layout.get("mechanical_status") != "mechanically_validated":
        errors.append("candidate mechanical status is not validated")
    if layout.get("registration_accepted") or layout.get("scale_calibrated"):
        errors.append("registration and scale flags must remain false")
    return errors


def _snapshot_dependencies(snapshot: dict[str, Any]) -> list[str]:
    errors = []
    declared = {
        item.get("path"): item.get("sha256") for item in snapshot.get("file_hashes", [])
    }
    for module in snapshot.get("modules", []):
        module_paths = set(module.get("dependencies", []))
        hashed_paths = {
            item.get("path") for item in module.get("dependency_hashes", [])
        }
        if not module_paths.issubset(hashed_paths):
            errors.append(
                f"module dependencies are missing hash coverage: {module.get('id')}"
            )
        for item in module.get("dependency_hashes", []):
            if declared.get(item.get("path")) != item.get("sha256"):
                errors.append(
                    f"module dependency differs from snapshot file manifest: {item.get('path')}"
                )
    for item in snapshot.get("file_hashes", []):
        path = _repo_file(item.get("path", ""))
        if path is None or not path.is_file():
            errors.append(
                "snapshot dependency is missing or escapes repository: "
                + item.get("path", "")
            )
        elif _sha256_file(path) != item.get(
            "sha256"
        ) and not _historical_archive_matches(item):
            errors.append("snapshot dependency hash mismatch: " + item["path"])
    return errors


def _historical_archive_matches(item: dict[str, Any]) -> bool:
    archive = HISTORICAL_LAYOUT_TOOL_ARCHIVES.get(item.get("path"))
    if archive is None or item.get("sha256") != archive["sha256"]:
        return False
    archive_path = _repo_file(archive["archive_path"])
    return (
        archive_path is not None
        and archive_path.is_file()
        and _sha256_file(archive_path) == archive["sha256"]
    )


def _placements_and_connections(
    layout: dict[str, Any], snapshot: dict[str, Any]
) -> list[str]:
    errors = []
    placements = {
        item.get("instance_id"): item for item in layout.get("placements", [])
    }
    modules = {item.get("id"): item for item in snapshot.get("modules", [])}
    if len(placements) != 4 or set(placements) != {"R000", "R001", "R002", "R003"}:
        return ["candidate must contain exactly four uniquely identified placements"]
    if {item.get("module_id") for item in placements.values()} != EXPECTED_DESIGNS:
        errors.append(
            "candidate does not contain the four expected distinct room designs"
        )
    if len(layout.get("connections", [])) != 3:
        errors.append("four-room chain must contain exactly three connections")
    errors.extend(_module_bindings(placements, modules))
    errors.extend(_connection_bindings(layout, placements, modules))
    errors.extend(_no_footprint_overlap(placements, modules))
    errors.extend(_connected_chain(layout, placements))
    return errors


def _module_bindings(placements: dict[str, Any], modules: dict[str, Any]) -> list[str]:
    errors = []
    for instance_id, placement in placements.items():
        module = modules.get(placement.get("module_id"))
        if module is None:
            errors.append(f"{instance_id} references an unknown module")
            continue
        declared_sockets = {item.get("id") for item in module.get("sockets", [])}
        if set(placement.get("open_sockets", [])) != declared_sockets:
            errors.append(
                f"{instance_id} open socket list differs from module contract"
            )
        if placement.get("module_version") != module.get("version") or placement.get(
            "scene"
        ) != module.get("scene"):
            errors.append(
                f"{instance_id} module version or scene differs from snapshot"
            )
        scene_path = "godot_walk/" + module["scene"].removeprefix("res://")
        expected = next(
            (
                item["sha256"]
                for item in module.get("dependency_hashes", [])
                if item["path"] == scene_path
            ),
            None,
        )
        if expected != placement.get("scene_sha256"):
            errors.append(
                f"{instance_id} scene digest differs from its module snapshot"
            )
    return errors


def _connection_bindings(
    layout: dict[str, Any], placements: dict[str, Any], modules: dict[str, Any]
) -> list[str]:
    errors = []
    used: dict[tuple[str, str], int] = {}
    for edge in layout.get("connections", []):
        source = edge.get("from", {})
        target = edge.get("to", {})
        left = _socket_endpoint(source, placements, modules)
        right = _socket_endpoint(target, placements, modules)
        if left is None or right is None:
            errors.append(
                "connection references a missing module or socket: "
                + edge.get("id", "unknown")
            )
        elif (
            not _sockets_match(left, right)
            or edge.get("compatibility_type") != left["socket"]["compatibility_type"]
        ):
            errors.append(
                "world socket transforms or aperture declarations mismatch: "
                + edge.get("id", "unknown")
            )
        for endpoint in (source, target):
            key = (endpoint.get("instance_id", ""), endpoint.get("socket_id", ""))
            used[key] = used.get(key, 0) + 1
        if left is not None and right is not None:
            source_ref = f"{target.get('instance_id')}/{target.get('socket_id')}"
            target_ref = f"{source.get('instance_id')}/{source.get('socket_id')}"
            source_placement = placements[source["instance_id"]]
            target_placement = placements[target["instance_id"]]
            if (
                source_placement.get("connected_sockets", {}).get(source["socket_id"])
                != source_ref
            ):
                errors.append(
                    "source connected-socket declaration differs from edge "
                    + edge.get("id", "unknown")
                )
            if (
                target_placement.get("connected_sockets", {}).get(target["socket_id"])
                != target_ref
            ):
                errors.append(
                    "target connected-socket declaration differs from edge "
                    + edge.get("id", "unknown")
                )
    for instance_id, placement in placements.items():
        for socket_id in placement.get("open_sockets", []):
            if used.get((instance_id, socket_id), 0) != 1:
                errors.append(
                    f"open socket is not connected exactly once: {instance_id}/{socket_id}"
                )
    return errors


def _socket_endpoint(
    endpoint: dict[str, Any], placements: dict[str, Any], modules: dict[str, Any]
) -> dict[str, Any] | None:
    placement = placements.get(endpoint.get("instance_id"))
    if placement is None:
        return None
    module = modules.get(placement.get("module_id"))
    socket = (
        next(
            (
                item
                for item in module.get("sockets", [])
                if item.get("id") == endpoint.get("socket_id")
            ),
            None,
        )
        if module
        else None
    )
    if socket is None:
        return None
    origin = placement["transform"]["position"]
    yaw = placement["transform"]["yaw_degrees"]
    center_x, center_z = _rotate(socket["local_floor_center"], yaw)
    normal_x, normal_z = _rotate(socket["outward_normal"], yaw)
    return {
        "center": [
            origin[0] + center_x,
            origin[1] + socket["local_floor_center"][1],
            origin[2] + center_z,
        ],
        "normal": [normal_x, socket["outward_normal"][1], normal_z],
        "socket": socket,
    }


def _sockets_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left["socket"], right["socket"]
    position_ok = all(
        abs(left["center"][i] - right["center"][i]) <= TOLERANCE for i in range(3)
    )
    normal_dot = sum(left["normal"][i] * right["normal"][i] for i in range(3))
    declarations_ok = (
        a["clear_size_m"] == b["clear_size_m"]
        and a["compatibility_type"] == b["compatibility_type"]
    )
    return position_ok and normal_dot <= -0.999 and declarations_ok


def _rotate(vector: list[float], yaw: int) -> tuple[float, float]:
    x, z = vector[0], vector[2]
    rotation = yaw % 360
    if rotation == 0:
        return x, z
    if rotation == 90:
        return z, -x
    if rotation == 180:
        return -x, -z
    if rotation == 270:
        return -z, x
    raise ValueError("Only right-angle module rotations are supported")


def _no_footprint_overlap(
    placements: dict[str, Any], modules: dict[str, Any]
) -> list[str]:
    errors = []
    values = list(placements.values())
    for index, left in enumerate(values):
        a = _footprint_bounds(left, modules[left["module_id"]])
        for right in values[index + 1 :]:
            b = _footprint_bounds(right, modules[right["module_id"]])
            overlap_x = min(a[2], b[2]) - max(a[0], b[0])
            overlap_z = min(a[3], b[3]) - max(a[1], b[1])
            if overlap_x > TOLERANCE and overlap_z > TOLERANCE:
                errors.append(
                    f"walkable placement footprints overlap: {left['instance_id']} and {right['instance_id']}"
                )
    return errors


def _footprint_bounds(
    placement: dict[str, Any], module: dict[str, Any]
) -> tuple[float, float, float, float]:
    points = [
        _rotate([point[0], 0.0, point[1]], placement["transform"]["yaw_degrees"])
        for point in module["placement_footprint_xz"]
    ]
    origin = placement["transform"]["position"]
    xs = [origin[0] + point[0] for point in points]
    zs = [origin[2] + point[1] for point in points]
    return min(xs), min(zs), max(xs), max(zs)


def _connected_chain(layout: dict[str, Any], placements: dict[str, Any]) -> list[str]:
    adjacency = {key: set() for key in placements}
    for edge in layout.get("connections", []):
        left, right = edge["from"]["instance_id"], edge["to"]["instance_id"]
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)
    reached, pending = set(), ["R000"]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(adjacency[current] - reached)
    degrees = sorted(map(len, adjacency.values()))
    if len(reached) != 4 or degrees != [1, 1, 2, 2]:
        return ["layout is not a connected four-room chain"]
    return []


def _repo_file(relative: str) -> Path | None:
    candidate = (ROOT / relative).resolve()
    return candidate if candidate.is_relative_to(ROOT.resolve()) else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, required=True)
    arguments = parser.parse_args()
    layout, errors = validate_bundle(arguments.layout)
    for error in errors:
        print("INVALID: " + error)
    if errors:
        return 1
    print(
        f"validated {layout['layout_id']}: 4 distinct modules, 3 connected sockets, walkable footprints disjoint, operator review pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
