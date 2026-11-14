"""Deterministic FreeView-style local-consensus scoring for seed views.

The paper's reference-selection score is the mean cosine similarity between one
view's embedding and its k most similar neighbours. This module keeps the score
pure and deterministic so it can be compared with the existing mechanical score
without changing the frozen seed-review workflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

K_SWEEP = (3, 5, 8)
SCORE_DIGITS = 6
MIN_OUTLIER_VIEWS = 3
MIN_OTSU_EXPLAINED_VARIANCE = 0.85
MIN_OTSU_CLASS_SEPARATION = 0.15


class ConsensusError(ValueError):
    """Embeddings or scoring parameters violate the consensus contract."""


def unit_embeddings(embeddings: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    """Return a float64 matrix whose rows are L2-normalized."""
    matrix = np.asarray(embeddings, dtype=np.float64)
    if matrix.ndim != 2:
        raise ConsensusError("Embeddings must be a two-dimensional matrix")
    if matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ConsensusError("Embeddings must not be empty")
    if not np.isfinite(matrix).all():
        raise ConsensusError("Embeddings must contain only finite values")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 0.0):
        raise ConsensusError("Embedding vectors must be non-zero")
    return matrix / norms


def cosine_similarity(unit_matrix: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity for an already unit-normalized matrix."""
    return unit_matrix @ unit_matrix.T


def local_consensus_scores(unit_matrix: np.ndarray, k: int) -> list[float]:
    """Mean similarity to the k most similar other views, one score per row."""
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ConsensusError("k must be a positive integer")
    view_count = unit_matrix.shape[0]
    if view_count == 1:
        return [0.0]
    effective_k = min(k, view_count - 1)
    similarities = cosine_similarity(unit_matrix)
    scores = []
    for index in range(view_count):
        others = np.delete(similarities[index], index)
        neighbours = np.sort(others)[-effective_k:]
        scores.append(round(float(neighbours.mean()), SCORE_DIGITS))
    return scores


def rank_scores(scores: Sequence[float], frame_ids: Sequence[str]) -> list[int]:
    """One-based ranks; ties break on frame ID so input order never matters."""
    if len(scores) != len(frame_ids):
        raise ConsensusError("Scores and frame IDs must have the same length")
    _require_unique_frame_ids(frame_ids)
    order = sorted(
        range(len(scores)), key=lambda index: (-scores[index], frame_ids[index])
    )
    ranks = [0] * len(scores)
    for position, index in enumerate(order, start=1):
        ranks[index] = position
    return ranks


def reference_index(scores: Sequence[float], frame_ids: Sequence[str]) -> int:
    """Index of the top-scoring view with the same deterministic tie-break."""
    _require_unique_frame_ids(frame_ids)
    return min(range(len(scores)), key=lambda index: (-scores[index], frame_ids[index]))


def adaptive_relevance_boundary(relevance: Sequence[float]) -> float | None:
    """Otsu-style keep/reject boundary for relevance-to-reference scores.

    Returns ``None`` when the scores are too few or too evenly spread to
    support a split. The guard is what keeps a coherent collection from always
    being divided into a lower class.
    """
    values = np.sort(np.asarray(relevance, dtype=np.float64))
    if values.size < MIN_OUTLIER_VIEWS or not np.isfinite(values).all():
        return None
    total_variance = float(np.var(values))
    if total_variance <= 0.0:
        return None
    best = _best_split(values, total_variance)
    if best is None:
        return None
    explained, separation, threshold = best
    if explained < MIN_OTSU_EXPLAINED_VARIANCE:
        return None
    if separation < MIN_OTSU_CLASS_SEPARATION:
        return None
    return round(float(threshold), SCORE_DIGITS)


def evaluate_consensus(
    frame_ids: Sequence[str],
    embeddings: Sequence[Sequence[float]] | np.ndarray,
    k_values: Sequence[int] = K_SWEEP,
) -> dict[str, Any]:
    """Score every view for every k and flag appearance outliers per k."""
    if len(frame_ids) != len(embeddings):
        raise ConsensusError("Every frame ID must have exactly one embedding")
    _require_unique_frame_ids(frame_ids)
    _require_k_values(k_values)
    matrix = unit_embeddings(embeddings)
    summaries: dict[str, Any] = {}
    view_records: dict[str, dict[str, Any]] = {
        frame_id: {"frame_id": frame_id, "consensus": {}} for frame_id in frame_ids
    }
    for k in k_values:
        scores = local_consensus_scores(matrix, k)
        ranks = rank_scores(scores, frame_ids)
        reference = reference_index(scores, frame_ids)
        relevance = [
            round(float(matrix[index] @ matrix[reference]), SCORE_DIGITS)
            for index in range(len(frame_ids))
        ]
        boundary = adaptive_relevance_boundary(relevance)
        outlier_ids = []
        for index, frame_id in enumerate(frame_ids):
            is_outlier = (
                boundary is not None
                and index != reference
                and relevance[index] < boundary
            )
            if is_outlier:
                outlier_ids.append(frame_id)
            view_records[frame_id]["consensus"][f"k{k}"] = {
                "score": scores[index],
                "rank": ranks[index],
                "is_reference": index == reference,
                "relevance_to_reference": relevance[index],
                "outlier": bool(is_outlier),
                "outlier_threshold": boundary,
            }
        summaries[f"k{k}"] = {
            "effective_k": 0 if len(frame_ids) == 1 else min(k, len(frame_ids) - 1),
            "reference_frame_id": frame_ids[reference],
            "outlier_threshold": boundary,
            "outlier_frame_ids": sorted(outlier_ids),
        }
    return {
        "k_values": [int(k) for k in k_values],
        "view_count": len(frame_ids),
        "variants": summaries,
        "views": [view_records[frame_id] for frame_id in sorted(frame_ids)],
    }


def _best_split(
    values: np.ndarray, total_variance: float
) -> tuple[float, float, float] | None:
    best: tuple[float, float, float] | None = None
    count = values.size
    for split in range(1, count):
        low = values[:split]
        high = values[split:]
        low_mean = float(low.mean())
        high_mean = float(high.mean())
        weight = (split / count) * ((count - split) / count)
        explained = weight * (high_mean - low_mean) ** 2 / total_variance
        threshold = (values[split - 1] + values[split]) / 2.0
        candidate = (explained, high_mean - low_mean, float(threshold))
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return best


def _require_unique_frame_ids(frame_ids: Sequence[str]) -> None:
    if len(set(frame_ids)) != len(frame_ids):
        raise ConsensusError("Frame IDs must be unique")


def _require_k_values(k_values: Sequence[int]) -> None:
    if not k_values:
        raise ConsensusError("At least one k value is required")
    if any(not isinstance(k, int) or isinstance(k, bool) or k < 1 for k in k_values):
        raise ConsensusError("k values must be positive integers")
    if len(set(k_values)) != len(k_values):
        raise ConsensusError("k values must be unique")
