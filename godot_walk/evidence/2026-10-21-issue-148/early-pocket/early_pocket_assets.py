"""Geometry definitions shared by the standalone and assembled pocket scenes."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from collision_meshes import box_mesh
from early_pocket_geometry import (
    FLOOR_Y_M,
    WALL_HEIGHT_M,
    WALL_THICKNESS_M,
    merge_meshes,
    rectangle_floor,
    room_walls,
    room_wall_boxes,
)

POCKET_LOWER = (0.0, 0.0)
POCKET_UPPER = (6.0, 13.8)
LATER_BAY_LOWER = (-5.4, -5.0)
LATER_BAY_UPPER = (4.5, 8.8)
ASSEMBLED_POCKET_OFFSET = (8.0, 0.0, -5.0)
ASSEMBLED_LOWER = (-5.4, -5.0)
ASSEMBLED_UPPER = (14.0, 8.8)
DOOR_Z_BOUNDS = (2.8, 5.2)
CORRIDOR_X_BOUNDS = (4.5, 8.0)
PATTERN_WALL = (0.64, 0.67, 0.35)
PATTERN_LIGHT = (0.74, 0.72, 0.43)
PATTERN_DARK = (0.54, 0.58, 0.29)
TRIM = (0.77, 0.73, 0.57)
GRID = (0.49, 0.43, 0.25)
CARPET = (0.60, 0.45, 0.20)
CEILING = (0.82, 0.75, 0.49)
LIGHT = (0.97, 0.94, 0.78)


def standalone_collision_meshes() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    meshes = {"floor": rectangle_floor(POCKET_LOWER, POCKET_UPPER, FLOOR_Y_M)}
    meshes.update(room_walls(POCKET_LOWER, POCKET_UPPER))
    return meshes


def assembled_collision_meshes(column_bounds: tuple[tuple[float, float], tuple[float, float]]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    meshes = {"floor": rectangle_floor(ASSEMBLED_LOWER, ASSEMBLED_UPPER, FLOOR_Y_M)}
    meshes["column"] = box_mesh(
        np.asarray(column_bounds[0]), np.asarray(column_bounds[1]), FLOOR_Y_M, WALL_HEIGHT_M
    )
    meshes.update(room_walls(ASSEMBLED_LOWER, ASSEMBLED_UPPER))
    meshes["interior"] = merge_meshes(interior_wall_meshes())
    return meshes


def interior_wall_boxes() -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
    x0, x1 = CORRIDOR_X_BOUNDS
    z0, z1 = DOOR_Z_BOUNDS
    thickness = WALL_THICKNESS_M
    return [
        ("authored_later_bay_divider_south", (4.5 - thickness / 2, -5.0), (4.5 + thickness / 2, z0)),
        ("authored_later_bay_divider_north", (4.5 - thickness / 2, z1), (4.5 + thickness / 2, 8.8)),
        ("authored_pocket_divider_south", (8.0 - thickness / 2, -5.0), (8.0 + thickness / 2, z0)),
        ("authored_pocket_divider_north", (8.0 - thickness / 2, z1), (8.0 + thickness / 2, 8.8)),
        ("authored_connector_wall_south", (x0, z0 - thickness / 2), (x1, z0 + thickness / 2)),
        ("authored_connector_wall_north", (x0, z1 - thickness / 2), (x1, z1 + thickness / 2)),
    ]


def interior_wall_meshes() -> list[tuple[np.ndarray, np.ndarray]]:
    return [
        box_mesh(np.asarray(lower), np.asarray(upper), FLOOR_Y_M, WALL_HEIGHT_M)
        for _, lower, upper in interior_wall_boxes()
    ]


def standalone_visual_boxes() -> list[dict]:
    return room_visual_boxes((POCKET_LOWER, POCKET_UPPER), room_wall_boxes(POCKET_LOWER, POCKET_UPPER))


def assembled_visual_boxes(
    column_bounds: tuple[tuple[float, float], tuple[float, float]],
) -> list[dict]:
    wall_boxes = room_wall_boxes(ASSEMBLED_LOWER, ASSEMBLED_UPPER) + interior_wall_boxes()
    visuals = room_visual_boxes((ASSEMBLED_LOWER, ASSEMBLED_UPPER), wall_boxes)
    lower, upper = column_bounds
    visuals.append(
        colored_box(
            "authored_later_bay_column_visual",
            (
                (lower[0] + upper[0]) / 2,
                FLOOR_Y_M + WALL_HEIGHT_M / 2,
                (lower[1] + upper[1]) / 2,
            ),
            (upper[0] - lower[0], WALL_HEIGHT_M, upper[1] - lower[1]),
            TRIM,
        )
    )
    return visuals


def room_visual_boxes(
    bounds: tuple[tuple[float, float], tuple[float, float]],
    wall_boxes: Iterable[tuple[str, tuple[float, float], tuple[float, float]]],
) -> list[dict]:
    lower, upper = bounds
    x0, z0 = lower
    x1, z1 = upper
    center_x, center_z = (x0 + x1) / 2, (z0 + z1) / 2
    items = [
        colored_box("authored_carpet_visual", (center_x, FLOOR_Y_M + 0.008, center_z), (x1 - x0, 0.03, z1 - z0), CARPET),
        colored_box("authored_ceiling_visual", (center_x, FLOOR_Y_M + WALL_HEIGHT_M + 0.01, center_z), (x1 - x0, 0.04, z1 - z0), CEILING),
    ]
    for name, wall_lower, wall_upper in wall_boxes:
        items.append(wall_visual_box(name, wall_lower, wall_upper, PATTERN_WALL))
        items.extend(wall_pattern_visuals(name, wall_lower, wall_upper))
    items.extend(ceiling_grid_visuals(bounds))
    items.extend(light_visuals(x0, x1, center_z))
    return items


def wall_pattern_visuals(
    name: str, lower: tuple[float, float], upper: tuple[float, float]
) -> list[dict]:
    x0, z0 = lower
    x1, z1 = upper
    width_x, width_z = x1 - x0, z1 - z0
    visuals = []
    if width_x <= width_z:
        for index, z in enumerate(pattern_centers(z0, z1)):
            color = PATTERN_LIGHT if index % 2 == 0 else PATTERN_DARK
            for face in (-1.0, 1.0):
                visuals.append(
                    colored_box(
                        f"{name}_wallpaper_{index}_{'a' if face < 0 else 'b'}",
                        ((x0 + x1) / 2 + face * (width_x / 2 + 0.012), FLOOR_Y_M + 1.25, z),
                        (0.024, 1.7, 0.22),
                        color,
                    )
                )
    else:
        for index, x in enumerate(pattern_centers(x0, x1)):
            color = PATTERN_LIGHT if index % 2 == 0 else PATTERN_DARK
            for face in (-1.0, 1.0):
                visuals.append(
                    colored_box(
                        f"{name}_wallpaper_{index}_{'a' if face < 0 else 'b'}",
                        (x, FLOOR_Y_M + 1.25, (z0 + z1) / 2 + face * (width_z / 2 + 0.012)),
                        (0.22, 1.7, 0.024),
                        color,
                    )
                )
    return visuals


def pattern_centers(lower: float, upper: float) -> list[float]:
    return [lower + 0.42 + index * 0.68 for index in range(int((upper - lower) / 0.68))]


def ceiling_grid_visuals(
    bounds: tuple[tuple[float, float], tuple[float, float]],
) -> list[dict]:
    (x0, z0), (x1, z1) = bounds
    y = FLOOR_Y_M + WALL_HEIGHT_M - 0.025
    vertical_count = int((x1 - x0) / 1.2)
    horizontal_count = int((z1 - z0) / 1.2)
    vertical = [
        colored_box(
            f"authored_ceiling_grid_x_{index}",
            (x0 + (index + 1) * (x1 - x0) / (vertical_count + 1), y, (z0 + z1) / 2),
            (0.035, 0.05, z1 - z0),
            GRID,
        )
        for index in range(vertical_count)
    ]
    horizontal = [
        colored_box(
            f"authored_ceiling_grid_z_{index}",
            ((x0 + x1) / 2, y, z0 + (index + 1) * (z1 - z0) / (horizontal_count + 1)),
            (x1 - x0, 0.05, 0.035),
            GRID,
        )
        for index in range(horizontal_count)
    ]
    return vertical + horizontal


def wall_visual_box(
    name: str,
    lower: tuple[float, float],
    upper: tuple[float, float],
    color: tuple[float, float, float],
) -> dict:
    x0, z0 = lower
    x1, z1 = upper
    return colored_box(
        name,
        ((x0 + x1) / 2, FLOOR_Y_M + WALL_HEIGHT_M / 2, (z0 + z1) / 2),
        (x1 - x0, WALL_HEIGHT_M, z1 - z0),
        color,
    )


def colored_box(
    name: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    color: tuple[float, float, float],
) -> dict:
    return {
        "name": name,
        "center_world_m": list(center),
        "size_m": list(size),
        "color_srgb": list(color),
    }


def light_visuals(lower_x: float, upper_x: float, center_z: float) -> list[dict]:
    count = 3
    spacing = (upper_x - lower_x) / (count + 1)
    y = FLOOR_Y_M + WALL_HEIGHT_M - 0.035
    return [
        colored_box(
            f"authored_ceiling_light_{index + 1}",
            (lower_x + spacing * (index + 1), y, center_z),
            (1.5, 0.06, 0.55),
            LIGHT,
        )
        for index in range(count)
    ]
