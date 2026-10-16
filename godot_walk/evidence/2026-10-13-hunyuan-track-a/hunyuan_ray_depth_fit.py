"""Fit Hunyuan-to-#100 scale from registered COLMAP points along source-camera rays.

No feature matching is used. Each COLMAP observation's pixel is mapped to the
Hunyuan panorama through the registered camera model (the same mapping as
hunyuan_calibration_screen.reproject_panorama), and the mesh layer's grid vertex
at that panorama pixel gives Hunyuan's generated distance along the same ray.
The ratio of COLMAP range to Hunyuan range is a per-point scale sample.

All metric values are #100 declared metres (the chosen 2.4 m clear-height
convention). The source video is synthetic, so no surveyed scale exists; this
fit registers Hunyuan to #100's declared frame and tests whether a single
similarity transform is consistent with the generated depth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pycolmap
from PIL import Image

EVIDENCE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVIDENCE_DIR.parents[2]
DEFAULT_SOURCE = REPO_ROOT / "data/scenes/corridor_travel/images/frame_0141.jpg"
DEFAULT_MESH = REPO_ROOT / "data/track-a/hunyuan/scene-run-05/mesh_layer1.ply"
DEFAULT_FG_MASK = REPO_ROOT / "data/track-a/hunyuan/scene-run-05/fg1_mask.png"
DEFAULT_COLMAP = REPO_ROOT / "data/scenes/corridor_travel/sparse/0"
DEFAULT_DATAPARSER = REPO_ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
DEFAULT_ALIGNMENT = REPO_ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
DEFAULT_CALIBRATION = EVIDENCE_DIR / "calibration_manifest_frame_141.json"
# #100 reference floor/ceiling world y at the shared reference x/z (SCALE_CALIBRATION.md).
REFERENCE_FLOOR_Y = -1.2709904916
REFERENCE_CEILING_Y = 1.1290095084
TOLERANCE_M = 0.02
# Panorama row-fraction bands (v from top; horizon at 0.5).
BANDS = {"top": (0.0, 0.45), "middle": (0.45, 0.55), "bottom": (0.55, 1.0)}
DEPTH_BINS_M = [(0.0, 4.0), (4.0, 6.0), (6.0, 10.0), (10.0, float("inf"))]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_grid_vertices(path: Path) -> np.ndarray:
    """Return the Open3D panorama-grid vertices as an (H, W, 3) array."""
    with path.open("rb") as handle:
        header = []
        while (line := handle.readline().strip()) != b"end_header":
            header.append(line.decode("ascii"))
        count = next(int(item.split()[-1]) for item in header if item.startswith("element vertex"))
        layout = np.dtype([("p", "<f8", 3), ("n", "<f8", 3), ("c", "u1", 3)])
        vertices = np.fromfile(handle, dtype=layout, count=count)["p"]
    width = round(np.sqrt(count * 2))
    height = count // width
    if width * height != count or width != 2 * height:
        raise ValueError("mesh vertex count is not a 2:1 panorama grid")
    return vertices.reshape(height, width, 3)


def ray_check_degrees(vertices: np.ndarray) -> float:
    """Max angle between grid vertices and the Hunyuan equirectangular ray convention."""
    height, width = vertices.shape[:2]
    worst = 0.0
    for row in np.linspace(height * 0.1, height * 0.9, 5).astype(int):
        for col in np.linspace(width * 0.1, width * 0.9, 5).astype(int):
            longitude = (col + 0.5) / width * 2 * np.pi - np.pi
            latitude = np.pi / 2 - (row + 0.5) / height * np.pi
            expected = np.array([
                -np.cos(latitude) * np.cos(longitude),
                np.cos(latitude) * np.sin(longitude),
                np.sin(latitude),
            ])
            direction = vertices[row, col] / np.linalg.norm(vertices[row, col])
            angle = np.degrees(np.arccos(np.clip(expected @ direction, -1.0, 1.0)))
            worst = max(worst, angle)
    return worst


def robust_summary(ratios: np.ndarray, rng: np.random.Generator, samples: int) -> dict:
    median = float(np.median(ratios))
    sigma = float(1.4826 * np.median(np.abs(ratios - median)))
    draws = rng.choice(ratios, size=(samples, len(ratios)), replace=True)
    low, high = np.percentile(np.median(draws, axis=1), [2.5, 97.5])
    relative = np.abs(ratios / median - 1.0)
    return {
        "count": len(ratios),
        "median": median,
        "bootstrap_95ci_of_median": [float(low), float(high)],
        "robust_sigma": sigma,
        "robust_sigma_fraction": sigma / median,
        "relative_residual_q50_q90": [float(q) for q in np.percentile(relative, [50, 90])],
    }


def plane_height(calibration: dict, plane: str, scale: float) -> float:
    """World y of a #134 fitted plane at the reference x/z, camera anchored."""
    follow_up = calibration["validation"]["plane_fit_follow_up"]
    a, b, c = follow_up[f"{plane}_fit"]["z_equals_a_x_plus_b_y_plus_c_local_units"]
    reference_x, reference_z = follow_up["reference_world_xz_declared"]
    rotation = np.asarray(calibration["rotation_local_to_world_row_major"])
    centre = np.asarray(calibration["registered_camera"]["camera_center_world_declared"])
    normal = rotation @ np.array([-a, -b, 1.0])
    return float(
        centre[1]
        + (scale * c - normal[0] * (reference_x - centre[0]) - normal[2] * (reference_z - centre[2]))
        / normal[1]
    )


def plane_check(calibration: dict, scale: float) -> dict:
    floor_y = plane_height(calibration, "floor", scale)
    ceiling_y = plane_height(calibration, "ceiling", scale)
    return {
        "scale_declared_metres_per_hunyuan_unit": scale,
        "floor_y": floor_y,
        "ceiling_y": ceiling_y,
        "floor_offset_m": floor_y - REFERENCE_FLOOR_Y,
        "ceiling_offset_m": ceiling_y - REFERENCE_CEILING_Y,
        "clear_height_m": ceiling_y - floor_y,
    }


def single_plane_scale(calibration: dict, plane: str, target_y: float) -> float:
    """Scale that puts one fitted plane on its #100 height with the camera anchored."""
    base = plane_height(calibration, plane, 0.0)
    unit = plane_height(calibration, plane, 1.0) - base
    return (target_y - base) / unit


def analyze(args: argparse.Namespace) -> dict:
    vertices = read_grid_vertices(args.mesh)
    height, width = vertices.shape[:2]
    distances = np.linalg.norm(vertices, axis=-1)
    foreground = (
        # The mask stores foreground label ids (0 = background), not 0/255 intensities.
        np.asarray(Image.open(args.fg_mask).convert("L").resize((width, height), Image.NEAREST)) > 0
    )

    reconstruction = pycolmap.Reconstruction(str(args.colmap))
    image = next(item for item in reconstruction.images.values() if item.name == args.source.name)
    camera = reconstruction.cameras[image.camera_id]
    pose = image.cam_from_world() if callable(image.cam_from_world) else image.cam_from_world
    focal, centre_x, centre_y, radial = camera.params
    intrinsics = np.array([[focal, 0, centre_x], [0, focal, centre_y], [0, 0, 1.0]])
    observations = [point for point in image.points2D if point.has_point3D()]
    pixels = np.array([point.xy for point in observations], dtype=np.float32)
    rays = cv2.undistortPoints(
        pixels.reshape(-1, 1, 2), intrinsics, np.array([radial, 0.0, 0.0, 0.0])
    ).reshape(-1, 2)
    points_camera = np.array(
        [pose * reconstruction.points3D[point.point3D_id].xyz for point in observations]
    )

    dataparser_scale = float(json.loads(args.dataparser.read_text())["scale"])
    alignment = json.loads(args.alignment.read_text())
    metres_per_colmap_unit = dataparser_scale * alignment["ply_to_world"]["metres_per_unit"]
    range_m = np.linalg.norm(points_camera, axis=1) * metres_per_colmap_unit

    longitude = np.arctan2(rays[:, 0], 1.0)
    latitude = np.arcsin(-rays[:, 1] / np.sqrt(rays[:, 0] ** 2 + rays[:, 1] ** 2 + 1.0))
    column = np.clip(((longitude / (2 * np.pi)) + 0.5) * width, 0, width - 1).astype(int)
    row = np.clip((0.5 - latitude / np.pi) * height, 0, height - 1).astype(int)
    keep = ~foreground[row, column]
    ratios = range_m / distances[row, column]
    v_fraction = row / height
    cells = {
        (min(3, int(x * 4 / camera.width)), min(3, int(y * 4 / camera.height)))
        for x, y in pixels[keep]
    }

    rng = np.random.default_rng(args.seed)
    overall = robust_summary(ratios[keep], rng, args.bootstrap)
    bands = {
        name: robust_summary(ratios[keep & (v_fraction >= low) & (v_fraction < high)], rng, args.bootstrap)
        for name, (low, high) in BANDS.items()
        if np.count_nonzero(keep & (v_fraction >= low) & (v_fraction < high)) >= args.min_bin
    }
    depth_bins = {
        f"{low:g}-{high:g}m": robust_summary(ratios[keep & (range_m >= low) & (range_m < high)], rng, args.bootstrap)
        for low, high in DEPTH_BINS_M
        if np.count_nonzero(keep & (range_m >= low) & (range_m < high)) >= args.min_bin
    }

    calibration = json.loads(args.calibration.read_text())
    convention_scale = float(calibration["scale"])
    ray_scale = overall["median"]
    floor_scale = single_plane_scale(calibration, "floor", REFERENCE_FLOOR_Y)
    ceiling_scale = single_plane_scale(calibration, "ceiling", REFERENCE_CEILING_Y)
    ray_plane = plane_check(calibration, ray_scale)
    # The camera anchor residual is zero by construction, so the gate is the floor and ceiling.
    similarity_passes = (
        abs(ray_plane["floor_offset_m"]) <= TOLERANCE_M
        and abs(ray_plane["ceiling_offset_m"]) <= TOLERANCE_M
    )

    return {
        "method": "COLMAP range vs Hunyuan grid-vertex range along registered source-camera rays",
        "units": "#100 declared metres (chosen 2.4 m clear-height convention; source is synthetic)",
        "inputs": {
            "source_frame": {"path": str(args.source), "sha256": sha256(args.source)},
            "hunyuan_mesh": {"path": str(args.mesh), "sha256": sha256(args.mesh), "grid": [width, height]},
            "foreground_mask": {"path": str(args.fg_mask), "sha256": sha256(args.fg_mask)},
            "colmap_model": str(args.colmap),
            "dataparser_transforms": {"path": str(args.dataparser), "sha256": sha256(args.dataparser)},
            "alignment_manifest": {"path": str(args.alignment), "sha256": sha256(args.alignment)},
            "calibration_manifest": {"path": str(args.calibration), "sha256": sha256(args.calibration)},
        },
        "grid_ray_convention_max_error_degrees": ray_check_degrees(vertices),
        "metres_per_colmap_unit": metres_per_colmap_unit,
        "registered_observations": len(observations),
        "observations_used_after_foreground_mask": int(np.count_nonzero(keep)),
        "source_image_grid_cells_occupied_4x4": len(cells),
        "observations_masked_as_foreground": int(np.count_nonzero(~keep)),
        "scale_declared_metres_per_hunyuan_unit": {
            "all_rays": overall,
            "by_panorama_band": bands,
            "by_colmap_range": depth_bins,
        },
        "scale_comparison": {
            "convention_plane_fit_134": convention_scale,
            "ray_depth_median": ray_scale,
            "floor_plane_only_camera_anchored": floor_scale,
            "ceiling_plane_only_camera_anchored": ceiling_scale,
        },
        "camera_anchored_plane_checks": {
            "convention_scale": plane_check(calibration, convention_scale),
            "ray_depth_scale": ray_plane,
            "reference_floor_y": REFERENCE_FLOOR_Y,
            "reference_ceiling_y": REFERENCE_CEILING_Y,
        },
        "tolerance_m": TOLERANCE_M,
        "single_similarity_meets_tolerance": bool(similarity_passes),
        "limitations": [
            "One source frame; COLMAP points on low-texture wallpaper are sparse and may be noisy.",
            "The panorama band split uses Hunyuan row fraction; the bottom band has few points.",
            "Hunyuan layer depth may include upstream depth compression; ratios are not assumed linear.",
            "Plane checks reuse #134's fitted floor/ceiling coefficients and #100 reference heights.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--mesh", type=Path, default=DEFAULT_MESH)
    parser.add_argument("--fg-mask", type=Path, default=DEFAULT_FG_MASK)
    parser.add_argument("--colmap", type=Path, default=DEFAULT_COLMAP)
    parser.add_argument("--dataparser", type=Path, default=DEFAULT_DATAPARSER)
    parser.add_argument("--alignment", type=Path, default=DEFAULT_ALIGNMENT)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--min-bin", type=int, default=10)
    parser.add_argument("--seed", type=int, default=142)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = analyze(args)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
