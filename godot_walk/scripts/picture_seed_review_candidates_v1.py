"""Mechanical picture-set scoring for picture seed review v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from picture_seed_review_contract_v1 import (
    DIRECT_IMAGE_REVIEW,
    LOW_RESOLUTION_REASON,
    MIN_HUNYUAN_LONG_SIDE,
    PICTURE_REVIEW_WEIGHT_TOTAL,
    PictureSetRecord,
)
from seed_review_errors import SeedReviewError
from seed_review_metrics import (
    DUPLICATE_WEIGHT,
    EXPOSURE_WEIGHT,
    FOCUS_WEIGHT,
    analysis_gray,
    duplicate_similarity,
    exposure_measurements,
    focus_score,
    laplacian_variance,
    load_native_gray,
    rounded,
)


def evaluate_and_rank_images(
    source: PictureSetRecord, root: Path
) -> list[dict[str, Any]]:
    records, analysis_images = _evaluate_images(source, root)
    _score_duplicates(records, analysis_images)
    return _rank_images(records)


def _evaluate_images(
    source: PictureSetRecord, root: Path
) -> tuple[list[dict[str, Any]], list[Any]]:
    records = []
    analysis_images = []
    for image in source.images:
        native = load_native_gray(root / image["path"])
        if native.shape != (image["height"], image["width"]):
            raise SeedReviewError(
                "picture_size_mismatch",
                f"Picture dimensions changed: {image['image_id']}",
            )
        analysis = analysis_gray(native)
        analysis_images.append(analysis)
        mean, clipped_low, clipped_high, exposure = exposure_measurements(native)
        records.append(
            _candidate_metrics(
                image, native, analysis, mean, clipped_low, clipped_high, exposure
            )
        )
    return records, analysis_images


def _candidate_metrics(
    image: dict[str, Any],
    native: Any,
    analysis: Any,
    mean: float,
    clipped_low: float,
    clipped_high: float,
    exposure: float,
) -> dict[str, Any]:
    low_resolution = max(image["width"], image["height"]) < MIN_HUNYUAN_LONG_SIDE
    return {
        "image_id": image["image_id"],
        "capture_index": image["capture_index"],
        "path": image["path"],
        "sha256": image["sha256"],
        "width": image["width"],
        "height": image["height"],
        "origin": "direct_source_picture",
        "decode_operation": DIRECT_IMAGE_REVIEW,
        "resolution_warning": low_resolution,
        "resolution_warning_code": LOW_RESOLUTION_REASON if low_resolution else None,
        "metrics": {
            "focus_native_laplacian_variance": rounded(laplacian_variance(native)),
            "focus_analysis_laplacian_variance": rounded(laplacian_variance(analysis)),
            "exposure_mean_luminance": rounded(mean),
            "exposure_clipped_low_fraction": rounded(clipped_low),
            "exposure_clipped_high_fraction": rounded(clipped_high),
            "exposure_score": rounded(exposure),
            "duplicate_similarity": 0.0,
            "mechanical_score": 0.0,
        },
    }


def _score_duplicates(
    records: list[dict[str, Any]], analysis_images: list[Any]
) -> None:
    max_focus = max(
        item["metrics"]["focus_analysis_laplacian_variance"] for item in records
    )
    for index, record in enumerate(records):
        metrics = record["metrics"]
        focus = focus_score(metrics["focus_analysis_laplacian_variance"], max_focus)
        others = [
            image for position, image in enumerate(analysis_images) if position != index
        ]
        duplicate = duplicate_similarity(analysis_images[index], others)
        weighted = (
            FOCUS_WEIGHT * focus
            + EXPOSURE_WEIGHT * metrics["exposure_score"]
            + DUPLICATE_WEIGHT * (1.0 - duplicate)
        ) / PICTURE_REVIEW_WEIGHT_TOTAL
        metrics["focus_score"] = rounded(focus)
        metrics["duplicate_similarity"] = rounded(duplicate)
        metrics["mechanical_score"] = rounded(weighted)


def _rank_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        images,
        key=lambda image: (
            -image["metrics"]["mechanical_score"],
            -image["metrics"]["focus_score"],
            -image["metrics"]["exposure_score"],
            image["capture_index"],
            image["image_id"],
        ),
    )
    for rank, image in enumerate(ordered, start=1):
        image["mechanical_rank"] = rank
    return ordered
