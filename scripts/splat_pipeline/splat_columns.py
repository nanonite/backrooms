#!/usr/bin/env python3
"""Classify floor-plan columns straight from the Gaussian splat.

This is the *independent* half of the wall/opening check.  The generated
collision says which columns ended up solid; this module says which columns the
reconstruction itself observed surface in.  Comparing the two is what turns
"the walls look right" into a number, and it is what catches the failure mode
where the collision is solid everywhere: a mesh can agree with itself perfectly
while describing a room that was never there.

**Gaussian centres are not surfaces.**  Every splat contributes through its
rotated, scaled extent at the renderer's 3-sigma cutoff, so a splat whose centre
sits 30 cm from a wall still counts against the column the wall occupies if its
tail reaches it.  A centre-only test misses exactly the thin walls and doorway
reveals this task has to preserve, because those are the features reconstructed
by a handful of large, offset splats.

Column size is a parameter, not a constant, because the answer changes with it:
a 5 cm column resolves a doorway reveal, a 50 cm column averages it away.  The
recorded benchmark states the size it used and the coverage it achieved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

import splat_ply
from splat_frame import FrameContract

#: Splat extents are cut off at this many standard deviations, matching the
#: renderer (and therefore the collision voxelizer's own extent calculation).
SIGMA_CUTOFF = 3.0

#: Height band above the floor that counts as "something a person would walk
#: into".  Below the lower edge is floor-level detail, above the upper edge is
#: ceiling and lighting; neither says anything about whether a column is blocked.
OBSTRUCTION_BAND_M = (0.30, 1.80)

#: A column counts as floor-supported when this many splats reach the floor band.
#: One splat is not a floor: a low outlier over a doorway would otherwise read as
#: support where a person would fall through.
MIN_FLOOR_SPLATS = 8

#: A column counts as obstructed when its banded splat count reaches this
#: percentile of the floor-supported columns' distribution.  A percentile rather
#: than an absolute count because how densely a corridor reconstructs varies
#: with texture and exposure, and rather than a fraction of the median because
#: most walkable columns are open and a median-relative cut marks everything.
OBSTRUCTION_PERCENTILE = 90.0


#: World axes a floor plan spans.  Godot is y-up, so the plan is x/z and the
#: vertical band index is y -- the one place where reading the axes in the wrong
#: order turns a 19 x 14 m corridor into a 19 x 2.4 m one.
PLAN_AXES = (0, 2)
VERTICAL_AXIS = 1


class SplatColumnError(ValueError):
    """Raised when the splat lacks the columns needed for a column classification."""


@dataclass(frozen=True)
class ColumnGrid:
    """Per-column evidence extracted from the splat, in Godot world metres.

    The grid is indexed ``[ix, iy]`` along :data:`PLAN_AXES`, and
    ``origin`` is the world x/z of cell ``(0, 0)``'s minimum corner.
    """

    size_m: float
    origin: tuple[float, float]
    floor_splats: np.ndarray
    band_splats: np.ndarray
    floor_level_m: float
    obstructed: np.ndarray
    has_floor: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return self.floor_splats.shape  # type: ignore[return-value]

    @property
    def cells(self) -> int:
        return int(self.floor_splats.size)

    def cell_centre(self, index) -> np.ndarray:
        """Return the world-space centre of column ``(ix, iy)``, at floor level.

        Accepts a single ``(ix, iy)`` pair or an ``(N, 2)`` array of them, because
        the callers that want every column at once are the ones that matter for
        speed and there is no reason to make them loop.
        """
        cells = np.atleast_2d(np.asarray(index, dtype=np.float64))
        points = np.zeros((len(cells), 3))
        points[:, PLAN_AXES[0]] = self.origin[0] + (cells[:, 0] + 0.5) * self.size_m
        points[:, PLAN_AXES[1]] = self.origin[1] + (cells[:, 1] + 0.5) * self.size_m
        points[:, VERTICAL_AXIS] = self.floor_level_m
        return points[0] if np.ndim(index) == 1 else points

    def column_at(self, point) -> tuple[int, int] | None:
        """Return the column index containing the point's x/z, or ``None`` if outside."""
        delta = np.asarray(point, dtype=np.float64)[list(PLAN_AXES)] - np.asarray(self.origin)
        index = np.floor(delta / self.size_m).astype(int)
        if np.any(index < 0) or np.any(index >= np.asarray(self.shape)):
            return None
        return int(index[0]), int(index[1])

    def summary(self) -> dict:
        """Return the counts a coverage report needs."""
        supported = int(self.has_floor.sum())
        blocked = int((self.has_floor & self.obstructed).sum())
        return {
            "column_size_m": self.size_m,
            "cells": self.cells,
            "floor_supported_cells": supported,
            "obstructed_supported_cells": blocked,
            "open_supported_cells": supported - blocked,
        }


def classify_columns(
    ply_path: str | Path,
    contract: FrameContract,
    column_size_m: float = 0.25,
    bounds=None,
    window=None,
) -> ColumnGrid:
    """Split the scene into floor-plan columns and measure surface evidence in each.

    ``window`` is the box the reconstruction is trusted to have observed; it
    defaults to the contract's camera-path window.  The filter is not
    housekeeping: the floaters in this splat reach 140 m from the room, and every
    one of them crosses every column, so an unfiltered classification marks the
    entire floor plan obstructed and says nothing at all.

    ``bounds`` overrides the column grid's world extent; it defaults to the
    intersection of ``window`` and the contract's room, so the denominator is
    columns that were actually observed rather than corners nobody filmed.
    """
    if column_size_m <= 0.0:
        raise SplatColumnError("column_size_m must be positive")
    ply_to_world = contract.ply_to_world
    window_low, window_high = (
        (np.asarray(window[0]), np.asarray(window[1])) if window is not None else observed_window(contract)
    )
    room_low = np.asarray(contract.collider.min_corner)
    room_high = np.asarray(contract.collider.max_corner)
    low = np.maximum(room_low, window_low) if bounds is None else np.asarray(bounds[0])
    high = np.minimum(room_high, window_high) if bounds is None else np.asarray(bounds[1])
    centres = np.stack([ply_to_world.world_point(row) for row in splat_ply.read_positions(ply_path)])
    extents = rotated_extents(ply_path) * ply_to_world.metres_per_unit
    observed = _inside(centres, extents, low, high)
    origin = (float(low[PLAN_AXES[0]]), float(low[PLAN_AXES[1]]))
    shape = np.maximum(np.ceil((high[list(PLAN_AXES)] - low[list(PLAN_AXES)]) / column_size_m).astype(int), 1)
    floor_level = float(contract.collider.floor_height)
    floor_splats, band_splats = _accumulate(
        centres[observed],
        extents[observed],
        origin,
        shape,
        column_size_m,
        floor_level,
        floor_level + 2.0 * column_size_m,
        floor_level + OBSTRUCTION_BAND_M[0],
        floor_level + OBSTRUCTION_BAND_M[1],
    )
    has_floor = floor_splats >= MIN_FLOOR_SPLATS
    obstructed = _obstruction_mask(band_splats, has_floor)
    return ColumnGrid(
        size_m=column_size_m,
        origin=origin,
        floor_splats=floor_splats,
        band_splats=band_splats,
        floor_level_m=floor_level,
        obstructed=obstructed,
        has_floor=has_floor,
    )


def rotated_extents(ply_path: str | Path) -> np.ndarray:
    """Return each splat's 3-sigma half-extent per world axis, in reconstruction units.

    ``exp(scale_N)`` is the linear standard deviation and ``(rot_1..3, rot_0)`` the
    quaternion, so the extent of the rotated, scaled ellipsoid along world axis *j*
    is ``SIGMA_CUTOFF * sqrt(sum_i (R[j, i] * s_i)**2)``.  Summing in quadrature is
    the AABB of the ellipsoid -- conservative, which is the right direction: a
    surface has to reach a column to count against it.
    """
    header = splat_ply.parse_header(ply_path)
    for name in ("scale_0", "rot_0", "rot_1", "rot_2", "rot_3"):
        if name not in header.properties:
            raise SplatColumnError("%s: PLY has no %s property" % (ply_path, name))
    scales = np.exp(splat_ply.read_columns(ply_path, ("scale_0", "scale_1", "scale_2")))
    quaternions = splat_ply.read_columns(ply_path, ("rot_0", "rot_1", "rot_2", "rot_3"))
    w, x, y, z = quaternions.T
    norms = np.linalg.norm(quaternions, axis=1)
    norms = np.where(norms > 1e-12, norms, 1.0)
    w, x, y, z = (w / norms), (x / norms), (y / norms), (z / norms)
    rotation = np.empty((len(w), 3, 3))
    rotation[:, 0, 0] = 1 - 2 * (y * y + z * z)
    rotation[:, 0, 1] = 2 * (x * y - z * w)
    rotation[:, 0, 2] = 2 * (x * z + y * w)
    rotation[:, 1, 0] = 2 * (x * y + z * w)
    rotation[:, 1, 1] = 1 - 2 * (x * x + z * z)
    rotation[:, 1, 2] = 2 * (y * z - x * w)
    rotation[:, 2, 0] = 2 * (x * z - y * w)
    rotation[:, 2, 1] = 2 * (y * z + x * w)
    rotation[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return SIGMA_CUTOFF * np.sqrt(np.einsum("nij,ni->nj", rotation, scales) ** 2)


def observed_window(contract: FrameContract) -> tuple[np.ndarray, np.ndarray]:
    """Return the contract's camera-path window: the region actually filmed."""
    return np.asarray(contract.splat_bounds.core_min), np.asarray(contract.splat_bounds.core_max)


def _inside(centres: np.ndarray, extents: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """Return the mask of splats whose 3-sigma extent overlaps the box."""
    return np.all((centres + extents >= low) & (centres - extents <= high), axis=1)


def _accumulate(
    centres: np.ndarray,
    extents: np.ndarray,
    origin: tuple[float, float],
    shape: np.ndarray,
    column_size_m: float,
    floor_lo: float,
    floor_hi: float,
    band_lo: float,
    band_hi: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Bin each splat into every column its extent overlaps, by height band."""
    floor_splats = np.zeros((int(shape[0]), int(shape[1])), dtype=np.int64)
    band_splats = np.zeros_like(floor_splats)
    height = centres[:, VERTICAL_AXIS]
    reach = extents[:, VERTICAL_AXIS]
    floor_touches = (height - reach <= floor_hi) & (height + reach >= floor_lo)
    band_touches = (height - reach <= band_hi) & (height + reach >= band_lo)
    for mask, target in ((floor_touches, floor_splats), (band_touches, band_splats)):
        columns = _columns_for(centres[mask], extents[mask], origin, column_size_m, shape)
        # np.add.at rather than += : a splat's extent covers many columns and
        # another splat's covers the same ones, and += would drop all but one.
        np.add.at(target, (columns[:, 0], columns[:, 1]), 1)
    return floor_splats, band_splats


def _columns_for(
    centres: np.ndarray,
    extents: np.ndarray,
    origin: tuple[float, float],
    column_size_m: float,
    shape: np.ndarray,
) -> np.ndarray:
    """Return the ``(K, 2)`` column indices each splat's extent overlaps."""
    plan = np.asarray(PLAN_AXES)
    low = np.floor((centres[:, plan] - extents[:, plan] - np.asarray(origin)) / column_size_m).astype(int)
    high = np.floor((centres[:, plan] + extents[:, plan] - np.asarray(origin)) / column_size_m).astype(int)
    columns = []
    for x0, x1, y0, y1 in zip(low[:, 0], high[:, 0], low[:, 1], high[:, 1]):
        x0c, x1c = max(int(x0), 0), min(int(x1), int(shape[0]) - 1)
        y0c, y1c = max(int(y0), 0), min(int(y1), int(shape[1]) - 1)
        if x0c > x1c or y0c > y1c:
            continue
        grid_x, grid_y = np.meshgrid(np.arange(x0c, x1c + 1), np.arange(y0c, y1c + 1), indexing="ij")
        columns.append(np.stack([grid_x.ravel(), grid_y.ravel()], axis=1))
    if not columns:
        return np.zeros((0, 2), dtype=int)
    return np.concatenate(columns, axis=0)


def _obstruction_mask(band_splats: np.ndarray, has_floor: np.ndarray) -> np.ndarray:
    """Mark floor-supported columns carrying obstruction-band surface.

    The threshold is a high percentile of the observed distribution rather than a
    fraction of the median: most columns in a walkable room are *open*, so the
    median banded count is low and any median-relative cut would mark the whole
    plan obstructed -- which is exactly what the first version of this function
    did, and exactly the "solid everywhere" failure this module exists to catch.
    """
    if not has_floor.any():
        return np.zeros_like(has_floor)
    reference = float(np.percentile(band_splats[has_floor], OBSTRUCTION_PERCENTILE))
    # A percentile of zero means the overwhelming majority of columns saw no
    # band surface at all -- a thin wall in a large open plan.  Demanding a count
    # above zero then classifies nothing, which reads as "no walls anywhere" and
    # fails the wall check for the wrong reason, so the floor is any evidence.
    threshold = reference if reference > 0.0 else 1.0
    return has_floor & (band_splats >= threshold)