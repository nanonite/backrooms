"""Evidence-only source floor support grid utilities.

This module never turns unknown cells into support and does not define a runtime
asset contract. Coordinates are declared #100 Godot-world metres only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

STEP_DISCONTINUITY = 1
SLOPE_LIMIT = 2
NEIGHBOUR_OFFSETS = ((1, 0), (0, 1), (1, 1), (1, -1))


class SupportGridError(ValueError):
    """Raised when frame or support-grid inputs are ambiguous."""


@dataclass(frozen=True)
class SupportGrid:
    """Cell-centre heights; NaN means no observed source support."""

    origin_x_m: float
    origin_z_m: float
    spacing_m: float
    heights_m: np.ndarray

    def __post_init__(self) -> None:
        heights = np.asarray(self.heights_m, dtype=np.float64)
        if heights.ndim != 2 or min(heights.shape) < 2:
            raise SupportGridError("height grid must be 2D and at least 2x2")
        if not np.isfinite([self.origin_x_m, self.origin_z_m, self.spacing_m]).all():
            raise SupportGridError("grid origin and spacing must be finite")
        if self.spacing_m <= 0.0:
            raise SupportGridError("grid spacing must be positive")
        if np.isinf(heights).any():
            raise SupportGridError("unknown samples must use NaN, not infinity")
        object.__setattr__(self, "heights_m", heights)

    @property
    def observed(self) -> np.ndarray:
        """Return the source-observation mask without filling any cells."""
        return np.isfinite(self.heights_m)


@dataclass(frozen=True)
class FilteredSupport:
    """Support cells after local slope and step checks."""

    supported: np.ndarray
    rejection_reason: np.ndarray


@dataclass(frozen=True)
class SupportMesh:
    """Upward-facing triangles over fully observed adjacent support cells."""

    vertices: np.ndarray
    triangles: np.ndarray


def validate_alignment_manifest(document: dict, scene_id: str) -> dict:
    """Check scale derivation and axis mapping before accepting source samples."""
    if document.get("scene_id") != scene_id:
        raise SupportGridError("alignment manifest scene_id does not match the source")
    mapping = document.get("ply_to_world", {})
    reference = document.get("scale_reference", {})
    scale = float(mapping.get("metres_per_unit", 0.0))
    raw_units = float(reference.get("raw_units", 0.0))
    target_metres = float(reference.get("target_metres", 0.0))
    if scale <= 0.0 or raw_units <= 0.0 or target_metres <= 0.0:
        raise SupportGridError("alignment scale reference must be positive")
    expected_scale = target_metres / raw_units
    if abs(scale - expected_scale) > 1e-6 * max(expected_scale, 1.0):
        raise SupportGridError("declared scale disagrees with its alignment reference")
    columns = np.asarray(mapping.get("basis_columns"), dtype=np.float64)
    if columns.shape != (3, 3) or not np.isfinite(columns).all():
        raise SupportGridError("alignment basis must contain three finite columns")
    basis = columns.T
    if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-6):
        raise SupportGridError("alignment basis is not orthonormal")
    if not np.isclose(np.linalg.det(basis), 1.0, atol=1e-6):
        raise SupportGridError("alignment basis must preserve right-handed orientation")
    up_axis = str(mapping.get("up_axis", ""))
    if up_axis not in "xyz" or len(up_axis) != 1:
        raise SupportGridError("alignment up_axis must be x, y, or z")
    up_index = "xyz".index(up_axis)
    up_sign = int(mapping.get("up_sign", 0))
    world_up = columns[up_index] * up_sign
    if up_sign not in (-1, 1) or not np.allclose(world_up, [0.0, 1.0, 0.0], atol=1e-6):
        raise SupportGridError("source up axis does not map to Godot world +Y")
    horizontal = np.delete(columns, up_index, axis=0)
    if np.any(np.abs(horizontal[:, 1]) > 1e-6):
        raise SupportGridError("source horizontal axes do not map to world XZ")
    return {
        "metres_per_unit": scale,
        "scale_kind": str(reference.get("kind", "unknown")),
        "source_up_axis": up_axis,
        "world_up_axis": "y",
        "world_horizontal_axes": ["x", "z"],
    }


def grid_from_points(
    points_world: np.ndarray,
    origin_x_m: float,
    origin_z_m: float,
    spacing_m: float,
    shape: tuple[int, int],
) -> SupportGrid:
    """Bin observed floor samples into grid cells; empty bins remain NaN."""
    points = np.asarray(points_world, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise SupportGridError("world samples must be a finite N x 3 array")
    if spacing_m <= 0.0 or min(shape) < 2:
        raise SupportGridError("spacing and grid shape are invalid")
    samples: dict[tuple[int, int], list[float]] = {}
    for x, y, z in points:
        column = int(np.floor((x - origin_x_m) / spacing_m))
        row = int(np.floor((z - origin_z_m) / spacing_m))
        if 0 <= row < shape[0] and 0 <= column < shape[1]:
            samples.setdefault((row, column), []).append(float(y))
    heights = np.full(shape, np.nan, dtype=np.float64)
    for index, values in samples.items():
        heights[index] = float(np.median(values))
    return SupportGrid(origin_x_m, origin_z_m, spacing_m, heights)


def filter_support(
    grid: SupportGrid, max_slope_degrees: float, max_step_m: float
) -> FilteredSupport:
    """Reject both sides of excessive local slope or step; leave gaps unknown."""
    if not np.isfinite([max_slope_degrees, max_step_m]).all():
        raise SupportGridError("slope and step limits must be finite")
    if not 0.0 < max_slope_degrees < 90.0 or max_step_m <= 0.0:
        raise SupportGridError("slope and step limits must be positive and finite")
    heights = grid.heights_m
    observed = grid.observed
    reason = np.zeros(heights.shape, dtype=np.uint8)
    slope_limit = np.tan(np.deg2rad(max_slope_degrees))
    rows, columns = heights.shape
    for row in range(rows):
        for column in range(columns):
            if not observed[row, column]:
                continue
            for dx, dz in NEIGHBOUR_OFFSETS:
                neighbour_x = column + dx
                neighbour_z = row + dz
                if neighbour_x >= columns or not 0 <= neighbour_z < rows:
                    continue
                if not observed[neighbour_z, neighbour_x]:
                    continue
                delta = abs(heights[row, column] - heights[neighbour_z, neighbour_x])
                distance = grid.spacing_m * float(np.hypot(dx, dz))
                if delta > max_step_m:
                    reason[row, column] |= STEP_DISCONTINUITY
                    reason[neighbour_z, neighbour_x] |= STEP_DISCONTINUITY
                if delta / distance > slope_limit:
                    reason[row, column] |= SLOPE_LIMIT
                    reason[neighbour_z, neighbour_x] |= SLOPE_LIMIT
    return FilteredSupport(observed & (reason == 0), reason)


def triangulate_support(grid: SupportGrid, filtered: FilteredSupport) -> SupportMesh:
    """Triangulate only quads whose four source samples remain supported."""
    if filtered.supported.shape != grid.heights_m.shape:
        raise SupportGridError("filtered support shape does not match the height grid")
    if np.any(filtered.supported & ~grid.observed):
        raise SupportGridError("unknown cells cannot be marked as supported")
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    vertex_ids: dict[tuple[int, int], int] = {}
    rows, columns = grid.heights_m.shape
    for row in range(rows - 1):
        for column in range(columns - 1):
            corners = (
                (row, column),
                (row, column + 1),
                (row + 1, column),
                (row + 1, column + 1),
            )
            if not all(filtered.supported[index] for index in corners):
                continue
            ids = [_vertex_id(grid, index, vertices, vertex_ids) for index in corners]
            lower_left, lower_right, upper_left, upper_right = ids
            faces.extend(
                (
                    (lower_left, upper_left, lower_right),
                    (lower_right, upper_left, upper_right),
                )
            )
    return SupportMesh(
        np.asarray(vertices, dtype=np.float64).reshape(-1, 3),
        np.asarray(faces, dtype=np.int64).reshape(-1, 3),
    )


def _vertex_id(grid, index, vertices, vertex_ids) -> int:
    """Deduplicate one cell-centre mesh vertex."""
    if index not in vertex_ids:
        row, column = index
        vertex_ids[index] = len(vertices)
        vertices.append(
            (
                grid.origin_x_m + (column + 0.5) * grid.spacing_m,
                float(grid.heights_m[row, column]),
                grid.origin_z_m + (row + 0.5) * grid.spacing_m,
            )
        )
    return vertex_ids[index]
