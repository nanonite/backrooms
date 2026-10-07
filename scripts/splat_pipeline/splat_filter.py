#!/usr/bin/env python3
"""Cleanup decisions for the #103 candidate pass over an already-cropped PLY.

This module holds the *decision* only -- given per-splat world positions,
opacities, extents, training-view counts and explicit parameters, which splats
of the #100 result survive. No file I/O, no GPU, no RNG: the same inputs always
produce the same kept set, so the logic is unit-testable against tiny synthetic
arrays (``tests/test_splat_filter.py``).

It extends the #100 filter (``splat_cleanup``) with the two standard cleanups
that #100 did not attempt, because #100's crop already removed the far field:

1. ``views``     -- multi-view support: keep a splat only if at least
   ``min_views`` registered training cameras see its centre inside their image.
   This is the frustum half of the usual "prune splats observed by fewer than
   k training views"; it is an *upper bound* on real observation support,
   because a frustum test has no z-buffer (see ``view_support``).
2. ``component`` -- spatial outlier filtering: voxelize the cloud and keep
   components of at least ``min_component_splats`` splats. A blob floating
   clear of the room shell is its own component whatever its opacity or scale,
   which is why this stage exists at all: on this asset the floaters are opaque
   (median 0.995), so opacity thresholds cannot touch them.

``opacity`` and ``extent`` are the conservative pruning half of the brief:
explicit floors/caps, off by default, never data-derived percentiles (a
percentile is a function of the very outliers it is meant to drop, so a future
asset would silently change it -- the #100 report's rule, kept here).

Stage order is fixed and recorded: each splat is attributed to the first stage
that rejects it, so ``removed`` per stage sums to ``input - kept``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

import splat_components

#: Stage names, in application order. Used as report keys.
STAGE_VIEWS = "views"
STAGE_COMPONENT = "component"
STAGE_EXTENT = "extent"
STAGE_OPACITY = "opacity"
STAGES = (STAGE_VIEWS, STAGE_COMPONENT, STAGE_EXTENT, STAGE_OPACITY)


@dataclass(frozen=True)
class CandidateParams:
    """Explicit, serialisable candidate-cleanup parameters.

    A value of ``0`` disables its stage (``min_views``, ``min_component_splats``,
    ``min_opacity``, ``min_extent_m``, ``max_extent_m``), so any single-stage
    ablation and the full candidate are expressible with one dataclass and the
    report can say exactly which stages ran.
    """

    min_views: int = 0
    voxel_m: float = 0.08
    min_component_splats: int = 0
    min_opacity: float = 0.0
    min_extent_m: float = 0.0
    max_extent_m: float = 0.0

    def __post_init__(self) -> None:
        if self.min_views < 0:
            raise ValueError("min_views must not be negative (0 disables it)")
        if self.min_component_splats < 0:
            raise ValueError("min_component_splats must not be negative (0 disables it)")
        if self.voxel_m <= 0.0:
            raise ValueError("voxel_m must be positive")
        if not 0.0 <= self.min_opacity < 1.0:
            raise ValueError("min_opacity must be in [0, 1) (0 disables it)")
        if self.min_extent_m < 0.0 or self.max_extent_m < 0.0:
            raise ValueError("extent thresholds must not be negative (0 disables them)")
        if self.max_extent_m > 0.0 and self.min_extent_m > self.max_extent_m:
            raise ValueError("min_extent_m must not exceed max_extent_m")

    @property
    def uses_views(self) -> bool:
        """Whether the multi-view stage will run."""
        return self.min_views > 0

    @property
    def uses_components(self) -> bool:
        """Whether the spatial-outlier stage will run."""
        return self.min_component_splats > 0

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict of the parameters."""
        return {
            "min_views": self.min_views,
            "voxel_m": self.voxel_m,
            "min_component_splats": self.min_component_splats,
            "min_opacity": self.min_opacity,
            "min_extent_m": self.min_extent_m,
            "max_extent_m": self.max_extent_m,
            "stages": [stage for stage, active in zip(STAGES, self.stage_enabled()) if active],
        }

    def stage_enabled(self) -> tuple[bool, bool, bool, bool]:
        """Return the per-stage enabled flags in :data:`STAGES` order."""
        extent_on = self.max_extent_m > 0.0 or self.min_extent_m > 0.0
        return (
            self.uses_views,
            self.uses_components,
            extent_on,
            self.min_opacity > 0.0,
        )


def _stage_masks(
    world_positions: np.ndarray,
    opacity: np.ndarray,
    extent_m: np.ndarray,
    view_counts: np.ndarray | None,
    params: CandidateParams,
) -> list[tuple[str, np.ndarray]]:
    """Return ``(stage, survives)`` masks, evaluated in :data:`STAGES` order."""
    masks: list[tuple[str, np.ndarray]] = []
    if params.uses_views:
        if view_counts is None:
            raise ValueError("min_views > 0 requires view_counts")
        masks.append((STAGE_VIEWS, view_counts >= params.min_views))
    if params.uses_components:
        labels = splat_components.label_components(world_positions, params.voxel_m)
        sizes = splat_components.component_sizes(labels)
        masks.append((STAGE_COMPONENT, sizes[labels] >= params.min_component_splats))
    if params.max_extent_m > 0.0 or params.min_extent_m > 0.0:
        top = params.max_extent_m if params.max_extent_m > 0.0 else np.inf
        bottom = params.min_extent_m
        masks.append((STAGE_EXTENT, (extent_m >= bottom) & (extent_m <= top)))
    if params.min_opacity > 0.0:
        masks.append((STAGE_OPACITY, opacity >= params.min_opacity))
    return masks


def compute_keep_mask(
    world_positions: np.ndarray,
    opacity: np.ndarray,
    extent_m: np.ndarray,
    params: CandidateParams,
    view_counts: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, int]]:
    """Return ``(keep_mask, removed_per_stage)``.

    ``world_positions`` is ``(N, 3)`` in Godot world metres; ``opacity`` and
    ``extent_m`` are ``(N,)``; ``view_counts`` is ``(N,)`` and only required
    when the views stage runs. Component membership is a property of the input
    cloud, so it is computed once from the full input rather than re-derived
    from the survivors -- otherwise a splat removed by an earlier stage would
    silently change what "connected" means.
    """
    world_positions = np.asarray(world_positions, dtype=np.float64)
    if world_positions.ndim != 2 or world_positions.shape[1] != 3:
        raise ValueError("world_positions must have shape (N, 3)")
    count = world_positions.shape[0]
    opacity = np.asarray(opacity, dtype=np.float64)
    extent_m = np.asarray(extent_m, dtype=np.float64)
    if opacity.shape != (count,) or extent_m.shape != (count,):
        raise ValueError("opacity and extent_m must have shape (N,)")

    keep = np.ones(count, dtype=bool)
    removed: dict[str, int] = {stage: 0 for stage in STAGES}
    for stage, survives in _stage_masks(world_positions, opacity, extent_m, view_counts, params):
        removed[stage] = int((keep & ~survives).sum())
        keep = keep & survives
    return keep, removed
