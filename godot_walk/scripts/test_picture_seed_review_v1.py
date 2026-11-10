"""CPU-only tests for versioned picture-set seed review and guard binding."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import jsonschema
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_source_panogen
from generate_picture_set_fixture import create_picture_set
from picture_seed_review_v1 import (
    MAX_REVIEW_IMAGES,
    build_picture_model_invocation,
    build_picture_seed_review,
    load_picture_set_record,
    make_operator_decision,
    validate_picture_seed_decision,
)
from register_picture_sources import register_picture_set
from seed_review_errors import SeedReviewError
from seed_review_paths import canonical_sha256, sha256_file
from seed_review_provider import ModelIdentity
from video_source_library import PICTURE_SET_SOURCE_KIND


class PictureSeedReviewV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data/pictures").mkdir(parents=True)
        self.picture_dir = self.root / "data/pictures/synthetic-review-set"
        paths = create_picture_set(self.picture_dir, count=5, size=(1024, 768))
        Image.new("RGB", (800, 600), (130, 120, 110)).save(paths[-1])
        self.source_id = register_picture_set(self.picture_dir, self.root)
        self.record = load_picture_set_record(self.source_id, self.root)
        self.review = build_picture_seed_review(self.source_id, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_picture_set_loads_through_the_picture_specific_path(self) -> None:
        self.assertEqual(PICTURE_SET_SOURCE_KIND, self.review["source_kind"])
        self.assertEqual(self.source_id, self.record.source_id)
        self.assertEqual(
            self.record.source_image_set_sha256,
            self.review["source_image_set_sha256"],
        )
        self.assertEqual(5, len(self.record.images))

    def test_versioned_review_and_decision_schemas_validate(self) -> None:
        schema_dir = Path(__file__).resolve().parents[1] / "seed_review/picture_set_v1"
        review_schema = json.loads(
            (schema_dir / "review_request.schema.json").read_text(encoding="utf-8")
        )
        decision_schema = json.loads(
            (schema_dir / "operator_decision.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(self.review, review_schema)
        decision = make_operator_decision(
            self.review,
            self.review["candidates"][0]["image_id"],
            "Synthetic schema check.",
        )
        jsonschema.validate(decision, decision_schema)

    def test_scoring_has_no_temporal_term_and_bounds_model_review_to_three(
        self,
    ) -> None:
        self.assertEqual(3, self.review["model_review_limit"])
        self.assertLessEqual(len(self.review["candidates"]), MAX_REVIEW_IMAGES)
        self.assertFalse(self.review["scoring"]["temporal_coverage_term"])
        self.assertIn("file order only", self.review["capture_index_semantics"])
        self.assertEqual(3, len(self.review["candidates"]))
        for candidate in self.review["candidates"]:
            self.assertIn("focus_score", candidate["metrics"])
            self.assertIn("exposure_score", candidate["metrics"])
            self.assertIn("duplicate_similarity", candidate["metrics"])
            self.assertNotIn("temporal_coverage_score", candidate["metrics"])
        self.assertEqual(
            {1, 2, 3},
            {candidate["mechanical_rank"] for candidate in self.review["candidates"]},
        )

    def test_low_resolution_images_remain_listed_and_are_flagged(self) -> None:
        all_images = self.review["candidates"] + self.review["excluded"]
        self.assertEqual(5, len(all_images))
        low_resolution = [
            image for image in all_images if max(image["width"], image["height"]) < 1024
        ]
        self.assertEqual(1, len(low_resolution))
        self.assertTrue(low_resolution[0]["resolution_warning"])
        self.assertEqual(
            "below_1024_pixels_on_long_side",
            low_resolution[0]["resolution_warning_code"],
        )

    def test_model_invocation_uses_only_full_resolution_original_bytes(self) -> None:
        identity = ModelIdentity(
            provider="test",
            model="vision",
            image_input_supported=True,
            image_input_support_basis="unit-test",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
        )
        invocation = build_picture_model_invocation(self.review, identity, self.root)
        self.assertLessEqual(len(invocation.image_paths), 3)
        self.assertEqual(3, len(invocation.image_paths))
        for candidate, path in zip(self.review["candidates"], invocation.image_paths):
            self.assertEqual(self.root / candidate["path"], path)
            self.assertEqual(candidate["sha256"], sha256_file(path))
            with Image.open(path) as image:
                self.assertEqual((candidate["width"], candidate["height"]), image.size)
        self.assertIn("not resized", invocation.prompt)
        self.assertIn("not time", invocation.prompt)

    def test_guard_accepts_matching_decision_and_rejects_mismatched_bindings(
        self,
    ) -> None:
        candidate = next(
            item
            for item in self.review["candidates"]
            if max(item["width"], item["height"]) >= 1024
        )
        decision = make_operator_decision(
            self.review,
            candidate["image_id"],
            "Synthetic operator choice for guard test.",
        )
        receipt, arguments = self._guard_inputs(candidate, decision)
        run_source_panogen._validate_guard_source(receipt, arguments)

        wrong_hash = copy.deepcopy(decision)
        wrong_hash["source_image_set_sha256"] = "0" * 64
        self._resign(wrong_hash)
        bad_receipt = {**receipt, "seed_review_decision": wrong_hash}
        bad_receipt["seed_review_decision_sha256"] = wrong_hash["decision_sha256"]
        with self.assertRaisesRegex(RuntimeError, "picture-seed-review-bound"):
            run_source_panogen._validate_guard_source(bad_receipt, arguments)

        wrong_image = copy.deepcopy(decision)
        wrong_image["image_id"] = "img_9999"
        self._resign(wrong_image)
        bad_receipt = {**receipt, "seed_review_decision": wrong_image}
        bad_receipt["seed_review_decision_sha256"] = wrong_image["decision_sha256"]
        with self.assertRaisesRegex(RuntimeError, "picture-seed-review-bound"):
            run_source_panogen._validate_guard_source(bad_receipt, arguments)

    def test_low_resolution_approval_is_flagged_but_guard_rejects_it(self) -> None:
        candidate = next(
            image
            for image in self.review["candidates"] + self.review["excluded"]
            if max(image["width"], image["height"]) < 1024
        )
        low_review = self._one_image_low_resolution_review(candidate)
        low_decision = make_operator_decision(
            low_review, candidate["image_id"], "Synthetic low-resolution review."
        )
        with self.assertRaises(SeedReviewError) as caught:
            validate_picture_seed_decision(
                low_decision,
                self.record.source_image_set_sha256,
                candidate["image_id"],
                candidate["sha256"],
            )
        self.assertEqual("picture_seed_resolution_too_low", caught.exception.code)
        self.assertTrue(low_decision["resolution_warning"])
        receipt, arguments = self._guard_inputs(candidate, low_decision)
        with self.assertRaisesRegex(RuntimeError, "picture-seed-review-bound"):
            run_source_panogen._validate_guard_source(receipt, arguments)

    def _one_image_low_resolution_review(self, candidate: dict) -> dict:
        review = copy.deepcopy(self.review)
        review["candidates"] = [candidate]
        review["candidate_count"] = 1
        return review

    def _guard_inputs(self, candidate: dict, decision: dict) -> tuple[dict, object]:
        receipt = {
            "status": "passed",
            "source_id": self.source_id,
            "source_kind": PICTURE_SET_SOURCE_KIND,
            "source_image_set_sha256": self.record.source_image_set_sha256,
            "source_manifest_sha256": self.record.manifest_sha256,
            "seed_frame_sha256": candidate["sha256"],
            "seed_image_id": candidate["image_id"],
            "seed_review_decision": decision,
            "seed_review_decision_sha256": decision["decision_sha256"],
            "seed_image_width": candidate["width"],
            "seed_image_height": candidate["height"],
            "seed_image_source_path": candidate["path"],
            "seed_image_capture_index": candidate["capture_index"],
        }
        arguments = SimpleNamespace(
            source_kind=PICTURE_SET_SOURCE_KIND,
            source_id=self.source_id,
            source_manifest_sha256=self.record.manifest_sha256,
            source_image_set_sha256=self.record.source_image_set_sha256,
            image_id=candidate["image_id"],
            seed_frame_sha256=candidate["sha256"],
        )
        return receipt, arguments

    def _resign(self, decision: dict) -> None:
        decision.pop("decision_sha256", None)
        decision["decision_sha256"] = canonical_sha256(decision)


if __name__ == "__main__":
    unittest.main()
