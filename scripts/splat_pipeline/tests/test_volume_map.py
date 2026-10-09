#!/usr/bin/env python3
"""Tests for the view-based visual-enclosure score in volume_map.py.

The adjacent-face enclosure test (score_envelope) asks whether splats sit at
the cell's own faces, which is the wrong question in an open Backrooms room:
walls stand 2-5 m away, not 0.35 m. These tests pin the view-based score
instead -- eight compass cones from the production eye height -- around the
mistakes it could actually make:

* floor/ceiling splats standing in for a missing wall (band exclusion);
* a wall beyond visual range counting as enclosure (12 m cap);
* a single floater counting as a surface (minimum support count);
* an empty direction reporting a distance instead of None.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from volume_map import (
    EYE_ABOVE_FLOOR_M,
    VIEW_MAX_RANGE_M,
    VIEW_MIN_SUPPORT_SPLATS,
    score_cell_views,
    score_visual_enclosure,
)


def _grid(floor=0.0, ceiling=2.15):
    """One walkable cell centred on the origin."""
    return SimpleNamespace(
        size_m=0.25,
        floor_y=np.array([[floor]]),
        ceiling_y=np.array([[ceiling]]),
        cell_centre=lambda r, c: (0.0, 0.0),
    )


def _wall(x, n=12, spread=1.0):
    """A vertical patch of splats at world x, spanning the wall band."""
    ys = np.linspace(0.5, 1.8, n)
    zs = np.linspace(-spread / 2, spread / 2, n)
    return np.column_stack(
        [np.full(n, x), ys, zs]
    )


def test_wall_ahead_supported_with_nearest_distance():
    centres = _wall(3.0)
    views = score_cell_views(centres, _grid(), 0, 0)
    assert views["e"]["supported"] is True
    assert views["e"]["support_splats"] >= VIEW_MIN_SUPPORT_SPLATS
    assert views["e"]["nearest_m"] == nugget(views["e"]["nearest_m"], 3.0)
    assert views["w"]["supported"] is False
    assert views["w"]["nearest_m"] is None


def nugget(value, expect, tol=0.05):
    """Nearest conical splat is the wall plane to within the patch spread."""
    assert value is not None and abs(value - expect) <= tol, (value, expect)
    return value


def test_floor_splats_do_not_count_as_walls():
    n = 20
    centres = np.column_stack(
        [np.linspace(0.5, 5.0, n), np.full(n, 0.05), np.zeros(n)]
    )
    views = score_cell_views(centres, _grid(), 0, 0)
    assert all(v["supported"] is False for v in views.values())


def test_wall_beyond_range_is_a_gap():
    centres = _wall(VIEW_MAX_RANGE_M + 3.0)
    views = score_cell_views(centres, _grid(), 0, 0)
    assert views["e"]["supported"] is False
    assert views["e"]["nearest_m"] is None


def test_single_floater_is_not_a_surface():
    centres = np.array([[2.0, EYE_ABOVE_FLOOR_M, 0.0]])
    views = score_cell_views(centres, _grid(), 0, 0)
    assert views["e"]["supported"] is False
    assert views["e"]["support_splats"] == 1


def test_enclosure_aggregates_over_component():
    centres = np.vstack([_wall(3.0), _wall(-3.0)])
    grid = SimpleNamespace(
        size_m=0.25,
        floor_y=np.zeros((1, 2)),
        ceiling_y=np.full((1, 2), 2.15),
        cell_centre=lambda r, c: (0.0, 0.0),
    )
    component = np.array([[True, True]])
    result = score_visual_enclosure(centres, grid, component)
    assert result["cells"] == 2
    assert result["supported"]["e"] == 2
    assert result["supported"]["w"] == 2
