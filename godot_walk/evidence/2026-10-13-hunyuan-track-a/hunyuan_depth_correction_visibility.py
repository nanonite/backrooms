"""Project other registered COLMAP landmarks into frame 141 as floor holdouts."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from hunyuan_depth_correction_data import (
    FLOOR_Y,
    PLANE_MEMBERSHIP_TOLERANCE_M,
    RaySamples,
    _camera_points_world_y,
    _foreground_mask,
    _samples_from_arrays,
    map_pixels,
)
from hunyuan_depth_correction_mesh import MeshGrid

Z_BUFFER_NEIGHBORHOOD = 5
VISIBILITY_DEPTH_TOLERANCE_M = 0.10


def collect_cross_frame_floor_samples(
    context,
    mesh: MeshGrid,
    foreground_mask_path: Path,
) -> tuple[RaySamples, dict]:
    reconstruction = context.reconstruction
    source_ids = set(map(int, context.point_ids))
    observed_elsewhere = _observed_elsewhere(reconstruction, context.image.image_id)
    candidate_ids = sorted(observed_elsewhere - source_ids)
    point_map = reconstruction.points3D
    candidate_points = np.asarray(
        [point_map[point_id].xyz for point_id in candidate_ids], dtype=np.float64
    ).reshape(-1, 3)
    candidate_camera = _camera_coordinates(context, candidate_points)
    all_points = np.asarray(
        [point.xyz for point in point_map.values()], dtype=np.float64
    ).reshape(-1, 3)
    all_camera = _camera_coordinates(context, all_points)
    all_pixels, all_inside = _project_camera_points(context.camera, all_camera)
    all_depth_metres = all_camera[:, 2] * context.metres_per_colmap_unit
    z_buffer = _make_z_buffer(
        context.camera.width,
        context.camera.height,
        all_pixels,
        all_inside,
        all_depth_metres,
    )
    local_front_depth = cv2.erode(
        z_buffer,
        np.ones((Z_BUFFER_NEIGHBORHOOD, Z_BUFFER_NEIGHBORHOOD), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT,
        borderValue=float("inf"),
    )
    candidate_pixels, inside = _project_camera_points(context.camera, candidate_camera)
    safe_pixels = np.nan_to_num(
        candidate_pixels, copy=True, nan=0.0, posinf=0.0, neginf=0.0
    )
    safe_pixels[:, 0] = np.clip(safe_pixels[:, 0], 0, context.camera.width - 1)
    safe_pixels[:, 1] = np.clip(safe_pixels[:, 1], 0, context.camera.height - 1)
    candidate_xy = np.rint(safe_pixels).astype(np.int32)
    in_bounds = (
        inside
        & (candidate_pixels[:, 0] >= 0)
        & (candidate_pixels[:, 0] < context.camera.width)
        & (candidate_pixels[:, 1] >= 0)
        & (candidate_pixels[:, 1] < context.camera.height)
    )
    candidate_world_y = _camera_points_world_y(context, candidate_camera)
    floor_points = np.abs(candidate_world_y - FLOOR_Y) <= PLANE_MEMBERSHIP_TOLERANCE_M
    local_depth = local_front_depth[
        np.clip(candidate_xy[:, 1], 0, context.camera.height - 1),
        np.clip(candidate_xy[:, 0], 0, context.camera.width - 1),
    ]
    candidate_depth = candidate_camera[:, 2] * context.metres_per_colmap_unit
    visible = candidate_depth <= local_depth + VISIBILITY_DEPTH_TOLERANCE_M
    selection = in_bounds & floor_points & visible
    mask = _foreground_mask(foreground_mask_path, mesh)
    rows, columns, elevations, direction_y = map_pixels(
        context, safe_pixels, mesh.width, mesh.height
    )
    flat_indices = rows * mesh.width + columns
    mesh_positions = np.column_stack(
        (
            mesh.records["x"][flat_indices],
            mesh.records["y"][flat_indices],
            mesh.records["z"][flat_indices],
        )
    )
    mesh_depth = np.linalg.norm(mesh_positions, axis=1)
    selection &= ~mask[rows, columns] & np.isfinite(mesh_depth) & (mesh_depth > 1e-9)
    target_depth = np.linalg.norm(candidate_camera, axis=1) * context.metres_per_colmap_unit
    samples = _samples_from_arrays(
        source="other_frame_floor_holdout",
        point_ids=np.asarray(candidate_ids, dtype=np.uint64),
        source_pixels=safe_pixels,
        elevations=elevations,
        mesh_depth=mesh_depth,
        camera_depth=target_depth,
        direction_y=direction_y,
        rows=rows,
        columns=columns,
        width=mesh.width,
        height=mesh.height,
        plane_kind=np.full(len(candidate_ids), -1, dtype=np.int8),
        selection=selection,
        image_width=context.camera.width,
        image_height=context.camera.height,
    )
    return samples, {
        "candidate_landmarks_seen_in_other_frames": len(candidate_ids),
        "projected_inside_frame_141": int(np.count_nonzero(in_bounds)),
        "near_declared_floor_before_visibility": int(np.count_nonzero(in_bounds & floor_points)),
        "sparse_z_buffer_visible": int(np.count_nonzero(in_bounds & floor_points & visible)),
        "foreground_or_invalid_mesh_rays_rejected": int(np.count_nonzero(in_bounds & floor_points & visible) - len(samples.point_ids)),
        "accepted_extra_floor_holdouts": len(samples.point_ids),
        "z_buffer_neighborhood_pixels": Z_BUFFER_NEIGHBORHOOD,
        "visibility_depth_tolerance_m": VISIBILITY_DEPTH_TOLERANCE_M,
        "floor_membership_tolerance_m": PLANE_MEMBERSHIP_TOLERANCE_M,
        "limitation": "Visibility uses a sparse COLMAP z-buffer, not dense image depth; these samples validate but never train the correction field.",
    }


def _observed_elsewhere(reconstruction, source_image_id: int) -> set[int]:
    point_ids = set()
    for image in reconstruction.images.values():
        if image.image_id == source_image_id:
            continue
        point_ids.update(
            int(point.point3D_id) for point in image.points2D if point.has_point3D()
        )
    return point_ids


def _camera_coordinates(context, points: np.ndarray) -> np.ndarray:
    pose = (
        context.image.cam_from_world()
        if callable(context.image.cam_from_world)
        else context.image.cam_from_world
    )
    rotation = np.asarray(pose.rotation.matrix(), dtype=np.float64)
    translation = np.asarray(pose.translation, dtype=np.float64)
    return np.asarray(points, dtype=np.float64) @ rotation.T + translation


def _project_camera_points(camera, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    front = np.asarray(points)[:, 2] > 1e-6
    pixels = np.full((len(points), 2), np.nan, dtype=np.float64)
    if front.any():
        projected = camera.img_from_cam(np.asarray(points)[front])
        pixels[front] = np.asarray(projected, dtype=np.float64)
    inside = (
        front
        & np.isfinite(pixels).all(axis=1)
        & (pixels[:, 0] >= 0)
        & (pixels[:, 0] < camera.width)
        & (pixels[:, 1] >= 0)
        & (pixels[:, 1] < camera.height)
    )
    return pixels, inside


def _make_z_buffer(
    width: int,
    height: int,
    pixels: np.ndarray,
    inside: np.ndarray,
    camera_z: np.ndarray,
) -> np.ndarray:
    buffer = np.full((height, width), np.inf, dtype=np.float32)
    coordinates = np.rint(pixels[inside]).astype(np.int32)
    coordinates[:, 0] = np.clip(coordinates[:, 0], 0, width - 1)
    coordinates[:, 1] = np.clip(coordinates[:, 1], 0, height - 1)
    flat = coordinates[:, 1] * width + coordinates[:, 0]
    depths_m = camera_z[inside].astype(np.float64)
    np.minimum.at(buffer.reshape(-1), flat, depths_m.astype(np.float32))
    return buffer
