"""Validate direct-source candidates and produce a bounded review set."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from seed_review_errors import SeedReviewError
from seed_review_metrics import (
    analysis_gray,
    duplicate_similarity,
    exposure_measurements,
    focus_score,
    laplacian_variance,
    load_native_gray,
    mechanical_score,
    rounded,
    temporal_coverage_score,
    temporal_gap_seconds,
)
from seed_review_paths import resolve_repo_path, sha256_file
from seed_review_sources import SourceRecord

FRAME_ID_PATTERN = re.compile(r"^frame_[0-9]{4,}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_PATH_MARKERS = (
    "panorama",
    "contact_sheet",
    "contact-sheet",
    "composite",
)
SHORTLIST_REASON = "beyond_three_frame_model_review_limit"


@dataclass(frozen=True)
class SeedCandidate:
    frame_id: str
    index_zero_based: int
    pts_seconds: float
    path: str
    sha256: str
    width: int
    height: int
    origin: str
    decode_operation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "index_zero_based": self.index_zero_based,
            "pts_seconds": self.pts_seconds,
            "path": self.path,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "origin": self.origin,
            "decode_operation": self.decode_operation,
        }


@dataclass(frozen=True)
class MechanicalMetrics:
    focus_native_laplacian_variance: float
    focus_analysis_laplacian_variance: float
    exposure_mean_luminance: float
    exposure_clipped_low_fraction: float
    exposure_clipped_high_fraction: float
    exposure_score: float
    focus_score: float
    duplicate_similarity: float
    temporal_gap_seconds: float
    temporal_coverage_score: float
    mechanical_score: float
    mechanical_rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "focus_native_laplacian_variance": (self.focus_native_laplacian_variance),
            "focus_analysis_laplacian_variance": (
                self.focus_analysis_laplacian_variance
            ),
            "exposure_mean_luminance": self.exposure_mean_luminance,
            "exposure_clipped_low_fraction": self.exposure_clipped_low_fraction,
            "exposure_clipped_high_fraction": self.exposure_clipped_high_fraction,
            "exposure_score": self.exposure_score,
            "focus_score": self.focus_score,
            "duplicate_similarity": self.duplicate_similarity,
            "temporal_gap_seconds": self.temporal_gap_seconds,
            "temporal_coverage_score": self.temporal_coverage_score,
            "mechanical_score": self.mechanical_score,
            "mechanical_rank": self.mechanical_rank,
        }


@dataclass(frozen=True)
class EvaluatedCandidate:
    candidate: SeedCandidate
    metrics: MechanicalMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.candidate.to_dict(),
            "metrics": self.metrics.to_dict(),
        }

    def exclusion(self) -> dict[str, Any]:
        return {
            "frame_id": self.candidate.frame_id,
            "index_zero_based": self.candidate.index_zero_based,
            "pts_seconds": self.candidate.pts_seconds,
            "sha256": self.candidate.sha256,
            "mechanical_score": self.metrics.mechanical_score,
            "mechanical_rank": self.metrics.mechanical_rank,
            "reason": SHORTLIST_REASON,
        }


@dataclass(frozen=True)
class CandidateSet:
    provided_count: int
    reviewed: tuple[EvaluatedCandidate, ...]
    excluded: tuple[EvaluatedCandidate, ...]
    mechanical_shortlist_applied: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": 3,
            "provided_count": self.provided_count,
            "reviewed_count": len(self.reviewed),
            "mechanical_shortlist_applied": self.mechanical_shortlist_applied,
            "candidates": [item.to_dict() for item in self.reviewed],
            "excluded": [item.exclusion() for item in self.excluded],
        }


def candidates_from_document(document: dict[str, Any]) -> list[SeedCandidate]:
    raw_candidates = document.get("candidates")
    if not isinstance(raw_candidates, list):
        raise SeedReviewError(
            "request_invalid", "Seed-review request must contain a candidate list"
        )
    return [_candidate_from_dict(raw) for raw in raw_candidates]


def prepare_candidates(
    candidates: list[SeedCandidate],
    source: SourceRecord,
    root: Path,
    *,
    allow_mechanical_shortlist: bool = False,
) -> CandidateSet:
    if not candidates:
        raise SeedReviewError(
            "no_candidates", "At least one direct-source candidate is required"
        )
    _validate_candidates(candidates, source, root)
    evaluated = _evaluate(candidates, source, root)
    ranked = _rank(evaluated)
    if len(ranked) <= 3:
        return CandidateSet(
            provided_count=len(ranked),
            reviewed=tuple(ranked),
            excluded=(),
            mechanical_shortlist_applied=False,
        )
    if not allow_mechanical_shortlist:
        raise _too_many_candidates(ranked)
    return CandidateSet(
        provided_count=len(ranked),
        reviewed=tuple(ranked[:3]),
        excluded=tuple(ranked[3:]),
        mechanical_shortlist_applied=True,
    )


def _candidate_from_dict(raw: Any) -> SeedCandidate:
    if not isinstance(raw, dict):
        raise SeedReviewError("request_invalid", "Each candidate must be a JSON object")
    required = {
        "frame_id",
        "index_zero_based",
        "pts_seconds",
        "path",
        "sha256",
        "width",
        "height",
        "origin",
        "decode_operation",
    }
    if set(raw) != required:
        raise SeedReviewError(
            "request_invalid",
            "Candidate fields must match the frozen request schema",
        )
    return SeedCandidate(
        frame_id=str(raw["frame_id"]),
        index_zero_based=int(raw["index_zero_based"]),
        pts_seconds=float(raw["pts_seconds"]),
        path=str(raw["path"]),
        sha256=str(raw["sha256"]),
        width=int(raw["width"]),
        height=int(raw["height"]),
        origin=str(raw["origin"]),
        decode_operation=str(raw["decode_operation"]),
    )


def _validate_candidates(
    candidates: list[SeedCandidate], source: SourceRecord, root: Path
) -> None:
    frame_ids: set[str] = set()
    hashes: set[str] = set()
    indices: set[int] = set()
    for candidate in candidates:
        _validate_candidate(candidate, source, root)
        if (
            candidate.frame_id in frame_ids
            or candidate.sha256 in hashes
            or candidate.index_zero_based in indices
        ):
            raise SeedReviewError(
                "duplicate_candidate",
                f"Duplicate frame identity in candidate set: {candidate.frame_id}",
            )
        frame_ids.add(candidate.frame_id)
        hashes.add(candidate.sha256)
        indices.add(candidate.index_zero_based)


def _validate_candidate(
    candidate: SeedCandidate, source: SourceRecord, root: Path
) -> None:
    if FRAME_ID_PATTERN.fullmatch(candidate.frame_id) is None:
        raise SeedReviewError(
            "unsafe_frame_id", f"Unsafe frame ID: {candidate.frame_id}"
        )
    if SHA256_PATTERN.fullmatch(candidate.sha256) is None:
        raise SeedReviewError(
            "invalid_frame_hash", f"Invalid frame hash: {candidate.frame_id}"
        )
    _validate_origin(candidate)
    _validate_time_binding(candidate, source)
    if (candidate.width, candidate.height) != (source.width, source.height):
        raise SeedReviewError(
            "not_native_resolution",
            f"{candidate.frame_id} is {candidate.width}x{candidate.height}; "
            f"source is {source.width}x{source.height}",
        )
    path = resolve_repo_path(candidate.path, root, require_file=True)
    if any(marker in candidate.path.lower() for marker in FORBIDDEN_PATH_MARKERS):
        raise SeedReviewError(
            "not_direct_source_frame",
            f"Candidate path looks composite or panoramic: {candidate.path}",
        )
    if sha256_file(path) != candidate.sha256:
        raise SeedReviewError(
            "frame_hash_mismatch",
            f"Candidate frame bytes do not match {candidate.frame_id}",
        )


def _validate_origin(candidate: SeedCandidate) -> None:
    if candidate.origin != "direct_source_frame" or (
        candidate.decode_operation != "direct_source_video_decode_no_resize_or_edit"
    ):
        raise SeedReviewError(
            "not_direct_source_frame",
            f"{candidate.frame_id} is not a direct native source decode",
        )


def _validate_time_binding(candidate: SeedCandidate, source: SourceRecord) -> None:
    if (
        candidate.index_zero_based < 0
        or not math.isfinite(candidate.pts_seconds)
        or candidate.pts_seconds < 0
    ):
        raise SeedReviewError(
            "invalid_frame_time", f"Invalid frame time: {candidate.frame_id}"
        )
    tolerance = max(1.5 / source.fps, 1e-3)
    expected_pts = candidate.index_zero_based / source.fps
    if abs(candidate.pts_seconds - expected_pts) > tolerance:
        raise SeedReviewError(
            "frame_time_mismatch",
            f"{candidate.frame_id} index and PTS disagree with source frame rate",
        )
    if candidate.pts_seconds > source.duration_seconds + tolerance:
        raise SeedReviewError(
            "frame_time_out_of_range",
            f"{candidate.frame_id} PTS is beyond the source duration",
        )
    if source.frame_count is not None and (
        candidate.index_zero_based >= source.frame_count
    ):
        raise SeedReviewError(
            "frame_index_out_of_range",
            f"{candidate.frame_id} index is beyond the source frame count",
        )


def _evaluate(
    candidates: list[SeedCandidate], source: SourceRecord, root: Path
) -> list[EvaluatedCandidate]:
    native_images = []
    for candidate in candidates:
        path = resolve_repo_path(candidate.path, root, require_file=True)
        native = load_native_gray(path)
        if native.shape != (candidate.height, candidate.width):
            raise SeedReviewError(
                "frame_size_mismatch",
                f"{candidate.frame_id} decoded at {native.shape[1]}x"
                f"{native.shape[0]}, not {candidate.width}x{candidate.height}",
            )
        native_images.append(native)
    analysis_images = [analysis_gray(image) for image in native_images]
    native_focus = [laplacian_variance(image) for image in native_images]
    analysis_focus = [laplacian_variance(image) for image in analysis_images]
    exposure = [exposure_measurements(image) for image in native_images]
    pts_values = [candidate.pts_seconds for candidate in candidates]
    max_focus = max(analysis_focus)
    evaluated = []
    for index, candidate in enumerate(candidates):
        duplicate = duplicate_similarity(
            native_images[index],
            [
                image
                for position, image in enumerate(native_images)
                if position != index
            ],
        )
        gap = temporal_gap_seconds(candidate.pts_seconds, pts_values)
        focus = focus_score(analysis_focus[index], max_focus)
        mean_luminance, low_fraction, high_fraction, exposure_score = exposure[index]
        temporal = temporal_coverage_score(gap)
        metrics = MechanicalMetrics(
            focus_native_laplacian_variance=rounded(native_focus[index]),
            focus_analysis_laplacian_variance=rounded(analysis_focus[index]),
            exposure_mean_luminance=rounded(mean_luminance),
            exposure_clipped_low_fraction=rounded(low_fraction),
            exposure_clipped_high_fraction=rounded(high_fraction),
            exposure_score=rounded(exposure_score),
            focus_score=rounded(focus),
            duplicate_similarity=rounded(duplicate),
            temporal_gap_seconds=rounded(gap),
            temporal_coverage_score=rounded(temporal),
            mechanical_score=mechanical_score(
                focus, exposure_score, duplicate, temporal
            ),
            mechanical_rank=0,
        )
        evaluated.append(EvaluatedCandidate(candidate=candidate, metrics=metrics))
    return evaluated


def _rank(evaluated: list[EvaluatedCandidate]) -> list[EvaluatedCandidate]:
    ordered = sorted(evaluated, key=_ranking_key)
    return [
        replace(item, metrics=replace(item.metrics, mechanical_rank=position))
        for position, item in enumerate(ordered, start=1)
    ]


def _ranking_key(item: EvaluatedCandidate) -> tuple[Any, ...]:
    metrics = item.metrics
    return (
        -metrics.mechanical_score,
        -metrics.focus_score,
        -metrics.exposure_score,
        item.candidate.index_zero_based,
        item.candidate.frame_id,
    )


def _too_many_candidates(ranked: list[EvaluatedCandidate]) -> SeedReviewError:
    shortlist = [item.candidate.frame_id for item in ranked[:3]]
    return SeedReviewError(
        "candidate_count_exceeds_limit",
        f"{len(ranked)} candidates exceed the three-frame review limit. "
        f"Provide a three-frame mechanically ranked shortlist "
        f"({', '.join(shortlist)}) or rerun with --mechanical-shortlist.",
        details={
            "provided_count": len(ranked),
            "limit": 3,
            "mechanical_shortlist": shortlist,
            "ranked": [
                {
                    "frame_id": item.candidate.frame_id,
                    "mechanical_score": item.metrics.mechanical_score,
                    "mechanical_rank": item.metrics.mechanical_rank,
                }
                for item in ranked
            ],
            "requested_action": (
                "Provide a smaller mechanically ranked shortlist or explicitly "
                "enable the deterministic shortlist."
            ),
        },
    )
