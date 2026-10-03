#!/usr/bin/env python3
"""Minimal glTF-binary reader for the collision mesh ``splat-transform`` writes.

Only what a physics suitability check needs is decoded: positions, indices, and
the derived geometry (bounds, triangle quality, edge manifoldness, outward
winding).  Node hierarchies and materials are not resolved because the collision
mesh carries exactly one untransformed primitive -- see
https://developer.playcanvas.com/user-manual/splat-transform/voxel-format/ --
and a reader that silently ignored a transform would report the wrong frame.

The mesh ships **without** vertex normals (measured: the collision GLB's single
primitive declares only ``POSITION`` and ``indices``).  That is not a defect for
physics -- a concave trimesh collider is built from the triangles themselves --
but it means "do the normals point the right way" has to be answered from the
winding, so :func:`face_normals` is part of this module rather than a
convenience nobody calls.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

COMPONENT_DTYPES = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}

TYPE_COMPONENT_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class GlbFormatError(ValueError):
    """Raised when a GLB does not carry the single triangle mesh expected here."""


@dataclass(frozen=True)
class TriangleMesh:
    """A triangle mesh in the file's own frame, with no transforms applied."""

    positions: np.ndarray
    indices: np.ndarray
    generator: str

    @property
    def triangle_count(self) -> int:
        return int(len(self.indices) // 3)

    @property
    def vertex_count(self) -> int:
        return int(len(self.positions))

    @property
    def bounds_min(self) -> np.ndarray:
        return self.positions.min(axis=0)

    @property
    def bounds_max(self) -> np.ndarray:
        return self.positions.max(axis=0)

    def triangles(self) -> np.ndarray:
        """Return the ``(T, 3, 3)`` array of triangle corner positions."""
        return self.positions[self.indices.reshape(-1, 3)]

    def face_normals(self) -> np.ndarray:
        """Return the ``(T, 3)`` unit normal of every triangle, from its winding."""
        corners = self.triangles()
        cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        lengths = np.linalg.norm(cross, axis=1)
        safe = np.where(lengths > 0.0, lengths, 1.0)
        return cross / safe[:, None]

    def centroid(self) -> np.ndarray:
        """Return the mean of the vertex positions."""
        return self.positions.mean(axis=0)

    def signed_volume(self) -> float:
        """Return the volume enclosed by the triangles under the divergence theorem.

        A closed mesh with consistent outward winding has a positive value.  The
        sign is what makes it useful here: it answers "do these triangles face
        outwards, or inwards?" for the whole mesh at once, which per-triangle
        dot products against the voxel field answer only locally.
        """
        corners = self.triangles()
        return float(
            np.einsum("ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])).sum() / 6.0
        )

    def edge_manifoldness(self) -> dict[str, int]:
        """Return how many edges each triangle edge is shared by.

        Counts edges used by exactly one triangle (``boundary``) and by three or
        more (``non_manifold``); the remainder are shared by exactly two, which is
        what a closed surface needs.  Vertices are welded within a 1e-6 tolerance
        because marching-cubes output splits vertices along every edge.
        """
        corners = self.positions[self.indices]
        keys = np.round(corners.reshape(-1, 3) / WELD_TOLERANCE).astype(np.int64)
        unique, inverse = np.unique(keys, axis=0, return_inverse=True)
        del unique
        welded = inverse.reshape(-1, 3)
        edges = np.concatenate([welded[:, [0, 1]], welded[:, [1, 2]], welded[:, [2, 0]]], axis=0)
        edges = np.sort(edges, axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        return {
            "boundary": int((counts == 1).sum()),
            "manifold": int((counts == 2).sum()),
            "non_manifold": int((counts >= 3).sum()),
        }


#: Positions are welded at this multiple of the voxel edge when counting edges.
#: Marching-cubes output splits vertices along every edge, so the exact values are
#: identical but a small tolerance avoids failing on float32 round-trip noise.
WELD_TOLERANCE = 1e-5


def read_glb(path: str | Path) -> TriangleMesh:
    """Read the collision mesh from a ``.collision.glb`` file."""
    document, binary = _read_container(Path(path))
    primitive = _single_primitive(document, Path(path))
    positions = _read_attribute(document, binary, primitive["attributes"]["POSITION"], np.float32)
    indices = _read_attribute(document, binary, primitive.get("indices", primitive["attributes"]["POSITION"]), np.uint32)
    if indices.size % 3:
        raise GlbFormatError("%s: index count %d is not a multiple of 3" % (path, indices.size))
    return TriangleMesh(
        positions=positions.astype(np.float64),
        indices=indices.astype(np.int64).reshape(-1),
        generator=str(document.get("asset", {}).get("generator", "")),
    )


def _read_container(path: Path) -> tuple[dict, bytes]:
    """Split a GLB into its JSON document and binary chunk."""
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<III", raw, 0)
    if magic != GLB_MAGIC:
        raise GlbFormatError("%s: not a GLB (magic 0x%08x)" % (path, magic))
    if version != 2:
        raise GlbFormatError("%s: GLB container version %d, expected 2" % (path, version))
    if total != len(raw):
        raise GlbFormatError("%s: header declares %d bytes but the file holds %d" % (path, total, len(raw)))
    document, binary = None, b""
    offset = GLB_HEADER_BYTES
    while offset + CHUNK_HEADER_BYTES <= len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        body = raw[offset + CHUNK_HEADER_BYTES : offset + CHUNK_HEADER_BYTES + length]
        if kind == JSON_CHUNK:
            document = json.loads(body.decode("utf-8"))
        elif kind == BIN_CHUNK:
            binary = body
        offset += CHUNK_HEADER_BYTES + length
    if document is None:
        raise GlbFormatError("%s: no JSON chunk" % path)
    return document, binary


GLB_HEADER_BYTES = 12
CHUNK_HEADER_BYTES = 8


def _single_primitive(document: dict, path: Path) -> dict:
    """Return the only primitive in the document, refusing anything else."""
    meshes = document.get("meshes", [])
    if len(meshes) != 1 or len(meshes[0].get("primitives", [])) != 1:
        raise GlbFormatError(
            "%s: expected exactly one mesh with one primitive, found %d mesh(es)"
            % (path, len(meshes))
        )
    return meshes[0]["primitives"][0]


def _read_attribute(document: dict, binary: bytes, index: int, dtype) -> np.ndarray:
    """Decode one accessor out of the binary chunk."""
    accessor = document["accessors"][index]
    component = TYPE_COMPONENT_COUNTS.get(accessor["type"])
    if component is None:
        raise GlbFormatError("unsupported accessor type %r" % accessor["type"])
    element = COMPONENT_DTYPES.get(accessor["componentType"])
    if element is None:
        raise GlbFormatError("unsupported componentType %r" % accessor["componentType"])
    view = document["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    item = np.dtype(element).itemsize * component
    if accessor.get("byteStride"):
        raise GlbFormatError("interleaved buffer views are not supported")
    count = accessor["count"]
    if start + item * count > len(binary):
        raise GlbFormatError(
            "accessor %d reads %d bytes from offset %d but the binary chunk holds %d"
            % (index, item * count, start, len(binary))
        )
    flat = np.frombuffer(binary, dtype=element, count=count * component, offset=start)
    return flat.reshape(count, component) if component > 1 else flat