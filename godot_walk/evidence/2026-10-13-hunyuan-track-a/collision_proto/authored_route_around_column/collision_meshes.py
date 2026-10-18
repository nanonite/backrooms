"""Deterministic triangle meshes for the authored floor and collision proxies."""

from __future__ import annotations

import math

import numpy as np


def floor_ring_mesh(
    center_xz: np.ndarray, floor_y: float, inner_m: float, outer_m: float, segments: int
) -> tuple[np.ndarray, np.ndarray]:
    """Create an upward-facing triangle strip with the route width fixed."""
    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    vertices, faces = [], []
    for index, angle in enumerate(angles):
        next_angle = angles[(index + 1) % segments]
        vertices.extend(
            _ring_quad(center_xz, floor_y, inner_m, outer_m, angle, next_angle)
        )
        start = index * 4
        faces.extend(((start, start + 1, start + 2), (start + 2, start + 1, start + 3)))
    return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.uint32)


def _ring_quad(
    center: np.ndarray,
    floor_y: float,
    inner: float,
    outer: float,
    start: float,
    end: float,
) -> list[tuple[float, float, float]]:
    """Return one independently indexed ring segment in Godot world axes."""
    return [
        (
            center[0] + inner * math.cos(start),
            floor_y,
            center[1] + inner * math.sin(start),
        ),
        (center[0] + inner * math.cos(end), floor_y, center[1] + inner * math.sin(end)),
        (
            center[0] + outer * math.cos(start),
            floor_y,
            center[1] + outer * math.sin(start),
        ),
        (center[0] + outer * math.cos(end), floor_y, center[1] + outer * math.sin(end)),
    ]


def box_mesh(
    lower: np.ndarray, upper: np.ndarray, floor_y: float, height_m: float
) -> tuple[np.ndarray, np.ndarray]:
    """Create the conservative, axis-aligned obstacle proxy mesh."""
    return _box_vertices(lower, upper, floor_y, height_m), _box_faces()


def edge_boundary_mesh(
    center_xz: np.ndarray,
    inner_radius_m: float,
    outer_radius_m: float,
    floor_y: float,
    height_m: float,
    thickness_m: float,
    segments: int,
    side: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a watertight annular wall shell outside one open floor-strip edge."""
    if segments < 3 or height_m <= 0.0 or thickness_m <= 0.0:
        raise ValueError("edge boundary dimensions must be positive with at least three segments")
    if side == "inner":
        wall_inner, wall_outer = inner_radius_m - thickness_m, inner_radius_m
    elif side == "outer":
        wall_inner, wall_outer = outer_radius_m, outer_radius_m + thickness_m
    else:
        raise ValueError(f"unknown route edge boundary side: {side}")
    if wall_inner <= 0.0:
        raise ValueError("inner edge boundary crosses the route center")
    return _annular_wall_mesh(
        center_xz, wall_inner, wall_outer, floor_y, floor_y + height_m, segments
    )


def _annular_wall_mesh(
    center_xz: np.ndarray,
    inner_radius_m: float,
    outer_radius_m: float,
    bottom_y: float,
    top_y: float,
    segments: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Create connected inner, outer, top and bottom surfaces for a closed wall."""
    angles = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
    vertices = np.empty((segments * 4, 3), dtype=np.float32)
    radii = (inner_radius_m, outer_radius_m)
    for level, y in enumerate((bottom_y, top_y)):
        for radius_index, radius in enumerate(radii):
            start = (level * 2 + radius_index) * segments
            vertices[start : start + segments, 0] = center_xz[0] + radius * np.cos(angles)
            vertices[start : start + segments, 1] = y
            vertices[start : start + segments, 2] = center_xz[1] + radius * np.sin(angles)
    faces: list[tuple[int, int, int]] = []
    for index in range(segments):
        following = (index + 1) % segments
        _append_wall_segment_faces(faces, index, following, segments)
    return vertices, np.asarray(faces, dtype=np.uint32)


def _append_wall_segment_faces(
    faces: list[tuple[int, int, int]], index: int, following: int, segments: int
) -> None:
    """Append consistently wound wall faces for one angular segment."""
    inner_bottom, outer_bottom = index, segments + index
    inner_top, outer_top = 2 * segments + index, 3 * segments + index
    next_inner_bottom, next_outer_bottom = following, segments + following
    next_inner_top, next_outer_top = 2 * segments + following, 3 * segments + following
    faces.extend(
        (
            (outer_bottom, outer_top, next_outer_bottom),
            (next_outer_bottom, outer_top, next_outer_top),
            (inner_bottom, next_inner_bottom, inner_top),
            (next_inner_bottom, next_inner_top, inner_top),
            (inner_top, next_inner_top, outer_top),
            (outer_top, next_inner_top, next_outer_top),
            (inner_bottom, outer_bottom, next_inner_bottom),
            (outer_bottom, next_outer_bottom, next_inner_bottom),
        )
    )


def _box_vertices(
    lower: np.ndarray, upper: np.ndarray, floor_y: float, height_m: float
) -> np.ndarray:
    """Create the eight corners of an axis-aligned column proxy."""
    x0, z0 = lower
    x1, z1 = upper
    y0, y1 = floor_y, floor_y + height_m
    return np.array(
        [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y0, z1),
            (x0, y0, z1),
            (x0, y1, z0),
            (x1, y1, z0),
            (x1, y1, z1),
            (x0, y1, z1),
        ],
        dtype=np.float32,
    )


def _box_faces() -> np.ndarray:
    """Return twelve outward-wound triangles for a closed box."""
    return np.array(
        [
            (0, 1, 2),
            (0, 2, 3),
            (4, 6, 5),
            (4, 7, 6),
            (0, 4, 5),
            (0, 5, 1),
            (3, 2, 6),
            (3, 6, 7),
            (1, 5, 6),
            (1, 6, 2),
            (0, 3, 7),
            (0, 7, 4),
        ],
        dtype=np.uint32,
    )
