"""Load the registered #100 camera path for read-only visibility diagnostics."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PIPELINE_TOOLS = ROOT / "scripts" / "splat_pipeline"
sys.path.insert(0, str(PIPELINE_TOOLS))

import build_registered_floor_masks_all_frames as floor_masks
from source_inputs import sha256_file


@dataclass(frozen=True)
class CameraPathContext:
    """Inputs shared by the geometry and route-visibility reports."""

    contract: object
    dataparser: dict
    images: list
    cameras: dict
    centres_world_m: np.ndarray


def load_camera_path() -> CameraPathContext:
    """Load sorted COLMAP frames and map their centres through #100."""
    contract = floor_masks.contract_from_path(floor_masks.ALIGNMENT_PATH)
    dataparser = floor_masks.load_dataparser(str(floor_masks.DATAPARSER_PATH))
    raw_images = floor_masks.read_images(floor_masks.COLMAP_PATH)
    images = sorted(raw_images, key=lambda image: floor_masks.image_number(image.name))
    if len(images) != 192 or {
        floor_masks.image_number(image.name) for image in images
    } != set(range(1, 193)):
        raise ValueError("expected registered source frames 1 through 192")
    cameras = floor_masks.read_cameras(floor_masks.COLMAP_PATH)
    centres_ply = floor_masks.cameras_in_ply_frame(raw_images, dataparser)
    centres_by_frame = {
        floor_masks.image_number(image.name): contract.ply_to_world.world_point(centre)
        for image, centre in zip(raw_images, centres_ply, strict=True)
    }
    centres = np.stack(
        [centres_by_frame[floor_masks.image_number(image.name)] for image in images]
    )
    if not np.isfinite(centres).all():
        raise ValueError("mapped camera centres contain non-finite coordinates")
    return CameraPathContext(contract, dataparser, images, cameras, centres)


def input_hashes() -> dict[str, str]:
    """Hash alignment, pose, and camera inputs used by the diagnostics."""
    return {
        "alignment_manifest_sha256": sha256_file(floor_masks.ALIGNMENT_PATH),
        "colmap_images_sha256": sha256_file(floor_masks.COLMAP_PATH / "images.bin"),
        "colmap_cameras_sha256": sha256_file(floor_masks.COLMAP_PATH / "cameras.bin"),
        "dataparser_transforms_sha256": sha256_file(floor_masks.DATAPARSER_PATH),
    }


def project_world_points(
    context: CameraPathContext,
    image_index: int,
    points_world_m: np.ndarray,
    apply_radial_distortion: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Project world points with the registered SIMPLE_RADIAL camera model."""
    image = context.images[image_index]
    camera = context.cameras[image.camera_id]
    if camera.model != "SIMPLE_RADIAL" or len(camera.params) != 4:
        raise ValueError("expected registered COLMAP SIMPLE_RADIAL intrinsics")
    points = np.asarray(points_world_m, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("world points must be a finite N x 3 array")
    points_camera = world_to_camera_points(context, image_index, points)
    depth = points_camera[:, 2]
    in_front = depth > 1e-6
    normalized = np.zeros((len(points), 2), dtype=np.float64)
    normalized[in_front] = points_camera[in_front, :2] / depth[in_front, None]
    pixels, radial_valid = image_pixels(normalized, camera, apply_radial_distortion)
    in_front &= radial_valid
    pixels[~in_front] = np.nan
    return pixels, in_front


def world_to_camera_points(
    context: CameraPathContext, image_index: int, points_world_m: np.ndarray
) -> np.ndarray:
    """Map metric world points to one registered COLMAP camera frame."""
    image = context.images[image_index]
    mapping = context.contract.ply_to_world
    colmap_to_world = context.dataparser["rotation"].T @ mapping.rotation().T
    colmap_to_world *= mapping.metres_per_unit
    world_to_colmap = np.linalg.inv(colmap_to_world)
    delta_world = points_world_m - context.centres_world_m[image_index]
    return (delta_world @ world_to_colmap) @ image.rotation_w2c.T


def image_pixels(
    normalized: np.ndarray, camera, apply_radial_distortion: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Apply pinhole or monotonic SIMPLE_RADIAL projection to normalized points."""
    focal, center_x, center_y, radial = camera.params
    projected = normalized
    valid = np.ones(len(normalized), dtype=bool)
    if apply_radial_distortion:
        radius_squared = np.sum(normalized * normalized, axis=1)
        if radial < 0.0:
            monotonic_radius_squared = -1.0 / (3.0 * radial)
            valid = radius_squared < monotonic_radius_squared
        projected = normalized * (1.0 + radial * radius_squared)[:, None]
    pixels = projected * focal + np.array([center_x, center_y])
    return pixels, valid


def percentile_summary(values: np.ndarray) -> dict[str, float]:
    """Return stable, labeled percentile summaries for a finite vector."""
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or len(data) == 0 or not np.isfinite(data).all():
        raise ValueError("percentile input must be a non-empty finite vector")
    percentiles = np.percentile(data, [0, 10, 50, 90, 100])
    labels = ("min", "q10", "median", "q90", "max")
    return {label: round(float(value), 6) for label, value in zip(labels, percentiles)}
