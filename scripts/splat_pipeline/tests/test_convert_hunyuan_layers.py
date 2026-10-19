import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from convert_hunyuan_layers import convert_layers, load_triangle_mesh


def write_layer(path: Path, x_offset: float) -> None:
    mesh = trimesh.Trimesh(
        vertices=np.array([[x_offset, 0, 0], [x_offset + 1, 0, 0], [x_offset, 1, 0]]),
        faces=np.array([[0, 1, 2]]),
        vertex_colors=np.array([[255, 0, 0, 255], [0, 255, 0, 255], [0, 0, 255, 255]]),
        process=False,
    )
    mesh.export(path)


def test_converts_named_layers_and_preserves_vertex_colors(tmp_path):
    first = tmp_path / "mesh_layer0.ply"
    second = tmp_path / "mesh_layer1.ply"
    write_layer(first, 0.0)
    write_layer(second, 2.0)
    output = tmp_path / "layers.glb"
    report = tmp_path / "layers.json"

    metadata = convert_layers([first, second], output, report)
    imported = trimesh.load(output, force="scene")
    assert output.is_file()
    assert report.is_file()
    assert [layer["name"] for layer in metadata["layers"]] == ["mesh_layer0", "mesh_layer1"]
    assert set(imported.geometry) == {"mesh_layer0", "mesh_layer1"}
    assert all(len(mesh.faces) == 1 for mesh in imported.geometry.values())
    assert all(mesh.visual.kind == "vertex" for mesh in imported.geometry.values())


def test_rejects_empty_or_invalid_ply_layer(tmp_path):
    path = tmp_path / "empty.ply"
    path.write_text("not a PLY", encoding="utf-8")
    with pytest.raises(ValueError, match="could not parse"):
        load_triangle_mesh(path)


def test_refuses_to_overwrite_previous_conversion(tmp_path):
    layer = tmp_path / "mesh_layer0.ply"
    write_layer(layer, 0.0)
    output = tmp_path / "layers.glb"
    output.write_bytes(b"previous")
    with pytest.raises(FileExistsError):
        convert_layers([layer], output, tmp_path / "layers.json")
