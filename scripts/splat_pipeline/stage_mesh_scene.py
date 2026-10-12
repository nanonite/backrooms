#!/usr/bin/env python3
"""Stage a textured mesh GLB as a separate Godot visual-and-collision scene."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path

import numpy as np
import open3d as o3d
import pycolmap
import trimesh

MIN_WALKABLE_FLOOR_AREA_M2 = 0.81
FLOOR_NORMAL_Y_MINIMUM = 0.8
FLOOR_HEIGHT_FRACTION = 0.35


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir", required=True, type=Path)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--scene-name")
    args = parser.parse_args()
    args.scene_name = args.scene_name or args.scene_dir.name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.scene_name):
        parser.error("scene name may contain only letters, digits, underscores, and hyphens")
    return args


def scene_scale(scene_dir: Path) -> float:
    transform_path = scene_dir / "scene_transform.txt"
    for line in transform_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("scale:"):
            scale = float(line.split(":", 1)[1].strip())
            if math.isfinite(scale) and scale > 0.0:
                return scale
    raise ValueError(f"no positive scale found in {transform_path}")


def capture_cameras(scene_dir: Path, rotation: np.ndarray, scale: float) -> dict:
    report_path = scene_dir / "textured_mesh/texture_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    face_counts = report.get("faces_per_view", {})
    if not face_counts:
        raise ValueError(f"no selected source views in {report_path}")
    reconstruction = pycolmap.Reconstruction(str(scene_dir / "dense/sparse"))
    cameras = {}
    for image in reconstruction.images.values():
        world_to_camera = np.asarray(image.cam_from_world.rotation.matrix(), dtype=np.float64)
        center_world = -world_to_camera.T @ np.asarray(image.cam_from_world.translation)
        forward_world = world_to_camera.T @ np.array([0.0, 0.0, 1.0])
        position = rotation @ center_world * scale
        forward = rotation @ forward_world
        forward /= np.linalg.norm(forward)
        cameras[image.name] = {
            "position": position,
            "forward": forward,
            "yaw": math.atan2(-float(forward[0]), -float(forward[2])),
        }
    missing_views = set(face_counts) - set(cameras)
    if missing_views:
        raise ValueError(f"textured views absent from dense reconstruction: {sorted(missing_views)}")
    return cameras


def player_transform(position: np.ndarray, yaw: float, floor_y: float) -> str:
    spawn_y = floor_y + 0.61
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    return (
        "Transform3D(%.8f, 0.0, %.8f, 0.0, 1.0, 0.0, "
        "%.8f, 0.0, %.8f, %.8f, %.8f, %.8f)"
        % (cosine, sine, -sine, cosine, position[0], spawn_y, position[2])
    )


def floor_support(mesh: trimesh.Trimesh, cameras: dict) -> dict:
    centers = np.asarray(mesh.triangles_center)
    normals = np.asarray(mesh.face_normals)
    height = float(mesh.bounds[1, 1] - mesh.bounds[0, 1])
    floor_ceiling = float(mesh.bounds[0, 1] + height * FLOOR_HEIGHT_FRACTION)
    candidate = (centers[:, 1] <= floor_ceiling) & (
        np.abs(normals[:, 1]) >= FLOOR_NORMAL_Y_MINIMUM
    )
    area = float(np.asarray(mesh.area_faces)[candidate].sum())
    path_floor_hits = camera_path_floor_hits(mesh, cameras, floor_ceiling)
    path_fraction = len(path_floor_hits) / max(len(cameras), 1)
    walkable = area >= MIN_WALKABLE_FLOOR_AREA_M2 and path_fraction >= 0.75
    return {
        "walkable": walkable,
        "low_horizontal_support_area_m2": area,
        "required_floor_area_m2": MIN_WALKABLE_FLOOR_AREA_M2,
        "floor_search_height_fraction": FLOOR_HEIGHT_FRACTION,
        "low_horizontal_faces": int(candidate.sum()),
        "camera_path_floor_hits": len(path_floor_hits),
        "camera_path_poses": len(cameras),
        "camera_path_floor_fraction": path_fraction,
        "floor_height_by_view": path_floor_hits,
        "camera_path_positions": {
            name: pose["position"].tolist() for name, pose in cameras.items()
        },
        "synthetic_completion": False,
        "assessment": (
            "sufficient low horizontal support along the capture path"
            if walkable
            else "no collision floor under at least 75% of capture poses; no player staged"
        ),
    }


def camera_path_floor_hits(mesh: trimesh.Trimesh, cameras: dict, floor_ceiling: float) -> dict:
    legacy = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(np.asarray(mesh.vertices, dtype=np.float64)),
        o3d.utility.Vector3iVector(np.asarray(mesh.faces, dtype=np.int32)),
    )
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))
    bounds = mesh.bounds
    origins = np.array(
        [[pose["position"][0], bounds[1, 1] + 0.1, pose["position"][2]] for pose in cameras.values()],
        dtype=np.float32,
    )
    directions = np.tile(np.array([0.0, -1.0, 0.0], dtype=np.float32), (len(origins), 1))
    hits = scene.cast_rays(o3d.core.Tensor(np.column_stack((origins, directions))))
    distances = hits["t_hit"].numpy()
    normals = hits["primitive_normals"].numpy()
    hit_heights = origins[:, 1] - distances
    supported = np.isfinite(distances) & (normals[:, 1] > FLOOR_NORMAL_Y_MINIMUM)
    supported &= hit_heights <= floor_ceiling + 0.01
    return {
        name: float(hit_heights[index])
        for index, name in enumerate(cameras)
        if supported[index]
    }


def scene_source(scene_name: str, transform: str | None) -> str:
    mesh_path = f"res://generated_mesh_scenes/{scene_name}/scene.glb"
    player_nodes = ""
    if transform is not None:
        player_nodes = f"""[node name="PlayerSpawn" type="Marker3D" parent="."]
transform = {transform}

[node name="Player" parent="." instance=ExtResource("4_player")]
transform = {transform}
"""
    return f'''[gd_scene load_steps=8 format=3]

[ext_resource type="PackedScene" path="{mesh_path}" id="1_mesh"]
[ext_resource type="Script" path="res://scripts/psx/psx_post_effect.gd" id="2_psx_script"]
[ext_resource type="Script" path="res://scripts/generated_collision.gd" id="3_collision_script"]
[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="4_player"]

[sub_resource type="CompositorEffect" id="CompositorEffect_mesh_psx"]
script = ExtResource("2_psx_script")
pixel_size = 4
color_levels = 16
dither_strength = 1.0

[sub_resource type="Compositor" id="Compositor_mesh_psx"]
compositor_effects = Array[CompositorEffect]([SubResource("CompositorEffect_mesh_psx")])

[sub_resource type="Environment" id="Environment_mesh"]
background_mode = 1
background_color = Color(0.03, 0.035, 0.04, 1)
ambient_light_source = 2
ambient_light_color = Color(0.45, 0.48, 0.55, 1)
ambient_light_energy = 0.45

[node name="{scene_name}" type="Node3D"]

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Environment_mesh")
compositor = SubResource("Compositor_mesh_psx")

[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 4, 0)
rotation = Vector3(-0.785398, 0.523599, 0)

[node name="MeshAsset" parent="." instance=ExtResource("1_mesh")]

[node name="GeneratedCollision" type="StaticBody3D" parent="."]
script = ExtResource("3_collision_script")
mesh_path = "{mesh_path}"

{player_nodes}'''


def stage(scene_dir: Path, project_dir: Path, scene_name: str) -> Path:
    glb_path = scene_dir / "scene.glb"
    report_path = scene_dir / "textured_mesh/texture_report.json"
    if not glb_path.is_file() or not report_path.is_file():
        raise FileNotFoundError("scene.glb and textured_mesh/texture_report.json are required")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rotation = np.asarray(report.get("source_to_y_up_rotation"), dtype=np.float64)
    if rotation.shape != (3, 3) or not np.isfinite(rotation).all():
        raise ValueError(f"invalid source rotation in {report_path}")
    cameras = capture_cameras(scene_dir, rotation, scene_scale(scene_dir))
    mesh = trimesh.load(glb_path, force="mesh", process=False)
    support = floor_support(mesh, cameras)
    face_counts = report.get("faces_per_view", {})
    spawn_view = max(support["floor_height_by_view"], key=face_counts.get, default=None)
    source_view = max(face_counts, key=face_counts.get)
    output_dir = project_dir / "generated_mesh_scenes" / scene_name
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(glb_path, output_dir / "scene.glb")
    scene_path = output_dir / "scene.tscn"
    transform = None
    if support["walkable"] and spawn_view is not None:
        pose = cameras[spawn_view]
        transform = player_transform(
            pose["position"], pose["yaw"], support["floor_height_by_view"][spawn_view]
        )
    scene_path.write_text(
        scene_source(scene_name, transform),
        encoding="utf-8",
    )
    report = {
        **support,
        "spawn_view": spawn_view,
        "source_camera_position": cameras[source_view]["position"].tolist(),
        "source_camera_forward": cameras[source_view]["forward"].tolist(),
    }
    (output_dir / "scene_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return scene_path


def main() -> int:
    args = parse_args()
    scene_path = stage(args.scene_dir, args.project_dir, args.scene_name)
    print(f"Staged mesh scene: {scene_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
