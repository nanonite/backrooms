"""Write the pending v3 adaptation record for the issue 166 socket candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from video_adaptation_contracts import V3_FREEZE, candidate_identity_v2, sha256_file
from video_adaptation_resource_graph import discover_resource_graph
from video_adaptation_validation import ROOT

EVIDENCE = ROOT / "godot_walk/evidence/2026-10-26-four-room-transfer"
SOURCE_RECORD = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"
COMPATIBILITY = (
    ROOT
    / "godot_walk/room_catalog/adaptations/compatibility_v3/corridor-corner-authored-l-corridor-v2.json"
)
CANDIDATE_SNAPSHOT = (
    "godot_walk/evidence/2026-10-26-four-room-transfer/catalog_snapshot.json"
)
LAYOUT = "godot_walk/evidence/2026-10-26-four-room-transfer/layout_four_room.json"
LAYOUT_HASH = LAYOUT + ".sha256"
OUTPUT = EVIDENCE / "corridor_socket_adaptation_v3.json"


def main() -> int:
    arguments = _arguments()
    if OUTPUT.exists() and not arguments.refresh:
        raise FileExistsError(f"Refusing to overwrite adaptation record: {OUTPUT}")
    record = _build_record()
    OUTPUT.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "path": str(OUTPUT.relative_to(ROOT)),
                "candidate_identity": record["candidate_identity"],
                "status": record["status"],
                "validation": record["validation"],
            },
            indent=2,
        )
    )
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh this unapproved, pending candidate record",
    )
    return parser.parse_args()


def _build_record() -> dict[str, Any]:
    source = json.loads(SOURCE_RECORD.read_text(encoding="utf-8"))
    compat = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
    freeze_path = ROOT / V3_FREEZE
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    snapshot_ref = freeze["catalog_snapshot"]
    candidate_catalog = json.loads(
        (ROOT / CANDIDATE_SNAPSHOT).read_text(encoding="utf-8")
    )
    dependencies = _candidate_dependencies(
        source, candidate_catalog, compat, snapshot_ref
    )
    resolved = _resolved_adaptation(source, dependencies)
    record = {
        "schema_version": 3,
        "contract_id": "godot_video_room_completion",
        "contract_version": "3.0.0",
        "contract_freeze": {"path": V3_FREEZE, "sha256": sha256_file(freeze_path)},
        "adaptation_id": "corridor-corner-socket-candidate-v1",
        "status": "candidate_pending_review",
        "registration_accepted": False,
        "scale_calibrated": False,
        "source_observations": source["source_observations"],
        "reusable_requirements": source["reusable_requirements"],
        "resolved_adaptation": resolved,
        "validation": _validation_stages(),
        "operator_decision": {
            "status": "pending",
            "decision_record_path": None,
            "decision_sha256": None,
            "candidate_fingerprint": None,
            "scope": "new authored corridor socket and four-room comparison only",
        },
        "catalog_snapshot": snapshot_ref,
    }
    record["candidate_identity"] = candidate_identity_v2(record)
    for stage in record["validation"]["stages"]:
        stage["candidate_fingerprint"] = record["candidate_identity"]
    return record


def _candidate_dependencies(
    source: dict[str, Any],
    candidate_catalog: dict[str, Any],
    compatibility: dict[str, Any],
    snapshot_ref: dict[str, Any],
) -> list[dict[str, str]]:
    roles: dict[str, str] = {}
    declarations = compatibility.get("dynamic_resource_declarations", [])
    graph = discover_resource_graph(
        [
            "godot_walk/scenes/issue166_transfer_room_socket.tscn",
            "godot_walk/scenes/player.tscn",
        ],
        declarations,
        ROOT,
    )
    for path in graph:
        roles[path] = (
            "transitive Godot scene, script, shader, texture or controller dependency"
        )
    roles[snapshot_ref["path"]] = "immutable contract catalog snapshot"
    for path in [
        CANDIDATE_SNAPSHOT,
        LAYOUT,
        LAYOUT_HASH,
        "godot_walk/evidence/2026-10-26-four-room-transfer/candidate_manifest.json",
    ]:
        roles[path] = "four-room candidate layout or module snapshot"
    roles[
        "godot_walk/evidence/2026-10-26-four-room-transfer/protected_asset_hashes.json"
    ] = "read-only integrity record for accepted inputs"
    for module in candidate_catalog["modules"]:
        for path in module.get("dependencies", []):
            if path != "godot_walk/room_catalog/catalog.json":
                roles[path] = (
                    "versioned room module dependency from candidate catalog snapshot"
                )
    for path in [
        "godot_walk/evidence/2026-10-24-issue-164/catalog_snapshot.json",
        "godot_walk/evidence/2026-10-24-issue-164/layout_three_room.json",
        "godot_walk/evidence/2026-10-25-issue-165/REPORT.md",
        "godot_walk/evidence/2026-10-25-issue-165/source_frames/extraction_manifest.json",
        "godot_walk/scripts/build_issue166_candidate.py",
        "godot_walk/scripts/test_issue166_four_room_candidate.gd",
        "godot_walk/scripts/analyze_issue166_traversal.py",
        "godot_walk/scripts/validate_issue166_layout.py",
        "godot_walk/scripts/test_issue166_layout_validation.py",
        "godot_walk/scripts/capture_issue166_four_room.gd",
        "godot_walk/scripts/verify_bounded_psx.gd",
        "godot_walk/scripts/measure_bounded_fps.gd",
        "godot_walk/scripts/run_issue149_gpu.py",
        "godot_walk/scripts/write_issue166_adaptation_record.py",
    ]:
        roles[path] = "candidate authoring or validation provenance"
    _add_source_observation_dependencies(roles, source["source_observations"])
    _add_existing_evidence(roles)
    result = []
    for path, role in sorted(roles.items()):
        artifact = ROOT / path
        if not artifact.is_file():
            raise FileNotFoundError(f"Candidate dependency is missing: {path}")
        result.append({"path": path, "sha256": sha256_file(artifact), "role": role})
    return result


def _add_source_observation_dependencies(
    roles: dict[str, str], observations: dict[str, Any]
) -> None:
    roles[observations["video"]["path"]] = "direct source video provenance"
    for frame in observations["frames"]:
        roles[frame["path"]] = "directly decoded source frame provenance"
        for crop in frame.get("crops", []):
            roles[crop["path"]] = "direct rectangular source texture crop"


def _add_existing_evidence(roles: dict[str, str]) -> None:
    paths = [
        "godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/connection_controls_final.json",
        "godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/traversal_analysis_final_v2.json",
    ]
    for folder in [
        "assembled_final_v3",
        "corridor_standalone_final_v2",
        "large_room_standalone_final_v2",
        "issue164_regression_verified",
    ]:
        base = f"godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/{folder}"
        paths.extend(
            f"{base}/{name}"
            for name in [
                "physics_candidate.json",
                "route_positions.json",
                "boundary_positions.json",
            ]
        )
    capture_dir = EVIDENCE / "captures"
    paths.extend(
        path.relative_to(ROOT).as_posix() for path in capture_dir.glob("*.png")
    )
    resource_dir = EVIDENCE / "resource_runs"
    paths.extend(
        path.relative_to(ROOT).as_posix() for path in resource_dir.glob("*.json")
    )
    for path in paths:
        artifact = ROOT / path
        if artifact.is_file():
            roles[path] = "measured candidate verification or review evidence"


def _resolved_adaptation(
    source: dict[str, Any], dependencies: list[dict[str, str]]
) -> dict[str, Any]:
    old = source["resolved_adaptation"]
    physics = _read_json(
        EVIDENCE / "mechanics/corridor_standalone_final_v2/physics_candidate.json"
    )
    area = physics.get("walkable_area", {}).get("spawn_connected_area_estimate_m2")
    return {
        "candidate_version": "corridor-corner-socket-candidate-v1",
        "catalog_admission": "candidate_not_admitted",
        "scene_path": "res://scenes/issue166_transfer_room_socket.tscn",
        "catalog_module_refs": [],
        "walkable_space": {
            "coordinate_system": old["walkable_space"]["coordinate_system"],
            "footprint": old["walkable_space"]["footprint"],
            "floor_elevation": 0.0,
            "safe_spawn_xyz": [-5.0, 0.6, 0.0],
            "measurement": {
                "method": physics["walkable_area"]["method"],
                "resolution": physics["walkable_area"]["grid_step_m"],
                "spawn_connected_area": area,
                "status": "measured",
            },
        },
        "boundary_and_obstacle_collision": {
            "collision_origin": "Separate Godot StaticBody3D floor, perimeter and obstacle colliders; the authored west socket uses matching return/header visuals and collision.",
            "floor_bodies": ["AuthoredBoundaries/WalkableFloor"],
            "boundaries": [
                "AuthoredBoundaries/Boundary_SouthMain",
                "AuthoredBoundaries/Boundary_InnerElbow",
                "AuthoredBoundaries/Boundary_FarCap",
                "AuthoredBoundaries/Boundary_EastOuter",
                "AuthoredBoundaries/Boundary_NorthMain",
                "AuthoredBoundaries/WestSocketReturn_Left",
                "AuthoredBoundaries/WestSocketReturn_Right",
                "AuthoredBoundaries/WestSocketHeader",
            ],
            "obstacles": ["AuthoredBoundaries/SourceObservedColumnObstacle"],
            "exposed_boundary_policy": "The west edge is open only in the provisional connection scene. All other edges stay closed. The standalone scene restores the original full west wall; runtime tests probe every closed corridor edge.",
        },
        "rendered_placement_envelope": old["rendered_placement_envelope"],
        "surfaces": old["surfaces"],
        "sockets": [
            {
                "id": "source-room-passage-visible-frame-0001",
                "kind": "observed_opening",
                "status": "source_observation_only",
                "closure_behavior": "Source-visible gap remains a video observation only; it does not establish the authored game connection.",
            },
            {
                "id": "west",
                "kind": "authored_doorway",
                "status": "tested_connector",
                "local_floor_center_xyz": [-6.0, 0.0, 0.0],
                "outward_normal_xyz": [-1.0, 0.0, 0.0],
                "clear_size": [2.0, 2.1],
                "approach_clearance": 1.2,
                "compatibility_type": "level_doorway_2m_v1",
                "tested_connection_ref": "godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/traversal_analysis_final_v2.json#R002.west_back__R003.west",
                "closure_behavior": "Open in the four-room comparison adapter only; capped in the standalone module. Unused corridor edges remain closed.",
                "floor_elevation": 0.0,
                "approach_region_xz": {
                    "representation": "simple_orthogonal_polygon_xz",
                    "vertices_xz": [
                        [-5.7, -0.8],
                        [-4.8, -0.8],
                        [-4.8, 0.8],
                        [-5.7, 0.8],
                    ],
                },
            },
        ],
        "psx_profile_id": old["psx_profile_id"],
        "dependencies": dependencies,
        "authoring_log": {
            "manual_decisions": [
                "Author an east/west doorway pair on the unregistered west shell edge; footage does not prove a connection here.",
                "Reuse the accepted #164 room arrangement as the regression prefix and add the #165 corridor as a fourth distinct room.",
                "Keep all unused #165 perimeter edges closed and retain an independent closed standalone variant.",
            ],
            "operator_interventions": 0,
            "effort": "One versioned room adapter, one receiver adapter, a four-room layout, and bounded runtime verification; no source video, inference, or retraining.",
        },
        "room_clearance": {
            "floor_elevation": 0.0,
            "ceiling_elevation": 3.0,
            "basis": "authored",
        },
        "dynamic_resource_declarations": json.loads(
            COMPATIBILITY.read_text(encoding="utf-8")
        )["dynamic_resource_declarations"],
    }


def _validation_stages() -> dict[str, Any]:
    runtime_paths = [
        EVIDENCE / "mechanics/connection_controls_final.json",
        EVIDENCE / "mechanics/traversal_analysis_final_v2.json",
        EVIDENCE / "mechanics/assembled_final_v3/physics_candidate.json",
        EVIDENCE / "mechanics/corridor_standalone_final_v2/physics_candidate.json",
        EVIDENCE / "mechanics/large_room_standalone_final_v2/physics_candidate.json",
        EVIDENCE / "mechanics/issue164_regression_verified/physics_candidate.json",
    ]
    visual_paths = [
        EVIDENCE / "captures/connection_large_room_to_corridor.png",
        EVIDENCE / "captures/connection_corridor_to_large_room.png",
    ]
    artifacts = [_artifact(path) for path in runtime_paths]
    visual_artifacts = [_artifact(path) for path in visual_paths if path.is_file()]
    visual_complete = len(visual_artifacts) == len(visual_paths)
    return {
        "mechanical_status": "passed",
        "stages": [
            {
                "stage_id": "standalone_and_bidirectional_traversal",
                "status": "passed",
                "candidate_fingerprint": "0" * 64,
                "artifacts": artifacts,
                "notes": [
                    "Godot route, floor support, closed perimeters, approach clearance and negative controls are recorded."
                ],
            },
            {
                "stage_id": "guarded_visual_capture",
                "status": "passed" if visual_complete else "pending",
                "candidate_fingerprint": "0" * 64,
                "artifacts": visual_artifacts,
                "notes": []
                if visual_complete
                else [
                    "No guarded connection captures exist; visual review remains pending."
                ],
            },
        ],
    }


def _artifact(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required candidate verification output is missing: {path}"
        )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        "role": "candidate runtime evidence",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
