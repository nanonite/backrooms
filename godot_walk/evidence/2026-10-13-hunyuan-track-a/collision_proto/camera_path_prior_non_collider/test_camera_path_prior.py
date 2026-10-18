from __future__ import annotations

import numpy as np
import pytest
from camera_path_prior import (
    CameraPathPriorError,
    component_count,
    erase_hole,
    nearest_distances,
    rasterize_strip,
)


def route_grid(width: float) -> tuple[np.ndarray, tuple[float, float]]:
    path = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
    spacing = 0.05
    origin = (-0.5, -0.5)
    grid = rasterize_strip(path, spacing, width, origin, (40, 40))
    return grid, origin


def test_width_hypotheses_grow_monotonically_and_leave_off_route_unknown():
    grids = [route_grid(width)[0] for width in (0.8, 1.2, 1.6)]

    assert grids[0].sum() < grids[1].sum() < grids[2].sum()
    assert not grids[0][0, 0]
    assert component_count(grids[0]) == 1


def test_centerline_camera_and_segment_midpoint_samples_are_supported():
    grid, origin = route_grid(0.8)
    points = np.array([[0.0, 0.0], [0.5, 0.0], [1.0, 0.5], [1.0, 1.0]])

    distances = nearest_distances(grid, points, origin, 0.05)

    assert np.all(distances <= 0.05)


def test_hole_removes_support_without_mutating_source_or_filling_neighbours():
    grid, origin = route_grid(0.8)
    hole = erase_hole(grid, origin, 0.05, (0.5, 0.0), 0.55)
    distances = nearest_distances(hole, np.array([[0.5, 0.0]]), origin, 0.05)

    assert grid.any()
    assert np.isinf(distances[0]) or distances[0] > 0.30
    assert hole.sum() < grid.sum()


def test_wrong_axis_and_scale_controls_do_not_reuse_correct_registration():
    grid, origin = route_grid(0.8)
    correct_path = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
    wrong_axis_path = correct_path[:, ::-1] + [4.0, -4.0]
    wrong_scale_path = 2.0 * correct_path + [4.0, 4.0]

    for wrong_path in (wrong_axis_path, wrong_scale_path):
        distances = nearest_distances(grid, wrong_path, origin, 0.05)
        assert np.all(distances > 0.30)


@pytest.mark.parametrize(
    "path,width,spacing,shape",
    [
        (np.array([[0.0, 0.0]]), 0.8, 0.05, (4, 4)),
        (np.array([[0.0, 0.0], [0.0, 0.0]]), 0.8, 0.05, (4, 4)),
        (np.array([[0.0, 0.0], [1.0, 0.0]]), 0.0, 0.05, (4, 4)),
    ],
)
def test_invalid_path_and_grid_inputs_are_rejected(path, width, spacing, shape):
    with pytest.raises(CameraPathPriorError):
        rasterize_strip(path, spacing, width, (-1.0, -1.0), shape)
