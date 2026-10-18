"""Small deterministic indexed-triangle GLB writer for the route prototype."""

from __future__ import annotations

import json
import struct

import numpy as np


def build_glb(meshes: list[dict], extras: dict) -> bytes:
    """Serialize named meshes as a compact glTF 2.0 binary scene."""
    binary = bytearray()
    views, accessors, gltf_meshes, nodes = [], [], [], []
    for mesh in meshes:
        primitive = _glb_primitive(mesh, binary, views, accessors)
        gltf_meshes.append({"name": mesh["name"], "primitives": [primitive]})
        nodes.append({"name": mesh["name"], "mesh": len(gltf_meshes) - 1})
    document = _glb_document(gltf_meshes, nodes, views, accessors, len(binary), extras)
    return _pack_glb(document, bytes(binary))


def _glb_primitive(mesh: dict, binary: bytearray, views: list, accessors: list) -> dict:
    """Append one mesh's aligned buffers and return the glTF primitive."""
    positions = np.asarray(mesh["vertices"], dtype="<f4")
    indices = np.asarray(mesh["faces"], dtype="<u4").reshape(-1)
    _, position_accessor = _append_accessor(
        binary, views, accessors, positions, 34962, 5126, "VEC3"
    )
    _, index_accessor = _append_accessor(
        binary, views, accessors, indices, 34963, 5125, "SCALAR"
    )
    accessors[position_accessor]["min"] = positions.min(axis=0).tolist()
    accessors[position_accessor]["max"] = positions.max(axis=0).tolist()
    return {
        "attributes": {"POSITION": position_accessor},
        "indices": index_accessor,
        "mode": 4,
    }


def _append_accessor(
    binary: bytearray,
    views: list,
    accessors: list,
    data: np.ndarray,
    target: int,
    component: int,
    kind: str,
) -> tuple[int, int]:
    """Append aligned data and create its buffer view/accessor pair."""
    view_index = _append_payload(binary, views, data, target)
    accessor = _accessor(view_index, component, len(data), kind)
    accessors.append(accessor)
    return view_index, len(accessors) - 1


def _append_payload(
    binary: bytearray, views: list, data: np.ndarray, target: int
) -> int:
    """Append bytes on a four-byte boundary and add a glTF buffer view."""
    binary.extend(b"\0" * ((-len(binary)) % 4))
    view_index, offset = len(views), len(binary)
    payload = data.tobytes(order="C")
    binary.extend(payload)
    views.append(
        {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(payload),
            "target": target,
        }
    )
    return view_index


def _accessor(view: int, component: int, count: int, kind: str) -> dict:
    """Create a glTF accessor descriptor for one array buffer view."""
    return {
        "bufferView": view,
        "componentType": component,
        "count": count,
        "type": kind,
    }


def _glb_document(
    meshes: list,
    nodes: list,
    views: list,
    accessors: list,
    binary_size: int,
    extras: dict,
) -> dict:
    """Return the glTF scene document with identity node transforms."""
    return {
        "asset": {
            "version": "2.0",
            "generator": "track-a-authored-route-builder",
            "extras": extras,
        },
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "buffers": [{"byteLength": binary_size}],
        "bufferViews": views,
        "accessors": accessors,
    }


def _pack_glb(document: dict, binary: bytes) -> bytes:
    """Pack glTF JSON and binary chunks using the GLB 2.0 container format."""
    json_chunk = json.dumps(document, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    binary += b"\0" * ((-len(binary)) % 4)
    total_size = 28 + len(json_chunk) + len(binary)
    header = b"glTF" + struct.pack("<II", 2, total_size)
    return (
        header
        + struct.pack("<I", len(json_chunk))
        + b"JSON"
        + json_chunk
        + struct.pack("<I", len(binary))
        + b"BIN\0"
        + binary
    )
