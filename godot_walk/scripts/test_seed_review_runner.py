"""Mocked-model tests for the bounded seed-review runner and receipts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_review_errors import SeedReviewError
from seed_review_provider import (
    ModelIdentity,
    ModelInvocation,
    ProviderResponse,
)
from seed_review_runner import run_seed_review
from seed_review_test_support import (
    build_fake_repo,
    make_candidate,
    request_document,
    response_document,
)
from seed_review_workflow import load_workflow_spec

FIXED_NOW = "2026-11-02T00:00:00+00:00"


class RecordingModel:
    def __init__(
        self,
        response: dict[str, object] | None = None,
        *,
        status: str = "completed",
        error: str | None = None,
        usage: dict[str, object] | None = None,
    ) -> None:
        self.response = response
        self.status = status
        self.error = error
        self.usage = usage
        self.calls: list[ModelInvocation] = []

    def invoke(self, invocation: ModelInvocation) -> ProviderResponse:
        self.calls.append(invocation)
        raw_text = json.dumps(self.response) if self.response is not None else ""
        return ProviderResponse(
            status=self.status,
            raw_text=raw_text,
            usage_payload=self.usage,
            error=self.error,
            elapsed_seconds=0.25,
            command=("mock",),
        )


def free_identity() -> ModelIdentity:
    return ModelIdentity(
        provider="mock",
        model="bounded-vl",
        image_input_supported=True,
        image_input_support_basis="unit_test_assertion",
        is_free=True,
        listed_price_usd=0.0,
        accounting="free_no_charge",
        opencode_version="test-version",
    )


class SeedReviewRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        manifest, self.frame_dir = build_fake_repo(self.root)
        self.source_id = manifest["source_id"]
        self.source_sha256 = manifest["canonical_video"]["sha256"]
        self.receipts_dir = self.root / "godot_walk/evidence/test-receipts"
        self.spec = load_workflow_spec(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _request(self, indexes: list[int]) -> dict[str, object]:
        candidates = [
            make_candidate(self.root, self.frame_dir, index) for index in indexes
        ]
        return request_document(self.source_id, self.source_sha256, candidates)

    def _run(
        self,
        indexes: list[int],
        model: RecordingModel,
        *,
        identity: ModelIdentity | None = None,
        **kwargs: object,
    ) -> object:
        return run_seed_review(
            source_id=self.source_id,
            request_document=self._request(indexes),
            identity=identity or free_identity(),
            root=self.root,
            spec=self.spec,
            model=model,
            enable_model=True,
            receipts_dir=self.receipts_dir,
            timeout_seconds=30,
            now=lambda: FIXED_NOW,
            **kwargs,
        )

    def test_three_frame_review_records_receipt_and_usage_unavailable(self) -> None:
        model = RecordingModel(
            response_document("frame_0001", ["frame_0002", "frame_0000"], 2)
        )
        run = self._run([0, 1, 2], model)
        self.assertEqual("completed_low_confidence", run.status)
        self.assertEqual(2, run.exit_code)
        self.assertEqual(1, len(model.calls))
        self.assertEqual(3, len(model.calls[0].image_paths))
        self.assertIsNotNone(run.receipt_path)
        receipt = run.receipt
        self.assertEqual("frame_0001", receipt["result"]["selected_frame_id"])
        self.assertEqual(2, receipt["result"]["confidence_1_to_5"])
        self.assertTrue(receipt["requires_operator_review"])
        self.assertFalse(receipt["next_stage_authorized"])
        self.assertEqual(30, receipt["request"]["timeout_seconds"])
        self.assertEqual("mock/bounded-vl", receipt["model"]["reference"])
        self.assertTrue(receipt["guards"]["model_invoked"])
        self.assertFalse(receipt["usage"]["reported"])
        self.assertIsNone(receipt["usage"]["total_tokens"])
        self.assertEqual("frame_0001", receipt["result"]["selected_frame_id"])
        self.assertEqual(
            receipt["result"]["selected_frame_sha256"],
            self._request([0, 1, 2])["candidates"][1]["sha256"],
        )
        self.assertIn("frame_0001", receipt["prompt"]["text"])
        self.assertTrue(run.receipt_path.is_file())
        self.assertTrue((run.receipt_path.parent / "receipts.jsonl").is_file())

    def test_high_confidence_selection_completes_without_operator_pause(self) -> None:
        model = RecordingModel(
            response_document("frame_0002", ["frame_0000", "frame_0001"], 5)
        )
        run = self._run([0, 1, 2], model)
        self.assertEqual("completed", run.status)
        self.assertEqual(0, run.exit_code)
        self.assertFalse(run.receipt["requires_operator_review"])
        self.assertFalse(run.receipt["next_stage_authorized"])

    def test_abstention_pauses_for_operator(self) -> None:
        model = RecordingModel(response_document(None, [], 4))
        run = self._run([0, 1, 2], model)
        self.assertEqual("abstained", run.status)
        self.assertEqual(2, run.exit_code)
        self.assertEqual("abstained", run.receipt["result"]["selection_status"])
        self.assertIsNone(run.receipt["result"]["selected_frame_id"])
        self.assertTrue(run.receipt["requires_operator_review"])
        self.assertFalse(run.receipt["next_stage_authorized"])

    def test_unknown_selected_frame_is_invalid_and_written_as_evidence(self) -> None:
        model = RecordingModel(response_document("frame_9999", ["frame_0000"], 5))
        run = self._run([0, 1, 2], model)
        self.assertEqual("invalid_response", run.status)
        self.assertEqual(3, run.exit_code)
        self.assertTrue(run.receipt_path.is_file())
        self.assertIn("not in the reviewed", run.receipt["result"]["error"])
        self.assertTrue(run.receipt["requires_operator_review"])

    def test_timeout_is_recorded_without_retry(self) -> None:
        model = RecordingModel(status="timed_out", error="timeout after 30s")
        run = self._run([0, 1, 2], model)
        self.assertEqual("timed_out", run.status)
        self.assertEqual(3, run.exit_code)
        self.assertEqual(1, len(model.calls))
        self.assertEqual(30, run.receipt["request"]["timeout_seconds"])
        self.assertIn("timeout", run.receipt["result"]["error"])
        self.assertFalse(run.receipt["guards"]["automatic_retry_allowed"])

    def test_provider_error_is_recorded(self) -> None:
        model = RecordingModel(status="error", error="transport closed")
        run = self._run([0, 1, 2], model)
        self.assertEqual("provider_error", run.status)
        self.assertEqual(3, run.exit_code)
        self.assertIn("transport", run.receipt["result"]["error"])

    def test_paid_model_without_ceiling_is_refused_before_invocation(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        paid = ModelIdentity(
            provider="mock",
            model="paid-vl",
            image_input_supported=True,
            image_input_support_basis="unit_test_assertion",
            is_free=False,
            listed_price_usd=1.0,
            accounting="provider_reported",
        )
        with self.assertRaises(SeedReviewError) as caught:
            self._run([0, 1, 2], model, identity=paid)
        self.assertEqual("paid_call_requires_hard_ceiling", caught.exception.code)
        self.assertEqual([], model.calls)
        self.assertFalse(self.receipts_dir.exists())

    def test_paid_model_with_ceiling_and_accounting_is_allowed(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        paid = ModelIdentity(
            provider="mock",
            model="paid-vl",
            image_input_supported=True,
            image_input_support_basis="unit_test_assertion",
            is_free=False,
            listed_price_usd=1.0,
            accounting="provider_reported",
        )
        run = self._run(
            [0, 1, 2],
            model,
            identity=paid,
            hard_cost_ceiling_usd=0.05,
            provider_enforces_spend_limit=True,
        )
        self.assertEqual("completed", run.status)
        self.assertTrue(run.receipt["guards"]["paid_call_allowed"])
        self.assertEqual(0.05, run.receipt["guards"]["hard_cost_ceiling_usd"])
        self.assertEqual(1, len(model.calls))

    def test_unverified_image_support_is_refused(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        no_images = ModelIdentity(
            provider="mock",
            model="text-only",
            image_input_supported=False,
            image_input_support_basis="not_verified",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
        )
        with self.assertRaises(SeedReviewError) as caught:
            self._run([0, 1, 2], model, identity=no_images)
        self.assertEqual("image_input_support_not_verified", caught.exception.code)
        self.assertEqual([], model.calls)

    def test_dry_run_writes_nothing_and_does_not_invoke_model(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        paid_identity = ModelIdentity(
            provider="mock",
            model="paid-vl",
            image_input_supported=True,
            image_input_support_basis="dry_run_only",
            is_free=False,
            listed_price_usd=1.0,
            accounting="provider_reported",
        )
        run = self._run([0, 1, 2], model, identity=paid_identity, dry_run=True)
        self.assertEqual("dry_run", run.status)
        self.assertEqual(0, run.exit_code)
        self.assertIsNone(run.receipt_path)
        self.assertEqual([], model.calls)
        self.assertFalse(self.receipts_dir.exists())
        self.assertFalse(run.receipt["guards"]["model_invoked"])

    def test_identical_input_is_refused_instead_of_overwritten(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        first = self._run([0, 1, 2], model)
        self.assertTrue(first.receipt_path.is_file())
        with self.assertRaises(SeedReviewError) as caught:
            self._run([0, 1, 2], model)
        self.assertEqual("stage_already_completed", caught.exception.code)
        self.assertEqual(1, len(model.calls))

    def test_more_than_three_fails_closed_before_model(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        with self.assertRaises(SeedReviewError) as caught:
            self._run([0, 1, 2, 3, 4], model)
        self.assertEqual("candidate_count_exceeds_limit", caught.exception.code)
        self.assertEqual([], model.calls)
        self.assertFalse(self.receipts_dir.exists())

    def test_mechanical_shortlist_limits_model_to_three_images(self) -> None:
        model = RecordingModel(response_document("frame_0003", [], 4))
        run = self._run(
            [0, 1, 2, 3, 4],
            model,
            allow_mechanical_shortlist=True,
        )
        self.assertEqual("completed", run.status)
        self.assertEqual(3, len(model.calls[0].image_paths))
        self.assertEqual(5, run.receipt["candidate_set"]["provided_count"])
        self.assertEqual(3, run.receipt["candidate_set"]["reviewed_count"])
        self.assertEqual(2, len(run.receipt["candidate_set"]["excluded"]))
        self.assertTrue(run.receipt["candidate_set"]["mechanical_shortlist_applied"])

    def test_live_model_requires_explicit_enable_flag(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        with self.assertRaises(SeedReviewError) as caught:
            run_seed_review(
                source_id=self.source_id,
                request_document=self._request([0, 1, 2]),
                identity=free_identity(),
                root=self.root,
                spec=self.spec,
                model=model,
                receipts_dir=self.receipts_dir,
                now=lambda: FIXED_NOW,
            )
        self.assertEqual("model_stage_not_enabled", caught.exception.code)
        self.assertEqual([], model.calls)

    def test_request_source_mismatch_is_refused(self) -> None:
        model = RecordingModel(response_document("frame_0000", [], 4))
        document = self._request([0, 1, 2])
        document["source_id"] = "video-0000000000000000"
        with self.assertRaises(SeedReviewError) as caught:
            run_seed_review(
                source_id=self.source_id,
                request_document=document,
                identity=free_identity(),
                root=self.root,
                spec=self.spec,
                model=model,
                enable_model=True,
                receipts_dir=self.receipts_dir,
            )
        self.assertEqual("source_mismatch", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
