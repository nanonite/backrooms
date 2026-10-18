"""Focused safety tests for the evidence-only Hunyuan band filtering."""

from __future__ import annotations

import numpy as np
from hunyuan_band import (
    MAX_SLOPE_DEGREES,
    MAX_STEP_METRES,
    component_records,
    filter_safe_faces,
    panorama_vertex_selection,
    point_triangle_distance_2d,
    select_original_faces,
    triangle_metrics,
)


def test_panorama_selection_uses_v_band_and_forward_yaw() -> None:
    width, height = 2, 101
    local_x = np.full(width * height, -1.0)
    local_y = np.zeros(width * height)
    local_y[60 * width] = np.tan(np.deg2rad(36.0))

    selected = panorama_vertex_selection(local_x, local_y, height, width)

    assert selected.reshape(height, width)[56].sum() == 0
    assert selected.reshape(height, width)[60].tolist() == [False, True]
    assert selected.reshape(height, width)[63].sum() == 0


def test_foreground_mask_preserves_holes_and_excludes_added_faces() -> None:
    records = np.array(
        [(3, 0, 1, 2), (3, 1, 3, 2), (3, 0, 2, 4)],
        dtype=[("count", "u1"), ("a", "<u4"), ("b", "<u4"), ("c", "<u4")],
    )
    in_crop = np.ones(5, dtype=bool)
    foreground = np.array([False, False, True, False, False])

    faces, counts = select_original_faces(
        records, in_crop, foreground, triangle_limit=2, chunk_size=1
    )

    assert faces.shape == (0, 3)
    assert counts["foreground_mask_triangles_omitted"] == 2
    assert counts["triangles_after_crop_and_mask"] == 0


def test_flat_and_gentle_slope_pass_geometry_gate() -> None:
    flat = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1]], dtype=float)
    gentle = np.array([[0, 0, 0], [1, 0.1, 0], [0, 0, 1]], dtype=float)
    face = np.array([[0, 1, 2]])

    flat_metrics = triangle_metrics(flat, face)
    slope_metrics = triangle_metrics(gentle, face)

    assert filter_safe_faces(flat_metrics).tolist() == [True]
    assert filter_safe_faces(slope_metrics).tolist() == [True]
    assert slope_metrics["slope_degrees"][0] <= MAX_SLOPE_DEGREES


def test_steep_slope_is_rejected() -> None:
    points = np.array([[0, 0, 0], [1, 1, 0], [0, 0, 1]], dtype=float)
    metrics = triangle_metrics(points, np.array([[0, 1, 2]]))

    assert metrics["slope_degrees"][0] > MAX_SLOPE_DEGREES
    assert filter_safe_faces(metrics).tolist() == [False]


def test_large_vertical_step_is_rejected() -> None:
    points = np.array([[0, 0, 0], [1, 0.21, 0], [0, 0, 1]], dtype=float)
    metrics = triangle_metrics(points, np.array([[0, 1, 2]]))

    assert metrics["max_edge_vertical_step_m"][0] > MAX_STEP_METRES
    assert filter_safe_faces(metrics).tolist() == [False]


def test_zero_area_triangle_is_rejected() -> None:
    points = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)
    metrics = triangle_metrics(points, np.array([[0, 1, 2]]))

    assert metrics["area_m2"][0] == 0.0
    assert filter_safe_faces(metrics).tolist() == [False]


def test_projected_triangle_distance_and_large_hole_remain_unsupported() -> None:
    triangle = np.array([[[0, 0], [1, 0], [0, 1]]], dtype=float)
    query = np.array([[0.2, 0.2], [2.0, 2.0]])
    distances = point_triangle_distance_2d(query, triangle)

    assert distances.shape == (2, 1)
    assert distances[0, 0] == 0.0
    assert distances[1, 0] > 1.0


def test_disconnected_patch_components_are_reported_separately() -> None:
    faces = np.array([[0, 1, 2], [3, 4, 5]])

    components = component_records(faces, np.array([0.5, 2.0]))

    assert len(components) == 2
    assert components[0]["triangle_count"] == 1
    assert components[0]["area_m2"] == 2.0


def test_components_require_shared_edge_not_only_shared_vertex() -> None:
    faces = np.array([[0, 1, 2], [0, 3, 4], [1, 0, 5]])

    components = component_records(faces, np.ones(3))

    assert len(components) == 2
    assert sorted(component["triangle_count"] for component in components) == [1, 2]
