"""Focused checks for evidence-only floor support grids."""

from __future__ import annotations

import numpy as np
import pytest
from source_support import (
    SLOPE_LIMIT,
    STEP_DISCONTINUITY,
    SupportGrid,
    SupportGridError,
    filter_support,
    triangulate_support,
    validate_alignment_manifest,
)


def flat_grid(rows: int = 4, columns: int = 4, spacing: float = 0.1) -> SupportGrid:
    """Return a small fully observed level patch."""
    return SupportGrid(0.0, 0.0, spacing, np.zeros((rows, columns)))


def alignment_manifest() -> dict:
    """Return a right-handed z-up source mapped to Godot y-up."""
    return {
        "scene_id": "corridor_splat",
        "ply_to_world": {
            "metres_per_unit": 5.0,
            "basis_columns": [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            "up_axis": "z",
            "up_sign": 1,
        },
        "scale_reference": {"kind": "chosen", "raw_units": 2.0, "target_metres": 10.0},
    }


def test_flat_observed_grid_produces_only_upward_faces():
    grid = flat_grid()
    filtered = filter_support(grid, 15.0, 0.2)
    mesh = triangulate_support(grid, filtered)

    assert filtered.supported.all()
    assert mesh.triangles.shape == (18, 3)
    face = mesh.vertices[mesh.triangles[0]]
    assert np.cross(face[1] - face[0], face[2] - face[0])[1] > 0.0


def test_gentle_slope_is_supported_but_steep_slope_is_not():
    spacing = 0.1
    x = np.arange(5) * spacing
    gentle = SupportGrid(
        0.0, 0.0, spacing, np.tile(x * np.tan(np.deg2rad(10.0)), (4, 1))
    )
    steep = SupportGrid(
        0.0, 0.0, spacing, np.tile(x * np.tan(np.deg2rad(20.0)), (4, 1))
    )

    assert filter_support(gentle, 15.0, 0.2).supported.all()
    rejected = filter_support(steep, 15.0, 0.2)
    assert not rejected.supported.any()
    assert np.all(rejected.rejection_reason & SLOPE_LIMIT)


def test_large_step_rejects_both_sides_of_the_discontinuity():
    heights = np.zeros((4, 5))
    heights[:, 2:] = 0.3
    rejected = filter_support(SupportGrid(0.0, 0.0, 0.1, heights), 15.0, 0.2)

    assert np.all(rejected.rejection_reason[:, 1:3] & STEP_DISCONTINUITY)
    assert not rejected.supported[:, 1:3].any()


def test_masked_gap_stays_unknown_and_mesh_does_not_bridge_it():
    heights = np.zeros((3, 7))
    heights[:, 3] = np.nan
    grid = SupportGrid(0.0, 0.0, 0.1, heights)
    filtered = filter_support(grid, 15.0, 0.2)
    mesh = triangulate_support(grid, filtered)

    assert not filtered.supported[:, 3].any()
    assert mesh.triangles.shape == (16, 3)
    for triangle in mesh.vertices[mesh.triangles]:
        assert np.ptp(triangle[:, 0]) <= grid.spacing_m + 1e-9


def test_large_hole_is_not_filled_or_triangulated_across():
    heights = np.zeros((7, 7))
    heights[2:5, 2:5] = np.nan
    grid = SupportGrid(0.0, 0.0, 0.1, heights)
    filtered = filter_support(grid, 15.0, 0.2)
    mesh = triangulate_support(grid, filtered)

    assert np.isnan(grid.heights_m[2:5, 2:5]).all()
    assert not filtered.supported[2:5, 2:5].any()
    assert mesh.triangles.shape == (40, 3)
    for triangle in mesh.vertices[mesh.triangles]:
        assert np.ptp(triangle[:, 0]) <= grid.spacing_m + 1e-9


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda data: data["ply_to_world"].update(metres_per_unit=1.0),
            "scale disagrees",
        ),
        (lambda data: data["ply_to_world"].update(up_axis="y"), "does not map"),
    ],
)
def test_wrong_scale_or_axis_is_rejected(change, message):
    data = alignment_manifest()
    change(data)

    with pytest.raises(SupportGridError, match=message):
        validate_alignment_manifest(data, "corridor_splat")


def test_unknown_values_must_be_nan_not_infinity():
    with pytest.raises(SupportGridError, match="infinity"):
        SupportGrid(0.0, 0.0, 0.1, np.array([[0.0, np.inf], [0.0, 0.0]]))
