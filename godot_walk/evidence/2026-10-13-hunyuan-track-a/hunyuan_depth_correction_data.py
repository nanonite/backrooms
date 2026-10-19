"""Collect registered-ray samples for Route A CPU validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pycolmap
from PIL import Image

from hunyuan_depth_correction_mesh import MeshGrid

FLOOR_Y = -1.2709904916
CEILING_Y = 1.1290095084
PLANE_MEMBERSHIP_TOLERANCE_M = 0.10


@dataclass(frozen=True)
class RaySamples:
    source: str
    point_ids: np.ndarray
    elevation: np.ndarray
    depth: np.ndarray
    target_depth: np.ndarray
    direction_world_y: np.ndarray
    row: np.ndarray
    column: np.ndarray
    row_fraction: np.ndarray
    spatial_cell: np.ndarray
    plane_kind: np.ndarray

    def subset(self, selection: np.ndarray) -> "RaySamples":
        return RaySamples(
            source=self.source,
            point_ids=self.point_ids[selection],
            elevation=self.elevation[selection],
            depth=self.depth[selection],
            target_depth=self.target_depth[selection],
            direction_world_y=self.direction_world_y[selection],
            row=self.row[selection],
            column=self.column[selection],
            row_fraction=self.row_fraction[selection],
            spatial_cell=self.spatial_cell[selection],
            plane_kind=self.plane_kind[selection],
        )


@dataclass(frozen=True)
class CameraContext:
    reconstruction: pycolmap.Reconstruction
    image: object
    camera: object
    camera_points: np.ndarray
    pixels: np.ndarray
    point_ids: np.ndarray
    camera_center: np.ndarray
    rotation: np.ndarray
    metres_per_colmap_unit: float
    camera_frame_source: str


def make_camera_context(
    source_path: Path,
    colmap_path: Path,
    dataparser_path: Path,
    alignment_path: Path,
    calibration: dict,
    frame_camera_path: Path | None = None,
) -> CameraContext:
    reconstruction = pycolmap.Reconstruction(str(colmap_path))
    image = next(
        (record for record in reconstruction.images.values() if record.name == source_path.name),
        None,
    )
    if image is None:
        raise ValueError("source frame is not registered in COLMAP")
    camera = reconstruction.cameras[image.camera_id]
    if "SIMPLE_RADIAL" not in str(camera.model) or len(camera.params) != 4:
        raise ValueError("ray correction currently requires a SIMPLE_RADIAL camera")
    pose = image.cam_from_world() if callable(image.cam_from_world) else image.cam_from_world
    observations = [point for point in image.points2D if point.has_point3D()]
    point_ids = np.array([int(point.point3D_id) for point in observations], dtype=np.uint64)
    pixels = np.array([point.xy for point in observations], dtype=np.float64)
    camera_points = np.array(
        [pose * reconstruction.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    dataparser_scale = float(json.loads(dataparser_path.read_text())["scale"])
    alignment = json.loads(alignment_path.read_text())
    metres = dataparser_scale * float(alignment["ply_to_world"]["metres_per_unit"])
    camera_center, rotation, camera_frame_source = _camera_frame(
        frame_camera_path, source_path.name, calibration
    )
    return CameraContext(
        reconstruction=reconstruction,
        image=image,
        camera=camera,
        camera_points=camera_points,
        pixels=pixels,
        point_ids=point_ids,
        camera_center=camera_center,
        rotation=rotation,
        metres_per_colmap_unit=metres,
        camera_frame_source=camera_frame_source,
    )


def _camera_frame(
    frame_camera_path: Path | None, source_name: str, calibration: dict
) -> tuple[np.ndarray, np.ndarray, str]:
    if frame_camera_path is None:
        return (
            np.asarray(calibration["registered_camera"]["camera_center_world_declared"], dtype=np.float64),
            np.asarray(calibration["rotation_local_to_world_row_major"], dtype=np.float64),
            "frame-141 calibration manifest",
        )
    frame = json.loads(frame_camera_path.read_text())
    if frame["selected_frame"]["registered_image"] != source_name:
        raise ValueError("frame camera metadata does not match the selected source image")
    camera = frame["camera"]
    forward = np.asarray(camera["forward_godot_world"], dtype=np.float64)
    up = np.asarray(camera["up_godot_world"], dtype=np.float64)
    rotation = np.column_stack((-forward, np.cross(forward, up), up))
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-4):
        raise ValueError("frame camera orientation is not orthonormal")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-4):
        raise ValueError("frame camera orientation is not a proper rotation")
    return (
        np.asarray(camera["camera_center_godot_world_m"], dtype=np.float64),
        rotation,
        str(frame_camera_path),
    )


def collect_frame_samples(
    context: CameraContext,
    mesh: MeshGrid,
    foreground_mask_path: Path,
) -> tuple[RaySamples, dict]:
    rows, columns, elevations, direction_y = map_pixels(
        context, context.pixels, mesh.width, mesh.height
    )
    foreground = _foreground_mask(foreground_mask_path, mesh)
    positions = np.column_stack(
        (
            mesh.records["x"][rows * mesh.width + columns],
            mesh.records["y"][rows * mesh.width + columns],
            mesh.records["z"][rows * mesh.width + columns],
        )
    )
    mesh_depth = np.linalg.norm(positions, axis=1)
    camera_depth = np.linalg.norm(context.camera_points, axis=1) * context.metres_per_colmap_unit
    source_world_y = _camera_points_world_y(context, context.camera_points)
    selection = (
        ~foreground[rows, columns]
        & np.isfinite(mesh_depth)
        & (mesh_depth > 1e-9)
        & np.isfinite(camera_depth)
        & (camera_depth > 1e-9)
    )
    plane_kind = _plane_membership(source_world_y)
    samples = _samples_from_arrays(
        source=Path(context.image.name).stem,
        point_ids=context.point_ids,
        source_pixels=context.pixels,
        elevations=elevations,
        mesh_depth=mesh_depth,
        camera_depth=camera_depth,
        direction_y=direction_y,
        rows=rows,
        columns=columns,
        width=mesh.width,
        height=mesh.height,
        plane_kind=plane_kind,
        selection=selection,
        image_width=context.camera.width,
        image_height=context.camera.height,
    )
    return samples, {
        "registered_observations": len(context.point_ids),
        "foreground_masked": int(np.count_nonzero(~selection)),
        "used_for_training": len(samples.point_ids),
        "floor_plane_membership": int(np.count_nonzero(samples.plane_kind == -1)),
        "ceiling_plane_membership": int(np.count_nonzero(samples.plane_kind == 1)),
        "plane_membership_tolerance_m": PLANE_MEMBERSHIP_TOLERANCE_M,
    }


def map_pixels(
    context: CameraContext,
    pixels: np.ndarray,
    panorama_width: int,
    panorama_height: int,
) -> tuple[np.ndarray, ...]:
    focal, center_x, center_y, radial = context.camera.params
    intrinsics = np.array([[focal, 0, center_x], [0, focal, center_y], [0, 0, 1.0]])
    rays = cv2.undistortPoints(
        np.asarray(pixels, dtype=np.float32).reshape(-1, 1, 2),
        intrinsics,
        np.array([radial, 0.0, 0.0, 0.0]),
    ).reshape(-1, 2)
    norm = np.sqrt(rays[:, 0] ** 2 + rays[:, 1] ** 2 + 1.0)
    longitude = np.arctan2(rays[:, 0], 1.0)
    elevation = np.arcsin(-rays[:, 1] / norm)
    rows = np.clip(
        (0.5 - elevation / np.pi) * panorama_height, 0, panorama_height - 1
    ).astype(np.int32)
    columns = np.clip(
        ((longitude / (2 * np.pi)) + 0.5) * panorama_width, 0, panorama_width - 1
    ).astype(np.int32)
    camera_direction = np.column_stack((rays[:, 0], rays[:, 1], np.ones(len(rays)))) / norm[:, None]
    hunyuan_direction = np.column_stack(
        (-camera_direction[:, 2], camera_direction[:, 0], -camera_direction[:, 1])
    )
    world_direction_y = hunyuan_direction @ context.rotation[1, :]
    return rows, columns, elevation, world_direction_y


def _samples_from_arrays(
    source: str,
    point_ids: np.ndarray,
    source_pixels: np.ndarray,
    elevations: np.ndarray,
    mesh_depth: np.ndarray,
    camera_depth: np.ndarray,
    direction_y: np.ndarray,
    rows: np.ndarray,
    columns: np.ndarray,
    width: int,
    height: int,
    plane_kind: np.ndarray,
    selection: np.ndarray,
    image_width: int,
    image_height: int,
) -> RaySamples:
    image_grid_x = np.clip((source_pixels[:, 0] * 4 / image_width).astype(int), 0, 3)
    image_grid_y = np.clip((source_pixels[:, 1] * 4 / image_height).astype(int), 0, 3)
    return RaySamples(
        source=source,
        point_ids=point_ids[selection],
        elevation=elevations[selection],
        depth=mesh_depth[selection],
        target_depth=camera_depth[selection],
        direction_world_y=direction_y[selection],
        row=rows[selection],
        column=columns[selection],
        row_fraction=rows[selection] / height,
        spatial_cell=(image_grid_y[selection] * 4 + image_grid_x[selection]),
        plane_kind=plane_kind[selection],
    )


def _camera_points_world_y(context: CameraContext, camera_points: np.ndarray) -> np.ndarray:
    metric = camera_points * context.metres_per_colmap_unit
    hunyuan = np.column_stack((-metric[:, 2], metric[:, 0], -metric[:, 1]))
    return context.camera_center[1] + hunyuan @ context.rotation[1, :]


def _plane_membership(world_y: np.ndarray) -> np.ndarray:
    labels = np.zeros(len(world_y), dtype=np.int8)
    labels[np.abs(world_y - FLOOR_Y) <= PLANE_MEMBERSHIP_TOLERANCE_M] = -1
    labels[np.abs(world_y - CEILING_Y) <= PLANE_MEMBERSHIP_TOLERANCE_M] = 1
    return labels


def _foreground_mask(path: Path, mesh: MeshGrid) -> np.ndarray:
    with Image.open(path) as image:
        resized = image.convert("L").resize((mesh.width, mesh.height), Image.Resampling.NEAREST)
        return np.asarray(resized) > 0
