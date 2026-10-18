"""Read registered #100 inputs and project manually reviewed column pixels."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent
ROOT = HERE.parents[4]
GRID_PATH = (
    PROTO
    / "registered_floor_masks_all_frames"
    / "registered_floor_mask_support_all_192.npz"
)
sys.path.insert(0, str(PROTO))
sys.path.insert(0, str(ROOT / "scripts" / "splat_pipeline"))

import camera_path_diagnostic_inputs as camera_inputs
from registered_floor_masks import FrameContext, floor_intersections


def load_spec() -> dict:
    """Load the small, hand-reviewed route and pixel annotation manifest."""
    return json.loads((HERE / "route_spec.json").read_text(encoding="utf-8"))


def load_candidate_grid() -> dict:
    """Load the compact all-frame footprint without retaining an open archive."""
    with np.load(GRID_PATH) as archive:
        return {name: archive[name] for name in archive.files}


def analyze_source(context, spec: dict) -> dict:
    """Fit the camera orbit and project the reviewed column base pixels."""
    center, orbit_radius, residuals = fit_camera_circle(
        context.centres_world_m[:, [0, 2]]
    )
    records = project_column_review(context, spec)
    margin = float(spec["column_review"]["horizontal_margin_m"])
    lower, upper = conservative_column_bounds(records, margin)
    return {
        "center": center,
        "orbit_radius": orbit_radius,
        "residuals": residuals,
        "column_records": records,
        "lower": lower,
        "upper": upper,
    }


def fit_camera_circle(points_xz: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """Fit the circle center used only to define the authored route region."""
    points = np.asarray(points_xz, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        raise ValueError("circle fit requires at least three XZ points")
    matrix = np.column_stack((2.0 * points, np.ones(len(points))))
    solution, *_ = np.linalg.lstsq(matrix, np.sum(points * points, axis=1), rcond=None)
    center = solution[:2]
    radius = float(np.sqrt(solution[2] + center @ center))
    residuals = np.linalg.norm(points - center, axis=1) - radius
    return center, radius, residuals


def project_column_review(context, spec: dict) -> list[dict]:
    """Project the manually marked visible column-base corners for each frame."""
    frames_by_number = {
        camera_inputs.floor_masks.image_number(image.name): index
        for index, image in enumerate(context.images)
    }
    return [
        _project_column_frame(context, frame, frames_by_number)
        for frame in spec["column_review"]["frames"]
    ]


def _project_column_frame(context, frame: dict, frames_by_number: dict) -> dict:
    """Project one visible base triangle and derive its occluded corner."""
    index = frames_by_number[int(frame["frame_number"])]
    image = context.images[index]
    camera = context.cameras[image.camera_id]
    pixels = np.asarray(frame["visible_base_corner_pixels_uv"], dtype=np.float64)
    projected, stats = floor_intersections(
        pixels,
        FrameContext(image=image, camera=camera),
        context.dataparser,
        context.contract.ply_to_world,
        context.contract.collider.floor_height,
    )
    xz = projected[:, [0, 2]]
    corners = np.vstack((xz, xz[0] + xz[2] - xz[1]))
    return _column_frame_record(frame, pixels, corners, stats)


def _column_frame_record(
    frame: dict, pixels: np.ndarray, corners: np.ndarray, stats: dict
) -> dict:
    """Keep observed and parallelogram-derived footprint corners distinct."""
    return {
        "frame_number": int(frame["frame_number"]),
        "image": str(frame["image"]),
        "visible_base_corner_pixels_uv": pixels.astype(int).tolist(),
        "projected_base_corners_xz_m": corners.tolist(),
        "derived_corner_index": 3,
        "projection": stats,
    }


def conservative_column_bounds(
    records: list[dict], margin_m: float
) -> tuple[np.ndarray, np.ndarray]:
    """Bound all projected corners, then add the explicit review margin."""
    corners = np.concatenate(
        [np.asarray(record["projected_base_corners_xz_m"]) for record in records]
    )
    return corners.min(axis=0) - margin_m, corners.max(axis=0) + margin_m
