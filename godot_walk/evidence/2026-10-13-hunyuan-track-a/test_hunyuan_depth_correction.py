"""Tests for the locked six-term visual depth correction model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hunyuan_depth_correction_model import fit_scale_field, scale_design


class ScaleFieldTests(unittest.TestCase):
    def test_recovers_known_global_scale_and_smooth_band_distortion(self) -> None:
        elevations, depths = np.meshgrid(
            np.linspace(-0.7, 0.7, 20), np.geomspace(1.5, 18.0, 25), indexing="ij"
        )
        elevation = elevations.ravel()
        depth = depths.ravel()
        elevation_z = (elevation - elevation.mean()) / elevation.std()
        log_depth = np.log(depth)
        depth_z = (log_depth - log_depth.mean()) / log_depth.std()
        known_coefficients = np.array([1.42, 0.075, -0.04, 0.025, 0.018, 0.012])
        known_scale = np.exp(scale_design(elevation_z, depth_z) @ known_coefficients)

        field = fit_scale_field(elevation, depth, known_scale)
        recovered = field.predict(elevation, depth)

        self.assertEqual(len(field.coefficients), 6)
        self.assertGreater(float(np.min(recovered)), 0.0)
        np.testing.assert_allclose(recovered, known_scale, atol=1e-9, rtol=1e-9)

    def test_rejects_invalid_depths_and_nonpositive_scales(self) -> None:
        elevation = np.linspace(-0.5, 0.5, 12)
        depth = np.linspace(1.0, 4.0, 12)
        scale = np.full(12, 1.4)
        with self.assertRaisesRegex(ValueError, "no variation"):
            fit_scale_field(np.zeros(12), depth, scale)
        with self.assertRaisesRegex(ValueError, "positive"):
            fit_scale_field(elevation, depth, np.zeros(12))


if __name__ == "__main__":
    unittest.main()
