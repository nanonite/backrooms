#!/usr/bin/env python3
"""Bounded, deterministic cleanup of a 3DGS PLY for low-resolution presentation.

This module holds the *decision* only: given per-splat world positions,
opacities and extents, plus explicit parameters, which splats are kept. It does
no file I/O and touches no GPU, so the same inputs always produce the same kept
set and the logic can be unit-tested against tiny synthetic arrays.

Why a mask rather than a renderer toggle: the corridor splat's far-field
floaters are not faint. Measured on the shipped asset, 56.8% of the 182,569
splats sit outside the contract's observed room and their opacity median is
0.995 -- the existing compositor ``alpha_cutoff`` cannot remove them, because
they are opaque. They are removed by *where they are*, not by how transparent
they are. See ``godot_walk/assets/corridor_splat/CLEANUP.md``.

The pipeline applies three stages in a fixed order, each a boolean over the
survivors of the previous one:

1. ``bounds``  -- world position inside the crop box (the measured room plus a
   margin). This is what removes the far-field floaters.
2. ``extent``  -- maximum Gaussian extent in metres below a threshold. Removes
   giant splats that stay inside the box but smear across the view.
3. ``opacity`` -- sigmoid(opacity) at or above a threshold. Off by default: on
   this asset it removes almost nothing real and risks deleting faint surfaces.

Determinism is the point. There is no sampling, no RNG and no percentile chosen
from the data being filtered (a percentile threshold is a function of the very
outliers it is meant to drop, so a future asset changes it silently). Every
threshold is an explicit parameter recorded in the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: Stage names, in application order. Used as report keys.
STAGE_BOUNDS = "bounds"
STAGE_EXTENT = "extent"
STAGE_OPACITY = "opacity"
STAGES = (STAGE_BOUNDS, STAGE_EXTENT, STAGE_OPACITY)


def sigmoid_opacity(opacity_log: np.ndarray) -> np.ndarray:
    """Return ``sigmoid(opacity_log)``, the 3DGS per-splat alpha.

    The PLY stores opacity as a logit; GDGS applies the same sigmoid at import,
    so a threshold here means the same thing the renderer sees.
    """
    return 1.0 / (1.0 + np.exp(-opacity_log))


def max_extent_metres(scale_log: np.ndarray, metres_per_unit: float) -> np.ndarray:
    """Return each splat's largest axis extent in metres from its log-scales.

    3DGS ``scale_i`` are logarithms, so the linear extent is ``exp(scale_i)`` in
    reconstruction units and is scaled by ``metres_per_unit`` to compare against
    a metre threshold.
    """
    return np.exp(scale_log).max(axis=1) * metres_per_unit


def crop_bounds_from_room(
    room_min: tuple[float, float, float],
    room_max: tuple[float, float, float],
    margin_m: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the world-space crop box as ``(min, max)``.

    The room's horizontal extents are observation bounds, not measured walls
    (``capture.walls_measured`` is false for this capture), so the margin exists
    to keep wall surfaces that sit a little outside the observed window. It is
    an explicit parameter, never inferred from the cloud.
    """
    if margin_m < 0.0:
        raise ValueError("margin_m must not be negative")
    low = tuple(float(value) - margin_m for value in room_min)
    high = tuple(float(value) + margin_m for value in room_max)
    return low, high


@dataclass(frozen=True)
class CleanupParams:
    """Explicit, serialisable cleanup parameters.

    ``max_extent_m`` and ``min_opacity`` of ``0.0`` disable their stage, so a
    crop-only cleanup is expressible and the report says which stages ran.
    """

    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    max_extent_m: float = 0.0
    min_opacity: float = 0.0

    def __post_init__(self) -> None:
        if any(high < low for low, high in zip(self.bounds_min, self.bounds_max)):
            raise ValueError("bounds_max must not be below bounds_min on any axis")
        if self.max_extent_m < 0.0:
            raise ValueError("max_extent_m must not be negative (0 disables it)")
        if not 0.0 <= self.min_opacity < 1.0:
            raise ValueError("min_opacity must be in [0, 1) (0 disables it)")

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict of the parameters."""
        return {
            "bounds_min": list(self.bounds_min),
            "bounds_max": list(self.bounds_max),
            "max_extent_m": self.max_extent_m,
            "min_opacity": self.min_opacity,
        }

    @classmethod
    def from_room(
        cls,
        room_min: tuple[float, float, float],
        room_max: tuple[float, float, float],
        *,
        margin_m: float,
        max_extent_m: float = 0.0,
        min_opacity: float = 0.0,
    ) -> "CleanupParams":
        """Build parameters that crop to the room plus ``margin_m``."""
        low, high = crop_bounds_from_room(room_min, room_max, margin_m)
        return cls(
            bounds_min=low,
            bounds_max=high,
            max_extent_m=max_extent_m,
            min_opacity=min_opacity,
        )


def compute_keep_mask(
    world_positions: np.ndarray,
    opacity: np.ndarray,
    extent_m: np.ndarray,
    params: CleanupParams,
) -> tuple[np.ndarray, dict[str, int]]:
    """Return ``(keep_mask, removed_per_stage)``.

    ``world_positions`` is ``(N, 3)`` in Godot world metres; ``opacity`` and
    ``extent_m`` are ``(N,)``. ``removed_per_stage`` counts each splat once, at
    the stage that first rejects it, so the counts sum to ``N - kept``.
    """
    world_positions = np.asarray(world_positions, dtype=np.float64)
    opacity = np.asarray(opacity, dtype=np.float64)
    extent_m = np.asarray(extent_m, dtype=np.float64)
    if world_positions.ndim != 2 or world_positions.shape[1] != 3:
        raise ValueError("world_positions must have shape (N, 3)")
    count = world_positions.shape[0]
    if opacity.shape != (count,) or extent_m.shape != (count,):
        raise ValueError("opacity and extent_m must have shape (N,)")

    low = np.asarray(params.bounds_min, dtype=np.float64)
    high = np.asarray(params.bounds_max, dtype=np.float64)
    inside = np.all((world_positions >= low) & (world_positions <= high), axis=1)

    keep = inside
    removed: dict[str, int] = {STAGE_BOUNDS: int(count - inside.sum())}

    if params.max_extent_m > 0.0:
        extent_ok = extent_m <= params.max_extent_m
        removed[STAGE_EXTENT] = int((keep & ~extent_ok).sum())
        keep = keep & extent_ok
    else:
        removed[STAGE_EXTENT] = 0

    if params.min_opacity > 0.0:
        opacity_ok = opacity >= params.min_opacity
        removed[STAGE_OPACITY] = int((keep & ~opacity_ok).sum())
        keep = keep & opacity_ok
    else:
        removed[STAGE_OPACITY] = 0

    return keep, removed
