"""Read-only #100 geometry and registered-camera inputs for the prototype."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import splat_geometry
import splat_ply
from colmap_model import read_images
from measure_splat_frame import cameras_in_ply_frame, load_dataparser

FLOOR_BAND_M = 0.05
NORMAL_COSINE = float(np.cos(np.deg2rad(30.0)))
CAMERA_MARGIN_M = 0.30
ROUTE_SAMPLE_RADIUS_M = 0.30


def sha256_file(path: Path) -> str:
    """Hash a source file in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_camera_centres(
    contract, colmap_path: Path, dataparser_path: Path
) -> np.ndarray:
    """Map registered COLMAP cameras through the recorded #100 frame."""
    images = read_images(colmap_path)
    dataparser = load_dataparser(str(dataparser_path))
    centres_ply = cameras_in_ply_frame(images, dataparser)
    centres_world = np.stack(
        [contract.ply_to_world.world_point(point) for point in centres_ply]
    )
    if len(centres_world) != contract.cameras.count:
        raise ValueError("registered camera count does not match the #100 contract")
    if not np.allclose(
        centres_world.min(axis=0), contract.cameras.world_min, atol=1e-6
    ):
        raise ValueError("mapped camera minimum does not match the #100 contract")
    if not np.allclose(
        centres_world.max(axis=0), contract.cameras.world_max, atol=1e-6
    ):
        raise ValueError("mapped camera maximum does not match the #100 contract")
    return centres_world


def world_gaussian_geometry(ply_path: Path, contract) -> tuple[np.ndarray, np.ndarray]:
    """Load only centres and unsigned shortest-axis normals in Godot world."""
    positions = splat_ply.read_positions(ply_path)
    quaternions = splat_ply.read_columns(ply_path, ("rot_0", "rot_1", "rot_2", "rot_3"))
    scales = np.exp(splat_ply.read_columns(ply_path, ("scale_0", "scale_1", "scale_2")))
    normals = splat_geometry.gaussian_normal_axes(scales, quaternions)
    world_positions = np.stack(
        [contract.ply_to_world.world_point(point) for point in positions]
    )
    world_normals = np.stack(
        [contract.ply_to_world.world_vector(normal) for normal in normals]
    )
    world_normals /= np.maximum(np.linalg.norm(world_normals, axis=1)[:, None], 1e-30)
    return world_positions, world_normals


def select_floor_samples(
    world_positions: np.ndarray,
    world_normals: np.ndarray,
    floor_y_m: float,
    cameras_world: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Select vertical-normal splat centres close to the declared floor."""
    camera_xz = cameras_world[:, [0, 2]]
    lower = camera_xz.min(axis=0) - CAMERA_MARGIN_M
    upper = camera_xz.max(axis=0) + CAMERA_MARGIN_M
    in_window = np.all(
        (world_positions[:, [0, 2]] >= lower) & (world_positions[:, [0, 2]] <= upper),
        axis=1,
    )
    floor_distance = np.abs(world_positions[:, 1] - floor_y_m)
    floor_oriented = np.abs(world_normals[:, 1]) >= NORMAL_COSINE
    selected = in_window & floor_oriented & (floor_distance <= FLOOR_BAND_M)
    quantiles = (
        np.quantile(floor_distance[selected], [0.50, 0.90, 0.95]).tolist()
        if selected.any()
        else None
    )
    return world_positions[selected], {
        "floor_normal_candidates_in_camera_window": int(
            (in_window & floor_oriented).sum()
        ),
        "selected_floor_samples": int(selected.sum()),
        "selected_floor_height_residual_abs_q50_q90_q95_m": quantiles,
        "floor_band_m": FLOOR_BAND_M,
        "normal_threshold_degrees": 30.0,
        "camera_xz_window_expansion_m": CAMERA_MARGIN_M,
    }


def grid_parameters(
    cameras_world: np.ndarray, spacing_m: float
) -> tuple[float, float, tuple[int, int]]:
    """Bound the grid to registered camera XZ plus a capsule-radius margin."""
    camera_xz = cameras_world[:, [0, 2]]
    low = camera_xz.min(axis=0) - CAMERA_MARGIN_M
    high = camera_xz.max(axis=0) + CAMERA_MARGIN_M
    origin_x = math.floor(low[0] / spacing_m) * spacing_m
    origin_z = math.floor(low[1] / spacing_m) * spacing_m
    columns = math.ceil((high[0] - origin_x) / spacing_m)
    rows = math.ceil((high[1] - origin_z) / spacing_m)
    return origin_x, origin_z, (rows, columns)


def camera_sample_coverage(
    grid, supported: np.ndarray, cameras_world: np.ndarray
) -> dict:
    """Measure camera-centre proximity to support samples, not traversal."""
    rows, columns = np.nonzero(supported)
    if len(rows) == 0:
        return {
            "supported_camera_samples_within_radius": 0,
            "count": len(cameras_world),
            "minimum_distance_q50_q90_q95_max_m": None,
        }
    points = np.column_stack(
        (
            grid.origin_x_m + (columns + 0.5) * grid.spacing_m,
            grid.origin_z_m + (rows + 0.5) * grid.spacing_m,
        )
    )
    delta = cameras_world[:, None, [0, 2]] - points[None, :, :]
    nearest = np.sqrt(np.sum(delta * delta, axis=2)).min(axis=1)
    return {
        "supported_camera_samples_within_radius": int(
            (nearest <= ROUTE_SAMPLE_RADIUS_M).sum()
        ),
        "count": len(cameras_world),
        "radius_m": ROUTE_SAMPLE_RADIUS_M,
        "minimum_distance_q50_q90_q95_max_m": np.quantile(
            nearest, [0.50, 0.90, 0.95, 1.0]
        ).tolist(),
    }
