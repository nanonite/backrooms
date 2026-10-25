"""Contract and safety tests for the read-only adaptation workflow."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import video_adaptation_runner
from video_adaptation_validation import (
    ROOT,
    canonical_fingerprint,
    sha256_file,
    validate_bundle,
)


REFERENCE_BUNDLE = ROOT / "godot_walk/room_catalog/adaptations/room-large-v1.json"
TRANSFER_BUNDLE = ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json"


class VideoAdaptationWorkflowTests(unittest.TestCase):
    def test_both_fixture_records_validate_without_rewriting_them(self) -> None:
        before = {path: sha256_file(path) for path in (REFERENCE_BUNDLE, TRANSFER_BUNDLE)}
        reference, _ = validate_bundle(REFERENCE_BUNDLE)
        transfer, _ = validate_bundle(TRANSFER_BUNDLE)
        after = {path: sha256_file(path) for path in (REFERENCE_BUNDLE, TRANSFER_BUNDLE)}

        self.assertEqual(before, after)
        self.assertEqual(reference["operator_decision"]["status"], "accepted")
        self.assertEqual(transfer["operator_decision"]["status"], "accepted")
        self.assertFalse(transfer["registration_accepted"])
        self.assertFalse(transfer["scale_calibrated"])

    def test_candidate_fingerprint_changes_with_dependency_hash(self) -> None:
        original = [{"path": "candidate.tscn", "sha256": "a" * 64, "role": "scene"}]
        changed = [{"path": "candidate.tscn", "sha256": "b" * 64, "role": "scene"}]

        self.assertNotEqual(canonical_fingerprint(original), canonical_fingerprint(changed))

    def test_stage_output_cannot_escape_repository(self) -> None:
        with self.assertRaises(ValueError):
            video_adaptation_runner._relative_output("../outside.json")

    def test_stage_refuses_an_existing_output_before_launching_tool(self) -> None:
        arguments = argparse.Namespace(
            bundle=TRANSFER_BUNDLE,
            stage="overwrite_guard_test",
            output=["PLAN.md"],
            requires_gpu=False,
            command=["python3", "-c", "raise SystemExit(99)"],
            timeout_seconds=1,
            expect_exit_code=0,
        )
        with self.assertRaises(FileExistsError):
            video_adaptation_runner._run_tool(arguments)

    def test_stale_stage_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "adaptation.json"
            receipt_dir = Path(temporary) / "stage_receipts" / "candidate-v1"
            receipt_dir.mkdir(parents=True)
            receipt = {
                "candidate_fingerprint": "0" * 64,
                "artifacts": [],
            }
            (receipt_dir / "old.json").write_text(json.dumps(receipt), encoding="utf-8")
            with patch("video_adaptation_validation._verify_artifacts"):
                with self.assertRaisesRegex(ValueError, "Stage receipt is stale"):
                    from video_adaptation_validation import _verify_stage_receipts

                    _verify_stage_receipts(bundle, "candidate-v1", "1" * 64)


if __name__ == "__main__":
    unittest.main()
