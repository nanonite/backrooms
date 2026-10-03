#!/usr/bin/env python3
"""Bounded feature matching: what to compare, what that costs, and what it misses.

Exhaustive matching compares every pair of N frames -- 4.5 million pairs at 150
frames, which is hours of CPU on a workstation. Two bounded strategies replace
it, and both give up something specific that this module names rather than
hides:

* **sequential** -- each frame against its ``window`` temporal neighbours. It
  costs O(N*window) and it cannot match two views taken far apart in time, so a
  revisit after more than ``window`` samples is not matched unless retrieval
  covers it.
* **retrieval** -- each frame against ``keyframes`` keyframes spread over the
  walk, plus the keyframes against each other. This is what finds the revisits
  a walk-through produces, at O(N*keyframes).

The plan therefore reports the pair count of each strategy, which one was
chosen, the reduction against exhaustive, and the frames left unmatched -- the
part that decides whether a loop closure will be found.
"""

from __future__ import annotations

from dataclasses import dataclass

from sampling_budget import RETRIEVAL_KEYFRAMES, SEQUENTIAL_WINDOW

STRATEGY_SEQUENTIAL = "sequential"
STRATEGY_RETRIEVAL = "retrieval"
STRATEGY_EXHAUSTIVE = "exhaustive"


@dataclass(frozen=True)
class MatchingPlan:
    """The bounded matching strategy for a fixed number of selected frames."""

    frames: int
    strategy: str
    window: int
    keyframes: int
    pairs: int
    exhaustive_pairs: int
    reason: str
    unmatched_notes: tuple[str, ...]

    @property
    def reduction_factor(self) -> float:
        """How many times fewer pairs than exhaustive matching."""
        return self.exhaustive_pairs / self.pairs if self.pairs else 0.0

    def to_dict(self) -> dict:
        return {
            "frames": self.frames,
            "strategy": self.strategy,
            "window": self.window,
            "keyframes": self.keyframes,
            "pairs": self.pairs,
            "exhaustive_pairs": self.exhaustive_pairs,
            "reduction_factor": round(self.reduction_factor, 1),
            "reason": self.reason,
            "unmatched_notes": list(self.unmatched_notes),
        }


def exhaustive_pairs(frames: int) -> int:
    """Pairs compared by exhaustive matching."""
    return frames * (frames - 1) // 2


def sequential_pairs(frames: int, window: int) -> int:
    """Pairs compared by a sliding window of ``window`` temporal neighbours."""
    window = max(1, min(window, frames - 1)) if frames > 1 else 1
    total = 0
    for position in range(frames):
        total += min(window, frames - 1 - position)
    return total


def retrieval_pairs(frames: int, keyframes: int) -> int:
    """Pairs compared by matching every frame against spread keyframes.

    Each non-keyframe frame against all ``keyframes`` keyframes, plus the
    keyframes against each other: ``(N-K)*K + K(K-1)/2``.
    """
    if frames <= 1:
        return 0
    keyframes = max(2, min(keyframes, frames))
    return (frames - keyframes) * keyframes + keyframes * (keyframes - 1) // 2


def choose_keyframe_count(frames: int, requested: int) -> int:
    """Keyframes to spread over the walk, always leaving a floor of non-keyframes."""
    if frames <= 2:
        return frames
    return int(max(2, min(requested, max(2, frames // 4))))


def build_plan(
    frames: int,
    sequential_window: int = SEQUENTIAL_WINDOW,
    keyframes: int = RETRIEVAL_KEYFRAMES,
) -> MatchingPlan:
    """Choose between sequential and retrieval matching for ``frames`` frames.

    Retrieval wins on pair count for anything above a handful of frames, and it
    is the only one of the two that can match a revisit. The sequential window
    is kept in the plan because a global mapper still needs the local chain to
    bootstrap from, so the recommended command runs both.
    """
    if frames < 2:
        return MatchingPlan(
            frames=frames,
            strategy=STRATEGY_SEQUENTIAL,
            window=sequential_window,
            keyframes=0,
            pairs=0,
            exhaustive_pairs=exhaustive_pairs(frames),
            reason="fewer than two frames: there is nothing to match",
            unmatched_notes=("no pair is matched; the reconstruction has no baseline",),
        )
    keyframe_count = choose_keyframe_count(frames, keyframes)
    retrieval = retrieval_pairs(frames, keyframe_count)
    sequential = sequential_pairs(frames, sequential_window)
    return MatchingPlan(
        frames=frames,
        strategy=STRATEGY_RETRIEVAL,
        window=sequential_window,
        keyframes=keyframe_count,
        pairs=retrieval,
        exhaustive_pairs=exhaustive_pairs(frames),
        reason=(
            f"retrieval matching against {keyframe_count} keyframes costs {retrieval} pairs "
            f"against {exhaustive_pairs(frames)} exhaustive ({retrieval / max(1, exhaustive_pairs(frames)):.1%}); "
            f"the sequential window alone would cost {sequential} pairs and find no revisits"
        ),
        unmatched_notes=unmatched_notes(frames, sequential_window, keyframe_count),
    )


def unmatched_notes(frames: int, window: int, keyframes: int) -> tuple[str, ...]:
    """State what bounded matching will not compare."""
    longest_gap = frames // 2
    return (
        f"sequential matching compares only the {window} nearest temporal neighbours, so any two "
        f"views more than {window} samples apart are not matched by it; on this walk the largest "
        f"such gap is {longest_gap} samples",
        f"retrieval matching compares each frame against {keyframes} keyframes, so a revisit matches "
        "only if one of its frames is near a keyframe in appearance; a short revisit in a visually "
        "distinct part of the room can still be missed",
        "a loop closure missed here shows up as two disconnected reconstructions, not as a bad one: "
        "check the registration report before treating a sparse model as a single room",
    )


def colmap_matching_commands(
    database_path: str, plan: MatchingPlan, image_list_path: str | None = None
) -> tuple[str, ...]:
    """The COLMAP matcher commands this plan implies, ready to run."""
    common = ["--SiftExtraction.use_gpu", "0", "--SiftMatching.use_gpu", "0"]
    commands = []
    if plan.frames < 2:
        return ()
    base = ["colmap", "sequential_matcher", database_path]
    if image_list_path:
        base += ["--image_list_path", image_list_path]
    commands.append(" ".join(base + [f"--SequentialMatching.overlap={plan.window}", *common]))
    if plan.keyframes >= 2:
        loop_closure = ["colmap", "vocab_tree_matcher", database_path]
        if image_list_path:
            loop_closure += ["--image_list_path", image_list_path]
        commands.append(" ".join(loop_closure + [*common, f"--VocabTreeMatching.overlap={plan.window}"]))
    return tuple(commands)