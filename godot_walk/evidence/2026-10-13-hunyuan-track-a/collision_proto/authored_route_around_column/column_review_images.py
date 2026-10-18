"""Overlays for the manually reviewed column pixels in registered frames."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from route_source import camera_inputs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def render_column_frames(context, records: list[dict]) -> None:
    """Mark the reviewed base corners in their registered source frames."""
    frame_indices = {
        camera_inputs.floor_masks.image_number(image.name): index
        for index, image in enumerate(context.images)
    }
    for record in records:
        index = frame_indices[int(record["frame_number"])]
        _render_column_frame(context, record, index)


def _render_column_frame(context, record: dict, image_index: int) -> None:
    """Reproject the manual and derived corners, then save a labeled image."""
    xz = np.asarray(record["projected_base_corners_xz_m"], dtype=np.float64)
    floor = context.contract.collider.floor_height
    world = np.column_stack((xz[:, 0], np.full(4, floor), xz[:, 1]))
    pixels, _ = camera_inputs.project_world_points(context, image_index, world)
    _draw_frame_overlay(record, pixels)


def _draw_frame_overlay(record: dict, projected: np.ndarray) -> None:
    """Write red manual-corner markers and a blue derived-corner marker."""
    image_path = ROOT / "data/scenes/corridor_travel/images" / record["image"]
    image = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    points = [(round(float(x)), round(float(y))) for x, y in projected]
    _mark_frame_corners(draw, points)
    draw.rectangle((20, 20, 930, 68), fill=(0, 0, 0, 190))
    draw.text(
        (34, 35),
        "MANUAL COLUMN BASE / red: visible / blue: derived",
        fill=(255, 255, 255, 255),
    )
    image.convert("RGB").save(
        HERE / f"column_review_frame_{record['frame_number']:03d}.jpg", quality=92
    )


def _mark_frame_corners(draw, points: list[tuple[int, int]]) -> None:
    """Draw the base quadrilateral and number its evidence points."""
    draw.line(points + [points[0]], fill=(255, 214, 73, 220), width=4)
    for index, point in enumerate(points):
        _mark_frame_corner(draw, point, index)


def _mark_frame_corner(draw, point: tuple[int, int], index: int) -> None:
    """Mark one hand-selected or derived column corner."""
    color = (255, 68, 56, 255) if index < 3 else (71, 193, 255, 255)
    draw.ellipse(
        (point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8),
        fill=color,
        outline=(20, 20, 20, 255),
        width=2,
    )
    label = str(index + 1) if index < 3 else "4 derived"
    draw.text(
        (point[0] + 10, point[1] - 18),
        label,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220),
    )
