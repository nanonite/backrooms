"""Evidence-only rasterization of an explicitly assumed camera-path support strip."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
from scipy import ndimage


class CameraPathPriorError(ValueError):
    """Raised when a camera-path prior is not well-formed."""


def rasterize_strip(
    polyline_xz: np.ndarray,
    spacing_m: float,
    total_width_m: float,
    origin_xz_m: tuple[float, float],
    shape: tuple[int, int],
) -> np.ndarray:
    """Mark cells whose centres lie within half-width of any polyline segment."""
    path = _validate_path(polyline_xz)
    if not np.isfinite([spacing_m, total_width_m, *origin_xz_m]).all():
        raise CameraPathPriorError("grid and width values must be finite")
    if spacing_m <= 0.0 or total_width_m <= 0.0 or min(shape) < 2:
        raise CameraPathPriorError(
            "grid spacing, strip width, and shape must be positive"
        )

    supported = np.zeros(shape, dtype=bool)
    radius = total_width_m * 0.5
    for start, end in pairwise(path):
        _rasterize_segment(supported, start, end, spacing_m, radius, origin_xz_m)
    return supported


def erase_hole(
    supported: np.ndarray,
    origin_xz_m: tuple[float, float],
    spacing_m: float,
    center_xz_m: tuple[float, float],
    radius_m: float,
) -> np.ndarray:
    """Return a copy with support removed in a disk; never fill adjacent cells."""
    support = np.asarray(supported, dtype=bool)
    if support.ndim != 2 or min(support.shape) < 2:
        raise CameraPathPriorError("support must be a 2D grid of at least 2x2")
    if not np.isfinite([*origin_xz_m, *center_xz_m, spacing_m, radius_m]).all():
        raise CameraPathPriorError("hole and grid values must be finite")
    if spacing_m <= 0.0 or radius_m <= 0.0:
        raise CameraPathPriorError("grid spacing and hole radius must be positive")

    rows, columns = np.indices(support.shape)
    x = origin_xz_m[0] + (columns + 0.5) * spacing_m
    z = origin_xz_m[1] + (rows + 0.5) * spacing_m
    hole = (x - center_xz_m[0]) ** 2 + (z - center_xz_m[1]) ** 2 <= radius_m**2
    return support & ~hole


def nearest_distances(
    grid: np.ndarray,
    points_xz: np.ndarray,
    origin_xz_m: tuple[float, float],
    spacing_m: float,
) -> np.ndarray:
    """Return distance from each query to the closest supported cell centre."""
    support = np.asarray(grid, dtype=bool)
    points = np.asarray(points_xz, dtype=np.float64)
    if support.ndim != 2 or points.ndim != 2 or points.shape[1] != 2:
        raise CameraPathPriorError("support must be a grid and points must be Nx2")
    if (
        not np.isfinite(points).all()
        or not np.isfinite([*origin_xz_m, spacing_m]).all()
    ):
        raise CameraPathPriorError("grid and query coordinates must be finite")
    if spacing_m <= 0.0:
        raise CameraPathPriorError("grid spacing must be positive")
    rows, columns = np.nonzero(support)
    if not len(rows):
        return np.full(len(points), np.inf)

    cell_centres = np.column_stack(
        (
            origin_xz_m[0] + (columns + 0.5) * spacing_m,
            origin_xz_m[1] + (rows + 0.5) * spacing_m,
        )
    )
    distances = points[:, None, :] - cell_centres[None, :, :]
    return np.sqrt(np.sum(distances * distances, axis=2)).min(axis=1)


def component_count(supported: np.ndarray) -> int:
    """Count 8-connected supported regions in the raster."""
    grid = np.asarray(supported, dtype=bool)
    if grid.ndim != 2:
        raise CameraPathPriorError("support must be a 2D grid")
    labels, count = ndimage.label(grid, structure=np.ones((3, 3), dtype=np.uint8))
    del labels
    return int(count)


def _validate_path(polyline_xz: np.ndarray) -> np.ndarray:
    path = np.asarray(polyline_xz, dtype=np.float64)
    if path.ndim != 2 or path.shape[1] != 2 or len(path) < 2:
        raise CameraPathPriorError("camera path must contain at least two XZ points")
    if not np.isfinite(path).all():
        raise CameraPathPriorError("camera path must be finite")
    if np.any(np.linalg.norm(np.diff(path, axis=0), axis=1) <= 1e-9):
        raise CameraPathPriorError("camera path contains duplicate consecutive points")
    return path


def _rasterize_segment(support, start, end, spacing, radius, origin):
    """Rasterize only the bounded cell-centre window around one segment."""
    lower = np.minimum(start, end) - radius
    upper = np.maximum(start, end) + radius
    first = np.floor((lower - origin) / spacing - 0.5).astype(int)
    last = np.ceil((upper - origin) / spacing - 0.5).astype(int)
    first = np.maximum(first, [0, 0])
    last = np.minimum(last, [support.shape[1] - 1, support.shape[0] - 1])
    if np.any(last < first):
        return

    columns, rows = np.meshgrid(
        np.arange(first[0], last[0] + 1),
        np.arange(first[1], last[1] + 1),
    )
    points = np.column_stack(
        (
            origin[0] + (columns.ravel() + 0.5) * spacing,
            origin[1] + (rows.ravel() + 0.5) * spacing,
        )
    )
    segment = end - start
    parameter = np.clip(((points - start) @ segment) / (segment @ segment), 0.0, 1.0)
    closest = start + parameter[:, None] * segment
    within = np.sum((points - closest) ** 2, axis=1) <= radius**2 + 1e-12
    support[rows.ravel()[within], columns.ravel()[within]] = True
