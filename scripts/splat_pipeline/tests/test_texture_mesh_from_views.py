"""Tests for projected texture selection and OBJ material export."""

import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from texture_mesh_from_views import (
    CameraView,
    assign_views,
    make_raycast_scene,
    source_to_y_up,
    write_textured_obj,
)


class _PinholeCamera:
    width = 100
    height = 100

    def img_from_cam(self, points):
        points = np.asarray(points)
        return np.column_stack(
            (50.0 + 25.0 * points[:, 0] / points[:, 2],
             50.0 + 25.0 * points[:, 1] / points[:, 2])
        )


def _view(image_path: Path) -> CameraView:
    rotation = np.diag([1.0, -1.0, -1.0])
    center = np.array([0.0, 0.0, 1.0])
    return CameraView(
        "frame_0001.jpg",
        image_path,
        _PinholeCamera(),
        rotation,
        -rotation @ center,
        center,
    )


def _triangle_mesh() -> trimesh.Trimesh:
    vertices = np.array([[-0.4, -0.4, 0.0], [0.4, -0.4, 0.0], [0.0, 0.4, 0.0]])
    return trimesh.Trimesh(vertices=vertices, faces=np.array([[0, 1, 2]]), process=False)


def test_assign_views_projects_visible_triangle_to_image_pixels(tmp_path):
    mesh = _triangle_mesh()
    views = [_view(tmp_path / "frame_0001.jpg")]

    assignments, uv_coordinates = assign_views(mesh, views, make_raycast_scene(mesh))

    assert assignments.tolist() == [0]
    np.testing.assert_allclose(
        uv_coordinates[0],
        np.array([[0.4, 0.4], [0.6, 0.4], [0.5, 0.6]]),
        atol=1e-6,
    )


def test_source_up_rotation_maps_registered_camera_up_to_y(tmp_path):
    source_up, rotation, coherence = source_to_y_up([_view(tmp_path / "frame.jpg")])

    np.testing.assert_allclose(source_up, [0.0, 1.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(rotation @ source_up, [0.0, 1.0, 0.0], atol=1e-6)
    assert coherence == 1.0


def test_obj_export_keeps_only_assigned_faces_and_writes_view_materials(tmp_path):
    mesh = trimesh.Trimesh(
        vertices=np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [2, 0, 0], [2, 1, 0]],
            dtype=float,
        ),
        faces=np.array([[0, 1, 2], [1, 3, 2], [1, 4, 3]]),
        process=False,
    )
    image = tmp_path / "dense/images/frame_0001.jpg"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (200, 100), color=(128, 144, 96)).save(image)
    views = [_view(image)]
    source_rotation = np.array(
        [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]
    )
    uv_coordinates = np.zeros((3, 3, 2), dtype=np.float32)
    uv_coordinates[0] = [[0.1, 0.2], [0.3, 0.2], [0.2, 0.4]]

    covered, face_counts = write_textured_obj(
        tmp_path / "textured_mesh", mesh, views, np.array([0, -1, -1]),
        uv_coordinates, source_rotation,
    )

    obj_text = (tmp_path / "textured_mesh/mesh.obj").read_text(encoding="utf-8")
    material_text = (tmp_path / "textured_mesh/mesh.mtl").read_text(encoding="utf-8")
    assert covered == 1
    assert face_counts == {0: 1}
    assert obj_text.count("\nf ") == 1
    assert "vt 0.1000000 0.2000000" in obj_text
    assert "v 0.0000000 0.0000000 1.0000000" in obj_text
    assert "map_Kd images/view_000.jpg" in material_text
    assert (tmp_path / "textured_mesh/images/view_000.jpg").is_file()
