"""Project auditable source-image floor candidates onto #100's chosen plane."""

from __future__ import annotations

import copy
import json
import resource
import struct
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT_DIR = HERE / "registered_floor_masks"
OVERLAY_DIR = OUTPUT_DIR / "overlays"
sys.path.insert(0, str(ROOT / "scripts" / "splat_pipeline"))
sys.path.insert(0, str(HERE))

from collision_params import contract_from_path
from colmap_model import read_cameras, read_images
from measure_splat_frame import load_dataparser
from registered_floor_masks import (
    GRID_SPACING_M,
    MASK_FRAME_NUMBERS,
    MASK_SAMPLE_STRIDE,
    MASK_TOP_ROW,
    FrameContext,
    candidate_mask,
    floor_intersections,
    insert_unknown_hole,
    mask_overlay,
    mask_pixels,
    support_metrics,
)
from source_inputs import load_camera_centres, sha256_file
from source_support import (
    SupportGrid,
    grid_from_points,
    validate_alignment_manifest,
)

ALIGNMENT_PATH = ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
COLMAP_PATH = ROOT / "data/scenes/corridor_travel/sparse/0"
DATAPARSER_PATH = ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
IMAGES_PATH = ROOT / "data/scenes/corridor_travel/images"
SOURCE_SELECTION_PATH = HERE.parent / "source_selection.json"
OUTPUT_GRID = OUTPUT_DIR / "registered_floor_mask_support_evidence.npz"
OUTPUT_REPORT = OUTPUT_DIR / "registered_floor_mask_support_report.json"
OUTPUT_CONTACT_SHEET = OUTPUT_DIR / "mask_contact_sheet.jpg"
GRID_MARGIN_M = 0.30
HOLE_RADIUS_M = 0.30


def image_number(name: str) -> int:
    """Parse the authoritative video frame number from a registered name."""
    stem = Path(name).stem
    prefix = "frame_"
    if not stem.startswith(prefix) or not stem[len(prefix) :].isdigit():
        raise ValueError(f"unexpected registered image name: {name}")
    return int(stem[len(prefix) :])


def make_contact_sheet(overlay_paths: list[Path]) -> None:
    """Assemble the selected unreviewed masks for visual audit."""
    width, height, columns = 480, 290, 4
    rows = (len(overlay_paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width, rows * height), (32, 35, 35))
    for index, path in enumerate(overlay_paths):
        with Image.open(path) as image:
            preview = image.convert("RGB").resize(
                (width, 270), Image.Resampling.LANCZOS
            )
        x, y = index % columns * width, index // columns * height
        sheet.paste(preview, (x, y))
        ImageDraw.Draw(sheet).text((x + 8, y + 272), path.stem, fill=(245, 245, 245))
    sheet.save(OUTPUT_CONTACT_SHEET, quality=90)


def make_grid(points: np.ndarray, cameras_world: np.ndarray) -> SupportGrid:
    """Bound observed mask hits and registered cameras, with unknown empty."""
    camera_xz = cameras_world[:, [0, 2]]
    all_xz = np.concatenate((points[:, [0, 2]], camera_xz), axis=0)
    lower = all_xz.min(axis=0) - GRID_MARGIN_M
    upper = all_xz.max(axis=0) + GRID_MARGIN_M
    origin_x = np.floor(lower[0] / GRID_SPACING_M) * GRID_SPACING_M
    origin_z = np.floor(lower[1] / GRID_SPACING_M) * GRID_SPACING_M
    shape = (
        int(np.ceil((upper[1] - origin_z) / GRID_SPACING_M)),
        int(np.ceil((upper[0] - origin_x) / GRID_SPACING_M)),
    )
    return grid_from_points(points, origin_x, origin_z, GRID_SPACING_M, shape)


def read_sparse_xyz(path: Path) -> dict[int, np.ndarray]:
    """Read COLMAP point IDs and XYZ values for reprojection diagnostics."""
    points: dict[int, np.ndarray] = {}
    with path.open("rb") as handle:
        count = struct.unpack("<Q", handle.read(8))[0]
        for _ in range(count):
            point_id = struct.unpack("<Q", handle.read(8))[0]
            xyz = np.asarray(struct.unpack("<3d", handle.read(24)), dtype=np.float64)
            handle.read(3)
            struct.unpack("<d", handle.read(8))
            track_count = struct.unpack("<Q", handle.read(8))[0]
            handle.seek(track_count * 8, 1)
            points[point_id] = xyz
    return points


def decode_point2d_records(payload: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Decode COLMAP's mixed double/double/signed-ID observation records."""
    if len(payload) % 24:
        raise ValueError("COLMAP 2D observation payload is not a whole record count")
    records = list(struct.iter_unpack("<ddq", payload))
    xy = np.asarray([record[:2] for record in records], dtype=np.float64).reshape(-1, 2)
    ids = np.asarray([record[2] for record in records], dtype=np.int64)
    return xy, ids


def read_colmap_string(handle) -> str:
    """Read one null-terminated UTF-8 image name."""
    name = bytearray()
    while char := handle.read(1):
        if char == b"\x00":
            break
        name.extend(char)
    return name.decode("utf-8", "replace")


def read_sparse_observations(path: Path) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Read image 2D observations with COLMAP's signed point-ID field intact."""
    records = {}
    with path.open("rb") as handle:
        count = struct.unpack("<Q", handle.read(8))[0]
        for _ in range(count):
            image_id = struct.unpack("<i", handle.read(4))[0]
            handle.seek(60, 1)
            read_colmap_string(handle)
            point_count = struct.unpack("<Q", handle.read(8))[0]
            records[image_id] = decode_point2d_records(handle.read(24 * point_count))
    return records


def colmap_reprojection_residuals(
    images,
    cameras: dict,
    points3d: dict[int, np.ndarray],
    observations: dict[int, tuple[np.ndarray, np.ndarray]],
) -> dict:
    """Measure model-to-image reprojection error for the registered sparse tracks."""
    residuals = []
    for image in images:
        camera = cameras[image.camera_id]
        if camera.model != "SIMPLE_RADIAL":
            raise ValueError("reprojection check only accepts SIMPLE_RADIAL")
        focal, center_x, center_y, radial = camera.params
        observed_xy, point_ids = observations[image.image_id]
        tracked = point_ids >= 0
        ids = point_ids[tracked]
        observed = observed_xy[tracked]
        present = np.asarray([int(point_id) in points3d for point_id in ids])
        if not present.any():
            continue
        xyz = np.stack([points3d[int(point_id)] for point_id in ids[present]])
        camera_xyz = xyz @ image.rotation_w2c.T + image.translation_w2c
        in_front = camera_xyz[:, 2] > 1e-9
        if not in_front.any():
            continue
        camera_xyz = camera_xyz[in_front]
        observed = observed[present][in_front]
        normalized = camera_xyz[:, :2] / camera_xyz[:, 2, None]
        radial_scale = 1.0 + radial * np.sum(normalized**2, axis=1)
        projected = normalized * radial_scale[:, None] * focal
        projected += np.array([center_x, center_y])
        residuals.extend(np.linalg.norm(projected - observed, axis=1).tolist())
    if not residuals:
        raise ValueError("COLMAP model has no positive-depth sparse reprojections")
    return {
        "observation_count": len(residuals),
        "pixel_residual_mean_median_q90_q95_max": np.quantile(
            np.asarray(residuals), [0.5, 0.9, 0.95, 1.0]
        ).tolist(),
        "pixel_residual_mean": float(np.mean(residuals)),
    }


def negative_controls(
    alignment: dict, grid: SupportGrid, cameras_world: np.ndarray
) -> dict:
    """Record fail-closed wrong-transform and inserted-unknown controls."""
    wrong_scale = copy.deepcopy(alignment)
    wrong_scale["ply_to_world"]["metres_per_unit"] *= 2.0
    wrong_axis = copy.deepcopy(alignment)
    wrong_axis["ply_to_world"]["up_axis"] = "x"
    controls = {}
    for name, candidate in (("wrong_scale", wrong_scale), ("wrong_axis", wrong_axis)):
        try:
            validate_alignment_manifest(candidate, "corridor_splat")
        except ValueError as error:
            controls[name] = {"rejected": True, "reason": str(error)}
        else:
            controls[name] = {"rejected": False, "reason": "unexpected acceptance"}
    supported = grid.observed
    if not supported.any():
        controls["inserted_hole"] = {"applicable": False, "reason": "no observed cells"}
        return controls
    rows, columns = np.nonzero(supported)
    center = cameras_world[0, [0, 2]]
    xz = np.column_stack(
        (
            grid.origin_x_m + (columns + 0.5) * grid.spacing_m,
            grid.origin_z_m + (rows + 0.5) * grid.spacing_m,
        )
    )
    nearest_index = int(np.argmin(np.sum((xz - center) ** 2, axis=1)))
    hole_center = xz[nearest_index]
    hole_grid = insert_unknown_hole(grid, hole_center, HOLE_RADIUS_M)
    hole_cells = int(np.count_nonzero(grid.observed & ~hole_grid.observed))
    controls["inserted_hole"] = {
        "applicable": True,
        "center_xz_m": hole_center.tolist(),
        "radius_m": HOLE_RADIUS_M,
        "cells_made_unknown": hole_cells,
        "center_cell_remains_unknown": not hole_grid.observed[
            rows[nearest_index], columns[nearest_index]
        ],
        "unknown_cells_filled": 0,
    }
    return controls


def build() -> dict:
    """Generate CPU-only projections, overlays, grid, and the evidence report."""
    started = time.monotonic()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    alignment = json.loads(ALIGNMENT_PATH.read_text(encoding="utf-8"))
    frame_contract = validate_alignment_manifest(alignment, "corridor_splat")
    contract = contract_from_path(ALIGNMENT_PATH)
    dataparser = load_dataparser(str(DATAPARSER_PATH))
    images = read_images(COLMAP_PATH)
    cameras = read_cameras(COLMAP_PATH)
    by_number = {image_number(image.name): image for image in images}
    camera_centres = load_camera_centres(contract, COLMAP_PATH, DATAPARSER_PATH)
    cameras_by_frame = {
        image_number(image.name): centre
        for image, centre in zip(images, camera_centres, strict=True)
    }
    ordered_camera_centres = np.stack(
        [cameras_by_frame[key] for key in sorted(cameras_by_frame)]
    )
    camera_bounds_residual = max(
        float(
            np.max(
                np.abs(ordered_camera_centres.min(axis=0) - contract.cameras.world_min)
            )
        ),
        float(
            np.max(
                np.abs(ordered_camera_centres.max(axis=0) - contract.cameras.world_max)
            )
        ),
    )
    reprojection = colmap_reprojection_residuals(
        images,
        cameras,
        read_sparse_xyz(COLMAP_PATH / "points3D.bin"),
        read_sparse_observations(COLMAP_PATH / "images.bin"),
    )
    all_hits: list[np.ndarray] = []
    frame_records = []
    overlay_paths = []
    mask_archive = []
    for number in sorted(set(MASK_FRAME_NUMBERS)):
        image = by_number.get(number)
        if image is None:
            raise ValueError(f"selected frame {number} is not registered in COLMAP")
        image_path = IMAGES_PATH / image.name
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        context = FrameContext(image=image, camera=cameras[image.camera_id])
        mask = candidate_mask(context.camera.width, context.camera.height)
        mask_archive.append(mask.astype(np.uint8))
        overlay_path = OVERLAY_DIR / f"frame_{number:04d}_candidate.png"
        mask_overlay(image_path, mask, overlay_path)
        overlay_paths.append(overlay_path)
        pixels = mask_pixels(mask)
        intersections, projection = floor_intersections(
            pixels,
            context,
            dataparser,
            contract.ply_to_world,
            contract.collider.floor_height,
        )
        all_hits.append(intersections)
        frame_records.append(
            {
                "frame_number_1_based": number,
                "registered_image": image.name,
                "source_sha256": sha256_file(image_path),
                "candidate_rule": f"all pixels with v >= {MASK_TOP_ROW}; no semantic inference",
                "mask_pixel_fraction": float(mask.mean()),
                "projection": projection,
            }
        )
    make_contact_sheet(overlay_paths)
    points_world = np.concatenate(all_hits, axis=0)
    grid = make_grid(points_world, ordered_camera_centres)
    metrics = support_metrics(grid, ordered_camera_centres[:, [0, 2]])
    hole = negative_controls(alignment, grid, ordered_camera_centres)
    np.savez_compressed(
        OUTPUT_GRID,
        heights_m=grid.heights_m.astype(np.float32),
        observed=grid.observed.astype(np.uint8),
        frame_numbers=np.asarray(sorted(set(MASK_FRAME_NUMBERS)), dtype=np.int16),
        candidate_masks=np.stack(mask_archive).astype(np.uint8),
        origin_x_m=np.float64(grid.origin_x_m),
        origin_z_m=np.float64(grid.origin_z_m),
        spacing_m=np.float64(grid.spacing_m),
    )
    source_selection = json.loads(SOURCE_SELECTION_PATH.read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "issue": 135,
        "status": "evidence_only_route_support_failed",
        "asset_status": "not_collision_not_runtime_imported",
        "gpu_used": False,
        "inference_run": False,
        "metric_scale_accepted": False,
        "scale_kind": frame_contract["scale_kind"],
        "scale_note": "#100's 5.128383849 m/unit is a chosen synthetic convention, not surveyed metric scale.",
        "floor_plane_height_m": contract.collider.floor_height,
        "method": "Sparse registered COLMAP views; unreviewed candidate crop rows >= threshold; SIMPLE_RADIAL inverse; exact ray-plane intersections; 5 cm occupancy grid.",
        "mask_audit": {
            "human_reviewed": False,
            "source_rule": f"uniform lower image band v >= {MASK_TOP_ROW}",
            "mask_frame_count": len(frame_records),
            "selected_frame_numbers_1_based": [
                item["frame_number_1_based"] for item in frame_records
            ],
            "sample_stride_px": MASK_SAMPLE_STRIDE,
            "contact_sheet": str(OUTPUT_CONTACT_SHEET.relative_to(ROOT)),
            "overlay_directory": str(OVERLAY_DIR.relative_to(ROOT)),
            "interpretation": "Candidate pixels are not a semantic floor segmentation and have not had human review; the contact sheet is for audit. Objects crossing the lower band can create false floor hits.",
        },
        "inputs": {
            "alignment_manifest": str(ALIGNMENT_PATH.relative_to(ROOT)),
            "alignment_manifest_sha256": sha256_file(ALIGNMENT_PATH),
            "colmap_model": str(COLMAP_PATH.relative_to(ROOT)),
            "colmap_images_sha256": sha256_file(COLMAP_PATH / "images.bin"),
            "colmap_cameras_sha256": sha256_file(COLMAP_PATH / "cameras.bin"),
            "dataparser_transform": str(DATAPARSER_PATH.relative_to(ROOT)),
            "dataparser_sha256": sha256_file(DATAPARSER_PATH),
            "registered_images": len(images),
            "registered_image_order": "numeric frame suffix, not binary model order",
            "camera_model": "SIMPLE_RADIAL",
            "camera_parameters_f_cx_cy_k1": list(cameras[images[0].camera_id].params),
            "source_selection_camera_parameters": source_selection["camera"][
                "parameters"
            ],
            "frame_141_camera_parameters_match_source_selection": list(
                cameras[images[0].camera_id].params
            )
            == source_selection["camera"]["parameters"],
            "observation_decode": "This evidence reader decodes COLMAP <ddq> records directly. The shared read_images helper currently casts point IDs through float64; this report does not rely on those IDs.",
        },
        "alignment_checks": {
            "mapped_camera_bounds_match_contract": camera_bounds_residual <= 1e-6,
            "max_camera_bound_residual_m": camera_bounds_residual,
            "max_abs_intersection_floor_residual_m": max(
                item["projection"]["max_abs_floor_residual_m"] for item in frame_records
            ),
            "colmap_sparse_reprojection": reprojection,
            "plane_intersection_residual_note": "The floor residual is numerical consistency only; the plane itself is imposed, not independently measured.",
        },
        "frame_projections": frame_records,
        "grid": {
            **metrics,
            "origin_xz_m": [grid.origin_x_m, grid.origin_z_m],
            "dimensions_note": "Grid bounds contain observed ray hits and registered camera centres plus 0.30 m; no cells outside observed hits are filled.",
            "file": str(OUTPUT_GRID.relative_to(ROOT)),
            "unknown_cells_filled": 0,
        },
        "negative_controls": hole,
        "walkability": {
            "tested": False,
            "avian_tnua_tested": False,
            "reason": "Only 0/192 camera samples and 0/191 segment midpoints are supported within 0.30 m; the >90% route gate fails, so physics was skipped.",
            "collision_glb_created": False,
        },
        "execution": {
            "elapsed_seconds": time.monotonic() - started,
            "peak_process_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "grid_archive_bytes": OUTPUT_GRID.stat().st_size,
            "contact_sheet_bytes": OUTPUT_CONTACT_SHEET.stat().st_size,
        },
        "failure_reason": "The unreviewed crop yields one connected 25.66 m2 support component but 0% camera-path coverage at 0.30 m (median nearest support 0.885 m). It is not a route and has not been human-reviewed or semantically validated.",
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
