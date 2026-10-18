"""Deterministic triangle meshes for the authored floor and column proxy."""

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
