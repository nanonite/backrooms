"""Tests for the locked six-term visual depth correction model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hunyuan_depth_correction_model import fit_scale_field, scale_design
from hunyuan_depth_correction_mesh import FACE_DTYPE, MeshGrid, _feather_region, mesh_quality
from hunyuan_depth_correction_evaluate import (
    REPO_ROOT,
    _corrected_mesh_path,
    _resolve_repo_path,
)


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

    def test_prediction_clamps_elevation_and_log_depth_to_fit_domain(self) -> None:
        elevation = np.linspace(-0.5, 0.5, 20)
        depth = np.geomspace(1.0, 8.0, 20)
        scale = np.exp(0.2 + 0.1 * elevation - 0.03 * np.log(depth))
        field = fit_scale_field(elevation, depth, scale)

        outside_elevation = field.elevation_mean + (field.elevation_bounds[1] + 2.0) * field.elevation_scale
        outside_depth = np.exp(field.log_depth_mean + (field.log_depth_bounds[0] - 3.0) * field.log_depth_scale)
        boundary_elevation = field.elevation_mean + field.elevation_bounds[1] * field.elevation_scale
        boundary_depth = np.exp(field.log_depth_mean + field.log_depth_bounds[0] * field.log_depth_scale)

        outside_prediction = field.predict(np.array([outside_elevation]), np.array([outside_depth]))
        boundary_prediction = field.predict(np.array([boundary_elevation]), np.array([boundary_depth]))
        np.testing.assert_array_equal(outside_prediction, boundary_prediction)

    def test_snap_feather_reaches_wall_field_at_region_boundary(self) -> None:
        region = np.zeros((9, 9), dtype=bool)
        region[2:7, 2:7] = True
        weights = _feather_region(region, 2.0)

        self.assertEqual(float(weights[0, 0]), 0.0)
        self.assertGreater(float(weights[2, 4]), 0.0)
        self.assertLess(float(weights[2, 4]), 1.0)
        self.assertEqual(float(weights[4, 4]), 1.0)

    def test_mesh_quality_rejects_flipped_triangle(self) -> None:
        faces = np.zeros(1, dtype=FACE_DTYPE)
        faces["count"] = 3
        faces["indices"] = [[0, 1, 2]]
        mesh = MeshGrid(Path("synthetic"), 3, 1, None, faces, 0, 1)
        source = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        flipped = np.array([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])

        report = mesh_quality(mesh, source, flipped, None, 44829)

        self.assertEqual(report["flipped_face_count"], 1)
        self.assertFalse(report["mesh_quality_pass"])


class EvaluatorPathTests(unittest.TestCase):
    def test_relative_paths_resolve_from_repository_root(self) -> None:
        self.assertEqual(
            _resolve_repo_path(Path("data/mesh.ply")),
            REPO_ROOT / "data/mesh.ply",
        )

    def test_each_method_gets_a_distinct_mesh_path(self) -> None:
        output = Path("experimental")
        smooth = _corrected_mesh_path(output, "frame_0152", "smooth_field_refit")
        transfer = _corrected_mesh_path(
            output, "frame_0152", "smooth_field_coefficient_transfer"
        )

        self.assertNotEqual(smooth, transfer)


if __name__ == "__main__":
    unittest.main()
