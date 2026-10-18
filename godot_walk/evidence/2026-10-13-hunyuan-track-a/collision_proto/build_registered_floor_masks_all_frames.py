"""Stream the same candidate floor-mask rule across every registered frame."""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT_DIR = HERE / "registered_floor_masks_all_frames"
OUTPUT_GRID = OUTPUT_DIR / "registered_floor_mask_support_all_192.npz"
OUTPUT_REPORT = OUTPUT_DIR / "registered_floor_mask_support_all_192_report.json"
sys.path.insert(0, str(ROOT / "scripts" / "splat_pipeline"))
sys.path.insert(0, str(HERE))

from collision_params import contract_from_path
from colmap_model import read_cameras, read_images
from measure_splat_frame import cameras_in_ply_frame, load_dataparser
from registered_floor_masks import (
    GRID_SPACING_M,
    MASK_SAMPLE_STRIDE,
    MASK_TOP_ROW,
    FrameContext,
    candidate_band_pixels,
    floor_intersections,
    support_metrics,
)
from source_inputs import sha256_file
from source_support import SupportGrid, validate_alignment_manifest

ALIGNMENT_PATH = ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
COLMAP_PATH = ROOT / "data/scenes/corridor_travel/sparse/0"
DATAPARSER_PATH = ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
IMAGES_PATH = ROOT / "data/scenes/corridor_travel/images"
GRID_MARGIN_CELLS = 6


def image_number(name: str) -> int:
    """Parse the video frame index embedded in a registered image name."""
    stem = Path(name).stem
    if not stem.startswith("frame_") or not stem[6:].isdigit():
        raise ValueError(f"unexpected registered image name: {name}")
    return int(stem[6:])


def accumulate_frame_hits(
    cell_counts: dict[tuple[int, int], int],
    points_world: np.ndarray,
    spacing_m: float = GRID_SPACING_M,
) -> tuple[int, int]:
    """Bin one frame immediately and retain only per-cell hit counts."""
    if points_world.ndim != 2 or points_world.shape[1] != 3:
        raise ValueError("floor hits must be an N x 3 array")
    if not np.isfinite(points_world).all() or spacing_m <= 0.0:
        raise ValueError("floor hits and grid spacing must be finite and valid")
    columns = np.floor(points_world[:, 0] / spacing_m).astype(np.int64)
    rows = np.floor(points_world[:, 2] / spacing_m).astype(np.int64)
    indices, counts = np.unique(
        np.column_stack((rows, columns)), axis=0, return_counts=True
    )
    for (row, column), count in zip(indices, counts, strict=True):
        key = (int(row), int(column))
        cell_counts[key] = cell_counts.get(key, 0) + int(count)
    return len(points_world), len(indices)


def grid_from_counts(
    cell_counts: dict[tuple[int, int], int],
    cameras_world: np.ndarray,
    floor_height_m: float,
) -> tuple[SupportGrid, np.ndarray]:
    """Materialize a bounded grid after streaming has found all occupied keys."""
    if not cell_counts:
        raise ValueError("no candidate pixels intersected the declared floor plane")
    camera_columns = np.floor(cameras_world[:, 0] / GRID_SPACING_M).astype(np.int64)
    camera_rows = np.floor(cameras_world[:, 2] / GRID_SPACING_M).astype(np.int64)
    cell_rows = np.fromiter((row for row, _ in cell_counts), dtype=np.int64)
    cell_columns = np.fromiter((column for _, column in cell_counts), dtype=np.int64)
    min_row = min(int(cell_rows.min()), int(camera_rows.min())) - GRID_MARGIN_CELLS
    max_row = max(int(cell_rows.max()), int(camera_rows.max())) + GRID_MARGIN_CELLS
    min_column = (
        min(int(cell_columns.min()), int(camera_columns.min())) - GRID_MARGIN_CELLS
    )
    max_column = (
        max(int(cell_columns.max()), int(camera_columns.max())) + GRID_MARGIN_CELLS
    )
    shape = (max_row - min_row + 1, max_column - min_column + 1)
    hits = np.zeros(shape, dtype=np.int32)
    for (row, column), count in cell_counts.items():
        hits[row - min_row, column - min_column] = count
    heights = np.full(shape, np.nan, dtype=np.float64)
    heights[hits > 0] = floor_height_m
    origin_x = min_column * GRID_SPACING_M
    origin_z = min_row * GRID_SPACING_M
    return SupportGrid(origin_x, origin_z, GRID_SPACING_M, heights), hits


def build() -> dict:
    """Stream all masks and rays without retaining per-frame point clouds."""
    started = time.monotonic()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    alignment = json.loads(ALIGNMENT_PATH.read_text(encoding="utf-8"))
    frame_contract = validate_alignment_manifest(alignment, "corridor_splat")
    contract = contract_from_path(ALIGNMENT_PATH)
    dataparser = load_dataparser(str(DATAPARSER_PATH))
    raw_images = read_images(COLMAP_PATH)
    images = sorted(raw_images, key=lambda image: image_number(image.name))
    cameras = read_cameras(COLMAP_PATH)
    frame_numbers = [image_number(image.name) for image in images]
    if len(images) != 192 or set(frame_numbers) != set(range(1, 193)):
        raise ValueError("expected 192 uniquely named registered source frames")
    centers_ply = cameras_in_ply_frame(raw_images, dataparser)
    centers_by_frame = {
        image_number(image.name): contract.ply_to_world.world_point(center)
        for image, center in zip(raw_images, centers_ply, strict=True)
    }
    camera_centres = np.stack(
        [centers_by_frame[image_number(image.name)] for image in images]
    )
    bound_residual = max(
        float(np.max(np.abs(camera_centres.min(axis=0) - contract.cameras.world_min))),
        float(np.max(np.abs(camera_centres.max(axis=0) - contract.cameras.world_max))),
    )
    if bound_residual > 1e-6:
        raise ValueError("mapped source-camera bounds do not match the #100 contract")
    cell_counts: dict[tuple[int, int], int] = {}
    frame_records = []
    total_hits = 0
    total_candidate_pixels = 0
    max_floor_residual = 0.0
    total_elapsed_projection = 0.0
    for image in images:
        image_path = IMAGES_PATH / image.name
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        camera = cameras[image.camera_id]
        pixels = candidate_band_pixels(
            camera.width, camera.height, MASK_TOP_ROW, MASK_SAMPLE_STRIDE
        )
        frame_start = time.monotonic()
        points, projection = floor_intersections(
            pixels,
            FrameContext(image=image, camera=camera),
            dataparser,
            contract.ply_to_world,
            contract.collider.floor_height,
        )
        hit_count, occupied_cells = accumulate_frame_hits(cell_counts, points)
        total_elapsed_projection += time.monotonic() - frame_start
        total_hits += hit_count
        total_candidate_pixels += len(pixels)
        max_floor_residual = max(
            max_floor_residual, projection["max_abs_floor_residual_m"]
        )
        frame_records.append(
            {
                "frame_number_1_based": image_number(image.name),
                "registered_image": image.name,
                "source_sha256": sha256_file(image_path),
                "candidate_pixels": len(pixels),
                "forward_floor_hits": hit_count,
                "frame_occupied_cells": occupied_cells,
            }
        )
        del pixels, points
    grid, hit_counts = grid_from_counts(
        cell_counts, camera_centres, contract.collider.floor_height
    )
    metrics = support_metrics(grid, camera_centres[:, [0, 2]])
    np.savez_compressed(
        OUTPUT_GRID,
        heights_m=grid.heights_m.astype(np.float32),
        observed=grid.observed.astype(np.uint8),
        hit_counts=hit_counts,
        origin_x_m=np.float64(grid.origin_x_m),
        origin_z_m=np.float64(grid.origin_z_m),
        spacing_m=np.float64(grid.spacing_m),
        frame_numbers=np.asarray(
            [image_number(image.name) for image in images], dtype=np.int16
        ),
    )
    report = {
        "schema_version": 1,
        "issue": 135,
        "status": "evidence_only_route_support_failed",
        "asset_status": "not_collision_not_runtime_imported",
        "gpu_used": False,
        "inference_run": False,
        "metric_scale_accepted": False,
        "scale_kind": frame_contract["scale_kind"],
        "scale_note": "#100's chosen scale is a synthetic coordinate convention, not surveyed metric scale.",
        "floor_height_m": contract.collider.floor_height,
        "mask_rule": {
            "candidate_only": True,
            "human_reviewed": False,
            "rule": f"all pixels v >= {MASK_TOP_ROW}; fixed {MASK_SAMPLE_STRIDE}-pixel stride; no semantic inference",
            "illustrative_contact_sheet": "../registered_floor_masks/mask_contact_sheet.jpg",
            "frame_count": len(images),
        },
        "streaming": {
            "per_frame_masks_or_point_clouds_retained": False,
            "retained_accumulator": "occupied 5cm grid-cell hit counts only",
            "camera_pose_metadata_loaded_once": True,
            "source_image_pixels_read": False,
            "source_image_hashes_recorded": True,
        },
        "inputs": {
            "alignment_manifest_sha256": sha256_file(ALIGNMENT_PATH),
            "colmap_images_sha256": sha256_file(COLMAP_PATH / "images.bin"),
            "colmap_cameras_sha256": sha256_file(COLMAP_PATH / "cameras.bin"),
            "dataparser_sha256": sha256_file(DATAPARSER_PATH),
            "registered_image_count": len(images),
            "camera_model": "SIMPLE_RADIAL",
            "camera_parameters": list(cameras[images[0].camera_id].params),
            "mapped_camera_bounds_match_contract": bound_residual <= 1e-6,
            "max_camera_bound_residual_m": bound_residual,
        },
        "projection": {
            "candidate_pixels_total": total_candidate_pixels,
            "forward_floor_hits_total": total_hits,
            "max_abs_floor_plane_residual_m": max_floor_residual,
            "total_projection_binning_seconds": total_elapsed_projection,
            "per_frame": frame_records,
        },
        "grid": {
            **metrics,
            "hit_count_total": int(hit_counts.sum()),
            "origin_xz_m": [grid.origin_x_m, grid.origin_z_m],
            "grid_file": OUTPUT_GRID.name,
            "unknown_cells_filled": 0,
        },
        "decision": {
            "coverage_at_0_30m": metrics["coverage_radius_sensitivity"]["0.3"],
            "coverage_at_1_00m": metrics["coverage_radius_sensitivity"]["1.0"],
            "physics_tested": False,
            "reason": "The 0.30m camera-path support gate fails; no morphology, gap bridging, GPU, or physics test was used.",
        },
        "execution": {
            "elapsed_seconds": time.monotonic() - started,
            "peak_process_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "grid_archive_bytes": OUTPUT_GRID.stat().st_size,
        },
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
