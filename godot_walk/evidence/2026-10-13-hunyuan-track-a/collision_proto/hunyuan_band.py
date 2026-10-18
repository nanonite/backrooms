"""CPU-only Hunyuan panorama-band filters for evidence, not runtime assets."""

from __future__ import annotations

import numpy as np

GRID_HEIGHT = 1920
GRID_WIDTH = 3840
VERTEX_COUNT = GRID_HEIGHT * GRID_WIDTH
BASE_TRIANGLE_COUNT = 2 * (GRID_HEIGHT - 1) * GRID_WIDTH
FLOOR_V_RANGE = (0.56, 0.62)
YAW_LIMIT_DEGREES = 35.0
MAX_SLOPE_DEGREES = 15.0
MAX_STEP_METRES = 0.20


def panorama_vertex_selection(
    local_x: np.ndarray,
    local_y: np.ndarray,
    height: int = GRID_HEIGHT,
    width: int = GRID_WIDTH,
) -> np.ndarray:
    """Select forward floor-band vertices without materializing all positions."""
    x = np.asarray(local_x)
    y = np.asarray(local_y)
    if x.shape != (height * width,) or y.shape != x.shape or height < 2:
        raise ValueError("panorama coordinate arrays do not match their grid")
    first_row = int(np.ceil(FLOOR_V_RANGE[0] * (height - 1)))
    last_row = int(np.floor(FLOOR_V_RANGE[1] * (height - 1)))
    selected = np.zeros(x.shape, dtype=bool)
    for row in range(first_row, last_row + 1):
        start, end = row * width, (row + 1) * width
        yaw = np.rad2deg(np.arctan2(y[start:end], -x[start:end]))
        selected[start:end] = np.abs(yaw) <= YAW_LIMIT_DEGREES
    return selected


def select_original_faces(
    records: np.ndarray,
    in_crop: np.ndarray,
    foreground: np.ndarray,
    triangle_limit: int = BASE_TRIANGLE_COUNT,
    chunk_size: int = 1_000_000,
) -> tuple[np.ndarray, dict[str, int]]:
    """Keep base sheet triangles only; omit mask-touching and seam-fill faces."""
    if len(records) < triangle_limit:
        raise ValueError("PLY does not contain the complete original sheet face range")
    if in_crop.shape != foreground.shape:
        raise ValueError("vertex selection masks must match the panorama grid")
    kept = []
    crop_faces = 0
    masked_faces = 0
    boundary_faces = 0
    for start in range(0, triangle_limit, chunk_size):
        end = min(start + chunk_size, triangle_limit)
        faces = np.column_stack(
            (records["a"][start:end], records["b"][start:end], records["c"][start:end])
        ).astype(np.int64, copy=False)
        crop_corners = in_crop[faces]
        wholly_in_crop = crop_corners.all(axis=1)
        boundary_faces += int((crop_corners.any(axis=1) & ~wholly_in_crop).sum())
        crop_faces += int(wholly_in_crop.sum())
        mask_corners = foreground[faces]
        touches_mask = mask_corners.any(axis=1)
        masked_faces += int((wholly_in_crop & touches_mask).sum())
        keep = wholly_in_crop & ~touches_mask
        if keep.any():
            kept.append(faces[keep])
    result = np.concatenate(kept) if kept else np.empty((0, 3), dtype=np.int64)
    return result, {
        "wholly_in_crop_triangles": crop_faces,
        "crop_boundary_triangles_omitted": boundary_faces,
        "foreground_mask_triangles_omitted": masked_faces,
        "triangles_after_crop_and_mask": len(result),
    }


def triangle_metrics(
    points_world: np.ndarray, faces: np.ndarray
) -> dict[str, np.ndarray]:
    """Return per-face area, slope, vertical edge step, and winding direction."""
    triangles = np.asarray(points_world, dtype=np.float64)[faces]
    edges = np.stack(
        (
            triangles[:, 1] - triangles[:, 0],
            triangles[:, 2] - triangles[:, 1],
            triangles[:, 0] - triangles[:, 2],
        ),
        axis=1,
    )
    normal = np.cross(edges[:, 0], triangles[:, 2] - triangles[:, 0])
    normal_length = np.linalg.norm(normal, axis=1)
    area = normal_length * 0.5
    vertical_share = np.divide(
        np.abs(normal[:, 1]),
        normal_length,
        out=np.zeros_like(normal_length),
        where=normal_length > 1e-12,
    )
    slope = np.rad2deg(np.arccos(np.clip(vertical_share, 0.0, 1.0)))
    step = np.max(np.abs(edges[:, :, 1]), axis=1)
    return {
        "area_m2": area,
        "slope_degrees": slope,
        "max_edge_vertical_step_m": step,
        "normal_y": normal[:, 1],
    }


def filter_safe_faces(metrics: dict[str, np.ndarray]) -> np.ndarray:
    """Reject degenerate, steep, or vertically discontinuous triangles."""
    return (
        (metrics["area_m2"] > 1e-12)
        & (metrics["slope_degrees"] <= MAX_SLOPE_DEGREES)
        & (metrics["max_edge_vertical_step_m"] <= MAX_STEP_METRES)
    )


def point_triangle_distance_2d(points: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    """Compute horizontal point-to-projected-triangle distances in XZ."""
    query = np.asarray(points, dtype=np.float64)
    tri = np.asarray(triangle, dtype=np.float64)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    edges = ((a, b), (b, c), (c, a))
    signs = np.stack([_cross_2d(y - x, query[:, None] - x) for x, y in edges], axis=1)
    inside = np.all(signs >= -1e-10, axis=1) | np.all(signs <= 1e-10, axis=1)
    segment_distances = []
    for start, end in edges:
        edge = end - start
        fraction = np.sum((query[:, None] - start) * edge, axis=2) / np.maximum(
            np.sum(edge * edge, axis=1), 1e-30
        )
        nearest = start + np.clip(fraction, 0.0, 1.0)[..., None] * edge
        segment_distances.append(np.linalg.norm(query[:, None] - nearest, axis=2))
    nearest_edge = np.min(np.stack(segment_distances, axis=1), axis=1)
    return np.where(inside, 0.0, nearest_edge)


def _cross_2d(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Return the scalar cross product for broadcast-compatible 2D vectors."""
    return left[..., 0] * right[..., 1] - left[..., 1] * right[..., 0]


def component_records(faces: np.ndarray, area: np.ndarray) -> list[dict]:
    """Find triangle components connected through shared edges."""
    if len(faces) == 0:
        return []
    face_count = len(faces)
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges.sort(axis=1)
    _, edge_group, edge_counts = np.unique(
        edges, axis=0, return_inverse=True, return_counts=True
    )
    face_ids = np.tile(np.arange(face_count, dtype=np.int64), 3)
    order = np.argsort(edge_group)
    sorted_faces = face_ids[order]
    ends = np.cumsum(edge_counts)
    starts = np.concatenate(([0], ends[:-1]))
    shared = np.flatnonzero(edge_counts > 1)
    parent = np.arange(face_count, dtype=np.int64)
    rank = np.zeros(face_count, dtype=np.uint8)

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    for edge_index in shared:
        group_start, group_end = int(starts[edge_index]), int(ends[edge_index])
        adjacent = sorted_faces[group_start:group_end]
        first = root(int(adjacent[0]))
        for face_index in adjacent[1:]:
            other = root(int(face_index))
            if first == other:
                continue
            if rank[first] < rank[other]:
                first, other = other, first
            parent[other] = first
            if rank[first] == rank[other]:
                rank[first] += 1
    roots = np.array([root(index) for index in range(face_count)])
    _, inverse_roots = np.unique(roots, return_inverse=True)
    counts = np.bincount(inverse_roots)
    areas = np.bincount(inverse_roots, weights=area)
    records = [
        {"triangle_count": int(count), "area_m2": float(component_area)}
        for count, component_area in zip(counts, areas, strict=True)
    ]
    return sorted(records, key=lambda item: item["area_m2"], reverse=True)
