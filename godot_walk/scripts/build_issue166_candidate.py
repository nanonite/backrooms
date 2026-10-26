"""Build the isolated four-room comparison snapshot and layout."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-26-four-room-transfer"
REFERENCE_LAYOUT = (
    ROOT / "godot_walk/evidence/2026-10-24-issue-164/layout_three_room.json"
)
REFERENCE_CATALOG = (
    ROOT / "godot_walk/evidence/2026-10-24-issue-164/catalog_snapshot.json"
)
TRANSFER_RECORD = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: str) -> Path:
    candidate = ROOT / path
    if not candidate.is_file():
        raise FileNotFoundError(f"Candidate dependency is missing: {path}")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild this unapproved candidate snapshot and layout",
    )
    arguments = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    output_catalog = EVIDENCE / "catalog_snapshot.json"
    output_layout = EVIDENCE / "layout_four_room.json"
    outputs = [
        output_catalog,
        output_layout,
        Path(str(output_layout) + ".sha256"),
        EVIDENCE / "candidate_manifest.json",
    ]
    if not arguments.refresh and any(path.exists() for path in outputs):
        raise FileExistsError(
            "Refusing to overwrite the four-room candidate snapshot or layout"
        )
    snapshot = _build_snapshot()
    snapshot_bytes = _json_bytes(snapshot)
    output_catalog.write_bytes(snapshot_bytes)
    snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
    layout = _build_layout(snapshot, snapshot_hash)
    layout_bytes = _json_bytes(layout)
    output_layout.write_bytes(layout_bytes)
    layout_hash = hashlib.sha256(layout_bytes).hexdigest()
    Path(str(output_layout) + ".sha256").write_text(
        f"{layout_hash}  layout_four_room.json\n"
    )
    manifest = {
        "candidate_id": "issue166-four-room-transfer-v1",
        "operator_status": "review_pending",
        "mechanical_status": "mechanically_validated",
        "registration_accepted": False,
        "scale_calibrated": False,
        "candidate_snapshot": "godot_walk/evidence/2026-10-26-four-room-transfer/catalog_snapshot.json",
        "candidate_snapshot_sha256": snapshot_hash,
        "layout": "godot_walk/evidence/2026-10-26-four-room-transfer/layout_four_room.json",
        "layout_sha256": layout_hash,
        "source_catalog_snapshot": "godot_walk/evidence/2026-10-24-issue-164/catalog_snapshot.json",
        "source_catalog_snapshot_sha256": sha256(REFERENCE_CATALOG),
        "modules": [
            item["id"]
            for item in snapshot["modules"]
            if "dual_socket_candidate" in item["id"]
            or item["id"] == "godot_corridor_corner_socket_candidate_v1"
        ],
    }
    (EVIDENCE / "candidate_manifest.json").write_bytes(_json_bytes(manifest))
    print(json.dumps(manifest, indent=2))
    return 0


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _build_snapshot() -> dict[str, Any]:
    snapshot = json.loads(REFERENCE_CATALOG.read_text(encoding="utf-8"))
    base_modules = {item["id"]: item for item in snapshot["modules"]}
    large_room = copy.deepcopy(
        base_modules["godot_source_textured_large_room_hall_end_v1"]
    )
    large_room["id"] = "godot_source_textured_large_room_dual_socket_candidate_v1"
    large_room["scene"] = "res://scenes/issue166_room_large_dual_socket.tscn"
    large_room["variant_status"] = "provisional_operator_review_pending"
    large_room["sockets"] = copy.deepcopy(large_room["sockets"])
    large_room["sockets"].append(
        _socket(
            "west_back",
            [-6.0, -1.27099049, 0.0],
            [-1.0, 0.0, 0.0],
            -1.27099049,
            "Authored gameplay opening at the west wall; footage does not establish this connection.",
        )
    )
    large_room["visual_placement_envelope_xz"] = [
        [-6.12, -5.12],
        [6.12, -5.12],
        [6.12, -1.62],
        [13.12, -1.62],
        [13.12, 1.62],
        [6.12, 1.62],
        [6.12, 5.12],
        [-6.12, 5.12],
    ]
    large_room["collision_footprint_xz"] = copy.deepcopy(
        large_room["visual_placement_envelope_xz"]
    )
    large_room["dependencies"] = sorted(
        set(
            large_room["dependencies"]
            + [
                "godot_walk/scenes/issue166_room_large_dual_socket.tscn",
                "godot_walk/scripts/issue166_room_large_dual_socket.gd",
            ]
        )
    )
    large_room["version"] = 1
    large_room["collision_provenance"] = (
        "Separate versioned adapter: replaces the closed west wall with matching authored returns and header while preserving the accepted hall_end socket."
    )
    _refresh_module_hashes(large_room)

    transfer_record = json.loads(TRANSFER_RECORD.read_text(encoding="utf-8"))
    transfer = _build_transfer_module(transfer_record)
    snapshot["modules"].append(large_room)
    snapshot["modules"].append(transfer)
    snapshot["catalog_version"] = "0.2.0+issue166-candidate"
    snapshot["candidate_status"] = "provisional_operator_review_pending"
    snapshot["source_catalog"] = (
        "godot_walk/evidence/2026-10-24-issue-164/catalog_snapshot.json"
    )
    snapshot["source_catalog_sha256"] = sha256(REFERENCE_CATALOG)
    _refresh_snapshot_file_hashes(snapshot)
    return snapshot


def _socket(
    socket_id: str, center: list[float], normal: list[float], floor: float, closure: str
) -> dict[str, Any]:
    return {
        "id": socket_id,
        "local_floor_center": center,
        "outward_normal": normal,
        "clear_size_m": [2.0, 2.1],
        "floor_elevation_m": floor,
        "approach_clearance_m": 1.2,
        "compatibility_type": "level_doorway_2m_v1",
        "closure_behavior": closure,
    }


def _build_transfer_module(record: dict[str, Any]) -> dict[str, Any]:
    resolved = record["resolved_adaptation"]
    old_hashes = {
        item["path"]: item["sha256"]
        for item in resolved["dependencies"]
        if item["path"] != "godot_walk/room_catalog/catalog.json"
    }
    dependencies = sorted(
        set(old_hashes)
        | {
            "godot_walk/scenes/issue166_transfer_room_socket.tscn",
            "godot_walk/scenes/issue166_transfer_room_socket_standalone.tscn",
            "godot_walk/scripts/issue166_transfer_room_socket.gd",
        }
    )
    return {
        "id": "godot_corridor_corner_socket_candidate_v1",
        "version": 1,
        "kind": "authored_room_variant",
        "scene": "res://scenes/issue166_transfer_room_socket.tscn",
        "variant_status": "provisional_operator_review_pending",
        "floor_elevation_m": 0.0,
        "ceiling_elevation_m": 3.0,
        "placement_footprint_xz": copy.deepcopy(
            resolved["walkable_space"]["footprint"]["vertices_xz"]
        ),
        "collision_footprint_xz": copy.deepcopy(
            resolved["walkable_space"]["footprint"]["vertices_xz"]
        ),
        "visual_placement_envelope_xz": copy.deepcopy(
            resolved["rendered_placement_envelope"]["footprint"]["vertices_xz"]
        ),
        "sockets": [
            _socket(
                "west",
                [-6.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0],
                0.0,
                "Open only in the connection candidate; closed in the standalone scene and on all other perimeter edges.",
            )
        ],
        "closed_unused_sockets": "South, inner elbow, far end, east and north boundaries remain closed by matching visible geometry and collision.",
        "observed_openings": [],
        "obstacles": [
            {
                "id": "source_observed_column",
                "shape": "box",
                "center_local_xyz": [-2.5, 1.5, 0.0],
                "size_xyz": [0.9, 3.0, 0.9],
                "collision_node": "AuthoredBoundaries/SourceObservedColumnObstacle",
                "provenance": "Four-sided authored completion from source-visible faces; hidden faces remain unknown.",
            }
        ],
        "collision_provenance": "Separate floor, six perimeter boundaries and column blocker; the west socket is provisionally open with matched jamb/header visual and collision geometry.",
        "source_provenance": sorted(
            {
                "data/videos/corridor_corner.mp4",
                "godot_walk/evidence/2026-10-25-issue-165/REPORT.md",
                "godot_walk/evidence/2026-10-25-issue-165/source_frames/extraction_manifest.json",
                *[frame["path"] for frame in record["source_observations"]["frames"]],
                *[
                    crop["path"]
                    for frame in record["source_observations"]["frames"]
                    for crop in frame.get("crops", [])
                ],
            }
        ),
        "visual_assets": sorted(
            crop["path"]
            for frame in record["source_observations"]["frames"]
            for crop in frame.get("crops", [])
        ),
        "dependencies": dependencies,
        "dependency_hashes": [],
        "psx_profile_id": resolved["psx_profile_id"],
    } | _module_hashes(dependencies)


def _refresh_module_hashes(module: dict[str, Any]) -> None:
    module["dependency_hashes"] = [
        {"path": path, "sha256": sha256(relative(path))}
        for path in module["dependencies"]
    ]


def _module_hashes(dependencies: list[str]) -> dict[str, Any]:
    return {
        "dependency_hashes": [
            {"path": path, "sha256": sha256(relative(path))} for path in dependencies
        ]
    }


def _refresh_snapshot_file_hashes(snapshot: dict[str, Any]) -> None:
    runtime_paths = {item["path"] for item in snapshot["runtime_dependencies"]}
    runtime_paths.update(
        [
            "godot_walk/scenes/issue166_room_large_dual_socket.tscn",
            "godot_walk/scripts/issue166_room_large_dual_socket.gd",
            "godot_walk/scenes/issue166_transfer_room_socket.tscn",
            "godot_walk/scripts/issue166_transfer_room_socket.gd",
            "godot_walk/scenes/issue166_four_room_walkthrough.tscn",
            "godot_walk/scripts/issue166_four_room_walkthrough.gd",
        ]
    )
    paths = {item["path"] for item in snapshot["file_hashes"]}
    paths.update(runtime_paths)
    paths.update(
        path for module in snapshot["modules"] for path in module["dependencies"]
    )
    hashes = [
        {"path": path, "sha256": sha256(relative(path))} for path in sorted(paths)
    ]
    snapshot["file_hashes"] = hashes
    by_path = {item["path"]: item["sha256"] for item in hashes}
    snapshot["runtime_dependencies"] = [
        {"path": path, "sha256": by_path[path]} for path in sorted(runtime_paths)
    ]


def _build_layout(snapshot: dict[str, Any], snapshot_hash: str) -> dict[str, Any]:
    layout = json.loads(REFERENCE_LAYOUT.read_text(encoding="utf-8"))
    modules = {item["id"]: item for item in snapshot["modules"]}
    large_id = "godot_source_textured_large_room_dual_socket_candidate_v1"
    transfer_id = "godot_corridor_corner_socket_candidate_v1"
    for placement in layout["placements"]:
        if placement["instance_id"] == "R002":
            module = modules[large_id]
            placement.update(_placement_fields(module, ["hall_end", "west_back"]))
            placement["operator_status"] = "provisional_operator_review_pending"
            placement["connected_sockets"]["west_back"] = "R003/west"
        elif placement["instance_id"] in {"R000", "R001"}:
            placement["operator_status"] = "accepted_issue164_regression_reference"
    transfer_module = modules[transfer_id]
    layout["placements"].append(
        {
            **_placement_fields(transfer_module, ["west"]),
            "instance_id": "R003",
            "module_id": transfer_id,
            "module_version": 1,
            "operator_status": "provisional_operator_review_pending",
            "transform": {"position": [34.56, -1.27099049, 3.1], "yaw_degrees": 0},
            "connected_sockets": {"west": "R002/west_back"},
        }
    )
    layout["connections"].append(
        {
            "id": "R002.west_back__R003.west",
            "from": {"instance_id": "R002", "socket_id": "west_back"},
            "to": {"instance_id": "R003", "socket_id": "west"},
            "compatibility_type": "level_doorway_2m_v1",
            "mechanical_status": "mechanically_validated",
            "operator_status": "review_pending",
        }
    )
    layout.update(
        {
            "layout_id": "issue166_four_distinct_room_chain_seed_166",
            "seed": 166,
            "catalog_version": snapshot["catalog_version"],
            "catalog_snapshot_path": "res://evidence/2026-10-26-four-room-transfer/catalog_snapshot.json",
            "catalog_sha256": snapshot_hash,
            "mechanical_status": "mechanically_validated",
            "operator_status": "review_pending",
            "unique_module_designs": 4,
            "repeated_instances": 0,
            "module_counts": {
                "godot_later_bay_column_bounded_v1": 1,
                "godot_early_pocket_pass_through_v1": 1,
                large_id: 1,
                transfer_id: 1,
            },
            "walk_envelope": [-4.4, -3.98, 43.04, 13.98],
        }
    )
    layout["settings"].update(
        {
            "placement_count": 4,
            "layout_bounds_m": [-4.4, -3.98, 38.64, 10.0],
        }
    )
    layout["topology"] = {
        "type": "four_distinct_room_chain",
        "cycle_rank": 0,
        "edge_count": 3,
        "dead_end_count": 2,
    }
    layout["supported_constraints"] = [
        "reproduce_exact_issue164_three_room_chain_as_regression_prefix",
        "four_distinct_room_designs",
        "authored_west_back_socket_on_issue163_room_adapter",
        "authored_west_socket_on_issue165_corridor_adapter",
        "closed_unused_perimeter_boundaries",
        "safe_spawn_and_reset",
        "bidirectional_backtracking",
    ]
    layout["unsupported_constraints"] = [
        "source-video-proven connectivity at the new connection",
        "metric-scale calibration",
        "arbitrary room stitching",
        "unbounded streaming",
    ]
    layout["walk_route_xz"] = [
        [-3.5, 0.0],
        [-3.4, 2.6],
        [-1.8, 2.6],
        [2.4, 2.6],
        [2.4, 3.1],
        [3.3, 3.1],
        [4.3, 3.1],
        [6.5, 3.1],
        [8.7, 3.1],
        [9.5, 3.1],
        [12.5, 3.1],
        [16.56, 3.1],
        [18.56, 3.1],
        [18.56, 0.5],
        [22.56, 0.5],
        [26.56, 0.5],
        [26.56, 3.1],
        [27.5, 3.1],
        [28.4, 3.1],
        [29.4, 3.1],
        [30.56, 4.25],
        [33.56, 4.25],
        [35.0, 4.0],
        [35.36, 3.6],
        [36.56, 1.0],
        [36.56, -2.7],
    ]
    layout.pop("layout_sha256", None)
    layout["layout_sha256"] = hashlib.sha256(_canonical_bytes(layout)).hexdigest()
    return layout


def _placement_fields(
    module: dict[str, Any], open_sockets: list[str]
) -> dict[str, Any]:
    scene_path = "godot_walk/" + module["scene"].removeprefix("res://")
    scene_hash = next(
        item["sha256"]
        for item in module["dependency_hashes"]
        if item["path"] == scene_path
    )
    return {
        "module_id": module["id"],
        "module_version": module["version"],
        "scene": module["scene"],
        "scene_sha256": scene_hash,
        "open_sockets": open_sockets,
    }


if __name__ == "__main__":
    raise SystemExit(main())
