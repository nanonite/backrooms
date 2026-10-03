#!/usr/bin/env python3
"""Build the tiny fixtures the collision tests validate against.

Written once, here, so the tests do not need a GPU, the pinned tool, or the
45 MB corridor splat.  Everything produced here follows the published formats
exactly -- the voxel octree per
https://developer.playcanvas.com/user-manual/splat-transform/voxel-format/ and
the GLB per the glTF 2.0 container spec -- because a test double that is easier
than the real format proves nothing about the real format.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from itertools import count
from collections.abc import Callable

import numpy as np

LEAF_SIZE = 4
SOLID_LEAF_WORD = 0xFF000000

#: Unique node tags.  Python interns equal tuples, so two "solid" leaves can share
#: an id() and a dict keyed by id() then collapses them into one.
_UIDS = count()


def write_voxel_dataset(
    path: str | Path,
    solid: Callable[[np.ndarray, np.ndarray], np.ndarray],
    shape: tuple[int, int, int],
    resolution: float,
    origin: tuple[float, float, float],
) -> Path:
    """Write a ``.voxel.json`` / ``.voxel.bin`` pair describing a voxel room.

    ``solid`` is called with two ``(N, 3)`` arrays of voxel coordinates (the
    block being decided and all of its 64 local cells) and returns a boolean mask
    over the 64 local cells.  Blocks are emitted as absent, mixed or solid leaves
    according to the mask, and the tree is written breadth-first with children
    following their parent, exactly as the spec requires.
    """
    shape = tuple(int(count // LEAF_SIZE * LEAF_SIZE) for count in shape)
    blocks = tuple(count // LEAF_SIZE for count in shape)
    # unravel_index in C order is exactly the mapping a reshape(-1) applies, so
    # local[i] names the cell whose mask entry sits at i.  A meshgrid ordering
    # has to be kept in step with that by hand, and when it is not, the tree is
    # wrong in a way this repository's own reader cannot detect.
    local = np.stack(
        np.unravel_index(np.arange(LEAF_SIZE ** 3), (LEAF_SIZE,) * 3), axis=1
    ).astype(np.int64)
    grid = np.zeros(shape, dtype=bool)
    for bz in range(blocks[2]):
        for by in range(blocks[1]):
            for bx in range(blocks[0]):
                base = np.array([bx, by, bz]) * LEAF_SIZE
                mask = solid(local + base, np.array([base]))
                grid[bx * LEAF_SIZE : (bx + 1) * LEAF_SIZE,
                     by * LEAF_SIZE : (by + 1) * LEAF_SIZE,
                     bz * LEAF_SIZE : (bz + 1) * LEAF_SIZE] = mask.reshape(LEAF_SIZE, LEAF_SIZE, LEAF_SIZE)
    words, leaves, depth = _build_tree(grid)
    header = {
        "version": "1.1",
        "asset": {"generator": "test-fixture"},
        "gridBounds": {
            "min": [float(value) for value in origin],
            "max": [float(origin[axis] + shape[axis] * resolution) for axis in range(3)],
        },
        "sceneBounds": {
            "min": [float(origin[axis] - resolution) for axis in range(3)],
            "max": [float(origin[axis] + shape[axis] * resolution + resolution) for axis in range(3)],
        },
        "voxelResolution": resolution,
        "leafSize": LEAF_SIZE,
        "treeDepth": depth,
        "numInteriorNodes": sum(1 for w in words if (w >> 24) != 0 and w != SOLID_LEAF_WORD),
        "numMixedLeaves": sum(1 for w in words if (w >> 24) == 0),
        "nodeCount": len(words),
        "leafDataCount": len(leaves),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(header, handle, indent=2)
    binary = target.with_name(target.name[: -len(".voxel.json")] + ".voxel.bin")
    np.concatenate([np.asarray(words, dtype="<u4"), np.asarray(leaves, dtype="<u4")]).tofile(binary)
    return target


def _build_tree(grid: np.ndarray):
    """Return ``(node_words, leaf_words, tree_depth)`` for a dense boolean grid.

    The tree is built as nested tuples first and then flattened, so the index
    arithmetic the decoder depends on -- a parent immediately followed by its
    children, ascending by octant, with ``firstChild`` naming the first of them
    -- is produced by construction rather than by bookkeeping.
    """
    blocks_per_axis = [count // LEAF_SIZE for count in grid.shape]
    # Gathered block by block rather than by reshaping.  A reshape-and-transpose
    # of the flat array splits axes across the flattened index, which puts the
    # local coordinates in the wrong order and still round-trips through this
    # repository's own reader -- the reader and the writer would share the
    # mistake and the tests would pass on a wrong tree.
    cubes = np.stack(
        [
            grid[
                bx * LEAF_SIZE : (bx + 1) * LEAF_SIZE,
                by * LEAF_SIZE : (by + 1) * LEAF_SIZE,
                bz * LEAF_SIZE : (bz + 1) * LEAF_SIZE,
            ]
            for bx in range(blocks_per_axis[0])
            for by in range(blocks_per_axis[1])
            for bz in range(blocks_per_axis[2])
        ]
    )
    depth = int(np.ceil(np.log2(max(max(blocks_per_axis), 2))))
    words, leaves = _emit(_node_tree((0, 0, 0), 0, depth, blocks_per_axis, cubes))
    return words, leaves, depth


def _emit(root):
    """Return ``(node_words, leaf_words)`` for a nested tree.

    Indices are assigned breadth-first first and the words filled in afterwards.
    Doing both in one recursive pass puts the first child's subtree between the
    parent and its second child, so the reader -- which requires a parent's
    children to be contiguous -- descends into the wrong node and finds a leaf
    where a branch should be.
    """
    indices = {}
    order = []
    queue = [root]
    while queue:
        node = queue.pop(0)
        indices[node["uid"]] = len(order)
        order.append(node)
        if node["kind"] == "interior":
            queue.extend(node["children"][octant] for octant in sorted(node["children"]))
    words: list[int] = [0] * len(order)
    leaves: list[int] = []
    for node in order:
        index = indices[node["uid"]]
        if node["kind"] == "solid":
            words[index] = SOLID_LEAF_WORD
        elif node["kind"] == "mixed":
            leaves.extend(node["words"])
            words[index] = len(leaves) // 2 - 1
        else:
            octants = sorted(node["children"])
            mask = sum(1 << octant for octant in octants)
            words[index] = (mask << 24) | indices[node["children"][octants[0]]["uid"]]
    return words, leaves


def _node_tree(block, level, depth, blocks_per_axis, cubes, uid=None):
    """Return the nested tree for one node, or ``None`` when it is entirely empty."""
    tag = next(_UIDS) if uid is None else uid
    span = 1 << (depth - level)
    if span == 1:
        leaf = _classify_block(block, blocks_per_axis, cubes)
        return None if leaf is None else {"uid": tag, "kind": leaf[0], "words": leaf[1] or ()}
    children = {}
    for octant in range(8):
        child = tuple(block[axis] + ((octant >> axis) & 1) * (span // 2) for axis in range(3))
        if any(child[axis] >= blocks_per_axis[axis] for axis in range(3)):
            continue
        node = _node_tree(child, level + 1, depth, blocks_per_axis, cubes)
        if node is not None:
            children[octant] = node
    return {"uid": tag, "kind": "interior", "children": children} if children else None


def _classify_block(block, blocks_per_axis, cubes):
    """Return the leaf a single block encodes, or ``None`` for an absent block."""
    if any(block[axis] >= blocks_per_axis[axis] for axis in range(3)):
        return None
    offset = block[0] * blocks_per_axis[1] * blocks_per_axis[2] + block[1] * blocks_per_axis[2] + block[2]
    cells = cubes[offset]
    filled = int(cells.sum())
    if filled == 0:
        return None
    if filled == cells.size:
        return ("solid", None)
    # Entry i of cells.reshape(-1) is cell local[i], and its mask bit is
    # lx + 4*ly + 16*lz -- which is not i.  Iterating over i and writing to
    # bits[i] keeps the two apart; writing mask[bit] instead silently permutes
    # the block, and this repository's own reader cannot tell, because it reads
    # back the same permutation.
    local = np.stack(
        np.unravel_index(np.arange(LEAF_SIZE ** 3), (LEAF_SIZE,) * 3), axis=1
    ).astype(np.int64)
    bits = local[:, 0] + (local[:, 1] << 2) + (local[:, 2] << 4)
    mask = cells.reshape(-1)
    low = sum(int(mask[i]) << bits[i] for i in range(len(bits)) if bits[i] < 32)
    high = sum(int(mask[i]) << (bits[i] - 32) for i in range(len(bits)) if bits[i] >= 32)
    return ("mixed", (low, high))


def write_glb(path: str | Path, positions: np.ndarray, indices: np.ndarray, normals=None) -> Path:
    """Write a single-primitive GLB with float32 positions and uint32 indices."""
    buffer = bytearray()
    views = []
    accessors = [
        {
            "bufferView": 0,
            "componentType": 5126,
            "count": int(len(positions)),
            "type": "VEC3",
            "min": [float(value) for value in positions.min(axis=0)],
            "max": [float(value) for value in positions.max(axis=0)],
        },
        {"bufferView": 1, "componentType": 5125, "count": int(len(indices)), "type": "SCALAR"},
    ]
    buffer.extend(np.asarray(positions, dtype="<f4").tobytes())
    buffer.extend(b"\x00" * ((4 - len(buffer) % 4) % 4))
    views.append({"buffer": 0, "byteOffset": 0, "byteLength": int(len(positions)) * 12, "target": 34962})
    buffer.extend(np.asarray(indices, dtype="<u4").tobytes())
    buffer.extend(b"\x00" * ((4 - len(buffer) % 4) % 4))
    views.append({"buffer": 0, "byteOffset": len(buffer) - int(len(indices)) * 4,
                  "byteLength": int(len(indices)) * 4, "target": 34963})
    attributes = {"POSITION": 0}
    if normals is not None:
        buffer.extend(np.asarray(normals, dtype="<f4").tobytes())
        buffer.extend(b"\x00" * ((4 - len(buffer) % 4) % 4))
        views.append({"buffer": 0, "byteOffset": len(buffer) - int(len(normals)) * 12,
                      "byteLength": int(len(normals)) * 12, "target": 34962})
        accessors.append({"bufferView": 2, "componentType": 5126, "count": int(len(normals)), "type": "VEC3"})
        attributes["NORMAL"] = 2
    document = {
        "asset": {"version": "2.0", "generator": "test-fixture"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": attributes, "indices": 1}]}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(buffer)}],
    }
    payload = json.dumps(document).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    total = 12 + 8 + len(payload) + 8 + len(buffer)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.write(struct.pack("<III", 0x46546C67, 2, total))
        handle.write(struct.pack("<II", len(payload), 0x4E4F534A))
        handle.write(payload)
        handle.write(struct.pack("<II", len(buffer), 0x004E4942))
        handle.write(bytes(buffer))
    return target


def tetrahedron() -> tuple[np.ndarray, np.ndarray]:
    """Return an outward-wound tetrahedron's vertices and triangle indices."""
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    )
    indices = np.array([0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3], dtype=np.int64)
    return vertices, indices