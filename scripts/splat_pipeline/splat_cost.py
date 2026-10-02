#!/usr/bin/env python3
"""How many Gaussians cost how much VRAM, derived from measured runs.

The arithmetic every budget is built on, kept apart from the budgets themselves:
one observation is a :class:`SplatCostPoint`, and a slope needs two. Two runs
that produced nearly the same splat count cannot constrain a slope -- the fixed
cost of a run dominates and the difference is noise -- so the spread is checked
before a per-splat cost is quoted.

Training and runtime points are derived separately by the caller, because they
are different costs and mixing them produces a slope that describes neither.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from stage_measurement import StageMeasurement

#: Only measurements from a training stage describe reconstruction cost. Render
#: measurements also carry a splat count, and folding them in would produce a
#: "training budget" that is really a rendering budget.
TRAINING_LABEL_PREFIX = "splatfacto"

#: Splat counts this close together carry no usable slope: the fixed cost of the
#: run dominates and any derived per-splat cost is noise.
MIN_SPLAT_SPREAD = 50_000

#: A run is "bounded" when densification was frozen early, i.e. when
#: ``stop-split-at`` was set to something other than the 15000 default. Nerfstudio
#: 1.1.5 has no hard splat cap, so this is the flag that actually bounds one.
BOUNDED_SETTING = "stop-split-at"
DEFAULT_STOP_SPLIT_AT = "15000"


@dataclass(frozen=True)
class SplatCostPoint:
    """One observation of how many Gaussians cost how much VRAM."""

    label: str
    splat_count: int
    stage_vram_bytes: int
    bounded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "splat_count": self.splat_count,
            "stage_vram_bytes": self.stage_vram_bytes,
            "bounded": self.bounded,
        }


def is_bounded(settings: dict[str, str]) -> bool:
    """Return True when the run froze densification earlier than the default."""
    return settings.get(BOUNDED_SETTING, DEFAULT_STOP_SPLIT_AT) != DEFAULT_STOP_SPLIT_AT


def cost_points(measurements: list[StageMeasurement]) -> list[SplatCostPoint]:
    """Turn every successful training measurement into a splat-cost observation."""
    return [
        SplatCostPoint(
            label=f"{m.label} (stop-split-at={m.settings[BOUNDED_SETTING]})"
            if is_bounded(m.settings)
            else f"{m.label} (unbounded)",
            splat_count=int(m.splat_count or 0),
            stage_vram_bytes=m.peak.stage_vram_bytes,
            bounded=is_bounded(m.settings),
        )
        for m in measurements
        if m.succeeded and m.splat_count and m.label.startswith(TRAINING_LABEL_PREFIX)
    ]


def marginal_bytes_per_splat(points: list[SplatCostPoint]) -> float:
    """Return the slope of stage VRAM against splat count, or 0.0 if unusable.

    Uses the two observations furthest apart in splat count, because that is the
    pair that constrains the slope best.
    """
    ordered = sorted(points, key=lambda point: point.splat_count)
    if len(ordered) < 2:
        return 0.0
    low, high = ordered[0], ordered[-1]
    if high.splat_count - low.splat_count < MIN_SPLAT_SPREAD:
        return 0.0
    return (high.stage_vram_bytes - low.stage_vram_bytes) / (high.splat_count - low.splat_count)


def fixed_overhead_bytes(points: list[SplatCostPoint], slope: float) -> float:
    """Return the VRAM a run costs before any Gaussian is allocated."""
    if not points:
        return 0.0
    lowest = min(points, key=lambda point: point.splat_count)
    return max(0.0, lowest.stage_vram_bytes - slope * lowest.splat_count)


#: Render measurements carry this prefix so several assets can be priced in one
#: report without colliding with the training stage's label.
RENDER_LABEL_PREFIX = "render"


def render_cost_points(measurements: list[StageMeasurement]) -> list[SplatCostPoint]:
    """Turn every successful render measurement into a runtime splat-cost point."""
    return [
        SplatCostPoint(
            label=f"{m.label} @ {m.settings.get('resolution', 'unstated resolution')}",
            splat_count=int(m.splat_count or 0),
            stage_vram_bytes=m.peak.stage_vram_bytes,
            bounded=False,
        )
        for m in measurements
        if m.succeeded and m.label.startswith(RENDER_LABEL_PREFIX) and m.splat_count
    ]


def median_render_fps(measurements: list[StageMeasurement]) -> float:
    """Return the median render frame rate across render runs, or 0.0.

    The median rather than the mean: a single stall from a background
    compositor frame should not move the headline number.
    """
    rates = [
        float(m.extras["fps"])
        for m in measurements
        if m.label.startswith(RENDER_LABEL_PREFIX) and m.extras.get("fps")
    ]
    return statistics.median(rates) if rates else 0.0
