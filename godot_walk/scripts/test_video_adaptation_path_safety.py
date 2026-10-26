"""Regression coverage for safe receipt paths and immutable validation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import (
    create_new_file,
    receipt_file,
    receipt_files,
    validate_adaptation_id,
)
from video_adaptation_validation import ROOT, sha256_file, validate_bundle

BUNDLES = [
    ROOT / "godot_walk/room_catalog/adaptations/room-large-v1.json",
    ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json",
]


class ReceiptPathSafetyTests(unittest.TestCase):
    def test_absolute_and_traversal_adaptation_ids_are_rejected(self) -> None:
        for value in ("/tmp/out", "../escape", "a/b", "a\\b", ".."):
            with (
                self.subTest(value=value),
                self.assertRaises(AdaptationValidationError),
            ):
                validate_adaptation_id(value)

    def test_receipt_read_and_write_reject_directory_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            base = root / "adaptations"
            outside = Path(temporary) / "outside"
            base.mkdir(parents=True)
            outside.mkdir()
            bundle = base / "record.json"
            bundle.write_text("{}", encoding="utf-8")
            receipts = base / "stage_receipts"
            receipts.mkdir()
            (receipts / "fixture-room").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(AdaptationValidationError):
                receipt_file(
                    bundle, "fixture-room", "capture", root, create_directory=True
                )
            with self.assertRaises(AdaptationValidationError):
                receipt_files(bundle, "fixture-room", root)

    def test_existing_receipt_file_cannot_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            base = root / "adaptations"
            base.mkdir(parents=True)
            bundle = base / "record.json"
            bundle.write_text("{}", encoding="utf-8")
            receipt = receipt_file(
                bundle, "fixture-room", "capture", root, create_directory=True
            )
            create_new_file(receipt, b"first")
            with self.assertRaises(FileExistsError):
                create_new_file(receipt, b"replacement")


class ReadOnlyValidationTests(unittest.TestCase):
    def test_both_real_examples_validate_without_mutating_decisions_or_freezes(
        self,
    ) -> None:
        snapshot = (
            ROOT
            / "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.2.0.json"
        )
        protected = [
            *BUNDLES,
            snapshot,
            ROOT / "godot_walk/room_catalog/contract_freeze_v1.json",
            ROOT / "godot_walk/room_catalog/contract_freeze_v2.json",
            ROOT / "godot_walk/evidence/2026-10-24-issue-164/operator_review.json",
            ROOT / "godot_walk/evidence/2026-10-25-issue-165/operator_review.json",
        ]
        before = {path: sha256_file(path) for path in protected}
        validated = [validate_bundle(path) for path in BUNDLES]
        after = {path: sha256_file(path) for path in protected}
        self.assertEqual(before, after)
        self.assertTrue(
            all(
                record["operator_decision"]["status"] == "accepted"
                for record, _ in validated
            )
        )
        self.assertTrue(
            all(record["registration_accepted"] is False for record, _ in validated)
        )
        self.assertTrue(
            all(record["scale_calibrated"] is False for record, _ in validated)
        )


if __name__ == "__main__":
    unittest.main()
