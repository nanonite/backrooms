#!/usr/bin/env python3
"""Reader for the PlayCanvas sparse voxel octree (``.voxel.json`` + ``.voxel.bin``).

Only format 1.1 is accepted, because 1.1 is where the meaning of the stored
coordinates changed: version 1.0 stored them in the source PLY frame and 1.1
stores them in the PlayCanvas engine frame, which is the PLY frame rotated 180
degrees about z.  Reading a 1.0 file with this module would therefore place
every voxel mirrored, so the version is checked rather than assumed.

Why a reader is needed at all: the collision output is only trustworthy if the
solid/navigable split it claims is checked against something.  Every acceptance
question in this task -- is the floor continuous, are the walls solid, did a
doorway survive, did the room fill in -- is a question about *occupancy*, and
occupancy is exactly what this file records.  A collision mesh cannot answer
them, because a mesh does not say which side of a triangle is solid.

See the published format spec at
https://developer.playcanvas.com/user-manual/splat-transform/voxel-format/ .
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: Voxels per leaf-block edge, fixed by the format.
LEAF_SIZE = 4

#: Node word marking a fully solid subtree of any depth.
SOLID_LEAF_WORD = 0xFF000000

#: Mask for the 24-bit child or leafData index in a node word.
INDEX_MASK = 0xFFFFFF


class VoxelFormatError(ValueError):
    """Raised when a voxel dataset does not match the 1.1 specification."""


@dataclass(frozen=True)
class VoxelHeader:
    """The parsed ``.voxel.json`` side of a dataset."""

    version: str
    generator: str
    grid_min: tuple[float, float, float]
    grid_max: tuple[float, float, float]
    scene_min: tuple[float, float, float]
    scene_max: tuple[float, float, float]
    resolution: float
    tree_depth: int
    num_interior_nodes: int
    num_mixed_leaves: int
    node_count: int
    leaf_data_count: int

    @property
    def grid_shape(self) -> tuple[int, int, int]:
        """Voxel counts along each axis of ``gridBounds``."""
        return tuple(  # type: ignore[return-value]
            int(round((high - low) / self.resolution))
            for low, high in zip(self.grid_min, self.grid_max)
        )

    @property
    def block_shape(self) -> tuple[int, int, int]:
        """Leaf-block counts along each axis, derived from ``gridBounds``."""
        return tuple(count // LEAF_SIZE for count in self.grid_shape)  # type: ignore[return-value]


class VoxelOctree:
    """A loaded voxel dataset, queried in the frame the file stores.

    ``is_solid`` is the only occupancy predicate.  Everything the acceptance
    checks need -- floor support, wall solidity, doorway openness -- is a
    question about that one bit, and exposing the tree's internals would let a
    caller depend on the traversal instead of on the occupancy.
    """

    def __init__(self, header: VoxelHeader, nodes: np.ndarray, leaf_data: np.ndarray) -> None:
        self.header = header
        self._nodes = nodes
        self._leaf_data = leaf_data
        self._cache: dict[tuple[int, int, int], bool] = {}

    @classmethod
    def load(cls, path: str | Path) -> VoxelOctree:
        """Load a dataset from its ``.voxel.json`` path, reading the ``.bin`` beside it."""
        header_path = Path(path)
        if not header_path.name.endswith(".voxel.json"):
            raise VoxelFormatError(
                "%s: expected a *.voxel.json header path" % header_path
            )
        with header_path.open(encoding="utf-8") as handle:
            header = parse_header(json.load(handle), header_path)
        binary_path = header_path.with_name(
            header_path.name[: -len(".voxel.json")] + ".voxel.bin"
        )
        return cls(header, *_read_binary(binary_path, header))

    @property
    def resolution(self) -> float:
        """Voxel edge length in the stored frame's units."""
        return self.header.resolution

    def contains(self, point) -> bool:
        """Whether the world-space ``point`` lies inside ``gridBounds``."""
        offset = np.asarray(point, dtype=np.float64) - np.asarray(self.header.grid_min)
        index = np.floor(offset / self.header.resolution).astype(int)
        return bool(np.all(index >= 0) and np.all(index < np.asarray(self.header.grid_shape)))

    def is_solid(self, point) -> bool:
        """Whether the voxel containing ``point`` is solid.

        Outside ``gridBounds`` reads as solid, which is the convention the format
        documents for navigation consumers and the one the writer depends on:
        fully-solid blocks beyond the navigable region are cropped precisely
        because anything outside the grid already blocks.
        """
        index = self._voxel_index(point)
        if index is None:
            return True
        return self.is_solid_index(index)

    def is_navigable(self, point) -> bool:
        """Whether ``point`` is inside the grid and its voxel is empty."""
        return not self.is_solid(point)

    def is_solid_index(self, index: tuple[int, int, int]) -> bool:
        """Whether voxel ``(vx, vy, vz)`` is solid, memoised per voxel."""
        cached = self._cache.get(index)
        if cached is None:
            cached = self._read_solid(index)
            self._cache[index] = cached
        return cached

    def voxel_centre(self, index) -> np.ndarray:
        """World-space centre of voxel ``index``."""
        offset = (np.asarray(index, dtype=np.float64) + 0.5) * self.header.resolution
        return np.asarray(self.header.grid_min, dtype=np.float64) + offset

    def _voxel_index(self, point) -> tuple[int, int, int] | None:
        """Return the voxel containing ``point``, or ``None`` when outside the grid."""
        offset = np.asarray(point, dtype=np.float64) - np.asarray(self.header.grid_min)
        index = np.floor(offset / self.header.resolution).astype(int)
        if np.any(index < 0) or np.any(index >= np.asarray(self.header.grid_shape)):
            return None
        return int(index[0]), int(index[1]), int(index[2])

    def occupancy(self, low, high) -> np.ndarray:
        """Return a dense solid/empty array over the inclusive voxel box.

        ``low`` and ``high`` are world-space coordinates; the array is indexed
        ``[vx, vy, vz]`` from the voxel containing ``low`` up to and including
        the voxel containing ``high``.  Space outside ``gridBounds`` counts as
        solid, so the returned array is safe to reason about without separately
        handling the domain edge.

        Memory is proportional to the requested box, so callers should ask for
        the region they are measuring rather than the whole grid.
        """
        first, last = self._inclusive_box(low, high)
        if first is None:
            return np.zeros((0, 0, 0), dtype=bool)
        shape = tuple(int(last[axis] - first[axis]) + 1 for axis in range(3))
        result = np.zeros(shape, dtype=bool)

        # unravel_index in C order matches the flattening the mask bits are stored
        # in, so entry i of the result is cell i of the block.
        local = np.stack(
            np.unravel_index(np.arange(LEAF_SIZE ** 3), (LEAF_SIZE,) * 3), axis=1
        ).astype(np.int64)
        for bz in range(int(first[2]) // LEAF_SIZE, int(last[2]) // LEAF_SIZE + 1):
            for by in range(int(first[1]) // LEAF_SIZE, int(last[1]) // LEAF_SIZE + 1):
                for bx in range(int(first[0]) // LEAF_SIZE, int(last[0]) // LEAF_SIZE + 1):
                    block = self._leaf_node(bx, by, bz)
                    self._paint_block(result, first, last, (bx, by, bz), block, local)
        return result

    def is_solid_box(self, low, high) -> bool:
        """Whether any voxel overlapping the axis-aligned box is solid.

        A box that reaches outside ``gridBounds`` is solid by the format's
        domain convention, so this is answered without touching the tree.
        """
        lo = np.asarray(low, dtype=np.float64)
        hi = np.asarray(high, dtype=np.float64)
        grid_lo = np.asarray(self.header.grid_min, dtype=np.float64)
        grid_hi = np.asarray(self.header.grid_max, dtype=np.float64)
        if np.any(lo < grid_lo) or np.any(hi >= grid_hi):
            return True
        first, last = self._inclusive_box(lo, hi)
        if first is None:
            return False
        for vz in range(int(first[2]), int(last[2]) + 1):
            for vy in range(int(first[1]), int(last[1]) + 1):
                for vx in range(int(first[0]), int(last[0]) + 1):
                    if self.is_solid_index((vx, vy, vz)):
                        return True
        return False

    def _inclusive_box(self, low, high) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Convert a world-space box into an inclusive voxel-index box, or empty."""
        origin = np.asarray(self.header.grid_min, dtype=np.float64)
        resolution = self.header.resolution
        shape = np.asarray(self.header.grid_shape)
        first = np.floor((np.asarray(low, dtype=np.float64) - origin) / resolution).astype(int)
        last = np.floor((np.asarray(high, dtype=np.float64) - origin) / resolution).astype(int)
        clipped_first = np.clip(first, 0, shape - 1)
        clipped_last = np.clip(last, 0, shape - 1)
        if np.any(first > last) or np.any(clipped_first > clipped_last):
            return None, None
        if np.any(first < 0) or np.any(last >= shape):
            # The box reaches outside the grid, where the format defines solid.
            return clipped_first, clipped_last
        return clipped_first, clipped_last

    def _paint_block(
        self,
        result: np.ndarray,
        first: np.ndarray,
        last: np.ndarray,
        block: tuple[int, int, int],
        leaf,
        local: np.ndarray,
    ) -> None:
        """Write one leaf block's solid voxels into a dense box result.

        An absent block is written as empty rather than skipped, so the result
        is a complete answer for the requested box; both cases go through the
        same cell-wise path because painting a whole block's worth of slices
        would reach past the block into its neighbours.
        """
        if leaf is None:
            mask = np.zeros(LEAF_SIZE ** 3, dtype=bool)
        elif leaf[0] == "solid":
            mask = np.ones(LEAF_SIZE ** 3, dtype=bool)
        else:
            mask = _mask_bits(leaf[1], local)
        base = np.asarray(block, dtype=np.int64) * LEAF_SIZE
        indices = local[mask] + base
        keep = np.all((indices >= first) & (indices <= last), axis=1)
        indices = indices[keep] - first
        if indices.size == 0:
            return
        result[indices[:, 0], indices[:, 1], indices[:, 2]] = True

    def _read_solid(self, index: tuple[int, int, int]) -> bool:
        """Whether one voxel is solid, straight from the tree."""
        block = tuple(value // LEAF_SIZE for value in index)
        local = tuple(value % LEAF_SIZE for value in index)
        leaf = self._leaf_node(*block)
        if leaf is None:
            return False
        kind, payload = leaf
        if kind == "solid":
            return True
        bit = local[0] + (local[1] << 2) + (local[2] << 4)
        word = payload[0] if bit < 32 else payload[1]
        return bool((word >> (bit & 31)) & 1)

    def _leaf_node(self, bx: int, by: int, bz: int):
        """Return the leaf covering block ``(bx, by, bz)`` as ``(kind, payload)``."""
        shape = self.header.block_shape
        if not (0 <= bx < shape[0] and 0 <= by < shape[1] and 0 <= bz < shape[2]):
            return None
        depth = self.header.tree_depth
        index = 0
        for step in range(depth - 1, -1, -1):
            leaf = self._classify(index)
            if leaf is not None:
                return leaf
            word = int(self._nodes[index])
            mask = word >> 24
            octant = ((bx >> step) & 1) | (((by >> step) & 1) << 1) | (((bz >> step) & 1) << 2)
            if not (mask >> octant) & 1:
                return None
            index = (word & INDEX_MASK) + _popcount(mask & ((1 << octant) - 1))
        return self._classify(index)

    def _classify(self, index: int):
        """Return the leaf a node word encodes, or ``None`` if it has children."""
        word = int(self._nodes[index])
        if word == SOLID_LEAF_WORD:
            return ("solid", None)
        if (word >> 24) == 0:
            return ("mixed", self._mixed_payload(word))
        return None

    def _mixed_payload(self, word: int) -> tuple[int, int]:
        """Read a mixed leaf's two 32-bit occupancy words."""
        base = 2 * (word & INDEX_MASK)
        if base + 1 >= len(self._leaf_data):
            raise VoxelFormatError("mixed leaf points past the leafData array")
        return int(self._leaf_data[base]), int(self._leaf_data[base + 1])


def parse_header(data: dict, source: Path | str = "<dict>") -> VoxelHeader:
    """Validate and convert a ``.voxel.json`` document into a :class:`VoxelHeader`.

    Version 1.0 is rejected explicitly, not because it is a different layout --
    the binary layout is identical -- but because its ``gridBounds`` are in the
    source PLY frame while 1.1's are in the PlayCanvas engine frame.  Parsing a
    1.0 file with this reader would place every voxel rotated 180 degrees about z,
    which is the exact class of silent misplacement this module exists to
    prevent.
    """
    version = str(data.get("version", ""))
    if version.split(".", 1)[0] != "1" or version == "1.0":
        raise VoxelFormatError(
            "%s: voxel format version %r is not supported; this reader implements 1.1, "
            "whose coordinates are the PlayCanvas engine frame" % (source, version or "<missing>")
        )
    resolution = float(data["voxelResolution"])
    if resolution <= 0.0:
        raise VoxelFormatError("%s: voxelResolution must be positive" % source)
    leaf_size = int(data.get("leafSize", LEAF_SIZE))
    if leaf_size != LEAF_SIZE:
        raise VoxelFormatError(
            "%s: leafSize %d is not the fixed %d this reader assumes" % (source, leaf_size, LEAF_SIZE)
        )
    return VoxelHeader(
        version=version,
        generator=str(data.get("asset", {}).get("generator", "")),
        grid_min=_bounds(data["gridBounds"], source, "gridBounds")[0],
        grid_max=_bounds(data["gridBounds"], source, "gridBounds")[1],
        scene_min=_bounds(data["sceneBounds"], source, "sceneBounds")[0],
        scene_max=_bounds(data["sceneBounds"], source, "sceneBounds")[1],
        resolution=resolution,
        tree_depth=int(data["treeDepth"]),
        num_interior_nodes=int(data["numInteriorNodes"]),
        num_mixed_leaves=int(data["numMixedLeaves"]),
        node_count=int(data["nodeCount"]),
        leaf_data_count=int(data["leafDataCount"]),
    )


def _bounds(node: dict, source: Path | str, label: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Read a ``{min, max}`` pair as two float triples, rejecting inverted bounds."""
    try:
        low = tuple(float(v) for v in node["min"])
        high = tuple(float(v) for v in node["max"])
    except (KeyError, TypeError, ValueError) as error:
        raise VoxelFormatError("%s: malformed %s" % (source, label)) from error
    if len(low) != 3 or len(high) != 3 or any(a > b for a, b in zip(low, high)):
        raise VoxelFormatError("%s: %s min %s is not below max %s" % (source, label, low, high))
    return low, high  # type: ignore[return-value]


def _read_binary(path: Path, header: VoxelHeader) -> tuple[np.ndarray, np.ndarray]:
    """Read the two ``uint32`` arrays the header's counts promise."""
    if not path.exists():
        raise VoxelFormatError("%s: no binary payload beside the header" % path)
    expected = (header.node_count + header.leaf_data_count) * 4
    actual = path.stat().st_size
    if actual != expected:
        raise VoxelFormatError(
            "%s: is %d bytes but the header declares %d uint32 entries (%d bytes)"
            % (path, actual, header.node_count + header.leaf_data_count, expected)
        )
    words = np.fromfile(path, dtype="<u4")
    return words[: header.node_count], words[header.node_count :]


def _mask_bits(payload: tuple[int, int], local: np.ndarray) -> np.ndarray:
    """Expand a mixed leaf's two 32-bit words over ``local`` voxel coordinates."""
    bits = local[:, 0] + (local[:, 1] << 2) + (local[:, 2] << 4)
    low = bits < 32
    shifted = np.where(low, bits, bits - 32)
    words = np.where(low, np.uint32(payload[0]), np.uint32(payload[1]))
    return ((words >> shifted.astype(np.uint32)) & np.uint32(1)).astype(bool)


def _popcount(value: int) -> int:
    """Return the number of set bits in ``value``."""
    return bin(value).count("1")