"""Build the catalog record for the standalone authored early-pocket."""

from __future__ import annotations

import json

from catalog_support import (
    EARLY_ROOT,
    GENERATED,
    ISSUE_ROOT,
    LATER_ID,
    LATER_SOCKET_ID,
    EARLY_ID,
    EARLY_SOCKET_ID,
    ROOT,
    authored_asset,
    boundary_rule,
    connector_socket,
    evidence_reference,
    file_reference,
    tested_connector,
    source_provenance,
)


def validation_evidence() -> list[dict]:
    items = [
        (f"{ISSUE_ROOT}/REPORT.md", "Issue 148 decision, validation, resources, and review status."),
        (f"{ISSUE_ROOT}/COMMANDS.md", "Reproduction commands for route checks, scenes, and review."),
        (f"{EARLY_ROOT}/REPORT.md", "Pocket scope, separate assembly adaptation, and visual-review notes."),
        (f"{EARLY_ROOT}/authored_assembly_layout.svg", "Authored plan proposal, not recovered source layout."),
        (f"{EARLY_ROOT}/standalone_scene_manifest.json", "Standalone provenance and false calibration flags."),
        (f"{EARLY_ROOT}/module_manifest.json", "Separate assembly assets and false calibration flags."),
        (f"{GENERATED}/early_pocket_route_report.json", "Standalone bounds, authored shell, and collision declaration."),
        (f"{GENERATED}/early_pocket_walkability.json", "Standalone bidirectional route and boundary checks."),
        (f"{GENERATED}/early_pocket_scene_report.json", "CPU-only standalone scene and resource measurements."),
        (f"{GENERATED}/assembled_route_report.json", "Authored assembly route and separate collision layout."),
        (f"{GENERATED}/assembled_connector_walkability.json", "CPU route and collision checks for the authored connector."),
        (f"{GENERATED}/assembled_connector_scene_report.json", "CPU-only assembly scene resource measurements."),
        (f"{GENERATED}/assembled_connector_collision.glb", "Separate connector collision; #150 baseline collision is unchanged."),
        (f"{GENERATED}/assembled_review_visual.glb", "Separate review visual for the authored adaptation."),
        (f"{GENERATED}/captures/assembled_connector/bevy_capture_report.json", "Eight Vulkan review views and resource preflight."),
        (f"{GENERATED}/captures/assembled_connector/candidate_contact_sheet.jpg", "Eight-view visual review; not source footage."),
        (f"{GENERATED}/negative_controls/blocked_entry_walkability.json", "A wall across the opening blocks traversal."),
        (f"{GENERATED}/negative_controls/missing_connector_floor_walkability.json", "Missing floor fails route/support checks."),
        ("splat_walk/src/bin/walkability_harness/route_scene/authored_visuals.rs", "Procedural authored shell rendering implementation."),
    ]
    return [evidence_reference(path, purpose) for path, purpose in items]


def runtime_measurements() -> dict:
    path = f"{GENERATED}/early_pocket_scene_report.json"
    report = json.loads((ROOT / path).read_text(encoding="utf-8"))
    visual = report["visual"]
    update = report["update_time_ms"]
    triangles = sum(node["triangle_count"] for node in visual["visual_nodes"])
    surface_count = len(visual["authored_visual_surfaces"])
    return {
        "report": evidence_reference(path, "CPU-only standalone scene, route, update, visual-load, and resource report."),
        "mode": "cpu_headless",
        "gpu_used": False,
        "scene_total_wall_time_seconds": report["scene_total_wall_time_seconds"],
        "route_simulation_wall_time_seconds": report["route_simulation_wall_time_seconds"],
        "peak_rss_kib": report["peak_rss_kib"],
        "mean_update_ms": update["mean"],
        "p90_update_ms": update["p90"],
        "max_update_ms": update["max"],
        "visual_load_seconds": visual["load_time_seconds"],
        "visual_query_preparation_seconds": visual["query_preparation_time_seconds"],
        "visual_triangle_count": triangles,
        "note": f"CPU/headless, not an FPS result. {triangles} GLB triangles plus {surface_count} procedural authored visual surfaces declared in the route report.",
    }


def early_module(shared_controller: dict) -> dict:
    floor_y = -1.2709904909133911
    manifest = f"{EARLY_ROOT}/standalone_scene_manifest.json"
    walls = [
        boundary_rule(
            f"issue148-early-pocket-boundary-{side}",
            "room_boundary",
            f"authored_room_boundary_{side}",
            f"Closed authored {side} wall; not an observed source-video placement.",
        )
        for side in ("west", "east", "south", "north")
    ]
    return {
        "id": EARLY_ID,
        "display_name": "Issue 148 authored early-pocket",
        "kind": "room",
        "admission_status": "standalone_validated",
        "source": source_provenance(),
        "assets": {
            "visual": authored_asset(
                f"{GENERATED}/early_pocket_visual.glb",
                "visual_only",
                "Identity in the authored convention; floor/ceiling mesh layers, with the visual shell separately declared in the route report and rendered procedurally.",
            ),
            "collision": authored_asset(
                f"{GENERATED}/early_pocket_collision.glb",
                "collision_only",
                "Closed standalone authored room collision; no column, registration, or calibrated scale.",
            ),
        },
        "coordinate_frame": {
            "id": "issue148-early-pocket-authored-convention",
            "units": "convention_meters_not_calibrated",
            "handedness": "right_handed",
            "up_axis": "+Y",
            "transform_status": "uncalibrated_convention",
            "registration_accepted": False,
            "scale_calibrated": False,
            "scale_basis": "Authored 2.4 m wall-height convention reused from #100; not surveyed.",
            "transform_evidence": file_reference(manifest),
            "registration_evidence": None,
            "scale_evidence": None,
        },
        "floor_ceiling": {
            "floor": {
                "status": "authored_tested",
                "origin": "Authored early-pocket route floor.",
                "elevation_m": floor_y,
                "assumed_clear_height_m": None,
                "basis": "Same uncalibrated #100 Y convention as route harness; not measured from footage.",
                "collision_role": "Continuous walkable floor in standalone collision GLB.",
            },
            "ceiling": {
                "status": "authored_visual_unverified",
                "origin": "Authored visual convention, not source reconstruction.",
                "elevation_m": None,
                "assumed_clear_height_m": 2.4,
                "basis": "Authored shell height for review; not measured from footage.",
                "collision_role": "Visual only; no ceiling collider.",
            },
        },
        "observed_openings": [{
            "id": "issue145-opening-candidate-c",
            "inventory_catalog_id": "C",
            "frame_start": 13,
            "frame_end": 27,
            "description": "A broad gap between patterned partition ends is visible; the camera does not establish threshold traversal or what lies beyond.",
            "traversability": "visually_open",
            "module_relation": "unregistered",
        }],
        "connector_sockets": [connector_socket(
            EARLY_SOCKET_ID,
            "Authored west-wall socket only in the #148 assembly adaptation; the standalone wall stays closed and no video doorway is claimed.",
            [0.0, floor_y + 1.2, 9.0],
        )],
        "tested_connectors": [tested_connector(
            "issue148-early-pocket-to-later-bay",
            EARLY_SOCKET_ID,
            LATER_ID,
            LATER_SOCKET_ID,
        )],
        "boundary_rules": [
            boundary_rule(
                "issue148-early-pocket-floor",
                "floor",
                "AuthoredPlanarRouteFloor",
                "Continuous authored floor for the 6.0 x 13.8 convention-unit standalone pocket.",
            ),
            *walls,
        ],
        "shared_controller": shared_controller,
        "validation_evidence": validation_evidence(),
        "runtime_measurements": runtime_measurements(),
    }
