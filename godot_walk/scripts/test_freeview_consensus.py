"""Tests for deterministic FreeView-style local-consensus scoring."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freeview_consensus import (
    ConsensusError,
    adaptive_relevance_boundary,
    cosine_similarity,
    evaluate_consensus,
    local_consensus_scores,
    rank_scores,
    unit_embeddings,
)


def _fan(count: int, spread_degrees: float) -> list[list[float]]:
    return [
        [
            math.cos(math.radians(index * spread_degrees / max(count - 1, 1))),
            math.sin(math.radians(index * spread_degrees / max(count - 1, 1))),
        ]
        for index in range(count)
    ]


class ConsensusScoreTests(unittest.TestCase):
    def test_score_is_mean_of_k_nearest_other_views(self) -> None:
        unit = unit_embeddings(_fan(4, 40.0))
        similarities = cosine_similarity(unit)
        scores = local_consensus_scores(unit, 2)
        for index, score in enumerate(scores):
            others = np.delete(similarities[index], index)
            expected = round(float(np.sort(others)[-2:].mean()), 6)
            self.assertEqual(expected, score)

    def test_scores_are_deterministic_across_calls(self) -> None:
        unit = unit_embeddings(_fan(6, 60.0))
        self.assertEqual(
            local_consensus_scores(unit, 3), local_consensus_scores(unit, 3)
        )
        self.assertEqual(
            evaluate_consensus([f"frame_{i:04d}" for i in range(6)], unit, [3, 5]),
            evaluate_consensus([f"frame_{i:04d}" for i in range(6)], unit, [3, 5]),
        )

    def test_order_independence(self) -> None:
        frame_ids = [f"frame_{index:04d}" for index in range(7)]
        embeddings = _fan(7, 90.0)
        baseline = evaluate_consensus(frame_ids, embeddings, [3, 5])
        order = [4, 0, 6, 2, 5, 1, 3]
        shuffled = evaluate_consensus(
            [frame_ids[index] for index in order],
            [embeddings[index] for index in order],
            [3, 5],
        )
        self.assertEqual(baseline, shuffled)

    def test_k_is_capped_by_available_peers(self) -> None:
        report = evaluate_consensus(
            ["frame_0001", "frame_0002", "frame_0003"], _fan(3, 30.0), [8]
        )
        self.assertEqual(2, report["variants"]["k8"]["effective_k"])
        unit = unit_embeddings(_fan(3, 30.0))
        manual = []
        for index in range(3):
            others = [unit[index] @ unit[other] for other in range(3) if other != index]
            manual.append(round(float(np.mean(others)), 6))
        self.assertEqual(
            manual, [view["consensus"]["k8"]["score"] for view in report["views"]]
        )

    def test_identical_views_rank_by_frame_id(self) -> None:
        report = evaluate_consensus(
            ["frame_0003", "frame_0001", "frame_0002"], [[1.0, 0.0]] * 3, [1]
        )
        ranks = {
            view["frame_id"]: view["consensus"]["k1"]["rank"]
            for view in report["views"]
        }
        self.assertEqual({"frame_0001": 1, "frame_0002": 2, "frame_0003": 3}, ranks)

    def test_single_view_has_no_peers_and_no_outlier(self) -> None:
        report = evaluate_consensus(["frame_0001"], [[1.0, 0.0]], [3])
        view = report["views"][0]
        self.assertEqual(0.0, view["consensus"]["k3"]["score"])
        self.assertTrue(view["consensus"]["k3"]["is_reference"])
        self.assertFalse(view["consensus"]["k3"]["outlier"])
        self.assertEqual(0, report["variants"]["k3"]["effective_k"])


class OutlierFlagTests(unittest.TestCase):
    def test_distractor_is_flagged_against_a_coherent_cluster(self) -> None:
        frame_ids = [f"frame_{index:04d}" for index in range(5)]
        embeddings = _fan(4, 12.0) + [[-1.0, 0.0]]
        report = evaluate_consensus(frame_ids, embeddings, [3])
        self.assertEqual(["frame_0004"], report["variants"]["k3"]["outlier_frame_ids"])
        flags = {
            view["frame_id"]: view["consensus"]["k3"]["outlier"]
            for view in report["views"]
        }
        self.assertTrue(flags["frame_0004"])
        self.assertFalse(
            any(flag for name, flag in flags.items() if name != "frame_0004")
        )

    def test_smooth_fan_is_not_flagged(self) -> None:
        frame_ids = [f"frame_{index:04d}" for index in range(5)]
        report = evaluate_consensus(frame_ids, _fan(5, 40.0), [3])
        self.assertEqual([], report["variants"]["k3"]["outlier_frame_ids"])
        self.assertIsNone(report["variants"]["k3"]["outlier_threshold"])

    def test_flat_relevance_has_no_boundary(self) -> None:
        self.assertIsNone(adaptive_relevance_boundary([1.0, 1.0, 1.0, 1.0]))
        self.assertIsNone(adaptive_relevance_boundary([1.0, 0.9]))

    def test_boundary_is_round_and_deterministic(self) -> None:
        values = [1.0, 0.98, 0.97, 0.96, 0.42, 0.40]
        first = adaptive_relevance_boundary(values)
        second = adaptive_relevance_boundary(values)
        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        assert first is not None
        self.assertGreater(first, 0.42)
        self.assertLess(first, 0.96)


class InvalidInputTests(unittest.TestCase):
    def test_zero_embedding_is_rejected(self) -> None:
        with self.assertRaises(ConsensusError):
            unit_embeddings([[1.0, 0.0], [0.0, 0.0]])

    def test_empty_embeddings_are_rejected(self) -> None:
        with self.assertRaises(ConsensusError):
            unit_embeddings([])
        with self.assertRaises(ConsensusError):
            unit_embeddings([[]])

    def test_non_finite_embedding_is_rejected(self) -> None:
        with self.assertRaises(ConsensusError):
            unit_embeddings([[1.0, float("nan")]])

    def test_mismatched_lengths_are_rejected(self) -> None:
        with self.assertRaises(ConsensusError):
            evaluate_consensus(["frame_0001"], [[1.0, 0.0], [0.0, 1.0]], [3])

    def test_duplicate_frame_ids_are_rejected(self) -> None:
        with self.assertRaises(ConsensusError):
            evaluate_consensus(["frame_0001", "frame_0001"], _fan(2, 10.0), [1])

    def test_invalid_k_values_are_rejected(self) -> None:
        for k in (0, -1, True, 2.5):
            with self.subTest(k=k), self.assertRaises(ConsensusError):
                local_consensus_scores(unit_embeddings(_fan(3, 10.0)), k)  # type: ignore[arg-type]

    def test_duplicate_k_values_are_rejected(self) -> None:
        with self.assertRaises(ConsensusError):
            evaluate_consensus(["frame_0001", "frame_0002"], _fan(2, 10.0), [3, 3])


class RankTests(unittest.TestCase):
    def test_rank_scores_are_one_based_and_tie_broken(self) -> None:
        self.assertEqual(
            [2, 1, 3],
            rank_scores([0.5, 0.9, 0.1], ["frame_0001", "frame_0002", "frame_0003"]),
        )
        self.assertEqual([1, 2], rank_scores([0.5, 0.5], ["frame_0001", "frame_0002"]))


if __name__ == "__main__":
    unittest.main()
