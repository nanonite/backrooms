#!/usr/bin/env python3
"""Choose which sampled frames to reconstruct from.

Selection is a walk in time order, not a ranking. A frame is only useful if it
is sharp, is not adjacent to a cut, and shows the scene from a position the
previously kept frame did not -- a wall seen twice from 2 cm away adds a pair to
match and no geometry. So the selector keeps the first eligible frame, then
walks forward keeping a frame only when it has moved far enough from the last
kept one, and records why every other frame was dropped.

The frame target is applied last and by thinning, not by truncation: when a
capture has twice as much usable motion as the budget allows, every third frame
is dropped spread evenly, so the walk keeps its start, its middle and its end
instead of becoming a prefix of the clip.
"""

from __future__ import annotations

from dataclasses import dataclass

from camera_path import CameraPath, build_camera_path
from candidate_scan import CandidateFrame

#: Why a candidate was not selected. Reported per frame, because "we dropped 40
#: frames" is not actionable and "these 40 are blurred" is.
REASON_CUT = "adjacent_to_scene_cut"
REASON_BLUR = "below_relative_sharpness"
REASON_REDUNDANT = "below_minimum_translation"
REASON_OVER_BUDGET = "above_frame_target"

#: A candidate this close to a cut is excluded: the cut itself breaks the shared
#: geometry, and its neighbours are the frames most likely to straddle it.
CUT_NEIGHBOUR_RADIUS = 1


@dataclass(frozen=True)
class Exclusion:
    """One dropped frame and the reason it was dropped."""

    index: int
    reason: str
    detail: str

    def to_dict(self) -> dict:
        return {"index": self.index, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class SelectionResult:
    """The kept frames, in time order, plus the reason for every drop."""

    selected: tuple[int, ...]
    exclusions: tuple[Exclusion, ...]
    eligible: int
    sharpness_reference: float
    min_shift_fraction: float

    @property
    def count(self) -> int:
        return len(self.selected)

    def counts_by_reason(self) -> dict[str, int]:
        """Exclusion counts per reason, for a one-line summary."""
        counts: dict[str, int] = {}
        for exclusion in self.exclusions:
            counts[exclusion.reason] = counts.get(exclusion.reason, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "selected": list(self.selected),
            "selected_count": self.count,
            "eligible": self.eligible,
            "sharpness_reference": round(self.sharpness_reference, 2),
            "min_shift_fraction": self.min_shift_fraction,
            "excluded_by_reason": self.counts_by_reason(),
            "exclusions": [exclusion.to_dict() for exclusion in self.exclusions],
        }


def _cut_blocked_indices(candidates: tuple[CandidateFrame, ...]) -> set[int]:
    """Indices within one sample of a detected scene cut."""
    blocked: set[int] = set()
    for position, candidate in enumerate(candidates):
        if not candidate.is_cut:
            continue
        for neighbour in range(position - CUT_NEIGHBOUR_RADIUS, position + CUT_NEIGHBOUR_RADIUS + 1):
            if 0 <= neighbour < len(candidates):
                blocked.add(neighbour)
    return blocked


def sharpness_reference(candidates: tuple[CandidateFrame, ...]) -> float:
    """The clip's own 90th-percentile sharpness: the bar candidates are judged against."""
    if not candidates:
        return 0.0
    values = sorted(candidate.sharpness for candidate in candidates)
    position = min(len(values) - 1, int(round(0.9 * (len(values) - 1))))
    return values[position]


def _eligible_candidates(
    candidates: tuple[CandidateFrame, ...],
    reference_sharpness: float,
    min_sharpness_ratio: float,
) -> list[tuple[int, CandidateFrame]]:
    """Candidates that pass the cut and sharpness rules, in time order."""
    blocked = _cut_blocked_indices(candidates)
    threshold = reference_sharpness * min_sharpness_ratio
    eligible = []
    for position, candidate in enumerate(candidates):
        if position in blocked or candidate.sharpness < threshold:
            continue
        eligible.append((position, candidate))
    return eligible


def _walk_for_motion(
    eligible: list[tuple[int, CandidateFrame]],
    path: CameraPath,
    min_shift_pixels: float,
) -> tuple[list[int], list[Exclusion]]:
    """Keep a frame only once the camera has moved far enough since the last kept one."""
    kept: list[int] = []
    exclusions: list[Exclusion] = []
    last_position = None
    for position, candidate in eligible:
        if last_position is None:
            kept.append(candidate.index)
            last_position = position
            continue
        moved = abs(path.distances[position] - path.distances[last_position])
        if moved < min_shift_pixels:
            exclusions.append(
                Exclusion(
                    index=candidate.index,
                    reason=REASON_REDUNDANT,
                    detail=f"camera moved {moved:.1f}px since the last kept frame, "
                    f"under the {min_shift_pixels:.1f}px minimum",
                )
            )
            continue
        kept.append(candidate.index)
        last_position = position
    return kept, exclusions


def _thin_evenly(indices: list[int], target: int) -> list[int]:
    """Reduce ``indices`` to ``target`` entries spread across the whole walk."""
    if target >= len(indices):
        return indices
    span = len(indices) / target
    return [indices[min(len(indices) - 1, int(round(step * span)))] for step in range(target)]


def select_frames(
    candidates: tuple[CandidateFrame, ...],
    analysis_width: int,
    target_frames: int,
    min_sharpness_ratio: float,
    min_shift_fraction: float,
    parallax_gap: int = 1,
) -> SelectionResult:
    """Select the frames to reconstruct from, and account for every frame dropped."""
    reference = sharpness_reference(candidates)
    eligible = _eligible_candidates(candidates, reference, min_sharpness_ratio)
    eligible_positions = {position for position, _ in eligible}
    exclusions = _sharpness_and_cut_exclusions(candidates, reference, min_sharpness_ratio, eligible_positions)
    path = build_camera_path(candidates, parallax_gap)
    kept_indices, motion_exclusions = _walk_for_motion(
        eligible, path, min_shift_fraction * analysis_width
    )
    exclusions.extend(motion_exclusions)
    if len(kept_indices) > target_frames:
        thinned = _thin_evenly(kept_indices, target_frames)
        dropped = set(kept_indices) - set(thinned)
        exclusions.extend(
            Exclusion(
                index=index,
                reason=REASON_OVER_BUDGET,
                detail=f"kept {target_frames} of {len(kept_indices)} usable frames; this one was thinned out",
            )
            for index in sorted(dropped)
        )
        kept_indices = thinned
    return SelectionResult(
        selected=tuple(kept_indices),
        exclusions=tuple(sorted(exclusions, key=lambda item: item.index)),
        eligible=len(eligible),
        sharpness_reference=reference,
        min_shift_fraction=min_shift_fraction,
    )


def _sharpness_and_cut_exclusions(
    candidates: tuple[CandidateFrame, ...],
    reference_sharpness: float,
    min_sharpness_ratio: float,
    eligible_positions: set[int],
) -> list[Exclusion]:
    """Record why each cut-adjacent or soft candidate was dropped."""
    threshold = reference_sharpness * min_sharpness_ratio
    blocked = _cut_blocked_indices(candidates)
    exclusions = []
    for position, candidate in enumerate(candidates):
        if position in eligible_positions:
            continue
        if position in blocked:
            exclusions.append(
                Exclusion(
                    index=candidate.index,
                    reason=REASON_CUT,
                    detail=f"within one sample of a cut (histogram distance {candidate.cut_distance:.3f})",
                )
            )
        else:
            exclusions.append(
                Exclusion(
                    index=candidate.index,
                    reason=REASON_BLUR,
                    detail=f"sharpness {candidate.sharpness:.0f} under {threshold:.0f} "
                    f"({min_sharpness_ratio:.0%} of the clip's own p90 {reference_sharpness:.0f})",
                )
            )
    return exclusions