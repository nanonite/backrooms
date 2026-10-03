#!/usr/bin/env python3
"""How much of the room the retained views actually cover.

Coverage is reported in units of the analysis frame width, not metres: without a
scale there is no honest unit, and a frame-relative number transfers between a
720p phone capture and a 4K one. A camera that walked a corridor and one that
turned on the spot both produce frames; only the first covers anything, and the
difference is the total path length, the spread of viewpoints, and how many
distinct directions the camera travelled in.

The report also states what is *not* covered, because a splat reconstructs only
what a camera saw: the walk's own extent is the ceiling on the walkable volume,
and a report that omits that reads like a room survey rather than a coverage
measure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from camera_path import CameraPath, build_camera_path
from candidate_scan import CandidateFrame

#: Viewpoints are counted in bins of this many frame widths. Quarter-width bins
#: distinguish "moved to the other side of the room" from "took a step".
VIEWPOINT_BIN_WIDTHS = 0.25

#: Directions are counted in this many sectors, for "did the camera turn around
#: or walk one way".
DIRECTION_SECTORS = 8


@dataclass(frozen=True)
class CoverageReport:
    """Frame-relative coverage of the selected views."""

    selected_count: int
    analysed_count: int
    path_length_widths: float
    retained_path_length_widths: float
    viewpoint_bins: int
    distinct_directions: int
    extent_x_widths: float
    extent_y_widths: float
    selected_span_seconds: float
    clip_span_seconds: float

    @property
    def span_fraction(self) -> float:
        """Share of the clip's duration the selected frames span."""
        return self.selected_span_seconds / self.clip_span_seconds if self.clip_span_seconds else 0.0

    @property
    def viewpoint_efficiency(self) -> float:
        """Distinct viewpoints per selected frame; 1.0 means no redundancy."""
        return self.viewpoint_bins / self.selected_count if self.selected_count else 0.0

    def to_dict(self) -> dict:
        return {
            "selected_count": self.selected_count,
            "analysed_count": self.analysed_count,
            "path_length_widths": round(self.path_length_widths, 3),
            "retained_path_length_widths": round(self.retained_path_length_widths, 3),
            "viewpoint_bins": self.viewpoint_bins,
            "distinct_directions": self.distinct_directions,
            "extent_x_widths": round(self.extent_x_widths, 3),
            "extent_y_widths": round(self.extent_y_widths, 3),
            "selected_span_seconds": round(self.selected_span_seconds, 3),
            "clip_span_seconds": round(self.clip_span_seconds, 3),
            "span_fraction": round(self.span_fraction, 4),
            "viewpoint_efficiency": round(self.viewpoint_efficiency, 3),
        }


def _count_bins(points: np.ndarray, scale: int) -> int:
    if not len(points):
        return 0
    return len(
        {
            (int(round(x / scale / VIEWPOINT_BIN_WIDTHS)), int(round(y / scale / VIEWPOINT_BIN_WIDTHS)))
            for x, y in points
        }
    )


def _count_directions(candidates: tuple[CandidateFrame, ...]) -> int:
    sectors = set()
    for candidate in candidates:
        translation = candidate.translation
        if translation is None or translation.magnitude_px <= 0:
            continue
        angle = math.atan2(translation.dy_px, translation.dx_px)
        sectors.add(int((angle + math.pi) / (2 * math.pi) * DIRECTION_SECTORS) % DIRECTION_SECTORS)
    return len(sectors)


def _extent(points: np.ndarray, scale: int) -> tuple[float, float]:
    """Span of the retained viewpoints in frame widths, per axis."""
    if not len(points):
        return 0.0, 0.0
    return float(np.ptp(points[:, 0])) / scale, float(np.ptp(points[:, 1])) / scale


def measure_coverage(
    candidates: tuple[CandidateFrame, ...],
    selected: tuple[int, ...],
    analysis_width: int,
    clip_span_seconds: float,
    parallax_gap: int = 1,
) -> CoverageReport:
    """Measure coverage of the whole candidate walk and of the retained part."""
    selected_set = set(selected)
    path: CameraPath = build_camera_path(candidates, parallax_gap)
    retained_positions = np.asarray(
        [
            position
            for position, candidate in zip(path.positions, candidates)
            if candidate.index in selected_set
        ],
        dtype=float,
    )
    retained = tuple(candidate for candidate in candidates if candidate.index in selected_set)
    span = (retained[-1].timestamp - retained[0].timestamp) if len(retained) >= 2 else 0.0
    scale = analysis_width if analysis_width else 1
    extent_x, extent_y = _extent(retained_positions, scale)
    retained_length = _retained_length(retained, path, candidates, scale)
    return CoverageReport(
        selected_count=len(retained),
        analysed_count=len(candidates),
        path_length_widths=path.total_pixels / scale,
        retained_path_length_widths=retained_length,
        viewpoint_bins=_count_bins(retained_positions, scale),
        distinct_directions=_count_directions(retained),
        extent_x_widths=extent_x,
        extent_y_widths=extent_y,
        selected_span_seconds=span,
        clip_span_seconds=clip_span_seconds,
    )


def _retained_length(
    retained: tuple[CandidateFrame, ...],
    path: CameraPath,
    candidates: tuple[CandidateFrame, ...],
    scale: int,
) -> float:
    """Travelled distance between the first and last retained frame."""
    if len(retained) < 2:
        return 0.0
    positions = [candidate.index for candidate in candidates]
    first = positions.index(retained[0].index)
    last = positions.index(retained[-1].index)
    return abs(path.distances[last] - path.distances[first]) / scale