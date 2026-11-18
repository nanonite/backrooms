"""Tests for the versioned intake scene category and its routing gate."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scene_category_v1 as category

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = (
    ROOT / "godot_walk/evidence/2026-11-17-issue-267-open-scene-contract/fixtures"
)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class SceneCategoryV1Tests(unittest.TestCase):
    def test_valid_category_records_pass_validation(self) -> None:
        for name in (
            "category_enclosed_reviewed_v1.json",
            "category_open_world_reviewed_v1.json",
            "category_open_world_pending_v1.json",
            "category_unknown_v1.json",
        ):
            with self.subTest(name=name):
                self.assertEqual(category.validate(load(name)), [])

    def test_invalid_category_value_is_rejected(self) -> None:
        errors = category.validate(load("category_invalid_value_v1.json"))
        self.assertTrue(any("Unknown scene category" in error for error in errors))

    def test_reviewed_open_world_needs_non_unknown_provenance(self) -> None:
        errors = category.validate(load("category_reviewed_unknown_basis_v1.json"))
        self.assertTrue(any("non-unknown basis" in error for error in errors))

    def test_operator_reviewed_state_needs_a_decision_record(self) -> None:
        errors = category.validate(load("category_reviewed_missing_decision_v1.json"))
        self.assertTrue(any("decision_record" in error for error in errors))

    def test_legacy_manifest_routes_to_enclosed_without_rewrite(self) -> None:
        manifest = load("legacy_manifest_v1.json")
        original = copy.deepcopy(manifest)
        result = category.route_source(manifest)
        self.assertEqual(manifest, original)
        self.assertEqual(result["route"], category.ROUTE_ENCLOSED)
        self.assertEqual(result["category_source"], "legacy_default")
        self.assertEqual(result["review_state"], "not_applicable")
        self.assertFalse(result["can_enter_open_world"])

    def test_reviewed_open_world_is_released(self) -> None:
        result = category.route_source(
            load("open_world_manifest_v1.json"),
            load("category_open_world_reviewed_v1.json"),
        )
        self.assertEqual(result["route"], category.ROUTE_OPEN_WORLD)
        self.assertTrue(result["can_enter_open_world"])

    def test_pending_open_world_is_held_not_admitted(self) -> None:
        result = category.route_source(
            load("open_world_manifest_v1.json"),
            load("category_open_world_pending_v1.json"),
        )
        self.assertEqual(result["route"], category.ROUTE_OPEN_WORLD_HOLD)
        self.assertFalse(result["can_enter_open_world"])

    def test_unknown_category_defaults_to_enclosed(self) -> None:
        result = category.route_source(
            load("open_world_manifest_v1.json"), load("category_unknown_v1.json")
        )
        self.assertEqual(result["route"], category.ROUTE_ENCLOSED)
        self.assertFalse(result["can_enter_open_world"])

    def test_enclosed_category_routes_to_enclosed(self) -> None:
        result = category.route_source(
            load("open_world_manifest_v1.json"),
            load("category_enclosed_reviewed_v1.json"),
        )
        self.assertEqual(result["route"], category.ROUTE_ENCLOSED)
        self.assertFalse(result["can_enter_open_world"])

    def test_categorised_manifest_without_versioned_record_is_rejected(self) -> None:
        with self.assertRaisesRegex(category.SceneCategoryError, "versioned"):
            category.route_source(load("categorised_manifest_without_record_v1.json"))

    def test_source_id_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(category.SceneCategoryError, "source_id"):
            category.route_source(
                load("legacy_manifest_v1.json"),
                load("category_open_world_reviewed_v1.json"),
            )

    def test_validate_file_reports_actionable_error(self) -> None:
        with self.assertRaisesRegex(
            category.SceneCategoryError, "Unknown scene category"
        ):
            category.validate_file(FIXTURES / "category_invalid_value_v1.json")


if __name__ == "__main__":
    unittest.main()
