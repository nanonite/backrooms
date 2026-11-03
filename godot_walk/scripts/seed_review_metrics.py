"""Mechanical focus, exposure, duplicate, and coverage measurements."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError
from seed_review_errors import SeedReviewError

ANALYSIS_WIDTH = 640
ANALYSIS_HEIGHT = 360
DUPLICATE_SIZE = 32
TEMPORAL_TARGET_SECONDS = 0.5

FOCUS_WEIGHT = 0.50
EXPOSURE_WEIGHT = 0.25
DUPLICATE_WEIGHT = 0.15
TEMPORAL_WEIGHT = 0.10

CLIPPED_LOW_LEVEL = 5.0
CLIPPED_HIGH_LEVEL = 250.0
LUMINANCE_CENTER = 0.5
LUMINANCE_TOLERANCE_GAIN = 1.4
CLIPPING_PENALTY_GAIN = 0.6


def load_native_gray(path: Path) -> np.ndarray:
    """Load a frame as native-resolution 8-bit luminance."""
    try:
        with Image.open(path) as image:
            return np.asarray(image.convert("L"), dtype=np.float64)
    except (OSError, UnidentifiedImageError) as error:
        raise SeedReviewError(
            "frame_unreadable", f"Cannot read candidate frame: {path}"
        ) from error


def analysis_gray(native: np.ndarray) -> np.ndarray:
    """Downsample one native frame to the fixed analysis size."""
    image = Image.fromarray(native.astype(np.uint8), mode="L")
    resized = image.resize(
        (ANALYSIS_WIDTH, ANALYSIS_HEIGHT), resample=Image.Resampling.BICUBIC
    )
    return np.asarray(resized, dtype=np.float64)


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of a four-neighbour Laplacian; compare only within one set."""
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    laplacian = (
        -4.0 * gray
        + np.roll(gray, 1, axis=0)
        + np.roll(gray, -1, axis=0)
        + np.roll(gray, 1, axis=1)
        + np.roll(gray, -1, axis=1)
    )
    return float(np.var(laplacian))


def exposure_measurements(gray: np.ndarray) -> tuple[float, float, float, float]:
    """Return mean luminance, clipped-low fraction, clipped-high fraction, score."""
    mean_luminance = float(gray.mean() / 255.0) if gray.size else 0.0
    low_fraction = float(np.count_nonzero(gray <= CLIPPED_LOW_LEVEL) / gray.size)
    high_fraction = float(np.count_nonzero(gray >= CLIPPED_HIGH_LEVEL) / gray.size)
    deviation = abs(mean_luminance - LUMINANCE_CENTER)
    score = 1.0 - deviation * LUMINANCE_TOLERANCE_GAIN
    score -= (low_fraction + high_fraction) * CLIPPING_PENALTY_GAIN
    return mean_luminance, low_fraction, high_fraction, _clamp(score)


def duplicate_similarity(gray: np.ndarray, others: list[np.ndarray]) -> float:
    """Maximum 32x32 greyscale similarity to another candidate."""
    if not others:
        return 0.0
    image = Image.fromarray(gray.astype(np.uint8), mode="L").resize(
        (DUPLICATE_SIZE, DUPLICATE_SIZE), resample=Image.Resampling.BILINEAR
    )
    comparison = np.asarray(image, dtype=np.float64)
    similarities = []
    for other in others:
        other_image = Image.fromarray(other.astype(np.uint8), mode="L").resize(
            (DUPLICATE_SIZE, DUPLICATE_SIZE), resample=Image.Resampling.BILINEAR
        )
        other_array = np.asarray(other_image, dtype=np.float64)
        mean_absolute_difference = float(np.abs(comparison - other_array).mean())
        similarities.append(_clamp(1.0 - mean_absolute_difference / 255.0))
    return max(similarities)


def temporal_gap_seconds(pts_seconds: float, all_pts_seconds: list[float]) -> float:
    """Nearest-neighbour presentation-time gap within the candidate set."""
    gaps = [
        abs(pts_seconds - other) for other in all_pts_seconds if other != pts_seconds
    ]
    return min(gaps) if gaps else 0.0


def focus_score(value: float, maximum: float) -> float:
    return _clamp(value / maximum) if maximum > 0 else 0.0


def temporal_coverage_score(gap_seconds: float) -> float:
    return _clamp(gap_seconds / TEMPORAL_TARGET_SECONDS)


def mechanical_score(
    focus: float,
    exposure: float,
    duplicate: float,
    temporal: float,
) -> float:
    score = (
        FOCUS_WEIGHT * focus
        + EXPOSURE_WEIGHT * exposure
        + DUPLICATE_WEIGHT * (1.0 - duplicate)
        + TEMPORAL_WEIGHT * temporal
    )
    return round(_clamp(score), 6)


def rounded(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
