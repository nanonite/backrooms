"""Tests for building model requests from source-bound frame receipts."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_review_errors import SeedReviewError
from seed_review_request_builder import (
    DECODE_OPERATION,
    DECODER,
    build_request,
    write_request,
)
from seed_review_test_support import build_fake_repo, make_candidate, write_json


class SeedReviewRequestBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source, self.frame_dir = build_fake_repo(self.root)
        self.source_id = source["source_id"]
        self.source = source
        self.manifest_path = self.frame_dir / "extraction_manifest.json"
        self.extraction = self._extraction([0, 2, 4])
        write_json(self.manifest_path, self.extraction)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _extraction(self, indexes: list[int]) -> dict[str, Any]:
        candidates = [
            make_candidate(self.root, self.frame_dir, index) for index in indexes
        ]
        for candidate in candidates:
            candidate["frame_id"] = f"frame_{candidate['index_zero_based'] + 1:04d}"
            candidate["path"] = (
                f"{self.frame_dir.relative_to(self.root).as_posix()}/"
                f"{candidate['frame_id']}.png"
            )
            original = self.frame_dir / f"frame_{candidate['index_zero_based']:04d}.png"
            named = self.root / candidate["path"]
            original.rename(named)
            candidate["sha256"] = hashlib.sha256(named.read_bytes()).hexdigest()
            candidate["timestamp_seconds"] = float(candidate["index_zero_based"] / 10)
            candidate["decode_operation"] = DECODE_OPERATION
        return {
            "schema_version": 1,
            "source_video": self.source["canonical_video"]["path"],
            "source_video_sha256": self.source["canonical_video"]["sha256"],
            "metadata": {"width": 64, "height": 64, "fps": 10.0},
            "decoder": DECODER,
            "frames": candidates,
        }

    def _write_extraction(self, extraction: dict[str, Any]) -> None:
        write_json(self.manifest_path, extraction)

    def test_builds_request_from_three_verified_direct_frames(self) -> None:
        request = build_request(
            self.source_id,
            self.manifest_path.relative_to(self.root).as_posix(),
            self.root,
        )
        self.assertEqual(self.source_id, request["source_id"])
        self.assertEqual(3, len(request["candidates"]))
        self.assertEqual("direct_source_frame", request["candidates"][0]["origin"])
        self.assertEqual("frame_0005", request["candidates"][2]["frame_id"])

    def test_rejects_extraction_bound_to_another_source(self) -> None:
        changed = dict(self.extraction, source_video_sha256="0" * 64)
        self._write_extraction(changed)
        with self.assertRaises(SeedReviewError) as caught:
            self._build()
        self.assertEqual("extraction_source_mismatch", caught.exception.code)

    def test_rejects_frame_hash_mismatch(self) -> None:
        changed = json.loads(json.dumps(self.extraction))
        changed["frames"][0]["sha256"] = "0" * 64
        self._write_extraction(changed)
        with self.assertRaises(SeedReviewError) as caught:
            self._build()
        self.assertEqual("extraction_frame_mismatch", caught.exception.code)

    def test_rejects_non_native_frame_dimensions(self) -> None:
        from PIL import Image

        path = self.root / self.extraction["frames"][0]["path"]
        with Image.open(path) as image:
            image.resize((32, 32)).save(path)
        changed = json.loads(json.dumps(self.extraction))
        changed["frames"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self._write_extraction(changed)
        with self.assertRaises(SeedReviewError) as caught:
            self._build()
        self.assertEqual("extraction_frame_resized", caught.exception.code)

    def test_rejects_duplicate_or_unsorted_frames(self) -> None:
        changed = json.loads(json.dumps(self.extraction))
        changed["frames"][1], changed["frames"][2] = (
            changed["frames"][2],
            changed["frames"][1],
        )
        self._write_extraction(changed)
        with self.assertRaises(SeedReviewError) as caught:
            self._build()
        self.assertEqual("extraction_frame_order_invalid", caught.exception.code)

    def test_rejects_more_than_workflow_candidate_limit(self) -> None:
        changed = self._extraction([0, 2, 4, 6])
        self._write_extraction(changed)
        with self.assertRaises(SeedReviewError) as caught:
            self._build()
        self.assertEqual("candidate_count_exceeds_limit", caught.exception.code)

    def test_refuses_request_overwrite(self) -> None:
        target = self.root / "request.json"
        target.write_text("keep", encoding="utf-8")
        with self.assertRaises(SeedReviewError) as caught:
            write_request({"preserve": True}, "request.json", self.root)
        self.assertEqual("request_exists", caught.exception.code)
        self.assertEqual("keep", target.read_text(encoding="utf-8"))

    def _build(self) -> dict[str, Any]:
        return build_request(
            self.source_id,
            self.manifest_path.relative_to(self.root).as_posix(),
            self.root,
        )


if __name__ == "__main__":
    unittest.main()
