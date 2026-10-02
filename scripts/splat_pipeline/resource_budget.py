#!/usr/bin/env python3
"""Turn measurements into a budget: what fits, what does not, and what to do.

Two things this module deliberately refuses to do. It does not treat a GPU's
*total* VRAM as the budget, because a display server and any other job hold
part of it before the pipeline starts. And it does not treat an upstream
documentation figure as a measurement: the Nerfstudio Splatfacto page quotes
roughly 6 GB for the default method and roughly 12 GB for ``big``, and neither
number was produced on this machine, so they are recorded as claims next to the
numbers that were.

The headroom fractions exist so a stage that *just* fits at measurement time
still fits when the desktop compositor wakes up mid-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GIBIBYTE = 1024**3

#: Fraction of usable VRAM left unspent. Splatfacto densifies until it OOMs, so
#: running exactly to the limit guarantees an intermittent failure.
VRAM_HEADROOM_FRACTION = 0.20

#: Host RAM headroom. Colmap and nerfstudio both hold the full image set in RAM.
RAM_HEADROOM_FRACTION = 0.25

#: Disk multiplier over a stage's measured output, covering checkpoints that are
#: kept alongside the export plus temporary files the stage cleans up itself.
DISK_MULTIPLIER = 2

#: Documented upstream figures, quoted so a reader can see the gap between what
#: the vendor claims and what was measured here. Not used in any decision.
UPSTREAM_CLAIMS = {
    "splatfacto_default_vram_gib": 6.0,
    "splatfacto_big_vram_gib": 12.0,
    "source": "https://docs.nerf.studio/nerfology/methods/splat.html",
}


@dataclass(frozen=True)
class StageRequirement:
    """What one stage needs before it may be started."""

    stage: str
    compute_api: str
    min_vram_bytes: int
    min_ram_bytes: int
    min_free_disk_bytes: int


#: Floors for the stages the pipeline runs. Deliberately conservative and
#: deliberately *not* derived from the measured run: a floor is what a stage is
#: expected to need, and a measurement is what it actually cost.
STAGE_REQUIREMENTS: dict[str, StageRequirement] = {
    "splatfacto": StageRequirement(
        stage="splatfacto",
        compute_api="cuda",
        min_vram_bytes=int(4.0 * GIBIBYTE),
        min_ram_bytes=int(8.0 * GIBIBYTE),
        min_free_disk_bytes=int(20 * GIBIBYTE),
    ),
    "collision": StageRequirement(
        stage="collision",
        compute_api="webgpu",
        min_vram_bytes=int(2.0 * GIBIBYTE),
        min_ram_bytes=int(4.0 * GIBIBYTE),
        min_free_disk_bytes=int(5 * GIBIBYTE),
    ),
    "import": StageRequirement(
        stage="import",
        compute_api="vulkan",
        min_vram_bytes=int(2.0 * GIBIBYTE),
        min_ram_bytes=int(2.0 * GIBIBYTE),
        min_free_disk_bytes=int(5 * GIBIBYTE),
    ),
    "render": StageRequirement(
        stage="render",
        compute_api="vulkan",
        min_vram_bytes=int(2.0 * GIBIBYTE),
        min_ram_bytes=int(1 * GIBIBYTE),
        min_free_disk_bytes=int(0 * GIBIBYTE),
    ),
}


@dataclass(frozen=True)
class BudgetVerdict:
    """Whether one stage can start now, and what stands in the way if not."""

    stage: str
    fits: bool
    compute_api: str
    usable_vram_bytes: int
    required_vram_bytes: int
    blockers: tuple[str, ...]
    actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "fits": self.fits,
            "compute_api": self.compute_api,
            "usable_vram_bytes": self.usable_vram_bytes,
            "required_vram_bytes": self.required_vram_bytes,
            "blockers": list(self.blockers),
            "actions": list(self.actions),
        }


def _gib(value: int) -> str:
    """Format bytes as GiB with one decimal, for messages a human reads."""
    return f"{value / GIBIBYTE:.1f} GiB"


def vram_available_bytes(snapshot: Any, capability: Any) -> int:
    """Return the VRAM a stage may actually claim right now.

    Takes the smaller of what the card reports free and what torch can
    allocate, because torch's view is the one the training stage will hit.
    """
    readings = [snapshot.primary_gpu.free_vram_bytes if snapshot.primary_gpu else 0]
    if capability.free_vram_bytes:
        readings.append(capability.free_vram_bytes)
    return min(readings)


def evaluate_stage(
    stage: str,
    usable_vram_bytes: int,
    available_ram_bytes: int,
    free_disk_bytes: int,
    api_available: bool = True,
    api_name: str = "",
    api_error: str = "",
) -> BudgetVerdict:
    """Decide whether ``stage`` fits and is runnable on this machine now.

    ``api_available`` is the probe result for ``stage``'s compute API. A stage
    whose API is missing is blocked even when the card has room for it: a
    collision stage that cannot reach WebGPU does not run slowly, it does not
    run, and reporting it as "RUN" because the memory fits would be the exact
    kind of green tick this module exists to prevent.
    """
    if stage not in STAGE_REQUIREMENTS:
        return BudgetVerdict(
            stage, False, "unknown", usable_vram_bytes, 0, (f"unknown stage {stage!r}",), ("Add it to STAGE_REQUIREMENTS.",)
        )
    requirement = STAGE_REQUIREMENTS[stage]
    blockers, actions = _api_blockers(requirement, api_available, api_name, api_error)
    vram_budget = int(usable_vram_bytes * (1.0 - VRAM_HEADROOM_FRACTION))
    ram_budget = int(available_ram_bytes * (1.0 - RAM_HEADROOM_FRACTION))
    if vram_budget < requirement.min_vram_bytes:
        blockers.append(
            f"{requirement.compute_api} needs {_gib(requirement.min_vram_bytes)} VRAM but only "
            f"{_gib(vram_budget)} is free after {_gib(usable_vram_bytes)} usable minus "
            f"{int(VRAM_HEADROOM_FRACTION * 100)}% headroom"
        )
        actions.append("Stop other GPU jobs, or lower --stop-split-at / --downscale-factor.")
    if ram_budget < requirement.min_ram_bytes:
        blockers.append(
            f"{stage} needs {_gib(requirement.min_ram_bytes)} RAM but only "
            f"{_gib(ram_budget)} is available after headroom"
        )
        actions.append("Free host RAM or lower --max-num-iterations / the frame count.")
    if free_disk_bytes < requirement.min_free_disk_bytes:
        blockers.append(
            f"{stage} needs {_gib(requirement.min_free_disk_bytes)} free disk, "
            f"{_gib(free_disk_bytes)} available"
        )
        actions.append("Delete old checkpoints or point --output-dir at a larger filesystem.")
    return BudgetVerdict(
        stage=stage,
        fits=not blockers,
        compute_api=requirement.compute_api,
        usable_vram_bytes=usable_vram_bytes,
        required_vram_bytes=requirement.min_vram_bytes,
        blockers=tuple(blockers),
        actions=tuple(actions),
    )


def _api_blockers(
    requirement: StageRequirement,
    api_available: bool,
    api_name: str,
    api_error: str,
) -> tuple[list[str], list[str]]:
    """Return the blockers and actions contributed by a missing compute API."""
    if api_available:
        return [], []
    detail = f" ({api_error})" if api_error else ""
    return (
        [f"{requirement.compute_api} is unavailable on this host{detail}"],
        [f"Run the {api_name} probe's remediation before starting {requirement.stage}."],
    )