"""Schema checks for the Hunyuan PSX round and operator decision records."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot_walk" / "scripts"))
from hunyuan_round1_records import validate_document, validate_feedback_for_round

PROJECT = ROOT / "godot_walk"


class HunyuanRoundSchemaTests(unittest.TestCase):
    def test_round_one_variant_specs_validate(self) -> None:
        schema = PROJECT / "design_variants" / "hunyuan" / "variant.schema.json"
        for name in ("round-1-preserve.json", "round-1-source-surface-cleanup.json"):
            with self.subTest(variant=name):
                document = json.loads(
                    (schema.parent / name).read_text(encoding="utf-8")
                )
                validate_document(document, schema)

    def test_round_two_variant_specs_validate(self) -> None:
        schema = PROJECT / "design_variants" / "hunyuan" / "variant.schema.json"
        variant_dir = PROJECT / "design_variants" / "hunyuan" / "round-2"
        for name in ("preserve_hunyuan.json", "column_box_source_face.json"):
            with self.subTest(variant=name):
                document = json.loads((variant_dir / name).read_text(encoding="utf-8"))
                validate_document(document, schema)

    def test_round_two_feedback_coverage_uses_round_specific_variants(self) -> None:
        feedback = _confirmed_feedback()
        feedback["round_id"] = "hunyuan-psx-r2"
        for choice in feedback["view_choices"]:
            if choice["choice"] == "source_surface_cleanup":
                choice["choice"] = "column_box_source_face"
        feedback["variant_decisions"][1]["variant_id"] = "column_box_source_face"
        validate_document(
            feedback, PROJECT / "design_rounds" / "operator_feedback.schema.json"
        )
        validate_feedback_for_round(
            feedback, _round_manifest_for_feedback("hunyuan-psx-r2")
        )

    def test_pending_feedback_is_valid_but_not_a_decision(self) -> None:
        pending = {
            "schema_version": 1,
            "round_id": "hunyuan-psx-r1",
            "status": "pending_operator_review",
            "reviewer_timestamp": None,
        }
        schema_path = PROJECT / "design_rounds" / "operator_feedback.schema.json"
        validate_document(pending, schema_path)
        pending["status"] = "confirmed"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(pending)

    def test_confirmed_feedback_requires_reasoned_decisions(self) -> None:
        feedback = _confirmed_feedback()
        schema = PROJECT / "design_rounds" / "operator_feedback.schema.json"
        validate_document(feedback, schema)
        feedback["confidence"] = 6
        with self.assertRaises(ValidationError):
            validate_document(feedback, schema)

    def test_confirmed_feedback_requires_complete_view_and_variant_coverage(
        self,
    ) -> None:
        feedback = _confirmed_feedback()
        feedback["view_choices"].pop()
        with self.assertRaises(ValueError):
            validate_feedback_for_round(
                feedback, _round_manifest_for_feedback("hunyuan-psx-r1")
            )
        feedback = _confirmed_feedback()
        feedback["variant_decisions"][1]["variant_id"] = "preserve_hunyuan"
        with self.assertRaises(ValueError):
            validate_feedback_for_round(
                feedback, _round_manifest_for_feedback("hunyuan-psx-r1")
            )

    def test_feedback_coverage_accepts_round_specific_ids(self) -> None:
        feedback = _confirmed_feedback()
        feedback["round_id"] = "hunyuan-psx-r3"
        feedback["view_choices"][0]["view_id"] = "ceiling_corner"
        feedback["variant_decisions"][1]["variant_id"] = "source_texture_ceiling"
        for choice in feedback["view_choices"]:
            if choice["choice"] == "source_surface_cleanup":
                choice["choice"] = "source_texture_ceiling"
        manifest = _round_manifest_for_feedback("hunyuan-psx-r3")
        manifest["capture"]["view_ids"][0] = "ceiling_corner"
        manifest["variants"][1]["variant_id"] = "source_texture_ceiling"
        validate_document(
            feedback, PROJECT / "design_rounds" / "operator_feedback.schema.json"
        )
        validate_feedback_for_round(feedback, manifest)

    def test_feedback_rejects_choice_not_in_round_variants(self) -> None:
        feedback = _confirmed_feedback()
        feedback["view_choices"][0]["choice"] = "invented_variant"
        with self.assertRaisesRegex(ValueError, "name a manifest variant"):
            validate_feedback_for_round(
                feedback, _round_manifest_for_feedback("hunyuan-psx-r1")
            )

    def test_existing_confirmed_rounds_validate_against_their_manifests(self) -> None:
        for suffix in ("1", "2"):
            bundle = PROJECT / "evidence" / f"2026-10-21-issue-151-round-{suffix}"
            manifest = json.loads((bundle / "round_manifest.json").read_text())
            feedback = json.loads((bundle / "operator_feedback.json").read_text())
            validate_document(
                manifest, PROJECT / "design_rounds" / "hunyuan_round.schema.json"
            )
            validate_document(
                feedback, PROJECT / "design_rounds" / "operator_feedback.schema.json"
            )
            validate_feedback_for_round(feedback, manifest)

    def test_round_schema_pins_unaccepted_registration_and_scale(self) -> None:
        record = _valid_round_record()
        schema = PROJECT / "design_rounds" / "hunyuan_round.schema.json"
        validate_document(record, schema)
        record["convention"]["scale_calibrated"] = True
        with self.assertRaises(ValidationError):
            validate_document(record, schema)


def _confirmed_feedback() -> dict:
    return {
        "schema_version": 1,
        "round_id": "hunyuan-psx-r1",
        "status": "confirmed",
        "reviewer_timestamp": "2026-10-21T12:00:00Z",
        "view_choices": [
            {"view_id": view_id, "choice": "tie", "reason": "Equivalent here."}
            for view_id in (
                "patch_anchor",
                "south_end",
                "north_end",
                "west_wall",
                "east_wall",
                "column_south",
                "column_north",
                "column_west",
                "column_east",
            )
        ],
        "variant_decisions": [
            {
                "variant_id": variant_id,
                "decision": "iterate",
                "reason": "Keep reviewing this treatment.",
            }
            for variant_id in ("preserve_hunyuan", "source_surface_cleanup")
        ],
        "overall_walkthrough_notes": "The route was stable.",
        "remaining_problems": [],
        "next_round_directives": ["Clean the right wall."],
        "confidence": 4,
    }


def _valid_round_record() -> dict:
    asset = {"path": "asset", "sha256": "a" * 64, "role": "visual"}
    return {
        "schema_version": 1,
        "round_id": "hunyuan-psx-r1",
        "issue": 151,
        "status": "awaiting_operator_review",
        "provenance": {
            "source_video": asset,
            "seed_frame": asset,
            "hunyuan_asset": asset,
            "generation": {
                "model": "model",
                "commit": "hash",
                "panorama": {},
                "scene_generation": {},
                "reused_output": True,
            },
        },
        "convention": {
            "registration_accepted": False,
            "scale_calibrated": False,
            "bounds_m": {},
            "visual_collision_policy": "Hunyuan visual only; collision authored and separately validated",
        },
        "variants": [
            {
                "variant_id": "a",
                "parent_id": None,
                "hypothesis": "keep visuals",
                "region_decisions": [],
                "authored_changes": [],
            },
            {
                "variant_id": "b",
                "parent_id": "a",
                "hypothesis": "cover weak regions",
                "region_decisions": [],
                "authored_changes": [],
            },
        ],
        "capture": {
            "resolution": [960, 540],
            "fov_degrees": 75,
            "settle_frames": 12,
            "view_ids": [],
            "replay_note": "measured",
        },
        "toolchain": {
            "godot": "4.6.3",
            "python": "3.12.0",
            "odiff": "odiff-bin@4.5.0",
        },
        "mechanics": {"walkability_report": {}, "expected_negative_controls": []},
        "review_bundle": {
            "index": "index.html",
            "contact_sheet": "sheet.jpg",
            "layout": "layout.svg",
            "commands": "COMMANDS.md",
            "capture_directories": [],
        },
        "operator_feedback": {
            "path": "operator_feedback.json",
            "status": "pending_operator_review",
        },
    }


def _round_manifest_for_feedback(round_id: str) -> dict:
    if round_id == "hunyuan-psx-r1":
        variants = ["preserve_hunyuan", "source_surface_cleanup"]
    elif round_id == "hunyuan-psx-r2":
        variants = ["preserve_hunyuan", "column_box_source_face"]
    else:
        variants = ["preserve_hunyuan", "source_texture_ceiling"]
    return {
        "round_id": round_id,
        "capture": {
            "view_ids": [
                "patch_anchor",
                "south_end",
                "north_end",
                "west_wall",
                "east_wall",
                "column_south",
                "column_north",
                "column_west",
                "column_east",
            ]
        },
        "variants": [{"variant_id": variant} for variant in variants],
    }


if __name__ == "__main__":
    unittest.main()
