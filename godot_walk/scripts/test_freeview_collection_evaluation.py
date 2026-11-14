"""Tests for role-aware consensus collection metrics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freeview_collection_evaluation import (
    collection_metrics,
    mechanical_summary,
    similarity_diagnostics,
)
from freeview_consensus import evaluate_consensus


def _view(
    frame_id: str,
    score: float,
    rank: int,
    outlier: bool,
    reference: bool = False,
    threshold: float | None = 0.5,
) -> dict[str, object]:
    return {
        "frame_id": frame_id,
        "consensus": {
            "k3": {
                "score": score,
                "rank": rank,
                "is_reference": reference,
                "relevance_to_reference": 1.0 if reference else score,
                "outlier": outlier,
                "outlier_threshold": threshold,
            }
        },
    }


class CollectionMetricsTests(unittest.TestCase):
    def test_confusion_counts_and_rates(self) -> None:
        views = [
            _view("scene/a", 0.9, 1, False, reference=True),
            _view("scene/b", 0.8, 2, True),
            _view("distractor/c", 0.7, 3, True),
            _view("distractor/d", 0.6, 4, False),
        ]
        roles = {
            "scene/a": "scene",
            "scene/b": "scene",
            "distractor/c": "distractor",
            "distractor/d": "distractor",
        }
        metrics = collection_metrics(views, roles, [3])["by_k"]["k3"]
        self.assertEqual(metrics["reference_role"], "scene")
        self.assertEqual(metrics["flagged_scene"], 1)
        self.assertEqual(metrics["flagged_distractor"], 1)
        self.assertEqual(metrics["scene_keep_rate"], 0.5)
        self.assertEqual(metrics["distractor_rejection_rate"], 0.5)
        self.assertEqual(metrics["flag_precision"], 0.5)
        self.assertEqual(metrics["role_rank_auc"], 1.0)
        self.assertEqual(metrics["scene_rank_percentile_median"], 0.375)
        self.assertEqual(metrics["distractor_rank_percentile_median"], 0.875)

    def test_missing_role_leaves_rates_empty(self) -> None:
        views = [_view("scene/a", 0.9, 1, False, reference=True)]
        metrics = collection_metrics(views, {"scene/a": "scene"}, [3])["by_k"]["k3"]
        self.assertIsNone(metrics["distractor_rejection_rate"])
        self.assertIsNone(metrics["flag_precision"])
        self.assertIsNone(metrics["role_rank_auc"])

    def test_no_flag_gives_zero_rejection(self) -> None:
        views = [
            _view("scene/a", 0.9, 1, False, reference=True, threshold=None),
            _view("distractor/b", 0.1, 2, False, threshold=None),
        ]
        roles = {"scene/a": "scene", "distractor/b": "distractor"}
        metrics = collection_metrics(views, roles, [3])["by_k"]["k3"]
        self.assertEqual(metrics["distractor_rejection_rate"], 0.0)
        self.assertIsNone(metrics["flag_precision"])


class ConsensusIntegrationTests(unittest.TestCase):
    def test_tight_scene_cluster_outranks_incoherent_distractors(self) -> None:
        scene = [
            [1.0, 0.0, 0.0, 0.0],
            [0.99, 0.05, 0.0, 0.0],
            [0.98, 0.08, 0.0, 0.0],
            [0.97, 0.1, 0.0, 0.0],
        ]
        distractors = [
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        ids = [f"scene/{index}" for index in range(4)] + [
            f"distractor/{index}" for index in range(3)
        ]
        roles = {
            **{f"scene/{index}": "scene" for index in range(4)},
            **{f"distractor/{index}": "distractor" for index in range(3)},
        }
        variants = evaluate_consensus(ids, scene + distractors, [3])
        metrics = collection_metrics(variants["views"], roles, [3])["by_k"]["k3"]
        self.assertEqual(metrics["reference_role"], "scene")
        self.assertEqual(metrics["role_rank_auc"], 1.0)
        self.assertEqual(metrics["distractor_rejection_rate"], 1.0)
        self.assertEqual(metrics["scene_keep_rate"], 1.0)

    def test_a_tighter_foreign_cluster_beats_the_scene_cluster(self) -> None:
        # Characterisation, not desired behaviour: local consensus rewards
        # tightness, so a coherent foreign cluster can outrank the scene.
        scene = [[1.0, 0.0, 0.0, 0.0], [0.995, 0.0999, 0.0, 0.0]]
        distractors = [[0.0, 1.0, 0.0, 0.0], [0.0, 0.999, 0.0447, 0.0]]
        ids = ["scene/a", "scene/b", "distractor/c", "distractor/d"]
        roles = {
            "scene/a": "scene",
            "scene/b": "scene",
            "distractor/c": "distractor",
            "distractor/d": "distractor",
        }
        variants = evaluate_consensus(ids, scene + distractors, [1])
        metrics = collection_metrics(variants["views"], roles, [1])["by_k"]["k1"]
        self.assertEqual(metrics["reference_role"], "distractor")
        self.assertLess(metrics["role_rank_auc"], 0.5)
        self.assertGreater(metrics["distractor_scores"]["min"], 0.99)


class SimilarityTests(unittest.TestCase):
    def test_orthogonal_groups_have_zero_cross_similarity(self) -> None:
        embeddings = {
            "scene/a": [1.0, 0.0, 0.0],
            "scene/b": [0.0, 1.0, 0.0],
            "distractor/c": [0.0, 0.0, 1.0],
        }
        diagnostics = similarity_diagnostics(
            ["scene/a", "scene/b"], ["distractor/c"], embeddings
        )
        self.assertEqual(diagnostics["scene_to_scene"]["mean"], 0.0)
        self.assertEqual(diagnostics["scene_to_distractor"]["mean"], 0.0)
        self.assertEqual(diagnostics["nearest_neighbour"]["distractor"]["count"], 1)


class MechanicalTests(unittest.TestCase):
    def test_rank_auc_percentiles_and_spearman(self) -> None:
        ranked = [
            {"image_id": "scene/a", "mechanical_rank": 1},
            {"image_id": "scene/b", "mechanical_rank": 2},
            {"image_id": "distractor/c", "mechanical_rank": 3},
            {"image_id": "distractor/d", "mechanical_rank": 4},
        ]
        roles = {
            "scene/a": "scene",
            "scene/b": "scene",
            "distractor/c": "distractor",
            "distractor/d": "distractor",
        }
        consensus = {
            "scene/a": {"k5": 1},
            "scene/b": {"k5": 2},
            "distractor/c": {"k5": 3},
            "distractor/d": {"k5": 4},
        }
        summary = mechanical_summary(ranked, roles, consensus)
        self.assertEqual(summary["role_rank_auc"], 1.0)
        self.assertEqual(summary["scene_mechanical_rank_percentile_median"], 0.375)
        self.assertEqual(summary["distractor_mechanical_rank_percentile_median"], 0.875)
        self.assertEqual(summary["spearman_vs_k5"], 1.0)


if __name__ == "__main__":
    unittest.main()
