"""Hash-aware builders for the Issue 148 room catalog entry."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ISSUE_ROOT = "godot_walk/evidence/2026-10-21-issue-148"
EARLY_ROOT = f"{ISSUE_ROOT}/early-pocket"
GENERATED = f"{EARLY_ROOT}/generated"
EARLY_ID = "issue-148-early-pocket"
LATER_ID = "hunyuan-issue-150-later-bay"
EARLY_SOCKET_ID = "issue148-early-pocket-west-socket"
LATER_SOCKET_ID = "issue148-later-bay-east-socket"
CONNECTOR_EVIDENCE = f"{GENERATED}/assembled_connector_walkability.json"


def file_hash(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


def file_reference(relative_path: str) -> dict[str, str]:
    return {"path": relative_path, "sha256": file_hash(relative_path)}


def evidence_reference(relative_path: str, purpose: str) -> dict[str, str]:
    return {**file_reference(relative_path), "purpose": purpose}


def source_provenance() -> dict:
    usage = (
        "Direct #100 source frame selected from opening candidate C; visual context only. "
        "It does not establish a room, hallway, threshold traversal, scale, or connection."
    )
    return {
        "video": file_reference("data/scenes/corridor_travel/video.mp4"),
        "frames": [
            {
                "frame_id": frame_id,
                "zero_based_index": frame_id - 1,
                "timestamp_seconds": round((frame_id - 1) / 24, 10),
                "image": file_reference(
                    f"data/scenes/corridor_travel/images/frame_{frame_id:04}.jpg"
                ),
                "usage": usage,
            }
            for frame_id in (13, 17, 25, 27)
        ],
        "camera_metadata": file_reference(
            "godot_walk/evidence/2026-10-18-issue-145/camera_path.csv"
        ),
        "inventory_catalog": file_reference(
            "godot_walk/evidence/2026-10-18-issue-145/ROOM_CATALOG.md"
        ),
    }


def connector_socket(socket_id: str, description: str, position: list[float]) -> dict:
    return {
        "id": socket_id,
        "status": "authored_adaptation_socket",
        "description": description,
        "clear_width_m": 2.4,
        "clear_height_m": 2.4,
        "local_transform": {
            "translation_m": position,
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
        },
    }


def tested_connector(
    connector_id: str, from_socket: str, target_module: str, target_socket: str
) -> dict:
    return {
        "id": connector_id,
        "from_socket_id": from_socket,
        "target_module_id": target_module,
        "target_socket_id": target_socket,
        "evidence": evidence_reference(
            CONNECTOR_EVIDENCE,
            "CPU route, collision, floor continuity, column obstacle, and boundary checks for the authored assembly; not source connectivity.",
        ),
    }


def authored_asset(relative_path: str, role: str, note: str) -> dict:
    return {
        **file_reference(relative_path),
        "role": role,
        "transform": {
            "status": "authored_design_convention",
            "translation_m": [0.0, 0.0, 0.0],
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
            "note": note,
        },
    }


def boundary_rule(rule_id: str, kind: str, node: str, description: str) -> dict:
    path = f"{GENERATED}/early_pocket_route_report.json"
    return {
        "id": rule_id,
        "kind": kind,
        "origin": "authored",
        "description": description,
        "collision_node": node,
        "evidence": evidence_reference(
            path, "Standalone authored pocket bounds, floor, wall declaration, and collision mesh."
        ),
    }
