"""Role-aware metrics for consensus runs over labelled image collections.

The consensus scorer knows nothing about ground truth. This module turns its
per-view scores, ranks and outlier flags into keep/reject rates for the scene
and distractor roles, plus the similarity diagnostics that explain them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from freeview_consensus import SCORE_DIGITS

SCENE_ROLE = "scene"
DISTRACTOR_ROLE = "distractor"
PERCENTILE_DIGITS = 6


def collection_metrics(
    views: Sequence[dict[str, Any]],
    roles: Mapping[str, str],
    k_values: Sequence[int],
) -> dict[str, Any]:
    """Keep/reject and ranking metrics for every k of one collection."""
    by_id = {view["frame_id"]: view for view in views}
    scene_ids = _role_ids(roles, SCENE_ROLE, by_id)
    distractor_ids = _role_ids(roles, DISTRACTOR_ROLE, by_id)
    metrics = {}
    for k in k_values:
        metrics[f"k{k}"] = _k_metrics(by_id, roles, scene_ids, distractor_ids, k)
    return {"k_values": [int(k) for k in k_values], "by_k": metrics}


def similarity_diagnostics(
    scene_ids: Sequence[str],
    distractor_ids: Sequence[str],
    embeddings: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    """Pairwise similarity distributions and nearest-neighbour role mix."""
    scene = _unit_matrix(scene_ids, embeddings)
    distractor = _unit_matrix(distractor_ids, embeddings)
    scene_pairs = _off_diagonal(scene @ scene.T)
    distractor_pairs = _off_diagonal(distractor @ distractor.T)
    cross = scene @ distractor.T
    diagnostics: dict[str, Any] = {
        "scene_count": len(scene_ids),
        "distractor_count": len(distractor_ids),
        "scene_to_scene": _distribution(scene_pairs),
        "distractor_to_distractor": _distribution(distractor_pairs),
        "scene_to_distractor": _distribution(cross.reshape(-1)),
    }
    diagnostics["nearest_neighbour"] = {
        "scene": _nearest_role_summary(scene, distractor, "scene"),
        "distractor": _nearest_role_summary(distractor, scene, "distractor"),
    }
    return diagnostics


def mechanical_summary(
    ranked: Sequence[dict[str, Any]],
    roles: Mapping[str, str],
    consensus_ranks: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    """Compare the picture mechanical rank with the consensus rank."""
    by_id = {record["image_id"]: record for record in ranked}
    count = len(by_id)
    scene_ids = _role_ids(roles, SCENE_ROLE, by_id)
    distractor_ids = _role_ids(roles, DISTRACTOR_ROLE, by_id)
    summary: dict[str, Any] = {
        "view_count": count,
        "top_image_id": ranked[0]["image_id"] if ranked else None,
        "scene_mechanical_rank_percentile_median": _median_percentile(
            scene_ids, by_id, count
        ),
        "distractor_mechanical_rank_percentile_median": _median_percentile(
            distractor_ids, by_id, count
        ),
        "role_rank_auc": _rank_auc(
            [by_id[image_id]["mechanical_rank"] for image_id in scene_ids],
            [by_id[image_id]["mechanical_rank"] for image_id in distractor_ids],
        ),
    }
    for label in sorted(next(iter(consensus_ranks.values()), {})):
        pairs = [
            (by_id[image_id]["mechanical_rank"], ranks[label])
            for image_id, ranks in consensus_ranks.items()
            if image_id in by_id and label in ranks
        ]
        summary[f"spearman_vs_{label}"] = _spearman(pairs)
    return summary


def _k_metrics(
    by_id: Mapping[str, dict[str, Any]],
    roles: Mapping[str, str],
    scene_ids: Sequence[str],
    distractor_ids: Sequence[str],
    k: int,
) -> dict[str, Any]:
    label = f"k{k}"
    scene = [by_id[image_id]["consensus"][label] for image_id in scene_ids]
    distractor = [by_id[image_id]["consensus"][label] for image_id in distractor_ids]
    total = len(scene) + len(distractor)
    reference = _reference(by_id, label)
    flagged_scene = sum(1 for item in scene if item["outlier"])
    flagged_distractor = sum(1 for item in distractor if item["outlier"])
    return {
        "k": int(k),
        "reference_image_id": reference,
        "reference_role": roles.get(reference) if reference else None,
        "outlier_threshold": _threshold(by_id, label),
        "flagged_scene": flagged_scene,
        "flagged_distractor": flagged_distractor,
        "flagged_total": flagged_scene + flagged_distractor,
        "flag_precision": _flag_precision(
            flagged_scene, flagged_distractor, len(scene), len(distractor)
        ),
        "scene_keep_rate": _rate(
            sum(1 for item in scene if not item["outlier"]), len(scene)
        ),
        "distractor_rejection_rate": _rate(
            sum(1 for item in distractor if item["outlier"]), len(distractor)
        ),
        "scene_rank_percentile_median": _median(
            [_percentile(item["rank"], total) for item in scene]
        ),
        "distractor_rank_percentile_median": _median(
            [_percentile(item["rank"], total) for item in distractor]
        ),
        "distractor_best_rank": min(
            (item["rank"] for item in distractor), default=None
        ),
        "distractor_best_rank_percentile": min(
            (_percentile(item["rank"], total) for item in distractor), default=None
        ),
        "distractors_in_top_decile": sum(
            1 for item in distractor if item["rank"] <= max(1, total // 10)
        ),
        "distractors_in_top_quartile": sum(
            1 for item in distractor if item["rank"] <= max(1, total // 4)
        ),
        "role_rank_auc": _rank_auc(
            [item["rank"] for item in scene], [item["rank"] for item in distractor]
        ),
        "scene_scores": _score_summary(scene),
        "distractor_scores": _score_summary(distractor),
    }


def _reference(by_id: Mapping[str, dict[str, Any]], label: str) -> str | None:
    for image_id, view in by_id.items():
        if view["consensus"][label]["is_reference"]:
            return image_id
    return None


def _threshold(by_id: Mapping[str, dict[str, Any]], label: str) -> float | None:
    for view in by_id.values():
        return view["consensus"][label]["outlier_threshold"]
    return None


def _score_summary(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scores = [item["score"] for item in items]
    if not scores:
        return {"count": 0, "mean": None, "min": None, "max": None}
    return {
        "count": len(scores),
        "mean": round(float(np.mean(scores)), SCORE_DIGITS),
        "min": round(float(min(scores)), SCORE_DIGITS),
        "max": round(float(max(scores)), SCORE_DIGITS),
    }


def _role_ids(
    roles: Mapping[str, str], role: str, by_id: Mapping[str, Any]
) -> list[str]:
    return sorted(
        image_id
        for image_id, image_role in roles.items()
        if image_role == role and image_id in by_id
    )


def _median_percentile(
    image_ids: Sequence[str], by_id: Mapping[str, dict[str, Any]], count: int
) -> float | None:
    if not image_ids or count < 1:
        return None
    return _median(
        [
            _percentile(by_id[image_id]["mechanical_rank"], count)
            for image_id in image_ids
        ]
    )


def _rank_auc(
    scene_ranks: Sequence[int], distractor_ranks: Sequence[int]
) -> float | None:
    """Probability that a scene image outranks a distractor (ties count half)."""
    if not scene_ranks or not distractor_ranks:
        return None
    wins = 0.0
    for scene_rank in scene_ranks:
        for distractor_rank in distractor_ranks:
            if scene_rank < distractor_rank:
                wins += 1.0
            elif scene_rank == distractor_rank:
                wins += 0.5
    pairs = len(scene_ranks) * len(distractor_ranks)
    return round(wins / pairs, SCORE_DIGITS)


def _spearman(pairs: Sequence[tuple[int, int]]) -> float | None:
    if len(pairs) < 3:
        return None
    left = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
    right = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
    if np.var(left) == 0.0 or np.var(right) == 0.0:
        return None
    correlation = float(np.corrcoef(left, right)[0, 1])
    if not np.isfinite(correlation):
        return None
    return round(correlation, SCORE_DIGITS)


def _percentile(rank: int, total: int) -> float:
    return round(rank / total, PERCENTILE_DIGITS)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, SCORE_DIGITS)


def _flag_precision(
    flagged_scene: int,
    flagged_distractor: int,
    scene_count: int,
    distractor_count: int,
) -> float | None:
    if scene_count == 0 or distractor_count == 0:
        return None
    flagged_total = flagged_scene + flagged_distractor
    return _rate(flagged_distractor, flagged_total)


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(float(np.median(values)), SCORE_DIGITS)


def _unit_matrix(
    image_ids: Sequence[str], embeddings: Mapping[str, Sequence[float]]
) -> np.ndarray:
    if not image_ids:
        return np.empty((0, 0), dtype=np.float64)
    matrix = np.asarray(
        [embeddings[image_id] for image_id in image_ids], dtype=np.float64
    )
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / norms


def _off_diagonal(matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] < 2:
        return np.empty(0, dtype=np.float64)
    indices = ~np.eye(matrix.shape[0], dtype=bool)
    return matrix[indices]


def _distribution(values: np.ndarray) -> dict[str, Any]:
    if values.size == 0:
        return {"pairs": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "pairs": int(values.size),
        "mean": round(float(values.mean()), SCORE_DIGITS),
        "median": round(float(np.median(values)), SCORE_DIGITS),
        "p10": round(float(np.percentile(values, 10)), SCORE_DIGITS),
        "p90": round(float(np.percentile(values, 90)), SCORE_DIGITS),
    }


def _nearest_role_summary(
    own: np.ndarray, other: np.ndarray, own_role: str
) -> dict[str, Any]:
    if own.shape[0] == 0 or other.shape[0] == 0:
        return {"count": 0, "nearest_is_other_role": 0, "nearest_own_median": None}
    cross = own @ other.T
    own_similarity = own @ own.T
    np.fill_diagonal(own_similarity, -np.inf)
    nearest_own = own_similarity.max(axis=1)
    nearest_cross = cross.max(axis=1)
    nearest_is_other = int(np.count_nonzero(nearest_cross > nearest_own))
    return {
        "count": int(own.shape[0]),
        "own_role": own_role,
        "nearest_is_other_role": nearest_is_other,
        "nearest_is_other_role_fraction": _rate(nearest_is_other, int(own.shape[0])),
        "nearest_own_median": _finite_median(nearest_own),
        "nearest_cross_median": round(float(np.median(nearest_cross)), SCORE_DIGITS),
    }


def _finite_median(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return round(float(np.median(finite)), SCORE_DIGITS)
