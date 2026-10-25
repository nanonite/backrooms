"""Utilities for a room-bounded, vertex-color-preserving GLB derivative."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOM_POLYGON_XZ = np.array(
    [(-4.4, -1.2), (0.0, -1.2), (3.5, 1.2), (3.5, 5.6), (-0.3, 5.6), (-4.1, 3.7)],
    dtype=np.float64,
)
FLOOR_Y = -1.27099049
CEILING_Y = FLOOR_Y + 2.4
C02_SOURCE_MASK_XZ = np.array(((-1.6, 3.8), (-0.15, 5.0)), dtype=np.float64)
SOURCE_SCALE = 1.5582858
SOURCE_TRANSLATION = np.array((2.9209783, -0.205319, 3.703508), dtype=np.float64)
SOURCE_QUATERNION_XYZW = np.array(
    (0.6511913, 0.27745163, 0.27848938, -0.64916414), dtype=np.float64
)
CHUNK_JSON = b"JSON"
CHUNK_BIN = b"BIN\x00"


@dataclass(frozen=True)
class GltfDocument:
    document: dict[str, Any]
    binary: bytes


def read_glb(path: Path) -> GltfDocument:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError(f"GLB is too short: {path}")
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total != len(data):
        raise ValueError(f"Invalid GLB header: {path}")
    offset = 12
    document: dict[str, Any] | None = None
    binary: bytes | None = None
    while offset < total:
        length, kind = struct.unpack_from("<I4s", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        if len(chunk) != length:
            raise ValueError(f"Truncated GLB chunk: {path}")
        if kind == CHUNK_JSON:
            document = json.loads(chunk)
        elif kind == CHUNK_BIN:
            binary = chunk
        offset += length
    if document is None or binary is None:
        raise ValueError(f"GLB requires JSON and BIN chunks: {path}")
    return GltfDocument(document, binary)


def accessor_array(gltf: GltfDocument, accessor_index: int) -> np.ndarray:
    accessor = gltf.document["accessors"][accessor_index]
    view = gltf.document["bufferViews"][accessor["bufferView"]]
    dtype, width = _accessor_layout(accessor)
    count = accessor["count"]
    element_size = dtype.itemsize * width
    stride = view.get("byteStride", element_size)
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    shape = (count,) if width == 1 else (count, width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    return np.ndarray(shape, dtype=dtype, buffer=gltf.binary, offset=offset, strides=strides)


def clip_layer(
    positions: np.ndarray,
    colors: np.ndarray,
    indices: np.ndarray,
    *,
    batch_triangles: int = 250_000,
    mask_c02: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("POSITION must be a VEC3 accessor")
    if colors.shape != (positions.shape[0], 4):
        raise ValueError("COLOR_0 must be a VEC4 accessor matching POSITION")
    if indices.size % 3:
        raise ValueError("Triangle indices must contain complete triangles")
    if batch_triangles < 1:
        raise ValueError("batch_triangles must be positive")
    world_positions = _source_to_room(positions)
    inside = points_inside_room(world_positions)
    masked_vertices = int(np.count_nonzero(points_in_c02_mask(world_positions))) if mask_c02 else 0
    if mask_c02:
        inside &= ~points_in_c02_mask(world_positions)
    triangles = indices.reshape((-1, 3))
    retained: list[np.ndarray] = []
    for start in range(0, len(triangles), batch_triangles):
        batch = triangles[start : start + batch_triangles]
        keep = np.all(inside[batch], axis=1)
        if mask_c02:
            points = world_positions[batch][:, :, (0, 2)]
            lower = points.min(axis=1)
            upper = points.max(axis=1)
            mask_overlap = (
                (upper[:, 0] >= C02_SOURCE_MASK_XZ[0, 0])
                & (lower[:, 0] <= C02_SOURCE_MASK_XZ[1, 0])
                & (upper[:, 1] >= C02_SOURCE_MASK_XZ[0, 1])
                & (lower[:, 1] <= C02_SOURCE_MASK_XZ[1, 1])
            )
            keep &= ~mask_overlap
        retained.append(batch[keep])
    selected = np.concatenate(retained, axis=0) if retained else np.empty((0, 3), dtype=np.uint32)
    if selected.size == 0:
        raise ValueError("Room clipping removed every triangle")
    used_vertices, inverse = np.unique(selected, return_inverse=True)
    clipped_positions = world_positions[used_vertices].astype("<f4")
    clipped_colors = np.ascontiguousarray(colors[used_vertices], dtype=np.uint8)
    clipped_indices = inverse.astype("<u4", copy=False)
    return clipped_positions, clipped_colors, clipped_indices, len(triangles), masked_vertices


def points_inside_room(points: np.ndarray, tolerance: float = 1e-5) -> np.ndarray:
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Room-bound tests require three-dimensional points")
    relative = points[:, None, (0, 2)] - ROOM_POLYGON_XZ[None, :, :]
    edges = np.roll(ROOM_POLYGON_XZ, -1, axis=0) - ROOM_POLYGON_XZ
    cross = edges[None, :, 0] * relative[:, :, 1] - edges[None, :, 1] * relative[:, :, 0]
    horizontal = np.all(cross >= -tolerance, axis=1)
    vertical = (points[:, 1] >= FLOOR_Y - tolerance) & (
        points[:, 1] <= CEILING_Y + tolerance
    )
    return horizontal & vertical


def points_in_c02_mask(points: np.ndarray) -> np.ndarray:
    return (
        (points[:, 0] >= C02_SOURCE_MASK_XZ[0, 0])
        & (points[:, 0] <= C02_SOURCE_MASK_XZ[1, 0])
        & (points[:, 2] >= C02_SOURCE_MASK_XZ[0, 1])
        & (points[:, 2] <= C02_SOURCE_MASK_XZ[1, 1])
    )


def write_bounded_glb(layers: list[tuple[np.ndarray, np.ndarray, np.ndarray]], path: Path) -> None:
    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "issue160_bounded_visual"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "issue160_bounded_visual", "children": [1, 2]}],
        "meshes": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": [{"byteLength": 0}],
    }
    binary = bytearray()
    for layer_index, (positions, colors, indices) in enumerate(layers):
        _append_layer(document, binary, layer_index, positions, colors, indices)
    document["buffers"][0]["byteLength"] = len(binary)
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    binary.extend(b"\x00" * (-len(binary) % 4))
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary)
    with path.open("wb") as stream:
        stream.write(struct.pack("<4sII", b"glTF", 2, total_length))
        stream.write(struct.pack("<I4s", len(json_chunk), CHUNK_JSON))
        stream.write(json_chunk)
        stream.write(struct.pack("<I4s", len(binary), CHUNK_BIN))
        stream.write(binary)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_to_room(positions: np.ndarray) -> np.ndarray:
    rotation = _rotation_matrix(SOURCE_QUATERNION_XYZW)
    return (positions.astype(np.float64) @ rotation.T) * SOURCE_SCALE + SOURCE_TRANSLATION


def _rotation_matrix(quaternion: np.ndarray) -> np.ndarray:
    x, y, z, w = quaternion
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _accessor_layout(accessor: dict[str, Any]) -> tuple[np.dtype, int]:
    component_types = {5121: np.dtype("u1"), 5125: np.dtype("<u4"), 5126: np.dtype("<f4")}
    widths = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}
    try:
        return component_types[accessor["componentType"]], widths[accessor["type"]]
    except KeyError as error:
        raise ValueError(f"Unsupported GLB accessor layout: {accessor}") from error


def _append_layer(
    document: dict[str, Any],
    binary: bytearray,
    layer_index: int,
    positions: np.ndarray,
    colors: np.ndarray,
    indices: np.ndarray,
) -> None:
    mesh_index = len(document["meshes"])
    position_accessor = _append_accessor(document, binary, positions, 5126, "VEC3", bounds=True)
    color_accessor = _append_accessor(document, binary, colors, 5121, "VEC4", normalized=True)
    index_accessor = _append_accessor(document, binary, indices.reshape(-1), 5125, "SCALAR", bounds=True)
    document["meshes"].append(
        {"name": f"bounded_mesh_layer{layer_index}", "primitives": [{
            "attributes": {"POSITION": position_accessor, "COLOR_0": color_accessor},
            "indices": index_accessor,
            "mode": 4,
        }]}
    )
    document["nodes"].append({"name": f"bounded_mesh_layer{layer_index}", "mesh": mesh_index})


def _append_accessor(
    document: dict[str, Any],
    binary: bytearray,
    values: np.ndarray,
    component_type: int,
    accessor_type: str,
    *,
    normalized: bool = False,
    bounds: bool = False,
) -> int:
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary)
    contiguous = np.ascontiguousarray(values)
    binary.extend(contiguous.tobytes())
    view_index = len(document["bufferViews"])
    document["bufferViews"].append({"buffer": 0, "byteOffset": offset, "byteLength": contiguous.nbytes})
    accessor: dict[str, Any] = {
        "bufferView": view_index,
        "componentType": component_type,
        "count": len(contiguous),
        "type": accessor_type,
    }
    if normalized:
        accessor["normalized"] = True
    if bounds:
        accessor["min"] = np.min(contiguous, axis=0).tolist() if contiguous.ndim > 1 else [int(contiguous.min())]
        accessor["max"] = np.max(contiguous, axis=0).tolist() if contiguous.ndim > 1 else [int(contiguous.max())]
    document["accessors"].append(accessor)
    return len(document["accessors"]) - 1
