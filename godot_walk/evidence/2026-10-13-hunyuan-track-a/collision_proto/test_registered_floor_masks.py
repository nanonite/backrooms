"""Focused CPU tests for candidate source-image floor support."""

from __future__ import annotations

import struct
from types import SimpleNamespace

import numpy as np
import pytest
from build_registered_floor_masks import decode_point2d_records
from build_registered_floor_masks_all_frames import (
    accumulate_frame_hits,
    grid_from_counts,
)
from registered_floor_masks import (
    FrameContext,
    candidate_band_pixels,
    candidate_mask,
    floor_intersections,
    insert_unknown_hole,
    mask_pixels,
    path_gap_summary,
    undistort_simple_radial,
)
from source_support import SupportGrid, SupportGridError, validate_alignment_manifest


def alignment_manifest() -> dict:
    """Return the checked #100 z-up to Godot y-up transform convention."""
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


def test_candidate_mask_is_exact_bottom_band_and_overlay_sampling_uses_centres():
    mask = candidate_mask(5, 7, top_row=4)

    assert mask.sum() == 15
    assert not mask[:4].any()
    assert mask[4:].all()
    assert np.all(mask_pixels(mask, stride=2)[:, 1] >= 4.0)


def test_streamed_candidate_pixel_rule_matches_full_crop_mask():
    mask = candidate_mask(20, 30, top_row=19)

    np.testing.assert_array_equal(
        candidate_band_pixels(20, 30, top_row=19, stride=4),
        mask_pixels(mask, stride=4),
    )


def test_path_gap_summary_reports_contiguous_unsupported_intervals():
    summary = path_gap_summary(
        np.array([0.1, 0.5, 1.2, 0.2, 1.1]),
        np.array([0.1, 0.2, 0.3, 0.4, 0.5]),
        radius_m=0.3,
    )

    assert summary["unsupported_segment_count"] == 3
    assert summary["unsupported_gap_count"] == 2
    assert summary["longest_unsupported_segment_run_count"] == 2
    assert summary["unsupported_segment_path_length_m"] == pytest.approx(1.0)
    assert summary["longest_consecutive_gap_m"] == pytest.approx(0.5)
    assert [item["segment_count"] for item in summary["unsupported_segment_runs"]] == [
        2,
        1,
    ]


def test_streaming_cell_accumulator_keeps_unknown_cells_empty():
    counts = {}
    points = np.array([[0.01, -1.0, 0.01], [0.02, -1.0, 0.02], [0.06, -1.0, 0.01]])

    hit_count, frame_cells = accumulate_frame_hits(counts, points, spacing_m=0.05)
    grid, hit_grid = grid_from_counts(
        counts, np.array([[0.0, 1.0, 0.0]]), floor_height_m=-1.27
    )

    assert hit_count == 3
    assert frame_cells == 2
    assert grid.observed.sum() == 2
    assert hit_grid.sum() == 3
    assert np.isnan(grid.heights_m[~grid.observed]).all()


def test_simple_radial_inverse_recovers_distorted_pixel_rays():
    original = np.array([[0.1, -0.2], [-0.4, 0.3], [0.0, 0.0]])
    radius_squared = np.sum(original**2, axis=1)
    distorted = original * (1.0 - 0.07134 * radius_squared[:, None])
    pixels = distorted * 1200.0 + np.array([960.0, 540.0])

    recovered = undistort_simple_radial(pixels, 1200.0, 960.0, 540.0, -0.07134)

    np.testing.assert_allclose(recovered, original, atol=1e-10)


def test_colmap_image_observation_ids_remain_signed_in_binary_decode():
    payload = struct.pack("<ddqddq", 10.5, 20.5, 14321, 30.0, 40.0, -1)

    pixels, point_ids = decode_point2d_records(payload)

    np.testing.assert_array_equal(pixels, [[10.5, 20.5], [30.0, 40.0]])
    np.testing.assert_array_equal(point_ids, [14321, -1])


def test_ray_mapping_respects_image_down_and_intersects_declared_floor():
    rotation = np.diag([-1.0, -1.0, 1.0])
    mapping = SimpleNamespace(
        rotation=lambda: rotation,
        metres_per_unit=1.0,
        world_point=lambda point: rotation @ np.asarray(point),
    )
    image = SimpleNamespace(
        camera_center=np.array([0.0, -1.0, 0.0]),
        rotation_w2c=np.eye(3),
    )
    camera = SimpleNamespace(model="SIMPLE_RADIAL", params=(100.0, 50.0, 50.0, 0.0))
    context = FrameContext(image=image, camera=camera)

    points, record = floor_intersections(
        np.array([[50.0, 100.0]]),
        context,
        {"rotation": np.eye(3), "origin": np.zeros(3), "scale": 1.0},
        mapping,
        0.0,
    )

    assert record["forward_floor_intersections"] == 1
    np.testing.assert_allclose(points[0], [0.0, 0.0, 2.0], atol=1e-12)
    assert record["max_abs_floor_residual_m"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda data: data["ply_to_world"].update(metres_per_unit=10.0),
            "scale disagrees",
        ),
        (lambda data: data["ply_to_world"].update(up_axis="x"), "does not map"),
    ],
)
def test_wrong_scale_and_wrong_axis_are_rejected(change, message):
    data = alignment_manifest()
    change(data)

    with pytest.raises(SupportGridError, match=message):
        validate_alignment_manifest(data, "corridor_splat")


def test_inserted_hole_remains_unknown_and_is_not_interpolated():
    grid = SupportGrid(0.0, 0.0, 0.05, np.zeros((20, 20)))

    hole = insert_unknown_hole(grid, np.array([0.5, 0.5]), 0.30)

    assert np.isnan(hole.heights_m[9:12, 9:12]).all()
    assert np.isfinite(grid.heights_m).all()
    assert np.isnan(hole.heights_m).sum() > 100
