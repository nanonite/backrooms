#!/usr/bin/env python3
"""Integrate the measured translations into the camera's path through the scene.

The scan measures how far the view moved between samples that are ``gap``
candidates apart. Integrating those measurements gives two things the rest of
the pipeline reasons about: where the camera was, and how far it travelled in
total. Both are needed as a path rather than a per-pair number, because a camera
can cover a lot of ground in many small steps, and a rule that looks at one step
at a time sees nothing.

Integration is non-overlapping -- the step ending at candidate *i* is added to
the total at candidate *i-gap* -- so the travel reported is a distance walked,
not the same ground counted once per overlapping window. Scene cuts reset the
accumulation: frames on opposite sides of a cut share no geometry, and adding
the jump between them would attribute a cut to the camera.
"""

from __future__ import annotations

from dataclasses import dataclass

from candidate_scan import CandidateFrame


@dataclass(frozen=True)
class CameraPath:
    """Cumulative position and travelled distance at each candidate."""

    positions: tuple[tuple[float, float], ...]
    distances: tuple[float, ...]
    gap: int

    @property
    def total_pixels(self) -> float:
        """Distance travelled over the whole walk, in analysis pixels."""
        return self.distances[-1] if self.distances else 0.0


def integration_gap(candidate_count: int, gap: int) -> int:
    """The gap actually usable for this many candidates."""
    if candidate_count < 2:
        return 1
    return int(max(1, min(gap, candidate_count - 1)))


def build_camera_path(candidates: tuple[CandidateFrame, ...], gap: int) -> CameraPath:
    """Accumulate measured translations into positions and travelled distance."""
    step = integration_gap(len(candidates), gap)
    x = y = 0.0
    positions: list[tuple[float, float]] = []
    distances: list[float] = []
    for position, candidate in enumerate(candidates):
        if candidate.is_cut:
            x = y = 0.0
        if position >= step and candidate.translation is not None and not candidate.is_cut:
            x += candidate.translation.dx_px
            y += candidate.translation.dy_px
            travelled = distances[position - step] + candidate.translation.magnitude_px
        else:
            travelled = 0.0
        positions.append((x, y))
        distances.append(travelled)
    return CameraPath(positions=tuple(positions), distances=tuple(distances), gap=step)


def distance_between(path: CameraPath, from_index: int, to_index: int) -> float:
    """Travelled distance between two candidates, along the integrated path."""
    if not path.distances:
        return 0.0
    first = max(0, min(from_index, len(path.distances) - 1))
    second = max(0, min(to_index, len(path.distances) - 1))
    return abs(path.distances[second] - path.distances[first])