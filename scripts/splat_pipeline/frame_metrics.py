#!/usr/bin/env python3
"""Per-frame quality and motion metrics, computed with numpy alone.

Deliberately free of OpenCV. OpenCV is not installed in every environment this
pipeline runs in (``validate_input.py`` degrades when it is missing), and a
quality gate that silently switches measurement engines reports numbers that
cannot be compared across machines. These metrics are plain array arithmetic, so
the same input produces the same number anywhere numpy runs.

Two questions are answered here, and they are different questions:

* **Is this frame sharp?** ``laplacian_variance`` -- variance of a 4-neighbour
  Laplacian. Higher is sharper. It is measured at the *analysis* resolution, so
  its absolute value is only comparable between runs that use the same one.
* **Did the camera move sideways, or did the picture change some other way?**
  ``estimate_translation`` finds the single global translation that best
  explains the change, then reports how much of the change that translation
  *failed* to explain. A camera that translates leaves structure behind (the
  residual); a camera that only rotates or a frame whose content is rewritten
  leaves a residual as large as the original change.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Intensity levels per histogram bin. 32 bins over 8 levels of grey is the
#: usual content-detection resolution: fine enough to separate two views of a
#: room, coarse enough that sensor noise does not register as a change.
HISTOGRAM_BINS = 32

#: Coarse-to-fine search: average-pool by this factor, search the pooled frame,
#: then refine +/- FINE_RADIUS px on the full-resolution frame.
SEARCH_POOL_FACTOR = 4
FINE_SEARCH_RADIUS_PX = 2

#: Search radius growth. The radius starts around the previous pair's shift and
#: doubles when the residual says the alignment did not land.
SEED_RADIUS_FRACTION = 0.35
MIN_SEARCH_RADIUS_PX = 12
MAX_SEARCH_RADIUS_FRACTION = 0.35
MAX_SEARCH_ESCALATIONS = 2

#: A residual above this fraction means the reported shift does not explain the
#: pair, so the search widens instead of trusting a bad alignment.
ALIGNMENT_RESIDUAL_LIMIT = 0.12

#: Residual block grid. A 24 px block at 640 px width is 3.75% of the frame,
#: small enough to localise a person and large enough not to chase noise.
RESIDUAL_BLOCK_PX = 24
RESIDUAL_LEVEL_LIMIT = 12


@dataclass(frozen=True)
class TranslationEstimate:
    """One pair's best global translation and what it failed to explain."""

    dx_px: int
    dy_px: int
    frame_width_px: int
    change_before_px: float
    change_after_px: float
    residual_fraction: float
    hot_block_fraction: float

    @property
    def magnitude_px(self) -> float:
        """Translation distance in pixels."""
        return float(np.hypot(self.dx_px, self.dy_px))

    @property
    def magnitude_fraction(self) -> float:
        """Translation distance as a fraction of the frame width.

        Scale-free, and the form the verdict rules compare: "the camera moved
        2% of the frame between samples" transfers between 720p and 4K, and a
        pixel threshold would not.
        """
        return self.magnitude_px / self.frame_width_px if self.frame_width_px else 0.0

    @property
    def explained_fraction(self) -> float:
        """Share of the frame change the global translation accounts for."""
        if self.change_before_px <= 0:
            return 1.0
        return max(0.0, 1.0 - self.change_after_px / self.change_before_px)


def pool_mean(frame: np.ndarray, factor: int) -> np.ndarray:
    """Average-pool a frame by ``factor``; the trailing rows/columns are dropped."""
    height, width = frame.shape
    usable_h = height - height % factor
    usable_w = width - width % factor
    if usable_h == 0 or usable_w == 0:
        return frame.astype(np.int16)
    pooled = frame[:usable_h, :usable_w].reshape(usable_h // factor, factor, usable_w // factor, factor)
    return pooled.mean(axis=(1, 3)).astype(np.int16)


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian: the sharpness score."""
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    values = gray.astype(np.int16)
    laplacian = (
        -4 * values[1:-1, 1:-1]
        + values[:-2, 1:-1]
        + values[2:, 1:-1]
        + values[1:-1, :-2]
        + values[1:-1, 2:]
    )
    return float(laplacian.var())


def intensity_histogram(gray: np.ndarray, bins: int = HISTOGRAM_BINS) -> np.ndarray:
    """Normalised intensity histogram of one frame."""
    counts, _ = np.histogram(gray, bins=bins, range=(0, 256))
    total = counts.sum()
    return counts / total if total else counts.astype(np.float64)


def histogram_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Total-variation distance between two normalised histograms (0 to 2)."""
    return float(np.abs(first - second).sum())


def _overlap_slices(size: int, shift: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Slices of two equal-length axes that overlap under ``shift``."""
    near = (max(0, shift), size - max(0, -shift))
    return near, (near[0] - shift, near[1] - shift)


def _shift_candidates(size: int, centre: int, radius: int) -> range:
    """Shifts to try on an axis of length ``size``, near ``centre``.

    A shift only compares anything when the two frames still overlap, so the
    usable range is ``[-(size-1), size-1]``. The radius alone does not enforce
    that: a seed near the far edge pushes ``centre + radius`` past ``size``, the
    overlap becomes empty, and the mean of an empty slice is not a measurement
    of anything. So the window is intersected with the range that still overlaps,
    and a centre outside it collapses onto the nearest shift that does.
    """
    limit = size - 1
    low, high = max(-limit, centre - radius), min(limit, centre + radius)
    if low > high:
        low = high = max(-limit, min(limit, centre))
    return range(low, high + 1)


def _search_shift(first: np.ndarray, second: np.ndarray, cx: int, cy: int, radius: int) -> tuple[int, int]:
    """Integer shift near ``(cx, cy)`` minimising mean absolute difference."""
    height, width = first.shape
    radius = min(radius, height // 2, width // 2)
    best_difference = np.inf
    best = (0, 0)
    for dy in _shift_candidates(height, cy, radius):
        (ya, ya_end), (yb, yb_end) = _overlap_slices(height, dy)
        for dx in _shift_candidates(width, cx, radius):
            (xa, xa_end), (xb, xb_end) = _overlap_slices(width, dx)
            window = first[ya:ya_end, xa:xa_end]
            shifted = second[yb:yb_end, xb:xb_end]
            difference = float(np.abs(window - shifted).mean())
            if difference < best_difference:
                best_difference, best = difference, (dx, dy)
    return best


def hierarchical_shift(
    first: np.ndarray, second: np.ndarray, seed: tuple[int, int], radius: int
) -> tuple[int, int]:
    """Locate the shift near ``seed``: pooled coarse search, then full-res refine."""
    factor = SEARCH_POOL_FACTOR
    pooled_radius = max(2, radius // factor)
    cx, cy = seed[0] // factor, seed[1] // factor
    dx, dy = _search_shift(pool_mean(first, factor), pool_mean(second, factor), cx, cy, pooled_radius)
    return _search_shift(first, second, dx * factor, dy * factor, FINE_SEARCH_RADIUS_PX)


def residual_map(first: np.ndarray, second: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Absolute per-pixel difference after compensating ``(dx, dy)``."""
    height, width = first.shape
    compensated = np.full((height, width), 128, dtype=np.int16)
    (ya, ya_end), (yb, yb_end) = _overlap_slices(height, dy)
    (xa, xa_end), (xb, xb_end) = _overlap_slices(width, dx)
    compensated[ya:ya_end, xa:xa_end] = second[yb:yb_end, xb:xb_end]
    return np.abs(first.astype(np.int16) - compensated)


def residual_fractions(residual: np.ndarray, block_px: int = RESIDUAL_BLOCK_PX) -> tuple[float, float]:
    """Return ``(pixel fraction changed, block fraction changed)`` for a residual."""
    changed = residual >= RESIDUAL_LEVEL_LIMIT
    height, width = residual.shape
    blocks_h, blocks_w = height // block_px, width // block_px
    if blocks_h and blocks_w:
        trimmed = changed[: blocks_h * block_px, : blocks_w * block_px]
        per_block = trimmed.reshape(blocks_h, block_px, blocks_w, block_px).mean(axis=(1, 3))
        hot_blocks = float((per_block >= 0.5).mean())
    else:
        hot_blocks = 0.0
    return float(changed.mean()), hot_blocks


def _search_radius(frame_width: int, seed: tuple[int, int]) -> int:
    """Radius around ``seed``: wide enough to follow the motion, capped."""
    reach = SEED_RADIUS_FRACTION * max(abs(seed[0]), abs(seed[1])) + MIN_SEARCH_RADIUS_PX
    ceiling = int(MAX_SEARCH_RADIUS_FRACTION * frame_width)
    return int(min(ceiling, max(MIN_SEARCH_RADIUS_PX, reach)))


def _measure_pair(
    first: np.ndarray, second: np.ndarray, seed: tuple[int, int], radius: int
) -> TranslationEstimate:
    dx, dy = hierarchical_shift(first, second, seed, radius)
    residual = residual_map(first, second, dx, dy)
    pixel_fraction, block_fraction = residual_fractions(residual)
    before = float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())
    return TranslationEstimate(
        dx_px=dx,
        dy_px=dy,
        frame_width_px=first.shape[1],
        change_before_px=before,
        change_after_px=float(residual.mean()),
        residual_fraction=pixel_fraction,
        hot_block_fraction=block_fraction,
    )


def estimate_translation(
    first: np.ndarray, second: np.ndarray, seed: tuple[int, int] = (0, 0)
) -> TranslationEstimate:
    """Best global translation between two frames, widened until it explains them.

    The search is seeded with the previous pair's shift because camera motion is
    continuous, which keeps the radius small on long clips. When the residual
    says the alignment did not land, the radius doubles and the search is
    repeated -- a wrong shift is reported as a large residual rather than as a
    confident zero.
    """
    ceiling = int(MAX_SEARCH_RADIUS_FRACTION * first.shape[1])
    radius = _search_radius(first.shape[1], seed)
    best = _measure_pair(first, second, seed, radius)
    for _ in range(MAX_SEARCH_ESCALATIONS):
        if best.residual_fraction <= ALIGNMENT_RESIDUAL_LIMIT or radius >= ceiling:
            break
        radius = min(radius * 2, ceiling)
        wider = _measure_pair(first, second, seed, radius)
        if wider.residual_fraction >= best.residual_fraction:
            break
        best = wider
    return best


def is_scene_cut(previous_histogram: np.ndarray, histogram: np.ndarray, limit: float) -> bool:
    """True when two consecutive samples differ more than a cut limit allows."""
    return histogram_distance(previous_histogram, histogram) > limit