"""Derive the issue-273 v2 adaptation record from the accepted v1 record.

Every path hash and the candidate identity are computed from the working tree
with the repository's own contract helpers. No hash or fingerprint is authored
by hand. The output is a new version; the v1 record is never edited.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
ROOT = EVIDENCE_DIR.parents[2]
sys.path.insert(0, str(ROOT / "godot_walk/scripts"))

from video_adaptation_contracts import candidate_identity_v2, sha256_file

ROOMS = "godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms"
BASELINE = f"{ROOMS}/slot-canyon-courtyard-v1"
VARIANT = f"{ROOMS}/slot-canyon-courtyard-v2"
EVIDENCE = "godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues"


def artifact(relative: str, role: str) -> dict[str, str]:
    return {
        "path": relative,
        "sha256": sha256_file(ROOT / relative),
        "role": role,
    }


def main() -> int:
    source = ROOT / f"{BASELINE}/adaptation_candidate.json"
    target = ROOT / f"{VARIANT}/adaptation_candidate.json"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite candidate record: {target}")
    record = json.loads(source.read_text(encoding="utf-8"))

    record["adaptation_id"] = "slot-canyon-courtyard-v2"
    record["source_observations"]["suitability"]["rationale"] += [
        "Issue 273 authors a visual-only depth experiment (v2) from the operator-accepted v1 candidate; the seed frame, accepted panorama attempt and source identity are unchanged.",
        "The baseline candidate and its five direct source crops are re-used byte-for-byte; no new crop, model call, download or panorama attempt was made.",
    ]
    record["source_observations"]["unknowns"] += [
        "All v2 relief fins, overhead ledges and boulder caps are invented visual-only boxes; their count, positions, sizes, tilts and materials are not measured or inferred from the source.",
        "The relief has no collider and may visually overlap collidable walls and boulders; the operator must decide whether that mismatch is acceptable.",
    ]

    resolved = record["resolved_adaptation"]
    resolved["candidate_version"] = "slot-canyon-courtyard-v2"
    resolved["scene_path"] = f"{VARIANT}/room.tscn"
    resolved["boundary_and_obstacle_collision"]["exposed_boundary_policy"] += (
        " In v2 the complete floor, six perimeter walls and three rock obstacle "
        "colliders are identical to v1; fifteen relief fins, five overhead ledges and "
        "three boulder caps are visual-only MeshInstance3D nodes with no collider."
    )
    resolved["surfaces"] += [
        {
            "surface_id": "visual_relief_fins",
            "geometry_origin": "15 authored thin non-colliding boxes along inner wall faces, with staggered top heights and small Y-axis tilts.",
            "appearance_origin": "The accepted direct wall-strata crops from frame_1363 (dark and warm); no new crop.",
            "placement_basis": "Invented decorative relief inside the unchanged collidable footprint; irregular elevation silhouette.",
            "collision_origin": "None; visual only.",
            "evidence_refs": [
                "frame_1363",
                f"{BASELINE}/textures/wall_strata_dark.png",
                f"{BASELINE}/textures/wall_strata_warm.png",
                f"{EVIDENCE}/provenance/baseline_vs_variant_v1.json",
            ],
        },
        {
            "surface_id": "visual_overhead_ledges",
            "geometry_origin": "5 authored non-colliding thin boxes above the capsule top.",
            "appearance_origin": "Local solid-color PSX material authored in v2 room.gd.",
            "placement_basis": "Invented high-level occlusion cues; all above Y=1.2 so traversal is unaffected.",
            "collision_origin": "None; visual only.",
            "evidence_refs": [
                "frame_1363",
                f"{EVIDENCE}/provenance/baseline_vs_variant_v1.json",
            ],
        },
        {
            "surface_id": "visual_boulder_caps",
            "geometry_origin": "3 authored non-colliding chipped caps on the existing boulders.",
            "appearance_origin": "The accepted direct rock-debris crop from frame_1363.",
            "placement_basis": "Invented detail on the three existing collidable boulders; no new obstacle.",
            "collision_origin": "None; visual only.",
            "evidence_refs": ["frame_1363", f"{BASELINE}/textures/rock_rubble.png"],
        },
    ]
    resolved["authoring_log"]["manual_decisions"] += [
        "Create v2 as a new folder; the accepted v1 room and all frozen contracts stay byte-identical.",
        "Copy every collidable body, the declared XZ footprint, spawn, floor elevation, panorama, seed crops, camera and PSX settings from v1.",
        "Add 15 visual-only relief fins, 5 overhead ledges and 3 boulder caps; all positions, sizes, tilts and counts are invented, not measured.",
        "Record a boundary negative control that disables one wall and then all six walls to prove the check detects an escape or missing boundary.",
        "Leave operator appearance, collision-mismatch acceptance and catalog admission pending; flags remain false.",
    ]

    for relative, role in (
        (
            f"{VARIANT}/room.gd",
            "visual-only depth variant authored geometry and gameplay script",
        ),
        (f"{VARIANT}/room.tscn", "playable v2 candidate scene"),
        (
            f"{VARIANT}/test_room.gd",
            "standalone runtime, parity and negative-control harness",
        ),
        (
            f"{VARIANT}/run_capture_guarded.py",
            "shared GPU lock and resource guard wrapper",
        ),
        (f"{VARIANT}/capture_resource_run.json", "guarded capture resource receipt"),
        (
            f"{VARIANT}/captures/capture_manifest.json",
            "matched guarded capture manifest",
        ),
        *(
            (f"{VARIANT}/captures/{name}.png", "matched guarded render capture")
            for name in (
                "spawn_up_corridor",
                "bend_turn",
                "west_wall_strata",
                "open_sky_slot",
                "walk_00_spawn",
                "walk_01_forward",
                "walk_02_mid",
                "walk_03_bend",
                "walk_04_bend_exit",
            )
        ),
        (
            f"{BASELINE}/adaptation_candidate.json",
            "accepted baseline candidate identity",
        ),
        (
            f"{EVIDENCE}/provenance/baseline_vs_variant_v1.json",
            "generated baseline/variant provenance record",
        ),
        (
            f"{EVIDENCE}/fixture/pinned_supplement_v1.json",
            "computed frozen/accepted file hash supplement",
        ),
        (f"{EVIDENCE}/fixture/paired_capture.gd", "matched paired-capture harness"),
    ):
        resolved["dependencies"].append(artifact(relative, role))

    record["validation"]["mechanical_status"] = "passed"
    record["validation"]["stages"] = [
        {
            "stage_id": "standalone_spawn_floor_boundary_reset_v2",
            "status": "passed",
            "candidate_fingerprint": "",
            "artifacts": [
                artifact(f"{VARIANT}/test_room.gd", "standalone runtime test harness"),
                artifact(f"{VARIANT}/room.tscn", "playable v2 candidate scene"),
                artifact(
                    f"{VARIANT}/capture_resource_run.json",
                    "guarded capture resource receipt",
                ),
            ],
            "notes": [
                "Godot headless: spawn floor support, floor/rock/boundary rays, walk-and-backtrack, full collider-set parity with v1, 23 visual-only relief nodes, no new collidable obstacle, floor negative control, boundary escape negative control, all-walls-missing negative control and R reset.",
                "Matched guarded captures for v1 and v2 from identical camera poses; appearance decision pending the operator.",
            ],
        }
    ]

    identity = candidate_identity_v2(record)
    record["candidate_identity"] = identity
    record["validation"]["stages"][0]["candidate_fingerprint"] = identity
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target.relative_to(ROOT)}; candidate_identity={identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
