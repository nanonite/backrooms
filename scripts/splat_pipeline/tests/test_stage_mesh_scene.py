"""Tests for the separate Godot photogrammetry scene template."""

import sys
from pathlib import Path

import numpy as np
import trimesh

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from stage_mesh_scene import floor_support, scene_source


def test_mesh_scene_uses_textured_asset_for_rendering_and_collision():
    scene = scene_source("backrooms_mesh_v1", "Transform3D.IDENTITY")

    assert 'path="res://generated_mesh_scenes/backrooms_mesh_v1/scene.glb"' in scene
    assert 'mesh_path = "res://generated_mesh_scenes/backrooms_mesh_v1/scene.glb"' in scene
    assert "psx_post_effect.gd" in scene
    assert "gaussian_splat_node.gd" not in scene


def test_non_walkable_result_does_not_spawn_a_player():
    scene = scene_source("backrooms_mesh_v1", None)

    assert '[node name="GeneratedCollision" type="StaticBody3D"' in scene
    assert '[node name="PlayerSpawn"' not in scene
    assert '[node name="Player" parent="."' not in scene


def test_walkability_requires_floor_beneath_capture_path():
    floor = trimesh.Trimesh(
        vertices=np.array([[-1, 0, -1], [1, 0, -1], [1, 0, 1], [-1, 0, 1]]),
        faces=np.array([[0, 2, 1], [0, 3, 2]]),
        process=False,
    )
    cameras = {
        "frame_0001.jpg": {"position": np.array([0.0, 0.6, 0.0])},
    }

    report = floor_support(floor, cameras)

    assert report["walkable"]
    assert report["camera_path_floor_hits"] == 1


def test_horizontal_geometry_away_from_capture_path_is_not_walkable():
    floor = trimesh.Trimesh(
        vertices=np.array([[2, 0, -1], [4, 0, -1], [4, 0, 1], [2, 0, 1]]),
        faces=np.array([[0, 2, 1], [0, 3, 2]]),
        process=False,
    )
    cameras = {
        "frame_0001.jpg": {"position": np.array([0.0, 0.6, 0.0])},
    }

    report = floor_support(floor, cameras)

    assert report["low_horizontal_support_area_m2"] >= 0.81
    assert report["camera_path_floor_hits"] == 0
    assert not report["walkable"]
