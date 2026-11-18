"""Tests for the versioned open-scene coverage contract (CPU-only)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import open_scene_contract_v1 as open_scene
import video_adaptation_validation as room_validation
from deterministic_json import sha256_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = (
    ROOT / "godot_walk/evidence/2026-11-17-issue-267-open-scene-contract/fixtures"
)
VALID = "valid_open_scene_v1.json"
REFERENCE_BUNDLE = ROOT / "godot_walk/room_catalog/adaptations/room-large-v1.json"
TRANSFER_BUNDLE = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"
FROZEN_FILES = (
    "godot_walk/room_catalog/catalog.json",
    "godot_walk/room_catalog/contract_freeze_v3.json",
    "godot_walk/room_catalog/contract_freeze_v4.json",
    "godot_walk/room_catalog/video_adaptation.schema.v3.json",
    "godot_walk/room_catalog/video_adaptation_contract_v3.md",
    "godot_walk/room_catalog/MATERIAL_LANGUAGE.md",
    "godot_walk/room_catalog/material_palettes/PALETTES.md",
    "godot_walk/scripts/player.gd",
    "godot_walk/project.godot",
)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class OpenSceneContractV1Tests(unittest.TestCase):
    def test_contract_default_policy_is_stop(self) -> None:
        policy = open_scene.default_traversal_policy()
        self.assertEqual(policy["policy"], "stop")
        self.assertEqual(open_scene.DEFAULT_TRAVERSAL_POLICY, "stop")
        self.assertTrue(policy["coverage_indication"]["player_facing_text"])

    def test_valid_fixtures_pass(self) -> None:
        for name in (VALID, "valid_return_policy_v1.json"):
            with self.subTest(name=name):
                self.assertEqual(open_scene.validate(load(name)), [])

    def test_valid_fixture_is_an_unaccepted_synthetic_candidate(self) -> None:
        record = load(VALID)
        self.assertEqual(record["status"], "candidate_pending_review")
        self.assertFalse(record["registration_accepted"])
        self.assertFalse(record["scale_calibrated"])
        self.assertEqual(
            record["catalog_scope"], "not_admitted_pending_integration_design"
        )
        self.assertTrue(record["synthetic_fixture"])
        self.assertEqual(record["provenance"]["scale_status"], "uncalibrated")
        self.assertEqual(record["provenance"]["connectivity_status"], "unknown")

    def test_valid_fixture_declares_stop_indication_and_no_wall_ring(self) -> None:
        record = load(VALID)
        self.assertEqual(record["traversal_policy"]["policy"], "stop")
        self.assertTrue(
            record["traversal_policy"]["coverage_indication"]["player_facing_text"]
        )
        self.assertFalse(record["boundary"]["wall_ring_present"])
        self.assertFalse(record["boundary"]["boundary_collider_present"])
        self.assertFalse(record["boundary"]["edge_is_observed_geometry"])

    def test_negative_fixtures_fail_with_actionable_diagnostics(self) -> None:
        cases = {
            "invalid_missing_spawn_v1.json": "safe_spawn_xyz",
            "invalid_spawn_outside_v1.json": "not strictly inside",
            "invalid_spawn_on_edge_v1.json": "not strictly inside",
            "invalid_missing_exterior_v1.json": "Missing exterior classification",
            "invalid_contradictory_exterior_v1.json": "Exterior classification must be",
            "invalid_wall_ring_v1.json": "wall ring",
            "invalid_observed_edge_obstacle_v1.json": "coverage edge",
            "invalid_missing_policy_v1.json": "Missing traversal_policy",
            "invalid_missing_indication_v1.json": "Missing coverage indication",
            "invalid_calibration_flags_v1.json": "calibration flags",
            "invalid_catalog_admission_v1.json": "not admitted to the room catalog",
            "invalid_non_orthogonal_v1.json": "axis-aligned",
            "invalid_accepted_reference_v1.json": "cannot be an accepted reference",
            "invalid_observed_destination_v1.json": "destination_classification",
        }
        for name, needle in cases.items():
            with self.subTest(name=name):
                errors = open_scene.validate(load(name))
                self.assertTrue(errors, f"{name} should be rejected")
                self.assertTrue(
                    any(needle in error for error in errors),
                    f"{name}: expected {needle!r} in {errors}",
                )

    def test_room_contract_record_cannot_be_reinterpreted(self) -> None:
        room_record = json.loads(REFERENCE_BUNDLE.read_text(encoding="utf-8"))
        errors = open_scene.validate(room_record)
        self.assertTrue(
            any("Enclosed room-contract records" in error for error in errors), errors
        )

    def test_existing_room_contract_results_are_unchanged(self) -> None:
        before = {
            path: sha256_file(path) for path in (REFERENCE_BUNDLE, TRANSFER_BUNDLE)
        }
        reference, _ = room_validation.validate_bundle(REFERENCE_BUNDLE)
        transfer, _ = room_validation.validate_bundle(TRANSFER_BUNDLE)
        after = {
            path: sha256_file(path) for path in (REFERENCE_BUNDLE, TRANSFER_BUNDLE)
        }
        self.assertEqual(before, after)
        self.assertEqual(reference["operator_decision"]["status"], "accepted")
        self.assertEqual(transfer["operator_decision"]["status"], "accepted")
        self.assertFalse(transfer["registration_accepted"])
        self.assertFalse(transfer["scale_calibrated"])

    def test_frozen_files_are_unchanged_by_both_validators(self) -> None:
        paths = [ROOT / relative for relative in FROZEN_FILES]
        before = {path: sha256_file(path) for path in paths}
        open_scene.validate(load(VALID))
        room_validation.validate_bundle(REFERENCE_BUNDLE)
        after = {path: sha256_file(path) for path in paths}
        self.assertEqual(before, after)

    def test_validate_file_reports_all_errors(self) -> None:
        with self.assertRaisesRegex(
            open_scene.OpenSceneContractError, "safe_spawn_xyz"
        ):
            open_scene.validate_file(FIXTURES / "invalid_missing_spawn_v1.json")


if __name__ == "__main__":
    unittest.main()
