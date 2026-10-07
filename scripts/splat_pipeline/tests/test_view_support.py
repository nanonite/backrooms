#!/usr/bin/env python3
"""Tests for multi-view support counting (#103).

Two things are checked, because both can silently delete half a room:

* the projection maths -- inside/outside the image, in front of / behind the
  camera, the near plane, the far plane, and the two COLMAP camera models this
  capture uses;
* the coordinate chain -- ``world_to_colmap`` must be the exact inverse of the
  path ``measure_splat_frame`` used when the contract was built, and
  ``verify_camera_bound`` must fail loudly when it is not, so a wrong rotation
  cannot be mistaken for "this asset was never observed".

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_view_support.py -v
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import splat_frame
import view_support
from view_support import camera_centres_world, count_views, verify_camera_bound, world_to_colmap


def make_mapping() -> splat_frame.PlyToWorld:
    """A contract mapping with a real rotation, scale and centroid."""
    return splat_frame.PlyToWorld(
        basis_columns=((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        metres_per_unit=5.128,
        origin_ply_units=(0.7, -0.2, 0.1),
        frame_name="test",
        up_axis="z",
        up_sign=1,
        handedness="right",
    )


def make_dataparser() -> dict:
    """A nerfstudio-style similarity with a quarter turn about z."""
    rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    return {"rotation": rotation, "origin": np.array([0.3, -0.4, 0.9]), "scale": 0.25}


def make_image(centre: np.ndarray, rotation_w2c: np.ndarray | None = None) -> SimpleNamespace:
    """A camera at ``centre`` looking down +z with the identity rotation."""
    rotation = np.eye(3) if rotation_w2c is None else rotation_w2c
    translation = -rotation @ np.asarray(centre, dtype=np.float64)
    return SimpleNamespace(
        camera_center=np.asarray(centre, dtype=np.float64),
        rotation_w2c=rotation,
        translation_w2c=translation,
        camera_id=1,
    )


def make_camera(model: str = "PINHOLE") -> SimpleNamespace:
    """A 100x100 image with a 100 px focal length (90 degree horizontal FOV).

    ``PINHOLE`` is ``(fx, fy, cx, cy)`` and ``SIMPLE_RADIAL`` is
    ``(f, cx, cy, k1)`` -- COLMAP's two different parameter orders. With
    ``k1 = 0`` the two must project identically, which is the test below.
    """
    params = (100.0, 100.0, 50.0, 50.0) if model == "PINHOLE" else (100.0, 50.0, 50.0, 0.0)
    return SimpleNamespace(model=model, width=100, height=100, params=params)


class TestCountViews:
    def test_point_in_front_of_the_camera_counts_once(self):
        images = [make_image(np.zeros(3))]
        cameras = {1: make_camera()}
        counts = count_views(np.array([[0.0, 0.0, 5.0]]), images, cameras)
        assert counts.tolist() == [1]

    def test_points_behind_the_camera_never_count(self):
        images = [make_image(np.zeros(3))]
        cameras = {1: make_camera()}
        counts = count_views(np.array([[0.0, 0.0, -5.0]]), images, cameras)
        assert counts.tolist() == [0]

    def test_points_outside_the_image_never_count(self):
        images = [make_image(np.zeros(3))]
        cameras = {1: make_camera()}
        # x = 50 at depth 5 projects to pixel 1050 of 100; the axis point is
        # dead centre and must still count.
        counts = count_views(np.array([[50.0, 0.0, 5.0], [0.0, 0.0, 5.0]]), images, cameras)
        assert counts.tolist() == [0, 1]

    def test_the_near_plane_excludes_close_points(self):
        images = [make_image(np.zeros(3))]
        cameras = {1: make_camera()}
        counts = count_views(np.array([[0.0, 0.0, 0.01], [0.0, 0.0, 2.0]]), images, cameras)
        assert counts.tolist() == [0, 1]

    def test_the_far_plane_can_be_enabled(self):
        images = [make_image(np.zeros(3))]
        cameras = {1: make_camera()}
        points = np.array([[0.0, 0.0, 3.0], [0.0, 0.0, 30.0]])
        assert count_views(points, images, cameras).tolist() == [1, 1]
        assert count_views(points, images, cameras, max_depth_m=10.0).tolist() == [1, 0]

    def test_every_camera_that_sees_the_point_is_counted(self):
        images = [make_image(np.array([0.0, 0.0, -5.0])), make_image(np.array([1.0, 0.0, -5.0]))]
        cameras = {1: make_camera()}
        counts = count_views(np.array([[0.0, 0.0, 0.0]]), images, cameras)
        assert counts.tolist() == [2]

    def test_simple_radial_without_distortion_matches_pinhole(self):
        images = [make_image(np.zeros(3))]
        points = np.array([[0.4, -0.3, 4.0]])
        pinhole = count_views(points, images, {1: make_camera("PINHOLE")})
        radial = count_views(points, images, {1: make_camera("SIMPLE_RADIAL")})
        assert pinhole.tolist() == radial.tolist() == [1]

    def test_unsupported_camera_model_fails_loudly(self):
        images = [make_image(np.zeros(3))]
        cameras = {1: SimpleNamespace(model="FOV", width=100, height=100, params=(1.0,) * 4)}
        with pytest.raises(ValueError):
            count_views(np.array([[0.0, 0.0, 1.0]]), images, cameras)

    def test_shape_and_depth_arguments_are_validated(self):
        with pytest.raises(ValueError):
            count_views(np.zeros((2, 2)), [], {})
        with pytest.raises(ValueError):
            count_views(np.zeros((2, 3)), [], {}, min_depth_m=0.0)


class TestCoordinateChain:
    def test_world_to_colmap_inverts_the_contract_path(self):
        mapping = make_mapping()
        dataparser = make_dataparser()
        points_colmap = np.array([[0.2, -0.7, 1.4], [-3.0, 2.0, 0.5], [0.0, 0.0, 0.0]])
        points_ply = (points_colmap @ dataparser["rotation"].T + dataparser["origin"]) * dataparser["scale"]
        points_world = np.stack([mapping.world_point(point) for point in points_ply])
        back = world_to_colmap(points_world, mapping, dataparser)
        assert np.allclose(back, points_colmap, atol=1e-9)

    def test_camera_centres_round_trip_through_world(self):
        mapping = make_mapping()
        dataparser = make_dataparser()
        centres_colmap = np.array([[0.0, 0.0, 0.0], [2.0, -1.0, 0.4]])
        images = [make_image(centre) for centre in centres_colmap]
        centres_world = camera_centres_world(images, dataparser, mapping)
        points_ply = (centres_colmap @ dataparser["rotation"].T + dataparser["origin"]) * dataparser["scale"]
        expected = np.stack([mapping.world_point(point) for point in points_ply])
        assert np.allclose(centres_world, expected)

    def test_bound_check_accepts_the_recorded_bound(self):
        centres = np.array([[0.0, 0.0, 0.0], [2.0, 1.0, 3.0]])
        contract = SimpleNamespace(world_min=(0.0, 0.0, 0.0), world_max=(2.0, 1.0, 3.0))
        verify_camera_bound(centres, contract, tolerance_m=0.01)

    def test_bound_check_rejects_a_different_chain(self):
        centres = np.array([[0.0, 0.0, 0.0], [2.0, 1.0, 3.0]])
        contract = SimpleNamespace(world_min=(0.0, 0.0, 0.0), world_max=(2.0, 1.0, 9.0))
        with pytest.raises(ValueError):
            verify_camera_bound(centres, contract, tolerance_m=0.01)

    def test_shape_is_validated(self):
        with pytest.raises(ValueError):
            world_to_colmap(np.zeros((2, 2)), make_mapping(), make_dataparser())
