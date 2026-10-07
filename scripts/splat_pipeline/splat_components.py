#!/usr/bin/env python3
"""Voxel connected-component labelling for spatial outlier filtering (#103).

Two splats belong to the same structure when their centres land in touching
voxels of one uniform grid (6-neighbourhood). A component that is separate
from the room shell is a spatial outlier *regardless of its opacity or scale*,
which is what the #100 report needed: that asset's floaters sit at median
opacity 0.995, so no alpha threshold removes them (see
``godot_walk/assets/corridor_splat/CLEANUP.md``).

Why a voxel grid rather than a k-nearest-neighbour graph: the pitch is one
explicit metre parameter recorded in the report, so the same command on a new
asset means the same thing. A kNN graph's reach depends on local density, i.e.
on the very cloud being filtered.

Determinism: no sampling and no RNG anywhere. Iteration order, union order and
therefore label values are fixed by the input order, so the same points always
produce the same membership. Label *values* are internal ids; only which points
share an id (and the resulting sizes) is meaningful.
"""

from __future__ import annotations

import numpy as np

#: Positive axis shifts used to find each voxel's neighbours exactly once.
NEIGHBOUR_SHIFTS: tuple[tuple[int, int, int], ...] = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def _voxel_coordinates(points: np.ndarray, voxel_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(coords, dims)``: each point's integer voxel and the grid size."""
    if voxel_m <= 0.0:
        raise ValueError("voxel_m must be positive")
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points must have shape (N, 3)")
    if points.shape[0] == 0:
        raise ValueError("points must not be empty")
    shifted = (points - points.min(axis=0)) / voxel_m
    coords = np.floor(shifted).astype(np.int64)
    return coords, coords.max(axis=0) + 1


def _find(parent: np.ndarray, node: int) -> int:
    """Return the root of ``node`` with path compression."""
    root = node
    while parent[root] != root:
        root = parent[root]
    while parent[node] != root:
        parent[node], node = root, parent[node]
    return root


def _union(parent: np.ndarray, first: int, second: int) -> None:
    """Merge the sets holding ``first`` and ``second``."""
    root_a = _find(parent, first)
    root_b = _find(parent, second)
    if root_a != root_b:
        parent[root_b] = root_a


def _link_touching_voxels(coords: np.ndarray, dims: np.ndarray, keys: np.ndarray) -> np.ndarray:
    """Union every voxel with its positive-axis neighbours and return the parent array."""
    parent = np.arange(len(keys))
    for shift in NEIGHBOUR_SHIFTS:
        target = coords + np.asarray(shift)
        inside = np.all(target < dims, axis=1)
        source_rows = np.nonzero(inside)[0]
        if source_rows.size == 0:
            continue
        wanted = np.ravel_multi_index(target[inside].T, dims)
        found = np.searchsorted(keys, wanted)
        hit = found < len(keys)
        hit[hit] = keys[found[hit]] == wanted[hit]
        for source, match in zip(source_rows[hit], found[hit]):
            _union(parent, int(source), int(match))
    return parent


def label_components(points: np.ndarray, voxel_m: float) -> np.ndarray:
    """Return an ``(N,)`` integer label per point; equal labels = one structure.

    ``voxel_m`` is the grid pitch in the same units as ``points`` (Godot world
    metres when called from the cleanup CLI). Points closer together than one
    pitch are always connected, so lowering the pitch can only *split*
    components, never merge them -- the parameter's effect is monotone and can
    be reasoned about without re-running anything.
    """
    coords, dims = _voxel_coordinates(points, voxel_m)
    flat = np.ravel_multi_index(coords.T, dims)
    unique_keys, inverse = np.unique(flat, return_inverse=True)
    voxel_coords = np.stack(np.unravel_index(unique_keys, dims), axis=1)

    parent = _link_touching_voxels(voxel_coords, dims, unique_keys)
    root_per_unique = np.array([_find(parent, i) for i in range(len(unique_keys))])
    return root_per_unique[inverse]


def component_sizes(labels: np.ndarray) -> np.ndarray:
    """Return the splat count of every label, indexed by label value."""
    labels = np.asarray(labels)
    if labels.size == 0:
        raise ValueError("labels must not be empty")
    if labels.min() < 0:
        raise ValueError("labels must be non-negative")
    return np.bincount(labels)
