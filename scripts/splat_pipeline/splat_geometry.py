#!/usr/bin/env python3
"""Pure-geometry measurements used to derive the frame contract.

A Gaussian's covariance is ``R S S^T R^T``, so the row of ``R`` paired with the
smallest linear scale is the surface normal of the surface that splat was fitted
to.  Flat, axis-aligned architecture therefore shows up as splats whose
``|dot(normal, axis)| ~= 1``, and the *positions* of those splats cluster on the
plane offsets.

Two things this module refuses to do, because getting them wrong is what made the
original bug so hard to see:

* It does not trust the normal's **sign**. A covariance encodes an axis, not a
  facing, so "up-facing" and "down-facing" splats are indistinguishable. Floor
  and ceiling are therefore found as the two dominant *modes* along the up axis,
  never by splitting on sign -- splitting on sign silently finds the same sheet
  twice and reports a zero-thickness room.
* It does not report a measurement it cannot repeat. Every plane carries the
  number of splats behind it and a spread measured across independent stations,
  so a caller can fail loudly instead of inventing a landmark.

Everything here is a pure function of its inputs, so the numbers in a manifest
can be re-derived without touching a Godot project.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

# A splat counts as "perpendicular to this axis" above this |cos| angle, i.e.
# within 30 degrees of axis-aligned.  Backrooms walls and slabs are boxy; rounder
# geometry is a smear and must not become a landmark.
AXIS_ALIGNED_COSINE = float(np.cos(np.deg2rad(30.0)))

# A plane is only accepted when its mode is at least this much denser than the
# axis background.  8x was set from measurement, not taste: on this scene's PLY
# the true floor/ceiling reach 17x and 24x, while the horizontal axes peak at
# 2-7x and are smooth blobs rather than walls.  A threshold low enough to accept
# those would be accepting floaters, so horizontal-wall measurement is reported
# as unavailable rather than invented.
MIN_MODE_CONTRAST = 8.0

# Independent measurements a spread needs before it is worth reporting.
MIN_SPREAD_SAMPLES = 3

# A surface's averaging band spans at least this many histogram bins either side
# of its mode. One is too few: a flat sheet's peak is often a single bin wide, and
# averaging a 16-splat band gives a noisy plane offset.
MIN_REACH_BINS = 4.0

# Minimum splats in a surface's averaging band before its offset is trusted.
MIN_BAND_SAMPLES = 50


class MeasurementError(ValueError):
    """Raised when a plane or axis cannot be measured to a usable standard."""


@dataclass(frozen=True)
class Plane:
    """One measured axis-aligned surface, in reconstruction units."""

    axis: int
    offset: float
    spread: float
    sample_count: int
    contrast: float


def quaternions_to_rotations(quaternions: np.ndarray) -> np.ndarray:
    """Convert ``(N, 4)`` (w, x, y, z) quaternions to ``(N, 3, 3)`` rotation matrices."""
    quaternions = np.asarray(quaternions, dtype=np.float64)
    if quaternions.ndim != 2 or quaternions.shape[1] != 4:
        raise ValueError("quaternions must be (N, 4)")
    norms = np.linalg.norm(quaternions, axis=1)
    if not np.all(norms > 1e-12):
        raise ValueError("degenerate quaternion in input")
    w, x, y, z = (quaternions / norms[:, None]).T
    out = np.empty((len(w), 3, 3))
    out[:, 0, 0] = 1 - 2 * (y * y + z * z)
    out[:, 0, 1] = 2 * (x * y - z * w)
    out[:, 0, 2] = 2 * (x * z + y * w)
    out[:, 1, 0] = 2 * (x * y + z * w)
    out[:, 1, 1] = 1 - 2 * (x * x + z * z)
    out[:, 1, 2] = 2 * (y * z - x * w)
    out[:, 2, 0] = 2 * (x * z - y * w)
    out[:, 2, 1] = 2 * (y * z + x * w)
    out[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return out


def gaussian_normal_axes(scales_linear: np.ndarray, quaternions: np.ndarray) -> np.ndarray:
    """Return one unsigned normal axis per Gaussian, unit length.

    Uses the row of the rotation paired with the smallest linear scale.  Sign is
    deliberately not canonicalised here or consumed later: a covariance describes
    an axis, never a facing, so callers must find surfaces as mode *pairs* along
    an axis rather than by sign.
    """
    scales_linear = np.asarray(scales_linear, dtype=np.float64)
    rotations = quaternions_to_rotations(quaternions)
    smallest = np.argmin(scales_linear, axis=1)
    normals = rotations[np.arange(len(scales_linear)), smallest]
    norms = np.linalg.norm(normals, axis=1)
    if not np.all(norms > 1e-9):
        raise ValueError("degenerate rotation row in input")
    return normals / norms[:, None]


def axis_aligned_mask(normals: np.ndarray, axis: int) -> np.ndarray:
    """Return the mask of splats whose normal is perpendicular to ``axis``."""
    return np.abs(normals[:, axis]) >= AXIS_ALIGNED_COSINE


def measure_plane_pair(
    points: np.ndarray,
    normals: np.ndarray,
    axis: int,
    bin_width: float,
    min_separation: float,
) -> tuple[Plane, Plane]:
    """Return the two dominant surfaces on ``axis``, low offset first.

    Used for floor/ceiling and for the two side walls.  Both are found as the two
    tallest well-separated histogram modes among axis-aligned splats.
    """
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points must be (N, 3)")
    if not 0 <= axis <= 2:
        raise ValueError("axis must be 0, 1 or 2")
    mask = axis_aligned_mask(normals, axis)
    values = points[mask, axis]
    if values.size < 200:
        raise MeasurementError(
            "only %d splats are axis-aligned on %s; cannot resolve a plane pair"
            % (values.size, "xyz"[axis])
        )
    modes = _dominant_modes(values, bin_width, min_separation, count=2)
    if len(modes) != 2:
        raise MeasurementError(
            "found %d separated surface modes on %s, expected 2"
            % (len(modes), "xyz"[axis])
        )
    background = _background_level(values, bin_width)
    lower, upper = (_plane_from_mode(values, mode, axis, background) for mode in modes)
    return lower, upper


def measure_plane_strength(points: np.ndarray, normals: np.ndarray, axis: int) -> float:
    """Return how strongly two surfaces stand out on ``axis``, or 0.0 if unclear.

    Used to decide which non-up axis is the room's width, instead of assuming the
    axis that happens to be wider in the bounding box.
    """
    try:
        lower, upper = measure_plane_pair(points, normals, axis, 0.02, 0.05)
    except MeasurementError:
        return 0.0
    return float(min(lower.contrast, upper.contrast))


def measure_clear_height(
    points: np.ndarray, normals: np.ndarray, up_axis: int, bin_width: float = 0.02
) -> tuple[float, float, int]:
    """Return ``(height, spread, stations)`` between floor and ceiling.

    The separation is re-measured independently in slabs along the corridor, and
    the returned spread is their standard deviation.  That is the honest
    uncertainty of the metric reference: a per-Gaussian sheet thickness is not,
    because it barely moves between slabs.
    """
    lower, upper, spread, stations = measure_room_bounds(points, normals, up_axis, bin_width)
    return float(upper.offset - lower.offset), spread, stations


def measure_room_bounds(
    points: np.ndarray, normals: np.ndarray, up_axis: int, bin_width: float = 0.02
) -> tuple[Plane, Plane, float, int]:
    """Return ``(lower_plane, upper_plane, spread, stations)`` along the up axis.

    "Lower" and "upper" are by *offset*, not by facing: which one is the floor
    depends on the up axis sign, and that sign is only known once the frame's up
    direction has been measured from the camera poses.
    """
    lower, upper = measure_plane_pair(points, normals, up_axis, bin_width, 0.05)
    length_axis = (up_axis + 1) % 3
    stations = _station_heights(points, up_axis, lower.offset, upper.offset, length_axis)
    if len(stations) < MIN_SPREAD_SAMPLES:
        raise MeasurementError(
            "only %d usable corridor stations on axis %d; cannot bound the spread"
            % (len(stations), up_axis)
        )
    return lower, upper, float(np.std(stations, ddof=1)), len(stations)


def _background_level(values: np.ndarray, bin_width: float) -> float:
    """Return the typical per-bin splat count away from any surface.

    The median is used rather than the mean so a handful of huge floaters cannot
    inflate the "background" and make a real wall look like a smear.  This is the
    denominator of :data:`MIN_MODE_CONTRAST`.
    """
    low, high = float(values.min()), float(values.max())
    bins = max(int(np.ceil((high - low) / bin_width)), 4)
    counts, _ = np.histogram(values, bins=bins, range=(low, low + bins * bin_width))
    occupied = counts[counts > 0]
    return float(np.median(occupied)) if occupied.size else 0.0


def _plane_from_mode(
    values: np.ndarray, mode: tuple[float, float, int], axis: int, background: float
) -> Plane:
    """Turn a histogram mode into a :class:`Plane` with its own spread.

    ``contrast`` is the mode's peak density over the axis's background density.
    Comparing against the axis background rather than against the bins immediately
    beside the sheet matters because a real surface is flanked by its own
    falloff, so a local comparison rejects every genuine wall.
    """
    centre, half_width, peak_count = mode
    band = values[np.abs(values - centre) <= half_width]
    if band.size < MIN_BAND_SAMPLES:
        raise MeasurementError(
            "surface mode at %+.4f on axis %d has only %d splats in its band"
            % (centre, axis, band.size)
        )
    contrast = float(peak_count / max(background, 1.0))
    if contrast < MIN_MODE_CONTRAST:
        raise MeasurementError(
            "surface mode at %+.4f on axis %d peaks at only %.2fx the background density"
            % (centre, axis, contrast)
        )
    return Plane(
        axis=axis,
        offset=float(band.mean()),
        spread=float(band.std()),
        sample_count=int(band.size),
        contrast=contrast,
    )


def _station_heights(
    points: np.ndarray,
    up_axis: int,
    lower_offset: float,
    upper_offset: float,
    length_axis: int,
    band: float = 0.05,
    minimum_samples: int = 400,
) -> np.ndarray:
    """Measure the lower/upper separation once per slab along ``length_axis``.

    Re-measuring per slab is what turns one reconstruction's sheet thickness into
    a genuine spread: a systematic error (a sloped floor, a warped
    reconstruction) varies along the corridor, per-Gaussian noise does not.
    """
    values = points[:, length_axis]
    edges = np.linspace(float(values.min()), float(values.max()), 15)
    heights: list[float] = []
    for start, stop in pairwise(edges):
        slab = points[(values >= start) & (values < stop)]
        if len(slab) < minimum_samples:
            continue
        along_up = slab[:, up_axis]
        low = along_up[np.abs(along_up - lower_offset) <= band]
        high = along_up[np.abs(along_up - upper_offset) <= band]
        if low.size < MIN_BAND_SAMPLES or high.size < MIN_BAND_SAMPLES:
            continue
        heights.append(float(high.mean() - low.mean()))
    return np.asarray(heights, dtype=np.float64)





def _dominant_modes(
    values: np.ndarray, bin_width: float, min_separation: float, count: int
) -> list[tuple[float, float, int]]:
    """Return up to ``count`` tallest, well-separated histogram modes.

    Each mode is ``(centre, half_width, bin_count)``; ``half_width`` spans from
    the mode to where its support drops below a quarter of its height, so callers
    can gather a tight band without dragging in the neighbouring mode.
    """
    if bin_width <= 0.0:
        raise ValueError("bin_width must be positive")
    if min_separation <= 0.0:
        raise ValueError("min_separation must be positive")
    low, high = float(values.min()), float(values.max())
    bins = max(int(np.ceil((high - low) / bin_width)), 4)
    counts, edges = np.histogram(values, bins=bins, range=(low, low + bins * bin_width))
    centres = (edges[:-1] + edges[1:]) * 0.5
    step = float(edges[1] - edges[0])

    picked: list[int] = []
    for index in np.argsort(counts)[::-1]:
        if counts[index] <= 0:
            break
        if all(abs(centres[index] - centres[other]) >= min_separation for other in picked):
            picked.append(int(index))
        if len(picked) == count:
            break

    modes = []
    for index in sorted(picked):
        floor = counts[index] * 0.25
        # A band narrower than a couple of bins holds too few splats to average
        # meaningfully, and a sheet's peak is routinely only one bin wide.
        reach = step * MIN_REACH_BINS * 0.5
        for other in range(index - 1, -1, -1):
            if counts[other] < floor or centres[index] - centres[other] >= min_separation:
                break
            reach = max(reach, centres[index] - centres[other])
        for other in range(index + 1, len(counts)):
            if counts[other] < floor or centres[other] - centres[index] >= min_separation:
                break
            reach = max(reach, centres[other] - centres[index])
        modes.append((float(centres[index]), float(reach), int(counts[index])))
    return modes