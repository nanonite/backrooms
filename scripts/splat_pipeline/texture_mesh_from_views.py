#!/usr/bin/env python3
"""Project registered source images onto visible triangles of a COLMAP mesh."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import open3d as o3d
import pycolmap
import trimesh
from PIL import Image


MIN_VIEW_COSINE = 0.12
VISIBILITY_ABSOLUTE_TOLERANCE_M = 0.04
VISIBILITY_RELATIVE_TOLERANCE = 0.01
MIN_UP_ALIGNMENT_COHERENCE = 0.75
MAX_TEXTURE_DIMENSION = 1024
TEXTURE_JPEG_QUALITY = 88


@dataclass(frozen=True)
class CameraView:
    name: str
    image_path: Path
    camera: object
    rotation: np.ndarray
    translation: np.ndarray
    center: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", required=True, type=Path)
    parser.add_argument("--reconstruction", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-textured-fraction", type=float, default=0.5)
    args = parser.parse_args()
    if not 0.0 < args.minimum_textured_fraction <= 1.0:
        parser.error("--minimum-textured-fraction must be in (0, 1]")
    return args


def load_views(reconstruction_path: Path, image_root: Path) -> list[CameraView]:
    reconstruction = pycolmap.Reconstruction(str(reconstruction_path))
    views = []
    for image in reconstruction.images.values():
        image_path = (image_root / image.name).resolve()
        if image_root.resolve() not in image_path.parents or not image_path.is_file():
            continue
        camera = reconstruction.cameras[image.camera_id]
        rotation = np.asarray(image.cam_from_world.rotation.matrix(), dtype=np.float64)
        translation = np.asarray(image.cam_from_world.translation, dtype=np.float64)
        center = -rotation.T @ translation
        views.append(CameraView(image.name, image_path, camera, rotation, translation, center))
    if not views:
        raise ValueError(f"no registered images found under {image_root}")
    return sorted(views, key=lambda view: view.name)


def make_raycast_scene(mesh: trimesh.Trimesh) -> o3d.t.geometry.RaycastingScene:
    legacy = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(np.asarray(mesh.vertices, dtype=np.float64)),
        o3d.utility.Vector3iVector(np.asarray(mesh.faces, dtype=np.int32)),
    )
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))
    return scene


def source_to_y_up(views: list[CameraView]) -> tuple[np.ndarray, np.ndarray, float]:
    camera_ups = np.stack(
        [view.rotation.T @ np.array([0.0, -1.0, 0.0]) for view in views]
    )
    mean_up = camera_ups.mean(axis=0)
    coherence = float(np.linalg.norm(mean_up))
    if coherence < MIN_UP_ALIGNMENT_COHERENCE:
        raise ValueError(
            f"registered camera up directions disagree (coherence {coherence:.3f}); "
            "refusing to guess the mesh vertical axis"
        )
    source_up = mean_up / coherence
    target_up = np.array([0.0, 1.0, 0.0])
    cross = np.cross(source_up, target_up)
    sine = float(np.linalg.norm(cross))
    cosine = float(np.dot(source_up, target_up))
    if sine < 1e-8:
        rotation = np.eye(3) if cosine > 0.0 else np.diag([1.0, -1.0, -1.0])
    else:
        skew = np.array(
            [[0.0, -cross[2], cross[1]],
             [cross[2], 0.0, -cross[0]],
             [-cross[1], cross[0], 0.0]]
        )
        rotation = np.eye(3) + skew + (skew @ skew) * ((1.0 - cosine) / (sine**2))
    return source_up, rotation, coherence


def candidate_pixels(view: CameraView, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    camera_points = points @ view.rotation.T + view.translation
    in_front = camera_points[:, 2] > 0.05
    pixels = np.zeros((len(points), 2), dtype=np.float64)
    if in_front.any():
        pixels[in_front] = view.camera.img_from_cam(camera_points[in_front])
    inside = (
        in_front
        & (pixels[:, 0] >= 1.0)
        & (pixels[:, 0] < view.camera.width - 1.0)
        & (pixels[:, 1] >= 1.0)
        & (pixels[:, 1] < view.camera.height - 1.0)
    )
    return pixels, inside


def projected_corners(
    view: CameraView, vertices: np.ndarray, faces: np.ndarray, face_ids: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    corners = vertices[faces[face_ids]]
    camera_corners = corners @ view.rotation.T + view.translation
    front = np.all(camera_corners[:, :, 2] > 0.05, axis=1)
    pixels = np.zeros((len(face_ids), 3, 2), dtype=np.float64)
    if front.any():
        pixels[front] = view.camera.img_from_cam(camera_corners[front].reshape(-1, 3)).reshape(-1, 3, 2)
    inside = (
        front
        & np.all(pixels[:, :, 0] >= 0.0, axis=1)
        & np.all(pixels[:, :, 0] < view.camera.width, axis=1)
        & np.all(pixels[:, :, 1] >= 0.0, axis=1)
        & np.all(pixels[:, :, 1] < view.camera.height, axis=1)
    )
    return pixels, inside


def visible_candidates(
    scene: o3d.t.geometry.RaycastingScene,
    view: CameraView,
    centers: np.ndarray,
    face_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    vectors = centers[face_ids] - view.center
    distances = np.linalg.norm(vectors, axis=1)
    directions = vectors / np.maximum(distances[:, None], 1e-9)
    rays = np.column_stack((np.repeat(view.center[None, :], len(face_ids), axis=0), directions))
    hits = scene.cast_rays(o3d.core.Tensor(rays.astype(np.float32)))["t_hit"].numpy()
    tolerance = np.maximum(
        VISIBILITY_ABSOLUTE_TOLERANCE_M,
        distances * VISIBILITY_RELATIVE_TOLERANCE,
    )
    visible = np.isfinite(hits) & (np.abs(hits - distances) <= tolerance)
    return visible, distances


def assign_views(
    mesh: trimesh.Trimesh, views: list[CameraView], scene: o3d.t.geometry.RaycastingScene
) -> tuple[np.ndarray, np.ndarray]:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    centers = np.asarray(mesh.triangles_center, dtype=np.float64)
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    best_scores = np.full(len(faces), -np.inf)
    assignments = np.full(len(faces), -1, dtype=np.int32)
    uv_coordinates = np.zeros((len(faces), 3, 2), dtype=np.float32)
    for view_index, view in enumerate(views):
        pixels, in_frame = candidate_pixels(view, centers)
        face_ids = np.flatnonzero(in_frame)
        if not len(face_ids):
            continue
        corner_pixels, corners_inside = projected_corners(view, vertices, faces, face_ids)
        face_ids = face_ids[corners_inside]
        corner_pixels = corner_pixels[corners_inside]
        view_directions = view.center - centers[face_ids]
        view_directions /= np.maximum(np.linalg.norm(view_directions, axis=1)[:, None], 1e-9)
        facing = np.abs(np.einsum("ij,ij->i", normals[face_ids], view_directions))
        front_facing = facing >= MIN_VIEW_COSINE
        face_ids = face_ids[front_facing]
        corner_pixels = corner_pixels[front_facing]
        facing = facing[front_facing]
        visible, distances = visible_candidates(scene, view, centers, face_ids)
        face_ids = face_ids[visible]
        corner_pixels = corner_pixels[visible]
        facing = facing[visible]
        distances = distances[visible]
        if not len(face_ids):
            continue
        pixel_centers = pixels[face_ids]
        center_x = (pixel_centers[:, 0] / view.camera.width) * 2.0 - 1.0
        center_y = (pixel_centers[:, 1] / view.camera.height) * 2.0 - 1.0
        center_weight = np.maximum(0.25, 1.0 - 0.25 * np.hypot(center_x, center_y))
        view_weight = np.power(facing, 2.0)
        scores = view_weight * center_weight / np.sqrt(np.maximum(distances, 0.05))
        better = scores > best_scores[face_ids]
        chosen = face_ids[better]
        best_scores[chosen] = scores[better]
        assignments[chosen] = view_index
        selected_corners = corner_pixels[better]
        uv_coordinates[chosen, :, 0] = selected_corners[:, :, 0] / view.camera.width
        uv_coordinates[chosen, :, 1] = 1.0 - selected_corners[:, :, 1] / view.camera.height
    return assignments, uv_coordinates


def write_textured_obj(
    output_dir: Path,
    mesh: trimesh.Trimesh,
    views: list[CameraView],
    assignments: np.ndarray,
    uv_coordinates: np.ndarray,
    source_to_y_up_rotation: np.ndarray | None = None,
) -> tuple[int, Counter]:
    output_dir.mkdir(parents=True, exist_ok=True)
    used_views = sorted(int(index) for index in np.unique(assignments) if index >= 0)
    material_names = {index: f"view_{index:03d}" for index in used_views}
    mtl_path = output_dir / "mesh.mtl"
    obj_path = output_dir / "mesh.obj"
    write_materials(mtl_path, views, used_views, material_names, output_dir)
    covered_faces = np.flatnonzero(assignments >= 0)
    face_counts: Counter = Counter()
    with obj_path.open("w", encoding="utf-8") as obj_file:
        obj_file.write(f"mtllib {mtl_path.name}\n")
        rotation = source_to_y_up_rotation if source_to_y_up_rotation is not None else np.eye(3)
        for vertex in np.asarray(mesh.vertices) @ rotation.T:
            obj_file.write("v %.7f %.7f %.7f\n" % tuple(vertex))
        for face_id in covered_faces:
            for uv in uv_coordinates[face_id]:
                obj_file.write("vt %.7f %.7f\n" % tuple(uv))
        current_material = None
        for texture_index in used_views:
            for face_id in covered_faces[assignments[covered_faces] == texture_index]:
                material = material_names[texture_index]
                if material != current_material:
                    obj_file.write(f"usemtl {material}\n")
                    current_material = material
                texture_start = int(np.searchsorted(covered_faces, face_id)) * 3 + 1
                vertices = mesh.faces[face_id] + 1
                corners = " ".join(
                    f"{vertex}/{texture_start + offset}" for offset, vertex in enumerate(vertices)
                )
                obj_file.write(f"f {corners}\n")
                face_counts[texture_index] += 1
    return len(covered_faces), face_counts


def write_materials(
    path: Path,
    views: list[CameraView],
    used_views: list[int],
    material_names: dict[int, str],
    output_dir: Path,
) -> None:
    with path.open("w", encoding="utf-8") as material_file:
        for index in used_views:
            texture_path = write_compact_texture(output_dir, views[index], index)
            relative_image = os.path.relpath(texture_path, output_dir)
            material_file.write(f"newmtl {material_names[index]}\n")
            material_file.write("Ka 1.0 1.0 1.0\nKd 1.0 1.0 1.0\nKs 0.0 0.0 0.0\n")
            material_file.write(f"map_Kd {Path(relative_image).as_posix()}\n\n")


def write_compact_texture(output_dir: Path, view: CameraView, index: int) -> Path:
    texture_dir = output_dir / "images"
    texture_dir.mkdir(parents=True, exist_ok=True)
    texture_path = texture_dir / f"view_{index:03d}.jpg"
    with Image.open(view.image_path) as source:
        image = source.convert("RGB")
        image.thumbnail(
            (MAX_TEXTURE_DIMENSION, MAX_TEXTURE_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        image.save(texture_path, "JPEG", quality=TEXTURE_JPEG_QUALITY, optimize=True)
    return texture_path


def write_report(
    output_dir: Path,
    mesh: trimesh.Trimesh,
    views: list[CameraView],
    covered_faces: int,
    face_counts: Counter,
    source_up: np.ndarray,
    source_to_y_up_rotation: np.ndarray,
    up_coherence: float,
) -> None:
    fraction = covered_faces / max(len(mesh.faces), 1)
    report = {
        "method": "per-face source-image projection with COLMAP camera visibility ray tests",
        "input_vertices": int(len(mesh.vertices)),
        "input_faces": int(len(mesh.faces)),
        "textured_faces": covered_faces,
        "textured_fraction": fraction,
        "omitted_unobserved_faces": int(len(mesh.faces) - covered_faces),
        "registered_views": len(views),
        "used_views": len(face_counts),
        "texture_max_dimension": MAX_TEXTURE_DIMENSION,
        "source_up_world": source_up.tolist(),
        "source_to_y_up_rotation": source_to_y_up_rotation.tolist(),
        "camera_up_coherence": up_coherence,
        "faces_per_view": {
            views[index].name: count for index, count in sorted(face_counts.items())
        },
        "synthetic_completion": False,
    }
    (output_dir / "texture_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    mesh = trimesh.load(args.mesh, force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError(f"input has no triangle mesh: {args.mesh}")
    views = load_views(args.reconstruction, args.images)
    source_up, source_rotation, up_coherence = source_to_y_up(views)
    scene = make_raycast_scene(mesh)
    assignments, uv_coordinates = assign_views(mesh, views, scene)
    covered, face_counts = write_textured_obj(
        args.output, mesh, views, assignments, uv_coordinates, source_rotation
    )
    fraction = covered / len(mesh.faces)
    write_report(
        args.output, mesh, views, covered, face_counts,
        source_up, source_rotation, up_coherence,
    )
    print(f"Textured {covered}/{len(mesh.faces)} faces ({fraction:.1%}) from {len(face_counts)} views.")
    if fraction < args.minimum_textured_fraction:
        raise ValueError(
            f"textured fraction {fraction:.1%} is below required "
            f"{args.minimum_textured_fraction:.1%}; output is incomplete"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
