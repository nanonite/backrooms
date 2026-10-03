#!/usr/bin/env python3
"""Score a bounded sample of a clip: sharpness, cuts, translation, residuals.

The scan is three bounded passes over the video, and each one answers a
question the next one needs:

1. **Motion probe** -- a dozen small frames spread across the clip, aligned
   without a seed. It cannot be trusted for detail (tiny frames, coarse search)
   but it does establish how far the camera travels per source frame, which is
   what decides the candidate stride.
2. **Candidate pass** -- ``stride``-spaced analysis frames, aligned by seeding
   each pair with the previous pair's shift. This produces the per-candidate
   sharpness, cut distance and translation that the selector ranks on.
3. **Burst probe** -- a few *contiguous* windows. Between adjacent frames a
   static scene explains itself with one global translation, so whatever is
   left over is either a moving object or geometry that does not hold still.
   Measuring that on spaced-out candidates instead would confound it with
   parallax, which is also a residual.

Passes 1 and 2 stream the clip, so both visit every frame; pass 3 seeks. Every
count is in :class:`ScanResult` and reaches the report, because "bounded work"
is only useful if the bound is stated.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from frame_metrics import (
    TranslationEstimate,
    estimate_translation,
    histogram_distance,
    intensity_histogram,
    laplacian_variance,
)
from frame_reader import AnalysisSize, DecodeStats, analysis_size, decode_burst, stream_candidates
from sampling_budget import SamplingBudget
from video_probe import VideoMetadata

#: Candidates between the pair being aligned. One candidate gap is not always
#: enough: the alignment search does not resolve a displacement below roughly
#: 0.5% of the analysis frame width (about 3 px at 640 px), where compression
#: noise dominates the difference between a shifted and an unshifted frame, so
#: a single gap can measure as "no motion" on a camera that is moving. Two
#: gaps doubles the displacement without doubling the work.
PARALLAX_GAP = 2

#: Probe frames are decoded small and unrefined: they measure displacement, not
#: detail, and a 160x90 frame costs a fraction of a 640x360 one to align.
PROBE_WIDTH = 160
PROBE_HEIGHT = 90

#: Seconds of clip skipped before the first burst window, so a burst never
#: starts inside an encoder's opening frames.
BURST_MARGIN_SECONDS = 0.25

CANDIDATE_STRIDE_MIN = 1
CANDIDATE_STRIDE_MAX = 240


@dataclass(frozen=True)
class CandidateFrame:
    """One scored sample: what this frame looks like, and how it moved."""

    index: int
    timestamp: float
    sharpness: float
    luma: float
    cut_distance: float
    is_cut: bool
    cut_signal: str
    translation: TranslationEstimate | None

    def to_dict(self) -> dict:
        translation = self.translation
        return {
            "index": self.index,
            "timestamp_seconds": round(self.timestamp, 3),
            "sharpness": round(self.sharpness, 2),
            "luma": round(self.luma, 2),
            "cut_distance": round(self.cut_distance, 4),
            "is_cut": self.is_cut,
            "cut_signal": self.cut_signal,
            "translation_px": None if translation is None else round(translation.magnitude_px, 2),
            "translation_fraction": None
            if translation is None
            else round(translation.magnitude_fraction, 5),
            "explained_fraction": None
            if translation is None
            else round(translation.explained_fraction, 3),
        }


@dataclass(frozen=True)
class BurstStats:
    """What contiguous frames show that spaced-out candidates cannot."""

    pairs: int
    windows: int
    median_residual_fraction: float
    p90_residual_fraction: float
    median_hot_block_fraction: float
    p90_hot_block_fraction: float
    max_hot_block_fraction: float
    median_shift_fraction: float

    def to_dict(self) -> dict:
        return {
            "pairs": self.pairs,
            "windows": self.windows,
            "median_residual_fraction": round(self.median_residual_fraction, 4),
            "p90_residual_fraction": round(self.p90_residual_fraction, 4),
            "median_hot_block_fraction": round(self.median_hot_block_fraction, 4),
            "p90_hot_block_fraction": round(self.p90_hot_block_fraction, 4),
            "max_hot_block_fraction": round(self.max_hot_block_fraction, 4),
            "median_shift_fraction": round(self.median_shift_fraction, 5),
        }


@dataclass(frozen=True)
class ScanResult:
    """Everything the verdict, the selector and the reports need from a scan."""

    metadata: VideoMetadata
    size: AnalysisSize
    stride: int
    candidates: tuple[CandidateFrame, ...]
    bursts: BurstStats
    motion_px_per_frame: float
    parallax_gap: int
    probe_stats: DecodeStats
    candidate_stats: DecodeStats
    burst_frames_decoded: int
    seconds: float
    limits: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "analysis_size": self.size.to_dict(),
            "stride": self.stride,
            "parallax_gap": self.parallax_gap,
            "motion_px_per_frame": round(self.motion_px_per_frame, 4),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "bursts": self.bursts.to_dict(),
            "decode": {
                "probe": self.probe_stats.to_dict(),
                "candidates": self.candidate_stats.to_dict(),
                "burst_frames_decoded": self.burst_frames_decoded,
            },
            "seconds": round(self.seconds, 3),
            "limits": list(self.limits),
        }


@dataclass(frozen=True)
class MotionProbe:
    """How fast the camera moves, in analysis pixels per source frame."""

    pixels_per_frame: float
    stats: DecodeStats
    note: str


def probe_stride_for(clip_frames: int, probe_count: int) -> int:
    """Frames between motion-probe samples."""
    return max(CANDIDATE_STRIDE_MIN, int(round(clip_frames / max(1, probe_count))))


def probe_size_for(metadata: VideoMetadata) -> AnalysisSize:
    """Fixed small size for the motion probe, preserving aspect ratio."""
    scale = min(1.0, min(PROBE_WIDTH / metadata.width, PROBE_HEIGHT / metadata.height))
    return AnalysisSize(
        width=max(2, int(metadata.width * scale) // 2 * 2),
        height=max(2, int(metadata.height * scale) // 2 * 2),
        source_width=metadata.width,
        source_height=metadata.height,
    )


def measure_motion(metadata: VideoMetadata, budget: SamplingBudget) -> MotionProbe:
    """Measure inter-sample displacement and express it in analysis pixels."""
    probe = probe_size_for(metadata)
    analysis = analysis_size(metadata, budget.analysis_max_pixels)
    stride = probe_stride_for(metadata.frame_count, budget.probe_count)
    decoded = stream_candidates(metadata.path, probe, stride, metadata.frame_count)
    to_analysis = analysis.width / probe.width if probe.width else 1.0
    shifts: list[float] = []
    seed = (0, 0)
    for previous, current in zip(decoded.frames, decoded.frames[1:]):
        estimate = estimate_translation(previous, current, seed)
        seed = (estimate.dx_px, estimate.dy_px)
        shifts.append(estimate.magnitude_px * to_analysis)
    median = float(np.median(shifts)) if shifts else 0.0
    per_frame = median / stride if stride else 0.0
    note = (
        f"motion probe: {decoded.stats.retained} frames of {probe.width}x{probe.height}, "
        f"one every {stride} source frames, median inter-sample shift "
        f"{median:.1f}px at probe size -> {per_frame:.2f}px per source frame "
        f"at {analysis.width}px analysis width"
    )
    return MotionProbe(pixels_per_frame=per_frame, stats=decoded.stats, note=note)


def candidate_stride_for(
    clip_frames: int, motion_px_per_frame: float, analysis_width: int, budget: SamplingBudget
) -> int:
    """Stride in source frames, from measured motion and from the candidate cap.

    Two constraints decide this and they can disagree. The stride must be wide
    enough that consecutive samples differ by a measurable translation, or the
    samples differ by sensor noise; and narrow enough that the clip divided by
    the stride stays within the candidate budget.
    """
    target_pixels = budget.target_shift_fraction * analysis_width
    stride_for_motion = int(round(target_pixels / motion_px_per_frame)) if motion_px_per_frame > 0 else 1
    stride_for_cap = max(1, math.ceil(clip_frames / max(1, budget.max_candidates)))
    stride = max(stride_for_motion, stride_for_cap)
    return int(max(CANDIDATE_STRIDE_MIN, min(CANDIDATE_STRIDE_MAX, stride)))


def scan_candidates(
    metadata: VideoMetadata, budget: SamplingBudget, stride: int
) -> tuple[tuple[CandidateFrame, ...], DecodeStats, int]:
    """Decode and score one candidate pass at the given stride.

    Returns the candidates, the decode record, and the gap the translations were
    measured over.
    """
    size = analysis_size(metadata, budget.analysis_max_pixels)
    decoded = stream_candidates(metadata.path, size, stride, metadata.frame_count)
    gap = max(1, min(PARALLAX_GAP, len(decoded.frames) - 1))
    rate = metadata.fps if metadata.fps > 0 else 25.0
    candidates: list[CandidateFrame] = []
    previous_histogram = None
    seed = (0, 0)
    for position, (index, frame) in enumerate(zip(decoded.indices, decoded.frames)):
        histogram = intensity_histogram(frame)
        cut = 0.0 if previous_histogram is None else histogram_distance(previous_histogram, histogram)
        translation = None
        if position >= gap:
            estimate = estimate_translation(decoded.frames[position - gap], frame, seed)
            seed = (estimate.dx_px, estimate.dy_px)
            translation = estimate
        candidates.append(
            CandidateFrame(
                index=index,
                timestamp=index / rate,
                sharpness=laplacian_variance(frame),
                luma=float(frame.mean()),
                cut_distance=cut,
                is_cut=_is_cut(cut, translation, budget),
                cut_signal=_cut_signal(cut, translation, budget),
                translation=translation,
            )
        )
        previous_histogram = histogram
    return tuple(candidates), decoded.stats, gap


def _is_cut(cut_distance: float, translation, budget: SamplingBudget) -> bool:
    """A cut is either a histogram jump or content nothing can align."""
    if cut_distance > budget.cut_distance_limit:
        return True
    return translation is not None and translation.residual_fraction > budget.cut_residual_limit


def _cut_signal(cut_distance: float, translation, budget: SamplingBudget) -> str:
    """Name the signal that fired, so a reported cut can be checked by eye."""
    if cut_distance > budget.cut_distance_limit:
        return f"histogram distance {cut_distance:.3f} over {budget.cut_distance_limit:.2f}"
    if translation is not None and translation.residual_fraction > budget.cut_residual_limit:
        return (
            f"{translation.residual_fraction:.0%} of pixels unalignable, over "
            f"{budget.cut_residual_limit:.0%}"
        )
    return ""


def burst_starts(duration_seconds: float, count: int) -> list[float]:
    """Evenly spread window starts inside the clip."""
    usable = max(0.0, duration_seconds - BURST_MARGIN_SECONDS)
    return [BURST_MARGIN_SECONDS + usable * (index + 0.5) / count for index in range(count)]


def scan_bursts(metadata: VideoMetadata, budget: SamplingBudget) -> tuple[BurstStats, int]:
    """Measure residuals across a few contiguous windows of the clip."""
    size = analysis_size(metadata, budget.analysis_max_pixels)
    residuals: list[float] = []
    hot_blocks: list[float] = []
    shifts: list[float] = []
    windows = 0
    frames_decoded = 0
    for start in burst_starts(metadata.duration_seconds, budget.burst_count):
        frames = decode_burst(metadata.path, size, start, budget.burst_length)
        frames_decoded += len(frames)
        if len(frames) < 2:
            continue
        windows += 1
        seed = (0, 0)
        for previous, current in zip(frames, frames[1:]):
            estimate = estimate_translation(previous, current, seed)
            seed = (estimate.dx_px, estimate.dy_px)
            residuals.append(estimate.residual_fraction)
            hot_blocks.append(estimate.hot_block_fraction)
            shifts.append(estimate.magnitude_fraction)
    stats = BurstStats(
        pairs=len(residuals),
        windows=windows,
        median_residual_fraction=_median(residuals),
        p90_residual_fraction=_percentile(residuals, 90),
        median_hot_block_fraction=_median(hot_blocks),
        p90_hot_block_fraction=_percentile(hot_blocks, 90),
        max_hot_block_fraction=max(hot_blocks) if hot_blocks else 0.0,
        median_shift_fraction=_median(shifts),
    )
    return stats, frames_decoded


def _median(values: list[float]) -> float:
    return float(np.median(values)) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    return float(np.percentile(values, percentile)) if values else 0.0


def describe_limits(budget: SamplingBudget, stride: int, metadata: VideoMetadata) -> tuple[str, ...]:
    """State what this scan could not see, so a clean report is not read as proof."""
    limits = [
        "sharpness, cut distance and translation are measured on "
        f"{budget.analysis_max_pixels} analysed pixels per frame; the features COLMAP "
        f"later extracts come from the full {metadata.width}x{metadata.height} source, "
        "which this scan does not measure",
        f"residual statistics come from {budget.burst_count} contiguous windows of "
        f"{budget.burst_length} frames; something that walks through one of the other "
        "windows is not seen",
        "translation is one global shift per pair; camera rotation about the view axis "
        "is counted as unexplained change, not as measured rotation",
        f"displacements below about 0.5% of the analysis frame width fall under the "
        f"alignment search's resolution and are reported as zero, so a very slow camera "
        f"can measure as still; translations are therefore measured over {PARALLAX_GAP} "
        "candidate gaps",
    ]
    if stride > 1:
        limits.append(
            f"candidates are {stride} source frames apart, so anything that happens only "
            "between two candidates -- including a cut shorter than the stride -- is not examined"
        )
    return tuple(limits)


def scan_capture(metadata: VideoMetadata, budget: SamplingBudget) -> ScanResult:
    """Run all three bounded passes and return one record of the work done."""
    started = time.monotonic()
    size = analysis_size(metadata, budget.analysis_max_pixels)
    motion = measure_motion(metadata, budget)
    stride = candidate_stride_for(metadata.frame_count, motion.pixels_per_frame, size.width, budget)
    candidates, candidate_stats, gap = scan_candidates(metadata, budget, stride)
    bursts, burst_frames = scan_bursts(metadata, budget)
    return ScanResult(
        metadata=metadata,
        size=size,
        stride=stride,
        candidates=candidates,
        bursts=bursts,
        motion_px_per_frame=motion.pixels_per_frame,
        parallax_gap=gap,
        probe_stats=motion.stats,
        candidate_stats=candidate_stats,
        burst_frames_decoded=burst_frames,
        seconds=time.monotonic() - started,
        limits=describe_limits(budget, stride, metadata),
    )