#!/usr/bin/env python3
"""Publish what this machine can actually do, and say how confident that is.

The training budget: what a reconstruction run costs on a named scene, and
the largest splat count this machine can be said to support. The runtime budget
lives in ``runtime_budget.py`` because walking the result is a different claim.

The supported maximum is labelled as measured or projected. A projection says
so, because splat count is not the only thing that moves VRAM -- batch size,
resolution and the densification schedule all do -- and a reader deserves to know
which kind of number they are looking at before planning a capture around it.

When nothing was measured, :func:`publish_budget` returns None rather than a
number. Publishing a budget from a run that failed is the unmeasured performance
claim this work exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from resource_budget import VRAM_HEADROOM_FRACTION
from splat_cost import (
    SplatCostPoint,
    cost_points,
    fixed_overhead_bytes,
    is_bounded,
    marginal_bytes_per_splat,
)
from stage_measurement import StageMeasurement

@dataclass(frozen=True)
class PublishedBudget:
    """The training budget a reader plans a capture against."""

    scene: str
    gpu_name: str
    total_vram_bytes: int
    headroom_fraction: float
    default_splat_count: int
    default_stage_vram_bytes: int
    default_elapsed_seconds: float
    usable_vram_bytes: int
    supported_max_splats: int
    max_basis: str
    marginal_bytes_per_splat: float
    fixed_overhead_bytes: float
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "gpu_name": self.gpu_name,
            "total_vram_bytes": self.total_vram_bytes,
            "headroom_fraction": self.headroom_fraction,
            "default": {
                "splat_count": self.default_splat_count,
                "stage_vram_bytes": self.default_stage_vram_bytes,
                "elapsed_seconds": self.default_elapsed_seconds,
            },
            "usable_vram_bytes": self.usable_vram_bytes,
            "supported_max_splats": self.supported_max_splats,
            "max_basis": self.max_basis,
            "marginal_bytes_per_splat": self.marginal_bytes_per_splat,
            "fixed_overhead_bytes": self.fixed_overhead_bytes,
            "caveats": list(self.caveats),
        }


def _default_run(measurements: list[StageMeasurement]) -> StageMeasurement | None:
    """Return the unbounded training run, preferring the one with most splats."""
    training = [
        m
        for m in measurements
        if m.succeeded
        and m.splat_count
        and m.label.startswith("splatfacto")
        and not is_bounded(m.settings)
    ]
    return max(training, key=lambda m: m.splat_count, default=None)


def _bounded_max_splats(measurements: list[StageMeasurement]) -> int:
    """Return the largest splat count a bounded run actually reached."""
    bounded = [
        int(m.splat_count or 0)
        for m in measurements
        if m.succeeded
        and m.splat_count
        and m.label.startswith("splatfacto")
        and is_bounded(m.settings)
    ]
    return max(bounded, default=0)


def _projected_max_splats(points: list[SplatCostPoint], usable_vram_bytes: int) -> int:
    """Solve for the splat count that fits the headroom-adjusted VRAM budget."""
    slope = marginal_bytes_per_splat(points)
    if slope <= 0:
        return 0
    budget = usable_vram_bytes * (1.0 - VRAM_HEADROOM_FRACTION)
    return max(0, int((budget - fixed_overhead_bytes(points, slope)) / slope))


def _max_basis(measured_max: int, slope: float) -> str:
    """Say how the supported maximum was obtained, never just the number."""
    if measured_max:
        return "measured (a bounded run completed at this splat count)"
    if slope > 0:
        return "projected from two measured runs on this scene"
    return "unavailable: only one training run was measured"


def _caveats(
    measurements: list[StageMeasurement],
    capability_problems: list[str],
    scene: str,
) -> tuple[str, ...]:
    """State every gap between what was measured and what a reader might assume."""
    caveats = [
        f"Measured on one scene ({scene}); splat count is not portable to other captures.",
        "Peak VRAM is this stage on top of whatever the machine already held, sampled at 1 Hz.",
    ]
    labelled = {m.label for m in measurements if m.succeeded}
    for stage in ("collision", "import"):
        if not any(label.startswith(stage) for label in labelled):
            caveats.append(f"No successful {stage} run was measured; its cost is unverified.")
    caveats.extend(capability_problems)
    return tuple(caveats)


def publish_budget(
    scene: str,
    measurements: list[StageMeasurement],
    snapshot: Any,
    usable_vram_bytes: int,
    capability_problems: list[str],
) -> PublishedBudget | None:
    """Combine measurements and the machine snapshot into a training budget.

    Returns None when no training run succeeded. Publishing a budget from nothing
    measured would be exactly the unmeasured claim this task forbids.
    """
    default = _default_run(measurements)
    if default is None:
        return None
    points = cost_points(measurements)
    slope = marginal_bytes_per_splat(points)
    measured_max = _bounded_max_splats(measurements)
    gpu = snapshot.primary_gpu
    return PublishedBudget(
        scene=scene,
        gpu_name=gpu.name if gpu else "unknown",
        total_vram_bytes=gpu.total_vram_bytes if gpu else 0,
        headroom_fraction=VRAM_HEADROOM_FRACTION,
        default_splat_count=int(default.splat_count or 0),
        default_stage_vram_bytes=default.peak.stage_vram_bytes,
        default_elapsed_seconds=default.elapsed_seconds,
        usable_vram_bytes=usable_vram_bytes,
        supported_max_splats=measured_max or _projected_max_splats(points, usable_vram_bytes),
        max_basis=_max_basis(measured_max, slope),
        marginal_bytes_per_splat=slope,
        fixed_overhead_bytes=fixed_overhead_bytes(points, slope),
        caveats=_caveats(measurements, capability_problems, scene),
    )
