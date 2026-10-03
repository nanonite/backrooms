#!/usr/bin/env python3
"""Estimate what a selection will cost, before the GPU stages start.

Reconstruction fails late and expensively: COLMAP runs for an hour and then
runs out of disk, or a mapper OOMs after feature extraction has already spent
the time. Every number here is an *assumption* about COLMAP's on-disk formats
rather than a measurement of this machine's I/O, and each one is named so a
reader can check it. What the estimate is good for is refusing the obviously
unrunnable -- a 4000-frame selection against 6 GiB of free disk -- long before
the work starts.

Disk and RAM are read from the machine rather than assumed (via
:mod:`resource_probe`), so the verdict is about this host.
"""

from __future__ import annotations

from dataclasses import dataclass

from matching_plan import MatchingPlan
from sampling_budget import (
    SamplingBudget,
    estimated_analysis_bytes,
    estimated_sample_seconds,
)
from video_probe import VideoMetadata

GIBIBYTE = 1024**3

# --- Assumptions, each about COLMAP's on-disk cost at 1080p ---------------

#: JPEG at quality 2, the setting Stage A extracts with. ~0.12 bytes per pixel.
JPEG_BYTES_PER_PIXEL = 0.12

#: COLMAP's default SIFT cap, and the size of one stored feature (descriptor
#: plus keypoint bookkeeping) in database.db.
FEATURES_PER_FRAME = 4096
BYTES_PER_FEATURE = 100

#: Sparse SfM output: points visible in a couple of images, each with a track.
SPARSE_POINTS_PER_FRAME = 2000
SPARSE_BYTES_PER_FRAME = 200 * 1024
SPARSE_BYTES_PER_POINT = 48

#: CPU SIFT matching cost per pair on this class of workstation. On the GPU
#: this is far faster, but GPU SIFT is what exhausts CUDA texture memory at
#: 192 frames (LESSONS_LEARNED 2.1), so the budget is priced for the CPU path.
SECONDS_PER_MATCH_PAIR = 0.25

#: Headroom over the estimate, for the mapper's own working set and for the
#: checkpoints kept alongside an export.
DISK_HEADROOM_FRACTION = 0.25

#: RAM headroom for the same reason the VRAM budget keeps 20% (resource_budget).
RAM_HEADROOM_FRACTION = 0.25

#: Working set for feature extraction and matching, over the database size.
RAM_MULTIPLE_OVER_DATABASE = 2.0


class ResourceEstimationError(RuntimeError):
    """A resource could not be measured, so no estimate can be made."""


@dataclass(frozen=True)
class ResourceEstimate:
    """Predicted disk, RAM and time for one selection."""

    frames: int
    source_width: int
    source_height: int
    frame_files_bytes: int
    database_bytes: int
    sparse_model_bytes: int
    total_disk_bytes: int
    working_ram_bytes: int
    matching_pairs: int
    matching_seconds: float
    sampling_seconds: float

    def to_dict(self) -> dict:
        return {
            "frames": self.frames,
            "source_resolution": f"{self.source_width}x{self.source_height}",
            "frame_files_bytes": self.frame_files_bytes,
            "database_bytes": self.database_bytes,
            "sparse_model_bytes": self.sparse_model_bytes,
            "total_disk_bytes": self.total_disk_bytes,
            "working_ram_bytes": self.working_ram_bytes,
            "matching_pairs": self.matching_pairs,
            "matching_seconds": round(self.matching_seconds, 1),
            "sampling_seconds": round(self.sampling_seconds, 1),
        }


@dataclass(frozen=True)
class ResourceVerdict:
    """Whether the estimate fits the machine, and what to change if it does not."""

    fits: bool
    free_disk_bytes: int
    free_ram_bytes: int
    blockers: tuple[str, ...]
    actions: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "fits": self.fits,
            "free_disk_bytes": self.free_disk_bytes,
            "free_ram_bytes": self.free_ram_bytes,
            "blockers": list(self.blockers),
            "actions": list(self.actions),
        }


def estimate_selection(
    metadata: VideoMetadata, frames: int, plan: MatchingPlan, budget: SamplingBudget
) -> ResourceEstimate:
    """Estimate disk, RAM and time for ``frames`` selected from ``metadata``."""
    pixels = metadata.total_pixels
    frame_files = int(frames * pixels * JPEG_BYTES_PER_PIXEL)
    database = int(frames * FEATURES_PER_FRAME * BYTES_PER_FEATURE)
    sparse = int(frames * (SPARSE_BYTES_PER_FRAME + SPARSE_POINTS_PER_FRAME * SPARSE_BYTES_PER_POINT))
    disk = int((frame_files + database + sparse) * (1 + DISK_HEADROOM_FRACTION))
    return ResourceEstimate(
        frames=frames,
        source_width=metadata.width,
        source_height=metadata.height,
        frame_files_bytes=frame_files,
        database_bytes=database,
        sparse_model_bytes=sparse,
        total_disk_bytes=disk,
        working_ram_bytes=int(database * RAM_MULTIPLE_OVER_DATABASE),
        matching_pairs=plan.pairs,
        matching_seconds=plan.pairs * SECONDS_PER_MATCH_PAIR,
        sampling_seconds=estimated_sample_seconds(frames, "stream", metadata.frame_count),
    )


def analysis_footprint_bytes(budget: SamplingBudget, candidates: int) -> int:
    """Bytes an in-memory candidate set would occupy if nothing were streamed."""
    return estimated_analysis_bytes(candidates, budget.analysis_max_pixels)


def _gib(value: int) -> str:
    return f"{value / GIBIBYTE:.1f} GiB"


def evaluate_resources(
    estimate: ResourceEstimate, free_disk_bytes: int, free_ram_bytes: int
) -> ResourceVerdict:
    """Compare an estimate against this host's free disk and RAM."""
    disk_needed = int(estimate.total_disk_bytes * (1 + DISK_HEADROOM_FRACTION))
    ram_budget = int(free_ram_bytes * (1 - RAM_HEADROOM_FRACTION))
    blockers: list[str] = []
    actions: list[str] = []
    if free_disk_bytes < disk_needed:
        blockers.append(
            f"selection needs {_gib(disk_needed)} of disk (frames + database + sparse model + "
            f"{int(DISK_HEADROOM_FRACTION * 100)}% headroom), {_gib(free_disk_bytes)} is free"
        )
        actions.append(
            f"select fewer frames (target_frames), or point --staging-dir at a filesystem with more room"
        )
    if ram_budget < estimate.working_ram_bytes:
        blockers.append(
            f"feature extraction and matching need {_gib(estimate.working_ram_bytes)} RAM, "
            f"{_gib(ram_budget)} is available after headroom"
        )
        actions.append("select fewer frames, or match with a smaller feature cap")
    return ResourceVerdict(
        fits=not blockers,
        free_disk_bytes=free_disk_bytes,
        free_ram_bytes=free_ram_bytes,
        blockers=tuple(blockers),
        actions=tuple(actions),
    )


def measure_host(staging_dir) -> tuple[int, int]:
    """Return ``(free_disk_bytes, free_ram_bytes)`` for the output location.

    Raises :class:`ResourceEstimationError` rather than defaulting to zero: a
    zero would make every estimate look like a blocker, which is a different
    and wrong claim.
    """
    from resource_probe import filesystem_usage, read_memory

    try:
        disk = filesystem_usage(staging_dir).free_bytes
        memory = read_memory().available_bytes
    except (OSError, ValueError, RuntimeError) as exc:
        raise ResourceEstimationError(f"could not measure free disk/RAM at {staging_dir}: {exc}") from exc
    return disk, memory