"""Binary PLY grid I/O and ray-based visual mesh corrections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

import cv2
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
SNAP_BLEND_WIDTH_ELEVATION_DEGREES = 2.0


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
) -> tuple[np.ndarray, dict, np.ndarray]:
    smooth_world, factors = radial_world_positions(positions, camera_center, rotation, scale_field)
    flat = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    radii = np.linalg.norm(flat, axis=1)
    directions = (flat / np.maximum(radii[:, None], 1e-12)) @ np.asarray(rotation).T
    weights = plane_snap_blend_weights(mesh, rotation)
    corrected = smooth_world.reshape(-1, 3).copy()
    smooth_depth = radii * factors.reshape(-1)
    _blend_plane_depth(
        corrected, directions, smooth_depth, weights["floor"].reshape(-1), camera_center, floor_y
    )
    _blend_plane_depth(
        corrected, directions, smooth_depth, weights["ceiling"].reshape(-1), camera_center, ceiling_y
    )
    corrected = corrected.reshape(mesh.height, mesh.width, 3)
    snap_weights = np.maximum(weights["floor"], weights["ceiling"])
    report = {
        "method": "normal-qualified regions with 2-degree angular distance feathering from smooth-field depth to ray-plane depth",
        "floor_panorama_row_fraction": list(FLOOR_BAND),
        "ceiling_panorama_row_fraction": list(CEILING_BAND),
        "normal_vertical_dot_min": NORMAL_VERTICAL_DOT_MIN,
        "blend_width_elevation_degrees": SNAP_BLEND_WIDTH_ELEVATION_DEGREES,
        "floor_vertices_blended": int(np.count_nonzero(weights["floor"])),
        "ceiling_vertices_blended": int(np.count_nonzero(weights["ceiling"])),
        "floor_fully_snapped_vertices": int(np.count_nonzero(weights["floor"] >= 1.0)),
        "ceiling_fully_snapped_vertices": int(np.count_nonzero(weights["ceiling"] >= 1.0)),
        "scale_field_parameter_count": 6,
        "scale_factor_quantiles": np.percentile(factors, [5, 50, 95]).tolist(),
    }
    return corrected, report, snap_weights


def plane_snap_blend_weights(mesh: MeshGrid, rotation: np.ndarray) -> dict[str, np.ndarray]:
    regions = classify_plane_regions(mesh, rotation)
    width_pixels = mesh.height * SNAP_BLEND_WIDTH_ELEVATION_DEGREES / 180.0
    return {
        "floor": _feather_region(regions == -1, width_pixels),
        "ceiling": _feather_region(regions == 1, width_pixels),
    }


def _feather_region(region: np.ndarray, width_pixels: float) -> np.ndarray:
    tiled = np.tile(region.astype(np.uint8), (1, 3))
    distance = cv2.distanceTransform(tiled, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    distance = distance[:, region.shape[1] : 2 * region.shape[1]]
    ramp = np.clip(distance / width_pixels, 0.0, 1.0)
    weights = ramp * ramp * (3.0 - 2.0 * ramp)
    return np.where(region, weights, 0.0).astype(np.float32)


def classify_plane_regions(
    mesh: MeshGrid, rotation: np.ndarray
) -> np.ndarray:
    transform = np.asarray(rotation, dtype=np.float64)
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


def _blend_plane_depth(
    output: np.ndarray,
    directions: np.ndarray,
    smooth_depth: np.ndarray,
    weights: np.ndarray,
    camera_center: np.ndarray,
    plane_y: float,
) -> None:
    region = weights > 0
    vertical = directions[region, 1]
    distance = (plane_y - camera_center[1]) / vertical
    if not np.isfinite(distance).all() or np.any(distance <= 0):
        raise ValueError("plane blend contains a ray that does not point toward its plane")
    corrected_depth = smooth_depth[region] + weights[region] * (distance - smooth_depth[region])
    output[region] = camera_center + directions[region] * corrected_depth[:, None]


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


def mesh_quality(
    mesh: MeshGrid,
    source_baseline_positions: np.ndarray,
    after_positions: np.ndarray,
    snap_weights: np.ndarray | None,
    max_degenerate_triangles: int,
) -> dict:
    source = np.asarray(source_baseline_positions, dtype=np.float64).reshape(-1, 3)
    corrected = np.asarray(after_positions, dtype=np.float64).reshape(-1, 3)
    flat_weights = None if snap_weights is None else np.asarray(snap_weights).reshape(-1)
    edge_ratios = np.empty(mesh.face_count * 3, dtype=np.float32)
    boundary_ratios = []
    flipped_faces = 0
    flippable_faces = 0
    source_degenerate_faces = 0
    degenerate_faces = 0
    edge_offset = 0
    chunk_size = 250_000
    for start in range(0, mesh.face_count, chunk_size):
        indices = mesh.faces["indices"][start : start + chunk_size]
        source_triangles = source[indices]
        corrected_triangles = corrected[indices]
        source_normals = np.cross(
            source_triangles[:, 1] - source_triangles[:, 0],
            source_triangles[:, 2] - source_triangles[:, 0],
        )
        corrected_normals = np.cross(
            corrected_triangles[:, 1] - corrected_triangles[:, 0],
            corrected_triangles[:, 2] - corrected_triangles[:, 0],
        )
        source_area = np.linalg.norm(source_normals, axis=1)
        corrected_area = np.linalg.norm(corrected_normals, axis=1)
        source_degenerate_faces += int(np.count_nonzero(source_area <= 1e-10))
        degenerate_faces += int(np.count_nonzero(corrected_area <= 1e-10))
        flippable = (source_area > 1e-10) & (corrected_area > 1e-10)
        flippable_faces += int(np.count_nonzero(flippable))
        flipped_faces += int(np.count_nonzero(flippable & (np.einsum("ij,ij->i", source_normals, corrected_normals) < 0.0)))
        for edge_start, edge_end in ((0, 1), (1, 2), (2, 0)):
            source_length = np.linalg.norm(
                source_triangles[:, edge_start] - source_triangles[:, edge_end], axis=1
            )
            corrected_length = np.linalg.norm(
                corrected_triangles[:, edge_start] - corrected_triangles[:, edge_end], axis=1
            )
            valid = source_length > 1e-10
            ratio = corrected_length[valid] / source_length[valid]
            count = len(ratio)
            edge_ratios[edge_offset : edge_offset + count] = ratio
            edge_offset += count
            if flat_weights is not None:
                start_weight = flat_weights[indices[:, edge_start]]
                end_weight = flat_weights[indices[:, edge_end]]
                feather_edge = (
                    ((start_weight > 0) != (end_weight > 0))
                    | ((start_weight > 0) & (start_weight < 1))
                    | ((end_weight > 0) & (end_weight < 1))
                )
                if np.any(feather_edge & valid):
                    boundary = feather_edge & valid
                    boundary_ratios.append(corrected_length[boundary] / source_length[boundary])
    edge_ratios = edge_ratios[:edge_offset]
    within_range = (edge_ratios >= 0.5) & (edge_ratios <= 2.0)
    edge_fraction = float(np.count_nonzero(within_range) / len(edge_ratios)) if len(edge_ratios) else 0.0
    boundary = np.concatenate(boundary_ratios) if boundary_ratios else np.empty(0)
    return {
        "edge_population": "all triangle edge instances, including shared-edge repeats",
        "edge_count": int(len(edge_ratios)),
        "edge_ratio_q50_q90_q99_max": np.percentile(edge_ratios, [50, 90, 99, 100]).tolist(),
        "edge_fraction_within_0.5x_2x": edge_fraction,
        "edge_fraction_gate_pass": edge_fraction >= 0.99,
        "source_baseline_degenerate_triangle_count": source_degenerate_faces,
        "degenerate_triangle_count": degenerate_faces,
        "degenerate_triangle_limit": max_degenerate_triangles,
        "degenerate_triangle_gate_pass": degenerate_faces <= max_degenerate_triangles,
        "flipped_face_count": flipped_faces,
        "flippable_face_count": flippable_faces,
        "flipped_face_gate_pass": flipped_faces == 0,
        "mesh_quality_pass": (
            edge_fraction >= 0.99
            and degenerate_faces <= max_degenerate_triangles
            and flipped_faces == 0
        ),
        "snap_boundary_edge_count": int(len(boundary)),
        "snap_boundary_edge_stretch_q50_q90_q99_max": (
            np.percentile(boundary, [50, 90, 99, 100]).tolist() if len(boundary) else None
        ),
    }
