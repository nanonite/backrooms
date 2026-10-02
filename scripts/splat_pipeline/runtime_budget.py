#!/usr/bin/env python3
"""What walking the result costs at the renderer, measured rather than assumed.

This is the budget that decides interactive walking. It is kept apart from the
training budget because it is a different claim, and on a host where training
cannot run at all it is the only measured cost there is. Folding it into the
training figure to make one number look complete would be exactly the unmeasured
performance claim this work exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from splat_cost import RENDER_LABEL_PREFIX, marginal_bytes_per_splat, render_cost_points
from stage_measurement import StageMeasurement

#: The refresh rate of the display these measurements were taken on. Used only to
#: say whether a measured frame rate was capped by the display rather than by
#: the renderer.
TYPICAL_REFRESH_HZ = 60.0

#: Frame rates this close to the refresh are reported as capped by it, not as the
#: renderer's own limit: 59.9 and 60.1 are the same picture.
VSYNC_TOLERANCE_FPS = 1.0


@dataclass(frozen=True)
class RuntimeBudget:
    """What the walkable runtime costs, measured at the renderer.

    Published separately from the training budget because it is measured
    separately. On a host where training cannot run at all, this is the only
    measured cost, and folding it into the training figure to make one number
    look complete would be the unmeasured claim this work exists to prevent.
    """

    gpu_name: str
    resolution: str
    splat_count: int
    stage_vram_bytes: int
    fps: float
    frame_rate_is_vsync_limited: bool
    marginal_bytes_per_splat: float
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_name": self.gpu_name,
            "resolution": self.resolution,
            "splat_count": self.splat_count,
            "stage_vram_bytes": self.stage_vram_bytes,
            "fps": self.fps,
            "frame_rate_is_vsync_limited": self.frame_rate_is_vsync_limited,
            "marginal_bytes_per_splat": self.marginal_bytes_per_splat,
            "notes": list(self.notes),
        }


def _successful_renders(measurements: list[StageMeasurement]) -> list[StageMeasurement]:
    """Return render measurements that produced a frame rate."""
    return [
        m
        for m in measurements
        if m.succeeded and m.label.startswith(RENDER_LABEL_PREFIX) and m.extras.get("fps")
    ]


def publish_runtime_budget(
    measurements: list[StageMeasurement], gpu_name: str
) -> RuntimeBudget | None:
    """Build the runtime budget from render measurements, or None if there are none."""
    renders = _successful_renders(measurements)
    if not renders:
        return None
    largest = max(renders, key=lambda m: m.splat_count or 0)
    fps = float(largest.extras["fps"])
    return RuntimeBudget(
        gpu_name=gpu_name,
        resolution=_resolution_note(renders),
        splat_count=int(largest.splat_count or 0),
        stage_vram_bytes=largest.peak.stage_vram_bytes,
        fps=fps,
        frame_rate_is_vsync_limited=abs(fps - TYPICAL_REFRESH_HZ) <= VSYNC_TOLERANCE_FPS,
        marginal_bytes_per_splat=marginal_bytes_per_splat(render_cost_points(measurements)),
        notes=_runtime_notes(renders, fps),
    )


def _resolution_note(renders: list[StageMeasurement]) -> str:
    """Name every resolution the runtime probes ran at."""
    resolutions = sorted(
        {m.settings.get("resolution", "") for m in renders if m.settings.get("resolution")}
    )
    return "measured at " + ", ".join(resolutions)


def _runtime_notes(renders: list[StageMeasurement], fps: float) -> tuple[str, ...]:
    """State what the frame rate does and does not establish."""
    notes = [f"All {len(renders)} runtime probes ran with the viewpoint orbiting, not static."]
    if abs(fps - TYPICAL_REFRESH_HZ) <= VSYNC_TOLERANCE_FPS:
        notes.append(
            f"{fps:.2f} fps is at the display's {TYPICAL_REFRESH_HZ:.0f} Hz refresh, so this shows "
            "the renderer keeps up; it does not show how much headroom is left."
        )
    return tuple(notes)