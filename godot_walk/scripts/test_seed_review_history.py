"""Read-only replay of accepted #167/#168 seed evidence without new inference."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_review_candidates import candidates_from_document, prepare_candidates
from seed_review_errors import SeedReviewError
from seed_review_paths import ROOT, sha256_file
from seed_review_provider import ModelIdentity
from seed_review_response import RecordedResponse
from seed_review_runner import run_seed_review
from seed_review_schemas import validate_request, validate_response
from seed_review_sources import load_source_record
from seed_review_workflow import load_workflow_spec

SMOKE = ROOT / "godot_walk/evidence/2026-11-02-issue-169-model-smoke"
HISTORIC_167 = ROOT / "godot_walk/evidence/2026-10-26-issue-167-gopro-pilot"
SOURCE_ID = "video-ccf9722164a0bdc8"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _request_168() -> dict[str, object]:
    evidence = _load(SMOKE / "seed_rank_3frames.json")
    candidates = [
        {
            **item,
            "width": 1280,
            "height": 720,
            "origin": "direct_source_frame",
            "decode_operation": "direct_source_video_decode_no_resize_or_edit",
        }
        for item in evidence["inputs"]
    ]
    return {
        "schema_version": 1,
        "workflow_spec_version": "1.0.0",
        "source_id": evidence["source"]["source_id"],
        "source_video_sha256": evidence["source"]["video_sha256"],
        "candidates": candidates,
    }


def _request_167() -> dict[str, object]:
    evidence = _load(HISTORIC_167 / "adjacent_seed_frames.json")
    candidates = [
        {
            "frame_id": item["frame_id"],
            "index_zero_based": item["index_zero_based"],
            "pts_seconds": item["presentation_timestamp_seconds"],
            "path": item["path"],
            "sha256": item["sha256"],
            "width": 1280,
            "height": 720,
            "origin": "direct_source_frame",
            "decode_operation": "direct_source_video_decode_no_resize_or_edit",
        }
        for item in evidence["frames"]
    ]
    return {
        "schema_version": 1,
        "workflow_spec_version": "1.0.0",
        "source_id": evidence["source_id"],
        "source_video_sha256": evidence["source_video_sha256"],
        "candidates": candidates,
    }


class SeedReviewHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load_workflow_spec(ROOT)
        cls.source = load_source_record(SOURCE_ID, ROOT)

    def test_recorded_168_response_matches_frozen_schema(self) -> None:
        evidence = _load(SMOKE / "seed_rank_3frames.json")
        validate_response(evidence["response"], self.spec)
        self.assertEqual("frame_4560", evidence["response"]["selected_frame_id"])
        self.assertEqual(2, evidence["response"]["confidence_1_to_5"])

    def test_recorded_168_three_frame_request_matches_schema(self) -> None:
        validate_request(_request_168(), self.spec)

    def test_recorded_167_candidate_set_exceeds_limit_and_shortlists(self) -> None:
        document = _request_167()
        validate_request(document, self.spec)
        candidates = candidates_from_document(document)
        with self.assertRaises(SeedReviewError) as caught:
            prepare_candidates(candidates, self.source, ROOT)
        self.assertEqual("candidate_count_exceeds_limit", caught.exception.code)
        shortlist = caught.exception.details["mechanical_shortlist"]
        self.assertEqual(3, len(shortlist))
        self.assertIn("frame_1097", shortlist)
        candidate_set = prepare_candidates(
            candidates,
            self.source,
            ROOT,
            allow_mechanical_shortlist=True,
        )
        self.assertEqual(3, len(candidate_set.reviewed))
        self.assertIn(
            "frame_1097",
            [item.candidate.frame_id for item in candidate_set.reviewed],
        )
        self.assertEqual(8, len(candidate_set.excluded))

    def test_168_three_frame_replay_writes_receipt_without_model(self) -> None:
        evidence_path = SMOKE / "seed_rank_3frames.json"
        evidence = _load(evidence_path)
        replay = RecordedResponse(
            response=evidence["response"],
            fixture_path=evidence_path.relative_to(ROOT).as_posix(),
            fixture_sha256=sha256_file(evidence_path),
            usage_payload=evidence.get("usage"),
            provenance={
                "recorded_at_utc": evidence.get("started_at_utc"),
                "source": "issue-169-model-smoke",
            },
        )
        identity = ModelIdentity(
            provider="opencode",
            model="nemotron-3.5-super-vl-free",
            image_input_supported=True,
            image_input_support_basis="recorded_image_response_fixture",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
            opencode_version="2.0.22",
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            receipts_dir = Path(temporary) / "receipts"
            run = run_seed_review(
                source_id=SOURCE_ID,
                request_document=_request_168(),
                request_path=None,
                identity=identity,
                spec=self.spec,
                replay_response=replay,
                receipts_dir=receipts_dir,
                now=lambda: "2026-11-02T00:00:00+00:00",
            )
            self.assertEqual("completed_low_confidence", run.status)
            self.assertEqual(2, run.exit_code)
            self.assertTrue(run.receipt_path.is_file())
            receipt = run.receipt
            self.assertEqual("replayed_recorded_response", receipt["invocation_mode"])
            self.assertFalse(receipt["guards"]["model_invoked"])
            self.assertEqual("frame_4560", receipt["result"]["selected_frame_id"])
            self.assertEqual(2, receipt["result"]["confidence_1_to_5"])
            self.assertFalse(receipt["usage"]["reported"])
            self.assertTrue(receipt["requires_operator_review"])
            self.assertFalse(receipt["next_stage_authorized"])
            self.assertEqual(
                evidence_path.relative_to(ROOT).as_posix(),
                receipt["request"]["response_fixture_path"],
            )


if __name__ == "__main__":
    unittest.main()
