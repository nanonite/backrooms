"""Deterministic geometry helpers for the authored early-pocket module."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np

from collision_meshes import box_mesh

FLOOR_Y_M = -1.2709904909133911
WALL_HEIGHT_M = 2.4
WALL_THICKNESS_M = 0.12


def merge_meshes(
    meshes: Iterable[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0
    for mesh_vertices, mesh_faces in meshes:
        vertices.append(mesh_vertices)
        faces.append(mesh_faces + offset)
        offset += len(mesh_vertices)
    if not vertices:
        raise ValueError("cannot merge an empty mesh collection")
    return np.concatenate(vertices), np.concatenate(faces)


def rectangle_floor(
    lower: tuple[float, float], upper: tuple[float, float], y: float
) -> tuple[np.ndarray, np.ndarray]:
    x0, z0 = lower
    x1, z1 = upper
    vertices = np.asarray(
        [(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)], dtype=np.float32
    )
    faces = np.asarray([(0, 1, 2), (0, 2, 3)], dtype=np.uint32)
    return vertices, faces


def room_walls(
    lower: tuple[float, float], upper: tuple[float, float]
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    return {
        name: box_mesh(np.asarray(box_lower), np.asarray(box_upper), FLOOR_Y_M, WALL_HEIGHT_M)
        for name, box_lower, box_upper in room_wall_boxes(lower, upper)
    }


def room_wall_boxes(
    lower: tuple[float, float], upper: tuple[float, float]
) -> list[tuple[str, tuple[float, float], tuple[float, float]]]:
    x0, z0 = lower
    x1, z1 = upper
    thickness = WALL_THICKNESS_M
    return [
        ("authored_room_boundary_west", (x0 - thickness, z0 - thickness), (x0, z1 + thickness)),
        ("authored_room_boundary_east", (x1, z0 - thickness), (x1 + thickness, z1 + thickness)),
        ("authored_room_boundary_south", (x0, z0 - thickness), (x1, z0)),
        ("authored_room_boundary_north", (x0, z1), (x1, z1 + thickness)),
    ]


def room_walk_loop(
    lower: tuple[float, float], upper: tuple[float, float], margin: float = 0.8
) -> list[list[float]]:
    corners = [
        (lower[0] + margin, lower[1] + margin),
        (upper[0] - margin, lower[1] + margin),
        (upper[0] - margin, upper[1] - margin),
        (lower[0] + margin, upper[1] - margin),
    ]
    points: list[list[float]] = []
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        segments = max(2, math.ceil(math.dist(start, end) / 0.2))
        points.extend(
            [
                [
                    start[0] + (end[0] - start[0]) * step / segments,
                    start[1] + (end[1] - start[1]) * step / segments,
                ]
                for step in range(segments)
            ]
        )
    return points


def wall_box_spec(
    name: str,
    lower: tuple[float, float],
    upper: tuple[float, float],
    color: tuple[float, float, float],
) -> dict:
    x0, z0 = lower
    x1, z1 = upper
    return {
        "name": name,
        "center_world_m": [
            (x0 + x1) * 0.5,
            FLOOR_Y_M + WALL_HEIGHT_M * 0.5,
            (z0 + z1) * 0.5,
        ],
        "size_m": [x1 - x0, WALL_HEIGHT_M, z1 - z0],
        "color_srgb": list(color),
    }
