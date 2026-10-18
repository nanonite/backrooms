"""Candidate color segmentation for inspection only; no geometry is produced."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class FloorColorRule:
    """PIL HSV threshold and bottom-seed region settings for the experiment."""

    hue_min: int = 26
    hue_max: int = 35
    saturation_min: int = 125
    value_min: int = 80
    value_max: int = 205
    top_fraction: float = 0.42
    seed_band_rows: int = 8


def candidate_mask(hsv: np.ndarray, rule: FloorColorRule) -> np.ndarray:
    """Return raw HSV candidates below a conservative upper-image crop."""
    values = np.asarray(hsv)
    if values.ndim != 3 or values.shape[2] != 3:
        raise ValueError("HSV image must have shape HxWx3")
    if not np.issubdtype(values.dtype, np.integer):
        raise ValueError("PIL HSV input must use integer channel values")
    if not 0.0 <= rule.top_fraction < 1.0 or rule.seed_band_rows < 1:
        raise ValueError("vertical crop and seed band are invalid")

    height = values.shape[0]
    top_row = int(height * rule.top_fraction)
    hue = values[..., 0]
    saturation = values[..., 1]
    value = values[..., 2]
    below_ceiling_crop = np.arange(height)[:, None] >= top_row
    return (
        below_ceiling_crop
        & (hue >= rule.hue_min)
        & (hue <= rule.hue_max)
        & (saturation >= rule.saturation_min)
        & (value >= rule.value_min)
        & (value <= rule.value_max)
    )


def bottom_connected_mask(
    candidates: np.ndarray, seed_band_rows: int = 8
) -> tuple[np.ndarray, dict]:
    """Keep candidate components touching the lower image seed band, without closing gaps."""
    mask = np.asarray(candidates, dtype=bool)
    if mask.ndim != 2 or min(mask.shape) < 2:
        raise ValueError("candidate mask must be a 2D image")
    if seed_band_rows < 1:
        raise ValueError("seed band must contain at least one row")

    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    seed_start = max(0, mask.shape[0] - seed_band_rows)
    seed_labels = np.unique(labels[seed_start:])
    seed_labels = seed_labels[seed_labels != 0]
    selected = np.isin(labels, seed_labels)
    component_sizes = np.bincount(labels.ravel(), minlength=count + 1)[1:]
    seeded_sizes = component_sizes[seed_labels - 1]
    return selected, {
        "candidate_component_count_8_connected": int(count),
        "bottom_seeded_component_count": len(seed_labels),
        "bottom_seeded_component_pixels": int(selected.sum()),
        "largest_bottom_seeded_component_pixels": int(seeded_sizes.max())
        if len(seeded_sizes)
        else 0,
    }
