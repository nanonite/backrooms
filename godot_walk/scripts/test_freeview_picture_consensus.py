"""Tests for the picture-set consensus collection CLI."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freeview_collection_summary import render_summary
from PIL import Image
from run_freeview_picture_consensus import _cache_filename, main


def _images(root: Path, name: str, count: int, channel: int) -> Path:
    directory = root / name
    directory.mkdir()
    for index in range(count):
        Image.new("RGB", (24, 18), (index * 9 % 256, channel, 60)).save(
            directory / f"img_{index:03d}.png"
        )
    return directory


class BuildCommandTests(unittest.TestCase):
    def _build(self, output: Path, extra: list[str] | None = None) -> int:
        return main(
            [
                "build",
                "--scene-dir",
                str(self.scene),
                "--distractor-dir",
                str(self.distractors),
                "--room-sample",
                "4",
                "--mix",
                "0.25",
                "--mix",
                "0.5",
                "--seed",
                "1",
                "--output",
                str(output),
            ]
            + (extra or [])
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.scene = _images(self.root, "scene", 8, 10)
        self.distractors = _images(self.root, "distractor", 4, 140)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_is_deterministic_and_text_only(self) -> None:
        output = self.root / "collections.json"
        self.assertEqual(self._build(output), 0)
        first = output.read_bytes()
        self.assertEqual(self._build(output), 0)
        self.assertEqual(output.read_bytes(), first)
        spec = json.loads(first)
        self.assertEqual(len(spec["collections"]), 6)
        self.assertEqual(spec["k_values"], [3, 5, 8, 15, 30])
        self.assertEqual(spec["scene_source"]["image_count"], 8)
        self.assertEqual(spec["distractor_source"]["image_count"], 4)

    def test_mismatched_manifest_exits_with_error(self) -> None:
        manifest = self.root / "pictures.json"
        manifest.write_text(
            json.dumps(
                {
                    "content": {
                        "picture_set": [
                            {"path": "data/pictures/x/none.png", "sha256": "0" * 64}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        output = self.root / "collections.json"
        with redirect_stderr(StringIO()):
            self.assertEqual(
                self._build(output, ["--distractor-manifest", str(manifest)]), 2
            )


class SummaryTests(unittest.TestCase):
    def test_render_summary_includes_core_tables(self) -> None:
        metric = {
            "k": 3,
            "reference_image_id": "scene/a.png",
            "reference_role": "scene",
            "outlier_threshold": 0.5,
            "flagged_scene": 0,
            "flagged_distractor": 1,
            "flagged_total": 1,
            "flag_precision": 1.0,
            "scene_keep_rate": 1.0,
            "distractor_rejection_rate": 1.0,
            "scene_rank_percentile_median": 0.25,
            "distractor_rank_percentile_median": 0.75,
            "distractor_best_rank": 3,
            "distractor_best_rank_percentile": 0.75,
            "distractors_in_top_decile": 0,
            "distractors_in_top_quartile": 0,
            "role_rank_auc": 1.0,
            "scene_scores": {"count": 2, "mean": 0.9, "min": 0.8, "max": 1.0},
            "distractor_scores": {"count": 1, "mean": 0.1, "min": 0.1, "max": 0.1},
        }
        collection = {
            "name": "mixed-25-seed-1",
            "kind": "mixed",
            "seed": 1,
            "requested_distractor_fraction": 0.25,
            "realized_distractor_fraction": 0.25,
            "scene_count": 3,
            "distractor_count": 1,
            "collection_sha256": "a" * 64,
            "consensus": {},
            "metrics": {"k_values": [3], "by_k": {"k3": metric}},
            "top_views": {},
            "mechanical": None,
            "mechanical_ranks": None,
        }
        results = {
            "similarity_diagnostics": {
                "scene_to_scene": {
                    "pairs": 1,
                    "mean": 0.5,
                    "median": 0.5,
                    "p10": 0.5,
                    "p90": 0.5,
                },
                "distractor_to_distractor": {
                    "pairs": 0,
                    "mean": None,
                    "median": None,
                    "p10": None,
                    "p90": None,
                },
                "scene_to_distractor": {
                    "pairs": 1,
                    "mean": 0.1,
                    "median": 0.1,
                    "p10": 0.1,
                    "p90": 0.1,
                },
                "nearest_neighbour": {
                    "scene": {
                        "count": 3,
                        "nearest_is_other_role": 0,
                        "nearest_is_other_role_fraction": 0.0,
                        "nearest_own_median": 0.9,
                        "nearest_cross_median": 0.1,
                    },
                    "distractor": {
                        "count": 1,
                        "nearest_is_other_role": 0,
                        "nearest_is_other_role_fraction": 0.0,
                        "nearest_own_median": None,
                        "nearest_cross_median": 0.1,
                    },
                },
            },
            "collections": [collection],
        }
        text = render_summary(results)
        for heading in (
            "# Issue 246 collection results",
            "## DINOv2 similarity diagnostics",
            "## Clean collections",
            "## Mixed collections, pooled across seeds",
            "## Distractor ranking",
            "## Picture mechanical score comparison",
        ):
            self.assertIn(heading, text)
        self.assertIn("| 25% | 3 | 1 / 0 |", text)


class CacheTests(unittest.TestCase):
    def test_cache_filename_is_model_scoped(self) -> None:
        name = _cache_filename("facebook/dinov2-base", "d" * 64)
        self.assertEqual(name, "embeddings-facebook-dinov2-base-dddddddddddd.json")


if __name__ == "__main__":
    unittest.main()
