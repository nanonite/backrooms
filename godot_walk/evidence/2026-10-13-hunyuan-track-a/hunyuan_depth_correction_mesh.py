"""Binary PLY grid I/O and ray-based visual mesh corrections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

import numpy as np

from hunyuan_depth_correction_model import ScaleField

VERTEX_DTYPE = np.dtype(
    [
        ("x", "<f8"),
        ("y", "<f8"),
        ("z", "<f8"),
        ("nx", "<f8"),
        ("ny", "<f8"),
        ("nz", "<f8"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)
FACE_DTYPE = np.dtype([("count", "u1"), ("indices", "<u4", (3,))])
OUTPUT_VERTEX_DTYPE = np.dtype(
    [("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("red", "u1"), ("green", "u1"), ("blue", "u1")]
)
FLOOR_BAND = (0.56, 0.62)
CEILING_BAND = (0.37, 0.42)
NORMAL_VERTICAL_DOT_MIN = float(np.cos(np.deg2rad(35.0)))


@dataclass
class MeshGrid:
    path: Path
    width: int
    height: int
    records: np.memmap
    faces: np.memmap
    face_offset: int
    face_count: int

    @property
    def positions(self) -> np.ndarray:
        return np.stack((self.records["x"], self.records["y"], self.records["z"]), axis=-1).reshape(
            self.height, self.width, 3
        )

    @property
    def normals(self) -> np.ndarray:
        return np.stack((self.records["nx"], self.records["ny"], self.records["nz"]), axis=-1).reshape(
            self.height, self.width, 3
        )

    @property
    def colors(self) -> np.ndarray:
        return np.stack(
            (self.records["red"], self.records["green"], self.records["blue"]), axis=-1
        )


def read_mesh_grid(path: Path) -> MeshGrid:
    with path.open("rb") as source:
        header, vertex_count, face_count, vertex_offset = _read_header(source)
    if b"format binary_little_endian 1.0" not in header:
        raise ValueError("expected binary little-endian PLY")
    if b"property double x" not in header or b"property uchar red" not in header:
        raise ValueError("PLY vertex layout differs from the pinned Hunyuan export")
    if vertex_count * VERTEX_DTYPE.itemsize > path.stat().st_size:
        raise ValueError("PLY vertex data is truncated")
    width = round(np.sqrt(vertex_count * 2))
    height = vertex_count // width
    if width * height != vertex_count or width != 2 * height:
        raise ValueError("mesh vertex count is not a 2:1 panorama grid")
    face_offset = vertex_offset + vertex_count * VERTEX_DTYPE.itemsize
    expected_size = face_offset + face_count * FACE_DTYPE.itemsize
    if expected_size != path.stat().st_size:
        raise ValueError("PLY face data is truncated or has an unsupported layout")
    records = np.memmap(path, mode="r", dtype=VERTEX_DTYPE, offset=vertex_offset, shape=(vertex_count,))
    faces = np.memmap(path, mode="r", dtype=FACE_DTYPE, offset=face_offset, shape=(face_count,))
    if np.any(faces["count"] != 3):
        raise ValueError("only triangle faces are supported")
    return MeshGrid(path, width, height, records, faces, face_offset, face_count)


def _read_header(source) -> tuple[bytes, int, int, int]:
    lines = []
    vertex_count = face_count = None
    while True:
        line = source.readline()
        if not line:
            raise ValueError("PLY header has no end_header")
        lines.append(line)
        if line.startswith(b"element vertex "):
            vertex_count = int(line.split()[2])
        elif line.startswith(b"element face "):
            face_count = int(line.split()[2])
        elif line.strip() == b"end_header":
            break
    if vertex_count is None or face_count is None:
        raise ValueError("PLY header lacks vertex or face count")
    return b"".join(lines), vertex_count, face_count, source.tell()


def radial_world_positions(
    positions: np.ndarray,
    camera_center: np.ndarray,
    rotation: np.ndarray,
    scale_field: ScaleField,
) -> tuple[np.ndarray, np.ndarray]:
    flat = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    radius = np.linalg.norm(flat, axis=1)
    safe_radius = np.maximum(radius, 1e-12)
    elevation = np.arcsin(np.clip(flat[:, 2] / safe_radius, -1.0, 1.0))
    factor = scale_field.predict(elevation, safe_radius)
    if not np.isfinite(factor).all() or np.any(factor <= 0):
        raise ValueError("scale field predicts a non-positive or non-finite mesh scale")
    world = np.asarray(camera_center) + (flat * factor[:, None]) @ np.asarray(rotation).T
    return world.reshape(positions.shape), factor.reshape(positions.shape[:2])


def plane_snapped_world_positions(
    mesh: MeshGrid,
    positions: np.ndarray,
    camera_center: np.ndarray,
    rotation: np.ndarray,
    scale_field: ScaleField,
    floor_y: float,
    ceiling_y: float,
) -> tuple[np.ndarray, dict]:
    smooth_world, factors = radial_world_positions(positions, camera_center, rotation, scale_field)
    flat = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    regions = classify_plane_regions(mesh, rotation, camera_center)
    floor_region = regions.reshape(-1) == -1
    ceiling_region = regions.reshape(-1) == 1
    world_directions = (flat / np.maximum(np.linalg.norm(flat, axis=1)[:, None], 1e-12)) @ np.asarray(rotation).T
    corrected = smooth_world.reshape(-1, 3).copy()
    _snap_region(corrected, world_directions, floor_region, camera_center, floor_y)
    _snap_region(corrected, world_directions, ceiling_region, camera_center, ceiling_y)
    corrected = corrected.reshape(mesh.height, mesh.width, 3)
    report = {
        "method": "normal-and-elevation segmentation; radial plane intersection for floor/ceiling; quadratic smooth field for remaining vertices",
        "floor_panorama_row_fraction": list(FLOOR_BAND),
        "ceiling_panorama_row_fraction": list(CEILING_BAND),
        "normal_vertical_dot_min": NORMAL_VERTICAL_DOT_MIN,
        "floor_vertices_snapped": int(np.count_nonzero(floor_region)),
        "ceiling_vertices_snapped": int(np.count_nonzero(ceiling_region)),
        "wall_and_transition_vertices_smooth_corrected": int(len(flat) - np.count_nonzero(floor_region | ceiling_region)),
        "scale_field_parameter_count": 6,
        "scale_factor_quantiles_for_smooth_vertices": np.percentile(
            factors[~(floor_region | ceiling_region).reshape(mesh.height, mesh.width)], [5, 50, 95]
        ).tolist(),
    }
    return corrected, report


def classify_plane_regions(
    mesh: MeshGrid, rotation: np.ndarray, camera_center: np.ndarray
) -> np.ndarray:
    transform = np.asarray(rotation, dtype=np.float64)
    center = np.asarray(camera_center, dtype=np.float64)
    local = np.column_stack((mesh.records["x"], mesh.records["y"], mesh.records["z"]))
    local_normals = np.column_stack((mesh.records["nx"], mesh.records["ny"], mesh.records["nz"]))
    normal_y = local_normals @ transform[1, :]
    normal_length = np.linalg.norm(local_normals, axis=1)
    normal_y = np.divide(
        np.abs(normal_y), normal_length, out=np.zeros_like(normal_y), where=normal_length > 1e-12
    )
    ray_y = local @ transform[1, :]
    rows = np.arange(mesh.height, dtype=np.float64) / mesh.height
    row_fraction = np.repeat(rows, mesh.width)
    floor = (
        (row_fraction >= FLOOR_BAND[0])
        & (row_fraction <= FLOOR_BAND[1])
        & (normal_y >= NORMAL_VERTICAL_DOT_MIN)
        & (ray_y < 0.0)
    )
    ceiling = (
        (row_fraction >= CEILING_BAND[0])
        & (row_fraction <= CEILING_BAND[1])
        & (normal_y >= NORMAL_VERTICAL_DOT_MIN)
        & (ray_y > 0.0)
    )
    labels = np.zeros(len(local), dtype=np.int8)
    labels[floor] = -1
    labels[ceiling] = 1
    return labels.reshape(mesh.height, mesh.width)


def _snap_region(
    output: np.ndarray,
    directions: np.ndarray,
    region: np.ndarray,
    camera_center: np.ndarray,
    plane_y: float,
) -> None:
    vertical = directions[region, 1]
    distance = (plane_y - camera_center[1]) / vertical
    if not np.isfinite(distance).all() or np.any(distance <= 0):
        raise ValueError("plane region contains a ray that does not point toward its plane")
    output[region] = camera_center + directions[region] * distance[:, None]


def write_corrected_ply(
    mesh: MeshGrid,
    output_path: Path,
    world_positions: np.ndarray,
    chunk_vertices: int = 250_000,
) -> None:
    if output_path.exists():
        raise FileExistsError("refusing to overwrite corrected mesh: %s" % output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        "comment Route A experimental visual correction in #100 declared world coordinates\n"
        f"element vertex {mesh.records.shape[0]}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        f"element face {mesh.face_count}\nproperty list uchar uint vertex_indices\nend_header\n"
    ).encode("ascii")
    flat_positions = np.asarray(world_positions, dtype=np.float64).reshape(-1, 3)
    colors = mesh.colors
    with output_path.open("wb") as target:
        target.write(header)
        for start in range(0, len(flat_positions), chunk_vertices):
            end = min(start + chunk_vertices, len(flat_positions))
            chunk = np.empty(end - start, dtype=OUTPUT_VERTEX_DTYPE)
            chunk["x"], chunk["y"], chunk["z"] = flat_positions[start:end].T
            chunk["red"], chunk["green"], chunk["blue"] = colors[start:end].T
            chunk.tofile(target)
        with mesh.path.open("rb") as source:
            source.seek(mesh.face_offset)
            shutil.copyfileobj(source, target, length=4 * 1024 * 1024)


def seam_integrity(
    mesh: MeshGrid,
    before_positions: np.ndarray,
    after_positions: np.ndarray,
    snap_mask: np.ndarray | None,
    global_scale: float,
) -> dict:
    before = np.asarray(before_positions, dtype=np.float64)
    after = np.asarray(after_positions, dtype=np.float64)
    if snap_mask is None:
        seam_stats = _edge_stats(
            before[:-1], before[1:], after[:-1], after[1:], None, global_scale
        )
        col_stats = _edge_stats(
            before[:, :-1], before[:, 1:], after[:, :-1], after[:, 1:], None, global_scale
        )
        seam_label = "all grid edges; no region boundary in the smooth-field method"
    else:
        seam_stats = _edge_stats(
            before[:-1], before[1:], after[:-1], after[1:], snap_mask[:-1] != snap_mask[1:], global_scale
        )
        col_stats = _edge_stats(
            before[:, :-1], before[:, 1:], after[:, :-1], after[:, 1:], snap_mask[:, :-1] != snap_mask[:, 1:], global_scale
        )
        seam_label = "grid edges crossing snapped-floor/ceiling region boundaries"
    ratios = np.concatenate((seam_stats, col_stats))
    face_degenerate = _count_degenerate_faces(mesh, after)
    if not len(ratios):
        return {
            "edge_population": seam_label,
            "edge_count": 0,
            "max_stretch_ratio": None,
            "max_compression_ratio": None,
            "tear_like_edge_count_ratio_outside_0.5_2.0": 0,
            "degenerate_triangle_count": face_degenerate,
        }
    return {
        "edge_population": seam_label,
        "edge_count": len(ratios),
        "edge_stretch_ratio_q50_q90_q99_max": np.percentile(ratios, [50, 90, 99, 100]).tolist(),
        "max_stretch_ratio": float(np.max(ratios)),
        "max_compression_ratio": float(np.min(ratios)),
        "tear_like_edge_count_ratio_outside_0.5_2.0": int(
            np.count_nonzero((ratios < 0.5) | (ratios > 2.0))
        ),
        "degenerate_triangle_count": face_degenerate,
    }


def _edge_stats(
    before_start: np.ndarray,
    before_end: np.ndarray,
    after_start: np.ndarray,
    after_end: np.ndarray,
    seam: np.ndarray | None,
    global_scale: float,
) -> np.ndarray:
    if seam is None:
        seam = np.ones(before_start.shape[:-1], dtype=bool)
    raw_length = np.linalg.norm(before_start - before_end, axis=-1) * global_scale
    corrected_length = np.linalg.norm(after_start - after_end, axis=-1)
    valid = seam & (raw_length > 1e-8)
    return corrected_length[valid] / raw_length[valid]


def _count_degenerate_faces(mesh: MeshGrid, positions: np.ndarray, chunk: int = 500_000) -> int:
    flat = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    degenerate = 0
    for start in range(0, mesh.face_count, chunk):
        indices = mesh.faces["indices"][start : start + chunk]
        points = flat[indices]
        areas = np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)
        degenerate += int(np.count_nonzero(areas <= 1e-10))
    return degenerate
