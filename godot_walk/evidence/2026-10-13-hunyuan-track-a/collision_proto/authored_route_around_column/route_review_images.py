"""Plan and source-frame overlays for human review of the route proxy."""

from __future__ import annotations

import math

import numpy as np
from column_review_images import render_column_frames
from PIL import Image, ImageDraw
from route_source import HERE

MAP_BOUNDS = (-6.0, -4.5, 5.5, 6.5)
MAP_SCALE = 80.0
MAP_MARGIN = 54


def write_review_images(context, source: dict, geometry: dict, grid: dict) -> None:
    """Create the plan view and reviewed column-frame overlays."""
    render_plan_map(context.centres_world_m[:, [0, 2]], source, geometry, grid)
    render_column_frames(context, source["column_records"])


def render_plan_map(
    camera_xz: np.ndarray, source: dict, geometry: dict, grid: dict
) -> None:
    """Draw the candidate footprint, authored band, path, and proxy obstacle."""
    image = _new_map_image()
    draw = ImageDraw.Draw(image, "RGBA")
    transform = lambda point: _map_point(point, MAP_BOUNDS, MAP_SCALE, MAP_MARGIN)
    _draw_map_layers(draw, image, transform, camera_xz, source, geometry, grid)
    image.convert("RGB").save(HERE / "route_review_map.png", quality=92)


def _new_map_image() -> Image.Image:
    """Create a stable-size plan canvas for the registered scene extent."""
    width = round((MAP_BOUNDS[2] - MAP_BOUNDS[0]) * MAP_SCALE + 2 * MAP_MARGIN)
    height = round((MAP_BOUNDS[3] - MAP_BOUNDS[1]) * MAP_SCALE + 2 * MAP_MARGIN)
    return Image.new("RGBA", (width, height), (24, 31, 31, 255))


def _draw_map_layers(
    draw,
    image: Image.Image,
    transform,
    camera_xz: np.ndarray,
    source: dict,
    geometry: dict,
    grid: dict,
) -> None:
    """Draw map features in a fixed order so labels do not hide evidence."""
    _draw_map_grid(draw, transform)
    _draw_candidate_cells(draw, grid, transform)
    center = transform(geometry["center"])
    _draw_route_band(image, center, geometry["inner"], geometry["outer"])
    _draw_lines(draw, transform, camera_xz, geometry["centerline"])
    _draw_obstacle(draw, transform, source["lower"], source["upper"])
    _draw_start_end_marker(draw, transform, geometry["centerline"][0])
    _draw_map_legend(draw, image, geometry["center"], geometry)


def _draw_map_grid(draw, transform) -> None:
    """Draw one-meter coordinate lines behind the occupancy evidence."""
    for x in range(math.floor(MAP_BOUNDS[0]), math.ceil(MAP_BOUNDS[2]) + 1):
        draw.line(
            [transform((x, MAP_BOUNDS[1])), transform((x, MAP_BOUNDS[3]))],
            fill=(80, 94, 91, 90),
            width=1,
        )
    for z in range(math.floor(MAP_BOUNDS[1]), math.ceil(MAP_BOUNDS[3]) + 1):
        draw.line(
            [transform((MAP_BOUNDS[0], z)), transform((MAP_BOUNDS[2], z))],
            fill=(80, 94, 91, 90),
            width=1,
        )


def _draw_candidate_cells(draw, grid: dict, transform) -> None:
    """Show all unreviewed projected cells as source-informed candidates."""
    rows, columns = np.nonzero(grid["observed"].astype(bool))
    origin_x = float(grid["origin_x_m"])
    origin_z = float(grid["origin_z_m"])
    spacing = float(grid["spacing_m"])
    half = spacing * MAP_SCALE / 2.0
    for row, column in zip(rows, columns, strict=True):
        point = (origin_x + (column + 0.5) * spacing, origin_z + (row + 0.5) * spacing)
        x, y = transform(point)
        draw.rectangle(
            (x - half, y - half, x + half, y + half), fill=(73, 168, 112, 220)
        )


def _draw_route_band(
    image: Image.Image, center: tuple[int, int], inner: float, outer: float
) -> None:
    """Overlay the authored floor band without changing candidate cells."""
    mask = _ring_mask(image.size, center, inner * MAP_SCALE, outer * MAP_SCALE)
    tint = Image.new("RGBA", image.size, (53, 120, 176, 86))
    tint.putalpha(mask.point(lambda value: value * 86 // 255))
    image.alpha_composite(tint)


def _ring_mask(
    size: tuple[int, int], center: tuple[int, int], inner: float, outer: float
) -> Image.Image:
    """Make a binary annulus mask for the authored route floor."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(_ellipse(center, outer), fill=255)
    draw.ellipse(_ellipse(center, inner), fill=0)
    return mask


def _ellipse(
    center: tuple[int, int], radius: float
) -> tuple[float, float, float, float]:
    """Return the pixel-space bounds for a circular map overlay."""
    return (
        center[0] - radius,
        center[1] - radius,
        center[0] + radius,
        center[1] + radius,
    )


def _draw_lines(draw, transform, camera_xz: np.ndarray, centerline: np.ndarray) -> None:
    """Draw the registered camera arc and selected closed route."""
    draw.line(
        [transform(point) for point in camera_xz], fill=(93, 184, 223, 230), width=3
    )
    loop = np.vstack((centerline, centerline[0]))
    draw.line([transform(point) for point in loop], fill=(255, 225, 120, 255), width=4)


def _draw_obstacle(draw, transform, lower: np.ndarray, upper: np.ndarray) -> None:
    """Mark the conservative column proxy footprint."""
    polygon = [
        transform((lower[0], lower[1])),
        transform((upper[0], lower[1])),
        transform((upper[0], upper[1])),
        transform((lower[0], upper[1])),
    ]
    draw.polygon(polygon, fill=(203, 83, 67, 155), outline=(255, 125, 92, 255), width=3)


def _draw_start_end_marker(draw, transform, point: np.ndarray) -> None:
    """Mark the shared endpoint of the closed route."""
    x, y = transform(point)
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(16, 31, 31, 255))
    draw.ellipse(
        (x - 6, y - 6, x + 6, y + 6),
        fill=(50, 220, 226, 255),
        outline=(240, 245, 238, 255),
        width=2,
    )


def _draw_map_legend(
    draw, image: Image.Image, center: np.ndarray, geometry: dict
) -> None:
    """Label candidate and authored layers without covering the main route."""
    top = image.height - 166
    draw.rectangle((30, top, 590, image.height - 28), fill=(10, 17, 17, 226))
    labels = [
        ("#139 authored route / chosen #100 coordinates", (240, 245, 238, 255)),
        ("Green: unreviewed projected candidate cells", (117, 214, 151, 255)),
        (
            "Blue/yellow: authored floor; cyan dot: loop start = end",
            (133, 191, 226, 255),
        ),
        ("Red: conservative projected column AABB proxy", (255, 144, 111, 255)),
        (
            f"center XZ={center.round(2).tolist()} band={geometry['inner']:.2f}-{geometry['outer']:.2f}m",
            (240, 245, 238, 255),
        ),
    ]
    for index, (label, color) in enumerate(labels):
        draw.text((48, top + 12 + index * 23), label, fill=color)


def _map_point(
    point: np.ndarray, bounds: tuple, scale: float, margin: int
) -> tuple[int, int]:
    """Convert Godot XZ coordinates to top-down review image pixels."""
    return (
        round((float(point[0]) - bounds[0]) * scale + margin),
        round((bounds[3] - float(point[1])) * scale + margin),
    )
