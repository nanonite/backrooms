"""Tests for direct-source candidate validation and mechanical shortlisting."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_review_candidates import (
    candidates_from_document,
    prepare_candidates,
)
from seed_review_errors import SeedReviewError
from seed_review_sources import load_source_record
from seed_review_test_support import (
    build_fake_repo,
    make_candidate,
    request_document,
)


class SeedReviewCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        manifest, self.frame_dir = build_fake_repo(self.root)
        self.source_id = manifest["source_id"]
        self.source_sha256 = manifest["canonical_video"]["sha256"]
        self.source = load_source_record(self.source_id, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _document(self, indexes: list[int]) -> dict[str, object]:
        candidates = [
            make_candidate(self.root, self.frame_dir, index) for index in indexes
        ]
        return request_document(self.source_id, self.source_sha256, candidates)

    def _prepare(self, indexes: list[int], *, allow_shortlist: bool = False) -> object:
        document = self._document(indexes)
        return prepare_candidates(
            candidates_from_document(document),
            self.source,
            self.root,
            allow_mechanical_shortlist=allow_shortlist,
        )

    def test_three_direct_native_frames_pass_with_metrics(self) -> None:
        candidate_set = self._prepare([0, 1, 2])
        self.assertEqual(3, candidate_set.provided_count)
        self.assertEqual(3, len(candidate_set.reviewed))
        self.assertEqual((), candidate_set.excluded)
        metrics = candidate_set.reviewed[0].metrics.to_dict()
        self.assertIn("focus_native_laplacian_variance", metrics)
        self.assertIn("exposure_score", metrics)
        self.assertIn("duplicate_similarity", metrics)
        self.assertIn("temporal_coverage_score", metrics)
        self.assertEqual(
            {1, 2, 3}, {item.metrics.mechanical_rank for item in candidate_set.reviewed}
        )

    def test_hash_mismatch_is_rejected(self) -> None:
        document = self._document([0, 1, 2])
        document["candidates"][0]["sha256"] = "0" * 64
        with self.assertRaises(SeedReviewError) as caught:
            prepare_candidates(
                candidates_from_document(document), self.source, self.root
            )
        self.assertEqual("frame_hash_mismatch", caught.exception.code)

    def test_resized_frame_is_rejected(self) -> None:
        document = self._document([0, 1, 2])
        document["candidates"][0]["width"] = 32
        document["candidates"][0]["height"] = 32
        with self.assertRaises(SeedReviewError) as caught:
            prepare_candidates(
                candidates_from_document(document), self.source, self.root
            )
        self.assertEqual("not_native_resolution", caught.exception.code)

    def test_panorama_origin_is_rejected(self) -> None:
        document = self._document([0, 1, 2])
        document["candidates"][0]["origin"] = "panorama"
        with self.assertRaises(SeedReviewError) as caught:
            prepare_candidates(
                candidates_from_document(document), self.source, self.root
            )
        self.assertEqual("not_direct_source_frame", caught.exception.code)

    def test_index_and_pts_disagreement_is_rejected(self) -> None:
        document = self._document([0, 1, 2])
        document["candidates"][1]["pts_seconds"] = 1.5
        with self.assertRaises(SeedReviewError) as caught:
            prepare_candidates(
                candidates_from_document(document), self.source, self.root
            )
        self.assertEqual("frame_time_mismatch", caught.exception.code)

    def test_duplicate_frame_identity_is_rejected(self) -> None:
        document = self._document([0, 1, 2])
        document["candidates"][2] = copy.deepcopy(document["candidates"][1])
        with self.assertRaises(SeedReviewError) as caught:
            prepare_candidates(
                candidates_from_document(document), self.source, self.root
            )
        self.assertEqual("duplicate_candidate", caught.exception.code)

    def test_more_than_three_fails_closed_with_ranked_request(self) -> None:
        with self.assertRaises(SeedReviewError) as caught:
            self._prepare([0, 1, 2, 3, 4])
        self.assertEqual("candidate_count_exceeds_limit", caught.exception.code)
        details = caught.exception.details
        self.assertEqual(5, details["provided_count"])
        self.assertEqual(3, details["limit"])
        self.assertEqual(3, len(details["mechanical_shortlist"]))
        self.assertIn("mechanically ranked shortlist", str(caught.exception))

    def test_mechanical_shortlist_is_deterministic_and_records_exclusions(self) -> None:
        first = self._prepare([0, 1, 2, 3, 4], allow_shortlist=True)
        second = self._prepare([0, 1, 2, 3, 4], allow_shortlist=True)
        first_ids = [item.candidate.frame_id for item in first.reviewed]
        second_ids = [item.candidate.frame_id for item in second.reviewed]
        self.assertEqual(first_ids, second_ids)
        self.assertTrue(first.mechanical_shortlist_applied)
        self.assertEqual(3, len(first.reviewed))
        self.assertEqual(2, len(first.excluded))
        self.assertEqual(
            [4, 5],
            [item.metrics.mechanical_rank for item in first.excluded],
        )
        self.assertTrue(
            all(
                item.exclusion()["reason"] == "beyond_three_frame_model_review_limit"
                for item in first.excluded
            )
        )

    def test_duplicate_similarity_is_high_for_near_identical_frames(self) -> None:
        base = make_candidate(self.root, self.frame_dir, 0)
        import numpy as np

        generator = np.random.default_rng(7)
        image = generator.integers(0, 256, (64, 64, 3), dtype=np.uint8)
        near = image.copy()
        near[0, 0, 0] = (int(near[0, 0, 0]) + 1) % 256
        from PIL import Image

        first_path = self.root / base["path"]
        Image.fromarray(image, mode="RGB").save(first_path)
        import hashlib

        base["sha256"] = hashlib.sha256(first_path.read_bytes()).hexdigest()
        second = make_candidate(self.root, self.frame_dir, 1, image=near)
        document = request_document(self.source_id, self.source_sha256, [base, second])
        candidate_set = prepare_candidates(
            candidates_from_document(document), self.source, self.root
        )
        similarities = {
            item.candidate.frame_id: item.metrics.duplicate_similarity
            for item in candidate_set.reviewed
        }
        self.assertGreater(max(similarities.values()), 0.99)

    def test_temporal_coverage_uses_nearest_neighbour_gap(self) -> None:
        candidate_set = self._prepare([0, 1, 10])
        gaps = {
            item.candidate.frame_id: item.metrics.temporal_coverage_score
            for item in candidate_set.reviewed
        }
        self.assertAlmostEqual(0.2, gaps["frame_0000"], places=6)
        self.assertAlmostEqual(0.2, gaps["frame_0001"], places=6)
        self.assertAlmostEqual(1.0, gaps["frame_0010"], places=6)

    def test_request_document_is_json_serialisable(self) -> None:
        json.dumps(self._document([0, 1, 2]))


if __name__ == "__main__":
    unittest.main()
