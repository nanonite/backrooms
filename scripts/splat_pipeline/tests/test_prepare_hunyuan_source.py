import math

import numpy as np
import pytest

from hunyuan_source import camera_orientation_world, fov_degrees, focal_lengths
from colmap_model import Camera


def test_fov_degrees_uses_pinhole_geometry():
    assert fov_degrees(1920, 1230.189175616024) == pytest.approx(75.93466005)


@pytest.mark.parametrize("sensor_pixels,focal_pixels", [(0, 100.0), (100, 0.0), (100, math.inf)])
def test_fov_degrees_rejects_invalid_dimensions(sensor_pixels, focal_pixels):
    with pytest.raises(ValueError, match="positive and finite"):
        fov_degrees(sensor_pixels, focal_pixels)


def test_simple_radial_camera_uses_one_focal_length_for_both_axes():
    camera = Camera(1, "SIMPLE_RADIAL", 1920, 1080, (1230.0, 960.0, 540.0, -0.07))
    assert focal_lengths(camera) == (1230.0, 1230.0)


def test_pinhole_camera_uses_separate_focal_lengths():
    camera = Camera(1, "PINHOLE", 1920, 1080, (1200.0, 1210.0, 960.0, 540.0))
    assert focal_lengths(camera) == (1200.0, 1210.0)


def test_unknown_camera_model_is_rejected():
    camera = Camera(1, "RADIAL", 1920, 1080, (1230.0, 960.0, 540.0, -0.07, 0.01))
    with pytest.raises(ValueError, match="unsupported COLMAP camera model"):
        focal_lengths(camera)


def test_camera_orientation_maps_registered_forward_and_up_vectors():
    class Mapping:
        @staticmethod
        def world_vector(vector):
            return vector

    class Contract:
        ply_to_world = Mapping()

    class Image:
        rotation_w2c = np.eye(3)

    forward, up = camera_orientation_world(
        Image(), Contract(), {"rotation": np.eye(3), "scale": 1.0}
    )
    assert forward.tolist() == [0.0, 0.0, 1.0]
    assert up.tolist() == [0.0, -1.0, 0.0]
