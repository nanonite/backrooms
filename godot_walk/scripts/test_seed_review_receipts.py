"""Append-only receipt, fingerprint, and schema tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_review_errors import SeedReviewError
from seed_review_paths import sha256_text
from seed_review_provider import ModelIdentity, ModelInvocation, ProviderResponse
from seed_review_receipts import (
    finalize_receipt,
    find_existing_receipt,
    write_receipt,
)
from seed_review_runner import run_seed_review
from seed_review_schemas import validate_receipt
from seed_review_test_support import (
    build_fake_repo,
    make_candidate,
    request_document,
    response_document,
)
from seed_review_workflow import load_workflow_spec

FIXED_NOW = "2026-11-02T00:00:00+00:00"


class StaticModel:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[ModelInvocation] = []

    def invoke(self, invocation: ModelInvocation) -> ProviderResponse:
        self.calls.append(invocation)
        return ProviderResponse(
            status="completed",
            raw_text=json.dumps(self.response),
            usage_payload=None,
            error=None,
            elapsed_seconds=0.1,
            command=("mock",),
        )


class SeedReviewReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        manifest, self.frame_dir = build_fake_repo(self.root)
        self.source_id = manifest["source_id"]
        self.source_sha256 = manifest["canonical_video"]["sha256"]
        self.receipts_dir = self.root / "godot_walk/evidence/test-receipts"
        self.spec = load_workflow_spec(self.root)
        self.identity = ModelIdentity(
            provider="mock",
            model="bounded-vl",
            image_input_supported=True,
            image_input_support_basis="unit_test_assertion",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, indexes: list[int]) -> object:
        candidates = [
            make_candidate(self.root, self.frame_dir, index) for index in indexes
        ]
        document = request_document(self.source_id, self.source_sha256, candidates)
        model = StaticModel(response_document("frame_0000", [], 4))
        return run_seed_review(
            source_id=self.source_id,
            request_document=document,
            identity=self.identity,
            root=self.root,
            spec=self.spec,
            model=model,
            enable_model=True,
            receipts_dir=self.receipts_dir,
            timeout_seconds=30,
            now=lambda: FIXED_NOW,
        )

    def test_receipt_binds_source_frame_prompt_timeout_and_usage(self) -> None:
        run = self._run([0, 1, 2])
        receipt = run.receipt
        self.assertEqual(self.source_id, receipt["source"]["source_id"])
        self.assertEqual(self.source_sha256, receipt["source"]["video_sha256"])
        self.assertEqual(3, len(receipt["candidate_set"]["candidates"]))
        for candidate in receipt["candidate_set"]["candidates"]:
            self.assertIn("sha256", candidate)
        self.assertEqual(
            sha256_text(receipt["prompt"]["text"]), receipt["prompt"]["sha256"]
        )
        self.assertEqual(30, receipt["request"]["timeout_seconds"])
        self.assertFalse(receipt["usage"]["reported"])
        self.assertIsNone(receipt["usage"]["actual_cost_usd"])
        self.assertFalse(receipt["guards"]["registration_accepted"])
        self.assertFalse(receipt["guards"]["scale_calibrated"])
        self.assertFalse(receipt["next_stage_authorized"])

    def test_identical_receipt_is_refused(self) -> None:
        run = self._run([0, 1, 2])
        original = run.receipt_path.read_bytes()
        with self.assertRaises(SeedReviewError) as caught:
            write_receipt(run.receipt, self.receipts_dir, self.root)
        self.assertEqual("receipt_exists", caught.exception.code)
        self.assertEqual(original, run.receipt_path.read_bytes())

    def test_index_appends_and_preserves_prior_records(self) -> None:
        first = self._run([0, 1, 2])
        index_path = first.receipt_path.parent / "receipts.jsonl"
        first_index_bytes = index_path.read_bytes()
        second = self._run([3, 4, 5])
        content = index_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertEqual(2, len(lines))
        self.assertEqual(first_index_bytes, (lines[0] + "\n").encode("utf-8"))
        records = [json.loads(line) for line in lines]
        self.assertEqual([1, 2], [record["sequence"] for record in records])
        self.assertEqual(first.receipt["receipt_id"], records[0]["receipt_id"])
        self.assertEqual(second.receipt["receipt_id"], records[1]["receipt_id"])
        self.assertEqual(
            second.receipt_path.relative_to(self.root).as_posix(),
            records[1]["path"],
        )

    def test_find_existing_receipt_matches_input_fingerprint(self) -> None:
        run = self._run([0, 1, 2])
        record = find_existing_receipt(
            self.receipts_dir,
            self.source_id,
            run.receipt["input_fingerprint"],
            self.root,
        )
        self.assertIsNotNone(record)
        self.assertEqual(
            run.receipt_path.relative_to(self.root).as_posix(), record["path"]
        )

    def test_corrupt_index_is_refused_before_append(self) -> None:
        first = self._run([0, 1, 2])
        index_path = first.receipt_path.parent / "receipts.jsonl"
        index_path.write_text(
            index_path.read_text(encoding="utf-8") + '{"partial":',
            encoding="utf-8",
        )
        with self.assertRaises(SeedReviewError) as caught:
            self._run([3, 4, 5])
        self.assertEqual("receipt_index_corrupt", caught.exception.code)

    def test_missing_prompt_hash_fails_receipt_schema(self) -> None:
        run = self._run([0, 1, 2])
        receipt = json.loads(json.dumps(run.receipt))
        del receipt["prompt"]["sha256"]
        with self.assertRaises(SeedReviewError) as caught:
            validate_receipt(receipt, self.spec)
        self.assertEqual("schema_violation", caught.exception.code)

    def test_receipt_id_is_deterministic_over_body(self) -> None:
        run = self._run([0, 1, 2])
        without_id = {
            key: value for key, value in run.receipt.items() if key != "receipt_id"
        }
        first = finalize_receipt(without_id)
        second = finalize_receipt(without_id)
        self.assertEqual(first["receipt_id"], second["receipt_id"])
        changed = dict(without_id)
        changed["status"] = "abstained"
        self.assertNotEqual(
            first["receipt_id"], finalize_receipt(changed)["receipt_id"]
        )

    def test_receipt_directory_must_stay_in_repository(self) -> None:
        run = self._run([0, 1, 2])
        outside = self.root.parent / "outside-receipts"
        with self.assertRaises(SeedReviewError) as caught:
            write_receipt(run.receipt, outside, self.root)
        self.assertEqual("unsafe_receipt_path", caught.exception.code)
        self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
