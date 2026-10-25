from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from issue160_glb import (  # noqa: E402
    FLOOR_Y,
    clip_layer,
    points_inside_room,
    points_in_c02_mask,
    read_glb,
    write_bounded_glb,
    accessor_array,
)


class Issue160GlbTests(unittest.TestCase):
    def test_authored_polygon_and_vertical_bounds_are_enforced(self) -> None:
        points = np.array(
            [
                [-4.0, FLOOR_Y, 0.0],
                [0.0, FLOOR_Y + 2.4, 1.2],
                [4.0, 0.0, 2.0],
                [0.0, FLOOR_Y - 0.1, 1.0],
            ]
        )
        self.assertEqual(points_inside_room(points).tolist(), [True, True, False, False])

    def test_clipping_retains_only_complete_inside_triangles(self) -> None:
        center = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0],
                           [0.0, 0.0, 0.1]], dtype=np.float32)
        outside = np.array([[10.0, 0.0, 0.0], [10.2, 0.0, 0.0],
                            [10.0, 0.0, 0.2]], dtype=np.float32)
        positions = np.concatenate([center, outside])
        colors = np.full((6, 4), 255, dtype=np.uint8)
        indices = np.array([0, 1, 2, 3, 4, 5], dtype=np.uint32)
        clipped_positions, clipped_colors, clipped_indices, source_count, masked_count = clip_layer(
            positions, colors, indices
        )
        self.assertEqual(source_count, 2)
        self.assertEqual(masked_count, 0)
        self.assertEqual(clipped_indices.size, 3)
        self.assertEqual(len(clipped_positions), 3)
        self.assertEqual(clipped_colors.shape, (3, 4))
        self.assertTrue(points_inside_room(clipped_positions).all())
        c02 = np.array([[-0.7, 0.0, 4.4], [-2.0, 0.0, 4.4]])
        self.assertEqual(points_in_c02_mask(c02).tolist(), [True, False])

    def test_written_derivative_round_trips_as_glb(self) -> None:
        positions = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0],
                              [0.0, 0.0, 0.1]], dtype="<f4")
        colors = np.full((3, 4), 127, dtype=np.uint8)
        indices = np.array([0, 1, 2], dtype="<u4")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded.glb"
            write_bounded_glb([(positions, colors, indices)] * 2, path)
            parsed = read_glb(path)
            self.assertEqual(parsed.document["asset"]["version"], "2.0")
            self.assertEqual(len(parsed.document["meshes"]), 2)
            actual = accessor_array(parsed, 0)
            np.testing.assert_allclose(actual, positions)


if __name__ == "__main__":
    unittest.main()
