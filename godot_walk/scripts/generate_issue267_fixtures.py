"""Generate the CPU-only synthetic fixtures for Chainlink issue 267.

This writes new files only, under the issue's evidence folder. It never writes
ledger events, receipts or hash sidecars, and it refuses to overwrite a fixture
whose bytes differ from the deterministic derivation.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from deterministic_json import write_deterministic

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = (
    ROOT / "godot_walk/evidence/2026-11-17-issue-267-open-scene-contract/fixtures"
)

BASE_CANDIDATE: dict[str, Any] = {
    "schema_version": 1,
    "contract_id": "godot_open_scene_coverage",
    "contract_version": "1.0.0",
    "candidate_id": "synthetic-open-field-v1",
    "status": "candidate_pending_review",
    "scene_category": "open_world",
    "registration_accepted": False,
    "scale_calibrated": False,
    "catalog_scope": "not_admitted_pending_integration_design",
    "coverage": {
        "representation": "simple_orthogonal_polygon_xz",
        "vertices_xz": [[0, 0], [12, 0], [12, 9], [0, 9]],
        "floor_elevation": 0.0,
        "basis": "authored",
        "evidence_ref": "synthetic:no_real_source",
    },
    "safe_spawn_xyz": [6.0, 0.0, 4.5],
    "exterior_classification": "unknown",
    "visual_horizon": {
        "open_sky": True,
        "visual_only": True,
        "is_observed_geometry": False,
        "notes": "synthetic panorama stand-in, appearance only",
    },
    "boundary": {
        "wall_ring_present": False,
        "boundary_collider_present": False,
        "edge_is_observed_geometry": False,
        "coverage_limit_representation": "nonphysical_coverage_edge",
        "exits": [
            {
                "kind": "coverage_limit",
                "destination_classification": "unknown",
                "observed": False,
                "notes": "no claimed or observed destination",
            }
        ],
    },
    "obstacles": [
        {
            "id": "authored-rock-a",
            "provenance": "authored",
            "evidence_ref": "synthetic:no_real_source",
            "notes": "authored stand-in, not measured",
        }
    ],
    "traversal_policy": {
        "policy": "stop",
        "coverage_indication": {
            "kind": "coverage_limit_reached",
            "player_facing_text": "Coverage limit reached - no mapped ground beyond this point.",
        },
    },
    "provenance": {
        "source_kind": "synthetic_fixture",
        "scale_status": "uncalibrated",
        "connectivity_status": "unknown",
        "notes": "CPU-only synthetic fixture; no real source, no model, no operator acceptance",
    },
    "synthetic_fixture": True,
}

BASE_CATEGORY: dict[str, Any] = {
    "schema_version": 1,
    "contract_id": "godot_intake_scene_category",
    "contract_version": "1.0.0",
    "source_id": "video-0000000000000001",
    "source_manifest_path": "data/videos/synthetic.mp4",
    "category": "enclosed",
    "review": {
        "state": "operator_reviewed",
        "reviewer": "synthetic-test-double-not-a-real-operator",
        "decision_record": "synthetic:no_real_decision_record",
        "recorded_at_utc": "2026-11-17T00:00:00Z",
        "notes": "synthetic review stand-in used only to exercise routing logic",
    },
    "provenance": {
        "basis": "observed",
        "evidence_ref": "synthetic:no_real_source",
        "notes": "CPU-only fixture",
    },
    "synthetic_fixture": True,
}


def _candidate(**mutations: Any) -> dict[str, Any]:
    return copy.deepcopy(BASE_CANDIDATE)


def _category(**mutations: Any) -> dict[str, Any]:
    return copy.deepcopy(BASE_CATEGORY)


def candidate_fixtures() -> dict[str, dict[str, Any]]:
    fixtures: dict[str, dict[str, Any]] = {
        "valid_open_scene_v1.json": _candidate(),
    }

    return_policy = _candidate()
    return_policy["traversal_policy"]["policy"] = "return"
    fixtures["valid_return_policy_v1.json"] = return_policy

    missing_spawn = _candidate()
    del missing_spawn["safe_spawn_xyz"]
    fixtures["invalid_missing_spawn_v1.json"] = missing_spawn

    outside_spawn = _candidate()
    outside_spawn["safe_spawn_xyz"] = [20.0, 0.0, 20.0]
    fixtures["invalid_spawn_outside_v1.json"] = outside_spawn

    edge_spawn = _candidate()
    edge_spawn["safe_spawn_xyz"] = [0.0, 0.0, 4.5]
    fixtures["invalid_spawn_on_edge_v1.json"] = edge_spawn

    missing_exterior = _candidate()
    del missing_exterior["exterior_classification"]
    fixtures["invalid_missing_exterior_v1.json"] = missing_exterior

    enclosed_exterior = _candidate()
    enclosed_exterior["exterior_classification"] = "enclosed"
    fixtures["invalid_contradictory_exterior_v1.json"] = enclosed_exterior

    wall_ring = _candidate()
    wall_ring["boundary"]["wall_ring_present"] = True
    wall_ring["boundary"]["boundary_collider_present"] = True
    fixtures["invalid_wall_ring_v1.json"] = wall_ring

    edge_obstacle = _candidate()
    edge_obstacle["obstacles"] = [
        {
            "id": "coverage-edge-as-rock",
            "provenance": "observed",
            "evidence_ref": "synthetic:no_real_source",
            "is_coverage_edge": True,
        }
    ]
    fixtures["invalid_observed_edge_obstacle_v1.json"] = edge_obstacle

    missing_policy = _candidate()
    del missing_policy["traversal_policy"]
    fixtures["invalid_missing_policy_v1.json"] = missing_policy

    missing_indication = _candidate()
    del missing_indication["traversal_policy"]["coverage_indication"]
    fixtures["invalid_missing_indication_v1.json"] = missing_indication

    calibration = _candidate()
    calibration["registration_accepted"] = True
    calibration["scale_calibrated"] = True
    fixtures["invalid_calibration_flags_v1.json"] = calibration

    catalog = _candidate()
    catalog["catalog_scope"] = "admitted"
    fixtures["invalid_catalog_admission_v1.json"] = catalog

    diagonal = _candidate()
    diagonal["coverage"]["vertices_xz"] = [[0, 0], [12, 0], [12, 9], [6, 4]]
    diagonal["safe_spawn_xyz"] = [6.0, 0.0, 3.0]
    fixtures["invalid_non_orthogonal_v1.json"] = diagonal

    accepted = _candidate()
    accepted["status"] = "accepted_reference"
    fixtures["invalid_accepted_reference_v1.json"] = accepted

    observed_destination = _candidate()
    observed_destination["boundary"]["exits"][0]["destination_classification"] = (
        "observed"
    )
    observed_destination["boundary"]["exits"][0]["observed"] = True
    fixtures["invalid_observed_destination_v1.json"] = observed_destination

    return fixtures


def category_fixtures() -> dict[str, dict[str, Any]]:
    fixtures: dict[str, dict[str, Any]] = {
        "category_enclosed_reviewed_v1.json": _category(),
    }

    open_reviewed = _category()
    open_reviewed["category"] = "open_world"
    fixtures["category_open_world_reviewed_v1.json"] = open_reviewed

    open_pending = _category()
    open_pending["category"] = "open_world"
    open_pending["review"] = {"state": "pending"}
    fixtures["category_open_world_pending_v1.json"] = open_pending

    unknown = _category()
    unknown["category"] = "unknown"
    fixtures["category_unknown_v1.json"] = unknown

    invalid_value = _category()
    invalid_value["category"] = "outdoor"
    fixtures["category_invalid_value_v1.json"] = invalid_value

    unknown_basis = _category()
    unknown_basis["category"] = "open_world"
    unknown_basis["provenance"]["basis"] = "unknown"
    fixtures["category_reviewed_unknown_basis_v1.json"] = unknown_basis

    missing_decision = _category()
    missing_decision["category"] = "open_world"
    del missing_decision["review"]["decision_record"]
    fixtures["category_reviewed_missing_decision_v1.json"] = missing_decision

    fixtures["legacy_manifest_v1.json"] = {
        "schema_version": 1,
        "source_id": "video-legacy00000001",
    }
    fixtures["open_world_manifest_v1.json"] = {
        "schema_version": 3,
        "source_id": "video-0000000000000001",
        "source_kind": "video",
    }
    fixtures["categorised_manifest_without_record_v1.json"] = {
        "schema_version": 3,
        "source_id": "video-0000000000000001",
        "scene_category": "open_world",
    }
    return fixtures


def main() -> int:
    created = 0
    for name, record in {**candidate_fixtures(), **category_fixtures()}.items():
        status = write_deterministic(FIXTURES / name, _bytes(record))
        if status == "created":
            created += 1
    print(f"fixtures directory: {FIXTURES.relative_to(ROOT)}")
    print(f"created {created} new files; all others matched their derived bytes")
    return 0


def _bytes(record: dict[str, Any]) -> bytes:
    import json

    return (
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
