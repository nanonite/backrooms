"""Unreviewed lower-image floor candidates projected onto the #100 plane."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label
from scipy.spatial import cKDTree
from source_support import SupportGrid, filter_support

MASK_TOP_ROW = 930
MASK_SAMPLE_STRIDE = 4
GRID_SPACING_M = 0.05
MASK_FRAME_NUMBERS = tuple(range(9, 186, 8)) + (141,)
COMPONENT_STRUCTURE = np.ones((3, 3), dtype=np.uint8)


@dataclass(frozen=True)
class FrameContext:
    """One registered COLMAP image with its shared camera intrinsics."""

    image: object
    camera: object


def candidate_mask(width: int, height: int, top_row: int = MASK_TOP_ROW) -> np.ndarray:
    """Return the explicit bottom-band candidate crop; it is not semantic GT."""
    if width < 1 or height < 1 or not 0 <= top_row < height:
        raise ValueError("invalid candidate-mask image dimensions")
    mask = np.zeros((height, width), dtype=bool)
    mask[top_row:, :] = True
    return mask


def undistort_simple_radial(
    pixels: np.ndarray, focal: float, center_x: float, center_y: float, radial: float
) -> np.ndarray:
    """Invert COLMAP SIMPLE_RADIAL distortion by fixed-point iteration."""
    points = np.asarray(pixels, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError("pixels must be a finite N x 2 array")
    if focal <= 0.0 or not np.isfinite([focal, center_x, center_y, radial]).all():
        raise ValueError("camera intrinsics must be finite and focal length positive")
    distorted = (points - np.array([center_x, center_y])) / focal
    undistorted = distorted.copy()
    for _ in range(15):
        radius_squared = np.sum(undistorted * undistorted, axis=1)
        scale = 1.0 + radial * radius_squared
        if np.any(np.abs(scale) < 1e-8):
            raise ValueError("radial inverse became singular")
        undistorted = distorted / scale[:, None]
    return undistorted


def floor_intersections(
    pixels: np.ndarray,
    context: FrameContext,
    dataparser: dict,
    mapping,
    floor_height_m: float,
) -> tuple[np.ndarray, dict]:
    """Map distorted image pixels through COLMAP/#100 and intersect the floor."""
    camera = context.camera
    if camera.model != "SIMPLE_RADIAL" or len(camera.params) != 4:
        raise ValueError("only the registered SIMPLE_RADIAL camera is supported")
    focal, center_x, center_y, radial = camera.params
    normalized = undistort_simple_radial(pixels, focal, center_x, center_y, radial)
    rays_camera = np.column_stack((normalized, np.ones(len(normalized))))
    rays_colmap = rays_camera @ context.image.rotation_w2c
    rays_ply = rays_colmap @ dataparser["rotation"].T
    rays_world = rays_ply @ mapping.rotation().T * mapping.metres_per_unit
    center_ply = (
        context.image.camera_center @ dataparser["rotation"].T + dataparser["origin"]
    ) * dataparser["scale"]
    origin_world = mapping.world_point(center_ply)
    downward = rays_world[:, 1] < -1e-8
    parameters = np.full(len(pixels), np.nan, dtype=np.float64)
    parameters[downward] = (floor_height_m - origin_world[1]) / rays_world[downward, 1]
    forward = downward & np.isfinite(parameters) & (parameters > 0.0)
    intersections = origin_world + parameters[forward, None] * rays_world[forward]
    return intersections, {
        "candidate_pixels": len(pixels),
        "rays_downward": int(downward.sum()),
        "forward_floor_intersections": int(forward.sum()),
        "rejected_up_or_horizontal": int((~downward).sum()),
        "rejected_behind_camera": int((downward & ~forward).sum()),
        "max_abs_floor_residual_m": float(
            np.max(np.abs(intersections[:, 1] - floor_height_m))
            if len(intersections)
            else 0.0
        ),
    }


def mask_pixels(mask: np.ndarray, stride: int = MASK_SAMPLE_STRIDE) -> np.ndarray:
    """Subsample true pixel centres without changing the displayed mask."""
    if mask.ndim != 2 or stride < 1:
        raise ValueError("mask must be 2D and sample stride must be positive")
    rows, columns = np.nonzero(mask[::stride, ::stride])
    return np.column_stack((columns * stride + stride / 2, rows * stride + stride / 2))


def candidate_band_pixels(
    width: int,
    height: int,
    top_row: int = MASK_TOP_ROW,
    stride: int = MASK_SAMPLE_STRIDE,
) -> np.ndarray:
    """Sample the same crop mask without allocating a full-resolution mask."""
    if width < 1 or height < 1 or stride < 1 or not 0 <= top_row < height:
        raise ValueError("invalid candidate-band sampling parameters")
    sampled_rows = np.arange(0, height, stride)
    sampled_columns = np.arange(0, width, stride)
    sampled_rows = sampled_rows[sampled_rows >= top_row]
    row_grid, column_grid = np.meshgrid(sampled_rows, sampled_columns, indexing="ij")
    return np.column_stack(
        (
            column_grid.ravel() + stride / 2,
            row_grid.ravel() + stride / 2,
        )
    )


def path_gap_summary(
    segment_nearest_m: np.ndarray,
    segment_lengths_m: np.ndarray,
    radius_m: float,
) -> dict:
    """Summarize unsupported consecutive camera-path intervals at one radius."""
    distances = np.asarray(segment_nearest_m, dtype=np.float64)
    lengths = np.asarray(segment_lengths_m, dtype=np.float64)
    if distances.ndim != 1 or lengths.shape != distances.shape:
        raise ValueError("segment distances and lengths must be matching 1D arrays")
    if radius_m <= 0.0 or not np.isfinite(radius_m):
        raise ValueError("coverage radius must be finite and positive")
    unsupported = distances > radius_m
    padded = np.concatenate(([False], unsupported, [False])).astype(np.int8)
    starts = np.flatnonzero(np.diff(padded) == 1)
    ends = np.flatnonzero(np.diff(padded) == -1)
    run_lengths = ends - starts
    run_distances = [
        float(lengths[start:end].sum()) for start, end in zip(starts, ends, strict=True)
    ]
    runs = [
        {
            "start_segment_index_0_based": int(start),
            "end_segment_index_exclusive": int(end),
            "segment_count": int(end - start),
            "path_length_m": float(lengths[start:end].sum()),
        }
        for start, end in zip(starts, ends, strict=True)
    ]
    return {
        "unsupported_segment_count": int(unsupported.sum()),
        "unsupported_segment_path_length_m": float(lengths[unsupported].sum()),
        "unsupported_gap_count": len(run_lengths),
        "longest_unsupported_segment_run_count": int(run_lengths.max())
        if len(run_lengths)
        else 0,
        "longest_consecutive_gap_m": max(run_distances, default=0.0),
        "unsupported_segment_runs": runs,
    }


def mask_overlay(image_path, mask: np.ndarray, destination) -> None:
    """Save a translucent audit overlay, with the crop rule printed on-image."""
    source = Image.open(image_path).convert("RGB")
    if source.size != (mask.shape[1], mask.shape[0]):
        raise ValueError("candidate mask shape does not match source image")
    tint = Image.new("RGBA", source.size, (0, 0, 0, 0))
    overlay = Image.new("RGBA", source.size, (39, 172, 103, 74))
    tint.alpha_composite(
        Image.composite(
            overlay,
            Image.new("RGBA", source.size),
            Image.fromarray(mask.astype(np.uint8) * 255),
        )
    )
    output = Image.alpha_composite(source.convert("RGBA"), tint)
    draw = ImageDraw.Draw(output)
    draw.rectangle(
        (0, MASK_TOP_ROW, source.width - 1, source.height - 1),
        outline=(0, 255, 160, 255),
        width=3,
    )
    draw.rectangle((8, 8, 720, 48), fill=(0, 0, 0, 190))
    draw.text(
        (18, 17),
        f"candidate only / unreviewed / rows >= {MASK_TOP_ROW}",
        fill=(255, 255, 255, 255),
    )
    output.convert("RGB").save(destination, quality=90)


def support_metrics(
    grid: SupportGrid, camera_xz: np.ndarray, radius_m: float = 0.30
) -> dict:
    """Measure observed cells, components, and camera-path proximity gaps."""
    filtered = filter_support(grid, 15.0, 0.20)
    rows, columns = np.nonzero(filtered.supported)
    support_xz = np.column_stack(
        (
            grid.origin_x_m + (columns + 0.5) * grid.spacing_m,
            grid.origin_z_m + (rows + 0.5) * grid.spacing_m,
        )
    )
    if not len(support_xz):
        nearest = np.full(len(camera_xz), np.inf)
        segment_nearest = np.full(max(0, len(camera_xz) - 1), np.inf)
        components = np.zeros_like(filtered.supported, dtype=np.int32)
        component_sizes: list[int] = []
    else:
        tree = cKDTree(support_xz)
        nearest = tree.query(camera_xz)[0]
        midpoints = (camera_xz[:-1] + camera_xz[1:]) / 2.0
        segment_nearest = tree.query(midpoints)[0] if len(midpoints) else np.array([])
        components, _ = label(filtered.supported, structure=COMPONENT_STRUCTURE)
        counts = np.bincount(components.ravel())
        component_sizes = sorted((int(value) for value in counts[1:]), reverse=True)
    observed = grid.observed
    segment_lengths = np.linalg.norm(np.diff(camera_xz, axis=0), axis=1)
    radius_coverage = {
        str(radius): {
            "camera_sample_fraction": float(np.mean(nearest <= radius))
            if len(nearest)
            else 0.0,
            "segment_midpoint_fraction": float(np.mean(segment_nearest <= radius))
            if len(segment_nearest)
            else 0.0,
            "path_gaps": path_gap_summary(segment_nearest, segment_lengths, radius),
        }
        for radius in (0.30, 0.50, 1.00, 1.50, 2.00)
    }
    return {
        "grid_spacing_m": grid.spacing_m,
        "grid_shape_rows_z_columns_x": list(grid.heights_m.shape),
        "observed_cells": int(observed.sum()),
        "unknown_cells": int((~observed).sum()),
        "unknown_cells_filled": 0,
        "supported_cells_after_slope_step_filter": int(filtered.supported.sum()),
        "connected_component_count_8_connected": len(component_sizes),
        "component_cell_counts_descending": component_sizes[:20],
        "support_area_m2": float(filtered.supported.sum() * grid.spacing_m**2),
        "camera_samples_within_radius": int((nearest <= radius_m).sum()),
        "camera_sample_count": len(camera_xz),
        "camera_coverage_fraction": float(np.mean(nearest <= radius_m))
        if len(nearest)
        else 0.0,
        "camera_nearest_distance_q50_q90_q95_max_m": np.quantile(
            nearest, [0.5, 0.9, 0.95, 1.0]
        ).tolist()
        if len(nearest)
        else None,
        "adjacent_camera_segment_midpoints_within_radius": int(
            (segment_nearest <= radius_m).sum()
        ),
        "adjacent_camera_segment_count": len(segment_nearest),
        "segment_midpoint_coverage_fraction": float(
            np.mean(segment_nearest <= radius_m)
        )
        if len(segment_nearest)
        else 0.0,
        "segment_midpoint_nearest_distance_max_m": float(np.max(segment_nearest))
        if len(segment_nearest)
        else None,
        "coverage_radius_m": radius_m,
        "coverage_radius_sensitivity": radius_coverage,
    }


def insert_unknown_hole(
    grid: SupportGrid, center_xz: np.ndarray, radius_m: float
) -> SupportGrid:
    """Return a negative-control grid with a circular unknown region."""
    if radius_m <= 0.0 or not np.isfinite(radius_m):
        raise ValueError("hole radius must be finite and positive")
    heights = grid.heights_m.copy()
    rows, columns = np.indices(heights.shape)
    x = grid.origin_x_m + (columns + 0.5) * grid.spacing_m
    z = grid.origin_z_m + (rows + 0.5) * grid.spacing_m
    hole = (x - center_xz[0]) ** 2 + (z - center_xz[1]) ** 2 <= radius_m**2
    heights[hole] = np.nan
    return SupportGrid(grid.origin_x_m, grid.origin_z_m, grid.spacing_m, heights)
