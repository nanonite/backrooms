"""Build an explicitly assumed, evidence-only camera-path support grid."""

from __future__ import annotations

import csv
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
COLLISION_PROTO = HERE.parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "splat_pipeline"))
sys.path.insert(0, str(COLLISION_PROTO))

from camera_path_prior import (
    component_count,
    erase_hole,
    nearest_distances,
    rasterize_strip,
)
from collision_params import contract_from_path
from colmap_model import read_images
from measure_splat_frame import cameras_in_ply_frame, load_dataparser
from registered_floor_masks import path_gap_summary
from source_support import SupportGridError, validate_alignment_manifest

ALIGNMENT_PATH = ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
COLMAP_PATH = ROOT / "data/scenes/corridor_travel/sparse/0"
DATAPARSER_PATH = ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
OUTPUT_GRID = HERE / "camera_path_prior_non_collider.npz"
OUTPUT_REPORT = HERE / "CAMERA_PATH_PRIOR_NON_COLLIDER.json"
OUTPUT_CENTRES = HERE / "registered_camera_centres_godot_world.csv"
SPACING_M = 0.05
WIDTHS_M = (0.8, 1.2, 1.6)
GRID_MARGIN_M = 0.30
HOLE_FRAME_1_BASED = 97
HOLE_EXTRA_RADIUS_M = 0.15
ROUTE_TOLERANCES_M = (0.05, 0.30, 1.00)


def image_number(name: str) -> int:
    """Parse the numeric video frame in a registered image name."""
    stem = Path(name).stem
    if not stem.startswith("frame_") or not stem[6:].isdigit():
        raise ValueError(f"unexpected registered image name: {name}")
    return int(stem[6:])


def sha256_file(path: Path) -> str:
    """Hash a small alignment input in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_ordered_cameras(contract) -> tuple[list[int], np.ndarray, float]:
    """Map the sorted COLMAP camera centres through the declared #100 frame."""
    images = sorted(
        read_images(COLMAP_PATH), key=lambda image: image_number(image.name)
    )
    numbers = [image_number(image.name) for image in images]
    if len(images) != 192 or numbers != list(range(1, 193)):
        raise ValueError("expected frames 1 through 192 in registered COLMAP order")

    dataparser = load_dataparser(str(DATAPARSER_PATH))
    centres_ply = cameras_in_ply_frame(images, dataparser)
    centres_world = np.stack(
        [contract.ply_to_world.world_point(point) for point in centres_ply]
    )
    bounds_residual = max(
        float(np.max(np.abs(centres_world.min(axis=0) - contract.cameras.world_min))),
        float(np.max(np.abs(centres_world.max(axis=0) - contract.cameras.world_max))),
    )
    if bounds_residual > 1e-6:
        raise ValueError("camera centres do not match the declared #100 bounds")
    return numbers, centres_world, bounds_residual


def grid_bounds(path_xz: np.ndarray) -> tuple[tuple[float, float], tuple[int, int]]:
    """Return one aligned grid covering the largest strip plus unknown margin."""
    radius = max(WIDTHS_M) * 0.5 + GRID_MARGIN_M
    low = np.floor((path_xz.min(axis=0) - radius) / SPACING_M) * SPACING_M
    high = path_xz.max(axis=0) + radius
    shape = tuple(np.ceil((high - low) / SPACING_M).astype(int).tolist())
    return (float(low[0]), float(low[1])), (shape[1], shape[0])


def coverage_record(grid, points, origin, tolerance_m: float) -> dict:
    """Measure distance to synthetic support cell centres, not actual floor."""
    distances = nearest_distances(grid, points, origin, SPACING_M)
    supported = distances <= tolerance_m
    quantiles = np.quantile(distances, [0.0, 0.5, 0.9, 0.95, 1.0])
    return {
        "within_tolerance_count": int(supported.sum()),
        "sample_count": len(points),
        "fraction": float(supported.mean()),
        "tolerance_m": tolerance_m,
        "nearest_cell_centre_distance_min_q50_q90_q95_max_m": quantiles.tolist(),
    }


def route_metrics(grid, cameras_xz, midpoints_xz, segment_lengths, origin) -> dict:
    """Report generated-grid coverage at camera and segment samples."""
    midpoint_distances = nearest_distances(grid, midpoints_xz, origin, SPACING_M)
    return {
        "camera_centres": {
            f"{tolerance:.2f}m": coverage_record(grid, cameras_xz, origin, tolerance)
            for tolerance in ROUTE_TOLERANCES_M
        },
        "adjacent_camera_segment_midpoints": {
            f"{tolerance:.2f}m": coverage_record(grid, midpoints_xz, origin, tolerance)
            for tolerance in ROUTE_TOLERANCES_M
        },
        "unsupported_midpoint_gaps_at_0_30m": path_gap_summary(
            midpoint_distances, segment_lengths, 0.30
        ),
    }


def transformed_path_coverage(grid, path_xz, origin, transform) -> dict:
    """Measure how wrong-axis or wrong-scale route controls miss this grid."""
    wrong_path = transform(path_xz)
    result = coverage_record(grid, wrong_path, origin, 0.30)
    result["wrong_path_bounds_xz_m"] = [
        wrong_path.min(axis=0).tolist(),
        wrong_path.max(axis=0).tolist(),
    ]
    return result


def invalid_manifest_controls(alignment: dict) -> dict:
    """Confirm the #100 contract validator rejects doubled scale and bad up axis."""
    controls = {}
    wrong_scale = lambda document: document["ply_to_world"].update(
        metres_per_unit=2.0 * document["ply_to_world"]["metres_per_unit"]
    )
    wrong_axis = lambda document: document["ply_to_world"].update(up_axis="x")
    for name, mutate in (
        ("scale_doubled", wrong_scale),
        ("up_axis_mislabeled", wrong_axis),
    ):
        changed = json.loads(json.dumps(alignment))
        mutate(changed)
        try:
            validate_alignment_manifest(changed, "corridor_splat")
        except SupportGridError as error:
            controls[name] = {"rejected": True, "reason": str(error)}
        else:
            controls[name] = {"rejected": False, "reason": "unexpectedly accepted"}
    return controls


def write_camera_csv(numbers: list[int], centres_world: np.ndarray) -> None:
    """Save the ordered camera-centre samples used as the prior."""
    with OUTPUT_CENTRES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("video_frame_1_based", "x_m", "y_m", "z_m"))
        writer.writerows(
            (number, *(float(value) for value in point))
            for number, point in zip(numbers, centres_world, strict=True)
        )


def build() -> dict:
    """Write distinct non-collider grids for the three width hypotheses."""
    started = time.monotonic()
    alignment = json.loads(ALIGNMENT_PATH.read_text(encoding="utf-8"))
    frame_contract = validate_alignment_manifest(alignment, "corridor_splat")
    contract = contract_from_path(ALIGNMENT_PATH)
    numbers, centres_world, bounds_residual = load_ordered_cameras(contract)
    cameras_xz = centres_world[:, [0, 2]]
    midpoints_xz = 0.5 * (cameras_xz[:-1] + cameras_xz[1:])
    segment_lengths = np.linalg.norm(np.diff(cameras_xz, axis=0), axis=1)
    origin, shape = grid_bounds(cameras_xz)
    hole_center = cameras_xz[HOLE_FRAME_1_BASED - 1]
    width_grids = {}
    hole_grids = {}
    variants = {}

    for width in WIDTHS_M:
        key = f"width_{width:.1f}m".replace(".", "p")
        support = rasterize_strip(cameras_xz, SPACING_M, width, origin, shape)
        hole_radius = width * 0.5 + HOLE_EXTRA_RADIUS_M
        with_hole = erase_hole(
            support, origin, SPACING_M, tuple(hole_center), hole_radius
        )
        path_direction = (
            cameras_xz[HOLE_FRAME_1_BASED] - cameras_xz[HOLE_FRAME_1_BASED - 2]
        )
        path_direction /= np.linalg.norm(path_direction)
        path_normal = np.asarray([-path_direction[1], path_direction[0]])
        off_path_points = np.stack(
            (hole_center + 3.0 * path_normal, hole_center - 3.0 * path_normal)
        )
        width_grids[key] = support.astype(np.uint8)
        hole_grids[key] = with_hole.astype(np.uint8)
        variants[key] = {
            "hypothesis_total_width_m": width,
            "raster_rule": "cell centre within total_width/2 of the ordered registered-camera XZ polyline",
            "supported_cell_count": int(support.sum()),
            "support_area_by_cell_centres_m2": float(support.sum() * SPACING_M**2),
            "connected_components_8_neighbour": component_count(support),
            "route_metrics": route_metrics(
                support, cameras_xz, midpoints_xz, segment_lengths, origin
            ),
            "off_path_control": transformed_path_coverage(
                support,
                cameras_xz,
                origin,
                lambda path: path + [3.0, 0.0],
            ),
            "frame_97_local_lateral_controls": {
                "offset_m": 3.0,
                "normal_xz": path_normal.tolist(),
                "plus_side": coverage_record(
                    support, off_path_points[:1], origin, 0.30
                ),
                "minus_side": coverage_record(
                    support, off_path_points[1:], origin, 0.30
                ),
            },
            "wrong_axis_control": transformed_path_coverage(
                support, cameras_xz, origin, lambda path: path[:, ::-1]
            ),
            "wrong_scale_2x_control": transformed_path_coverage(
                support, cameras_xz, origin, lambda path: path * 2.0
            ),
            "hole_negative_control": {
                "frame_1_based": HOLE_FRAME_1_BASED,
                "center_xz_m": hole_center.tolist(),
                "radius_m": hole_radius,
                "removed_cell_count": int(support.sum() - with_hole.sum()),
                "supported_cell_count": int(with_hole.sum()),
                "connected_components_8_neighbour": component_count(with_hole),
                "route_metrics": route_metrics(
                    with_hole,
                    cameras_xz,
                    midpoints_xz,
                    segment_lengths,
                    origin,
                ),
            },
        }

    np.savez_compressed(
        OUTPUT_GRID,
        origin_xz_m=np.asarray(origin, dtype=np.float64),
        grid_shape=np.asarray(shape, dtype=np.int32),
        spacing_m=np.float64(SPACING_M),
        floor_height_m=np.float64(contract.collider.floor_height),
        frame_numbers_1_based=np.asarray(numbers, dtype=np.int16),
        camera_centres_godot_world_m=centres_world.astype(np.float64),
        **width_grids,
        **{f"hole_{key}": grid for key, grid in hole_grids.items()},
    )
    write_camera_csv(numbers, centres_world)

    report = {
        "schema_version": 1,
        "issue": 135,
        "status": "evidence_only_camera_path_prior_not_walkability_evidence",
        "asset_name": "camera-path-prior/non-collider",
        "asset_status": "not_collision_not_runtime_imported_not_a_floor_reconstruction",
        "gpu_used": False,
        "inference_run": False,
        "hunyuan_mesh_or_transform_used": False,
        "hunyuan_registration_accepted": False,
        "scale_kind": frame_contract["scale_kind"],
        "scale_note": "Uses only the #100 chosen 5.128383849 m/Nerfstudio-unit coordinate convention; it is not surveyed metric scale and does not transfer to Hunyuan.",
        "height_source": "#100 declared horizontal floor plane only; every synthetic cell shares its floor_height_m",
        "floor_height_m": contract.collider.floor_height,
        "registered_camera_count": len(numbers),
        "source_polyline_path_length_m": float(
            np.linalg.norm(np.diff(cameras_xz, axis=0), axis=1).sum()
        ),
        "grid": {
            "spacing_m": SPACING_M,
            "origin_xz_m": list(origin),
            "shape_rows_columns": list(shape),
            "unknown_outside_support_preserved": True,
            "unknown_filled": 0,
            "archive": OUTPUT_GRID.name,
            "camera_centres_csv": OUTPUT_CENTRES.name,
        },
        "hypothesis": {
            "camera_path_prior_only": True,
            "source_observed_floor_cells": 0,
            "not_reconstructed_scene_boundaries": True,
            "width_semantics": "total strip width is an explicit hypothetical supported band, not a camera-derived room width",
            "capsule_example": "0.8 m total = 0.30 m radius + 0.10 m clearance on each side",
            "segment_midpoints_tested": len(midpoints_xz),
            "variants": variants,
        },
        "negative_controls": {
            "wrong_alignment_manifest": invalid_manifest_controls(alignment),
            "off_path_translation_m": [3.0, 0.0],
            "wrong_axis": "swap world X and Z on the evaluated camera polyline",
            "wrong_scale": "multiply mapped world XZ by 2 about world origin",
            "deliberate_hole": "remove a disk wider than the strip half-width at registered frame 97; no infill",
        },
        "alignment": {
            "alignment_manifest_sha256": sha256_file(ALIGNMENT_PATH),
            "colmap_images_sha256": sha256_file(COLMAP_PATH / "images.bin"),
            "colmap_cameras_sha256": sha256_file(COLMAP_PATH / "cameras.bin"),
            "dataparser_sha256": sha256_file(DATAPARSER_PATH),
            "camera_bounds_match_contract": bounds_residual <= 1e-6,
            "max_bounds_residual_m": bounds_residual,
            "registration_residuals_to_source_geometry": None,
            "reason_residuals_absent": "The polyline is the registered camera input itself; no floor observations are being aligned to it.",
        },
        "physics": {
            "avian_or_tnua_tested": False,
            "reason_not_tested": "The prior creates its own route by assumption, so headless traversal would validate only synthetic support and cannot establish walkability on the mapped source or Hunyuan surfaces. No runtime collider is emitted.",
        },
        "execution": {
            "elapsed_seconds": time.monotonic() - started,
            "peak_process_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "archive_bytes": OUTPUT_GRID.stat().st_size,
        },
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
