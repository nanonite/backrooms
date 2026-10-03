#!/usr/bin/env python3
"""The budgets that keep reconstruction bounded on a local PC.

Three things in this pipeline grow without limit if left alone: the number of
frames handed to COLMAP, the pixels each frame is analysed at, and the time the
sampling stage is allowed to spend. Each has a configurable budget here, so the
limit is a decision someone wrote down rather than a machine that quietly ran
out of RAM.

**The frame target is a hypothesis, not a guarantee.** 100-200 selected frames
is where a small room starts: enough views for a global mapper to triangulate
walls, few enough to match sequentially on a workstation. It is *not* a property
of the problem -- a long corridor needs more views and a still photo needs
none. Every report says which side of the hypothesis the run landed on, and a
run outside it is flagged rather than clamped, because a target that silently
resets itself teaches nothing about why the number was wrong.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

#: Initial small-room hypothesis for selected frames. See the module docstring.
HYPOTHESIS_LOW_FRAMES = 100
HYPOTHESIS_HIGH_FRAMES = 200
DEFAULT_TARGET_FRAMES = 150

#: Candidates scored before selection. Selection keeps ``target_frames`` of
#: them; a wider net costs one alignment pass per extra candidate and buys
#: freedom to drop cut-adjacent, blurred or redundant frames.
DEFAULT_MAX_CANDIDATES = 240

#: Analysis resolution cap. Metrics are measured here, and the *source*
#: resolution still decides how many features COLMAP finds later.
DEFAULT_ANALYSIS_MAX_PIXELS = 640 * 360

#: Time ceiling for the sampling stage, in seconds.
DEFAULT_MAX_SAMPLE_SECONDS = 120.0

#: Inter-sample translation the candidate stride aims for, as a fraction of the
#: analysis frame width. This is also the smallest displacement the alignment
#: search resolves reliably: below roughly 0.5% of frame width (about 3 px at
#: 640 px) compression noise and smooth gradients dominate the difference
#: between a shifted and an unshifted frame, and the search reports zero.
TARGET_SHIFT_FRACTION = 0.008

#: Bounds on the candidate stride, in source frames.
MIN_CANDIDATE_STRIDE = 1
MAX_CANDIDATE_STRIDE = 240

#: Motion probe: wide, unseeded samples used only to size the clip's motion.
DEFAULT_PROBE_COUNT = 12

#: Burst probe: contiguous windows used to measure what a static scene fails to
#: explain -- moving objects and geometry that does not hold still.
DEFAULT_BURST_COUNT = 3
DEFAULT_BURST_LENGTH = 8

#: A candidate must be at least this fraction of the clip's own 90th-percentile
#: sharpness to be eligible. Relative, because the absolute Laplacian variance
#: of a frame depends on the analysis resolution and on the content.
MIN_SHARPNESS_RATIO = 0.35

#: Inter-sample translation below this is treated as no baseline at all.
MIN_SHIFT_FRACTION = 0.005

#: Scene-cut detection, on two independent signals. The histogram limit is the
#: usual content-detection measure: the six 1080p clips in ``data/videos/``
#: measure 0.024-0.090 between adjacent candidates, so 0.15 sits above them.
CUT_DISTANCE_LIMIT = 0.15

#: ...and the residual limit catches what the histogram misses. A cut between
#: two views that look alike histogram-wise (the same room, different corner)
#: leaves nothing a global translation can align: measured at 0.75 of pixels
#: changed on the ``cut_sequence`` fixture, against 0.14-0.29 for the six real
#: clips at candidate strides of 1-2. Both signals are reported.
CUT_RESIDUAL_LIMIT = 0.45

#: Bounded matching. A sequential window of ``SEQUENTIAL_WINDOW`` neighbours
#: covers motion between adjacent samples; retrieval keyframes cover the
#: revisits a walk-through produces.
SEQUENTIAL_WINDOW = 10
RETRIEVAL_KEYFRAMES = 24

#: Measured on the RTX 4070 Ti workstation (see HARDWARE_BUDGET.md). These are
#: estimates for choosing between decode strategies and for reporting how long
#: sampling should take -- they are not limits, and they are overridable.
STREAM_SECONDS_PER_FRAME = 0.002
SEEK_SECONDS_PER_FRAME = 0.14
ALIGN_SECONDS_PER_PAIR = 0.011

#: Environment prefix for every field, e.g. ``SPLAT_SAMPLE_TARGET_FRAMES``.
ENV_PREFIX = "SPLAT_SAMPLE_"

#: Per-frame analysis storage: one greyscale byte per analysed pixel.
BYTES_PER_ANALYSED_PIXEL = 1


class BudgetError(ValueError):
    """A budget that cannot be used, with the offending field named."""


@dataclass(frozen=True)
class SamplingBudget:
    """Configured limits for one sampling run."""

    target_frames: int = DEFAULT_TARGET_FRAMES
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    analysis_max_pixels: int = DEFAULT_ANALYSIS_MAX_PIXELS
    max_sample_seconds: float = DEFAULT_MAX_SAMPLE_SECONDS
    target_shift_fraction: float = TARGET_SHIFT_FRACTION
    probe_count: int = DEFAULT_PROBE_COUNT
    burst_count: int = DEFAULT_BURST_COUNT
    burst_length: int = DEFAULT_BURST_LENGTH
    min_sharpness_ratio: float = MIN_SHARPNESS_RATIO
    min_shift_fraction: float = MIN_SHIFT_FRACTION
    cut_distance_limit: float = CUT_DISTANCE_LIMIT
    cut_residual_limit: float = CUT_RESIDUAL_LIMIT
    sequential_window: int = SEQUENTIAL_WINDOW
    retrieval_keyframes: int = RETRIEVAL_KEYFRAMES
    decode_mode: str = "auto"
    notes: tuple[str, ...] = field(default=())

    def validate(self) -> None:
        """Raise :class:`BudgetError` for a budget that cannot be executed."""
        positive = {
            "target_frames": self.target_frames,
            "max_candidates": self.max_candidates,
            "analysis_max_pixels": self.analysis_max_pixels,
            "probe_count": self.probe_count,
            "burst_count": self.burst_count,
            "burst_length": self.burst_length,
            "sequential_window": self.sequential_window,
        }
        for name, value in positive.items():
            if value <= 0:
                raise BudgetError(f"{name} must be positive, got {value}")
        if self.max_sample_seconds <= 0:
            raise BudgetError(f"max_sample_seconds must be positive, got {self.max_sample_seconds}")
        if self.retrieval_keyframes <= 0:
            raise BudgetError(f"retrieval_keyframes must be positive, got {self.retrieval_keyframes}")
        if not 0 < self.target_shift_fraction < 1:
            raise BudgetError(f"target_shift_fraction must be in (0, 1), got {self.target_shift_fraction}")
        if self.decode_mode not in ("auto", "stream", "seek"):
            raise BudgetError(f"decode_mode must be auto, stream or seek; got {self.decode_mode!r}")

    def with_overrides(self, **overrides) -> "SamplingBudget":
        """Return a copy with the given fields replaced, validated."""
        unknown = set(overrides) - {f.name for f in fields(self)}
        if unknown:
            raise BudgetError(f"unknown budget fields: {', '.join(sorted(unknown))}")
        updated = replace(self, **overrides)
        updated.validate()
        return updated

    @property
    def in_frame_hypothesis(self) -> bool:
        """True when the frame target sits inside the small-room hypothesis."""
        return HYPOTHESIS_LOW_FRAMES <= self.target_frames <= HYPOTHESIS_HIGH_FRAMES

    def hypothesis_note(self, selected_frames: int) -> str:
        """Describe where the target and the outcome sit relative to the hypothesis."""
        target_note = "" if self.in_frame_hypothesis else (
            f" target {self.target_frames} is OUTSIDE the "
            f"{HYPOTHESIS_LOW_FRAMES}-{HYPOTHESIS_HIGH_FRAMES} hypothesis and is "
            f"treated as a deliberate choice, not as a guarantee"
        )
        return (
            f"frame target {self.target_frames}, selected {selected_frames} "
            f"(hypothesis {HYPOTHESIS_LOW_FRAMES}-{HYPOTHESIS_HIGH_FRAMES} frames "
            f"for a small room -- a starting point, not a guarantee).{target_note}"
        )


#: How to turn text from an environment variable or JSON file into a field value.
_COERCERS = {"int": int, "float": float, "str": str}


def _coerce(name: str, raw: str):
    """Convert an environment/JSON string to the field's declared type."""
    declared = {f.name: f.type for f in fields(SamplingBudget)}.get(name, "")
    convert = _COERCERS.get(declared)
    if convert is None:
        raise BudgetError(f"budget field {name!r} is not settable from text")
    try:
        return convert(raw)
    except ValueError as exc:
        raise BudgetError(f"budget field {name!r} cannot read {raw!r}: {exc}") from exc


def from_env(budget: SamplingBudget | None = None) -> SamplingBudget:
    """Apply ``SPLAT_SAMPLE_*`` overrides on top of ``budget`` (or the defaults)."""
    base = budget or SamplingBudget()
    overrides = {}
    for spec in fields(base):
        env_name = ENV_PREFIX + spec.name.upper()
        if env_name in os.environ:
            overrides[spec.name] = _coerce(spec.name, os.environ[env_name])
    return base.with_overrides(**overrides) if overrides else base


def load_json(path: str | Path, budget: SamplingBudget | None = None) -> SamplingBudget:
    """Apply a JSON budget file on top of ``budget`` (or the defaults).

    A missing key keeps the default, so a file can set one value without
    restating the rest.
    """
    budget_path = Path(path).expanduser()
    try:
        document = json.loads(budget_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BudgetError(f"could not read budget file {budget_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BudgetError(f"budget file {budget_path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BudgetError(f"budget file {budget_path} must contain a JSON object")
    known = {f.name for f in fields(budget or SamplingBudget())}
    unknown = set(document) - known
    if unknown:
        raise BudgetError(f"budget file {budget_path} has unknown keys: {', '.join(sorted(unknown))}")
    return from_env((budget or SamplingBudget()).with_overrides(**document))


def estimated_sample_seconds(candidate_count: int, mode: str, clip_frames: int) -> float:
    """Estimated seconds to decode and align ``candidate_count`` candidates."""
    decode = candidate_count * (SEEK_SECONDS_PER_FRAME if mode == "seek" else STREAM_SECONDS_PER_FRAME * clip_frames)
    return decode + max(0, candidate_count - 1) * ALIGN_SECONDS_PER_PAIR


def estimated_analysis_bytes(candidate_count: int, analysis_pixels: int) -> int:
    """Estimated bytes held by decoded analysis frames, if all were retained."""
    return candidate_count * analysis_pixels * BYTES_PER_ANALYSED_PIXEL


def decode_costs(clip_frames: int, candidate_count: int) -> dict[str, float]:
    """Estimated seconds to produce ``candidate_count`` candidates, per strategy.

    Streaming walks the clip once and keeps every ``stride``-th frame, so its
    cost scales with the clip; seeking touches only the frames wanted, so its
    cost scales with the number of candidates. Which wins therefore depends on
    how sparsely the clip is sampled, and both numbers are reported rather than
    the cheaper one being assumed.
    """
    return {
        "stream": clip_frames * STREAM_SECONDS_PER_FRAME + max(0, candidate_count - 1) * ALIGN_SECONDS_PER_PAIR,
        "seek": candidate_count * SEEK_SECONDS_PER_FRAME + max(0, candidate_count - 1) * ALIGN_SECONDS_PER_PAIR,
    }


def choose_decode_mode(budget: SamplingBudget, clip_frames: int, candidate_count: int) -> tuple[str, str]:
    """Pick the decode strategy and explain the choice in one reportable line."""
    costs = decode_costs(clip_frames, candidate_count)
    if budget.decode_mode != "auto":
        return budget.decode_mode, (
            f"decode mode {budget.decode_mode} configured explicitly "
            f"(stream {costs['stream']:.1f}s, seek {costs['seek']:.1f}s estimated)"
        )
    chosen = min(costs, key=lambda name: costs[name])
    other = "seek" if chosen == "stream" else "stream"
    return chosen, (
        f"auto chose {chosen} ({costs[chosen]:.1f}s estimated vs {costs[other]:.1f}s "
        f"for {other}); alignment is the same in both"
    )


def hypothesis_range() -> tuple[int, int]:
    """The initial small-room frame hypothesis, for reports."""
    return HYPOTHESIS_LOW_FRAMES, HYPOTHESIS_HIGH_FRAMES