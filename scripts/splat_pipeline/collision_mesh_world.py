#!/usr/bin/env python3
"""The generated collision mesh, in Godot world metres, with vertical queries.

The collision GLB that #84's ``splat-transform`` run writes is in the PlayCanvas
**engine** frame -- the reconstruction frame rotated 180 degrees about z -- and
already in metres, because the tool is handed a splat that the contract has
scaled in place.  :func:`load_world_mesh` applies the contract's mapping so the
triangles can be compared against the contract's floor, ceiling and landmarks.

Two query kinds are provided, and the difference between them is the whole
point of the module:

``surfaces_under``
    every triangle surface a vertical line at ``(x, z)`` passes through, sorted.
    A *count* of hits proves nothing on its own -- the tool emits a closed shell
    around a hollowed-out room, so a wall and a room both produce two hits.

``open_at``
    whether a height is inside one of the gaps *between* consecutive surfaces.
    This is the test that tells a walkable column from a solid one, and it is
    the only form of the question that a shell can answer honestly.

Both are pure functions of the mesh, so a test can build a fixture mesh and
assert the answers without a GPU, the tool, or Godot.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collision_params import (
    collision_node_transform,
    contract_from_path,
    engine_frame_to_world,
)
from glb_mesh import read_glb
from splat_frame import FrameContract

#: Godot's horizontal plane for a node with gravity along -y is x/z, so a
#: vertical line is a ray along y and the surface test is a 2D point-in-triangle
#: test in that plane.  Reading ``[:, :2]`` here would silently test x/y -- the
#: plane the frame is up along, where almost every triangle is edge-on and
#: nearly nothing is ever hit.
VERTICAL_AXIS = 1
PLAN_AXES = (0, 2)


class CollisionMeshError(ValueError):
    """Raised when the mesh or a query against it is unusable."""


@dataclass(frozen=True)
class WorldCollisionMesh:
    """Triangles of the generated collision mesh, in Godot world metres."""

    triangles: np.ndarray
    plan: np.ndarray
    bounds_xy: np.ndarray
    md5: str = ""
    path: str = ""

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the mesh's world-space minimum and maximum corners."""
        flat = self.triangles.reshape(-1, 3)
        return flat.min(axis=0), flat.max(axis=0)

    def surfaces_under(self, x: float, z: float) -> np.ndarray:
        """Return the sorted heights every triangle crosses above ``(x, z)``.

        Triangles whose projection onto the x/z plane degenerates to a segment
        contribute a height only when ``(x, z)`` lies on that segment, which the
        shared edge-function test handles because all three signs are then zero.

        Culled by bounding box first.  Without it every query evaluates the edge
        functions against all ten thousand triangles, and the plan needs one query
        per sample per floor-plan cell; the cull is what makes a capsule-volume
        test over the whole grid a few seconds rather than half an hour.

        A ray that runs exactly along a shared triangle edge matches both faces,
        so a coincident pair of heights is reported where one was crossed.  That
        is a property of the point-in-triangle test rather than of the mesh, and
        the callers here query cell centres and grid-aligned samples, none of
        which lands on a voxel seam.
        """
        point = np.array([float(x), float(z)], dtype=np.float64)
        near = self.bounds_xy
        candidate = (
            (near[:, 0] <= point[0])
            & (near[:, 1] >= point[0])
            & (near[:, 2] <= point[1])
            & (near[:, 3] >= point[1])
        )
        if not candidate.any():
            return np.zeros(0, dtype=np.float64)
        plan = self.plan[candidate]
        first, second, third = plan[:, 0], plan[:, 1], plan[:, 2]
        first_edge = _edge(first, second, point)
        second_edge = _edge(second, third, point)
        third_edge = _edge(third, first, point)
        inside = ((first_edge >= 0.0) & (second_edge >= 0.0) & (third_edge >= 0.0)) | (
            (first_edge <= 0.0) & (second_edge <= 0.0) & (third_edge <= 0.0)
        )
        return np.sort(self.triangles[candidate][inside, 0, VERTICAL_AXIS])

    def open_at(self, x: float, z: float, y: float) -> bool:
        """Whether ``y`` is navigable space at ``(x, z)``.

        The even-odd rule, not "is ``y`` inside some gap".  The tool's output is
        the boundary of the **solid** material, so a navigable column crosses four
        surfaces -- the outer shell's floor, the cavity's floor, the cavity's
        ceiling, the outer shell's ceiling -- and a solid column crosses two.
        Asking whether ``y`` falls in *any* gap therefore calls the solid column
        navigable and reports the whole 3 m shell interior as floor-to-ceiling
        headroom.  Counting the surfaces below ``y`` and taking the parity gets
        both right: below the outer floor is 0 surfaces (air), between outer floor
        and cavity floor is 1 (solid), between cavity floor and ceiling is 2 (air),
        and above the outer ceiling is 4 (air).

        A column with no surfaces at all counts as open, because the mesh simply
        does not reach there; callers distinguish that from real navigable space
        by testing the mesh's bounds, not by trusting this.
        """
        surfaces = self.surfaces_under(x, z)
        return bool(np.count_nonzero(surfaces < y) % 2 == 0)

    def first_blocked_ahead(self, x: float, z: float, direction: tuple[float, float],
                            heights: list[float], limit_m: float,
                            step_m: float = 0.01) -> tuple[float, float] | None:
        """Where a capsule of the given cross-sections first meets solid.

        Marches a horizontal ray and asks, at every step, whether **any** of
        ``heights`` is inside solid.  A single height is not enough: an obstacle
        can be open at the capsule's waist and closed at its shoulder -- the
        interior column in this capture is exactly that -- and a probe that only
        looked at the equator would march straight past the thing it is meant to
        be stopped by.

        Returns ``(distance, height)`` for the first blocking cross-section, or
        ``None``.  The step is a fifth of the voxel size, so the answer is good to
        about a centimetre, which is the resolution at which a capsule's resting
        position against a face means anything.
        """
        travelled = step_m
        while travelled <= limit_m:
            px = x + direction[0] * travelled
            pz = z + direction[1] * travelled
            for height in heights:
                if not self.open_at(px, pz, height):
                    return travelled, height
            travelled += step_m
        return None

    def band(self, x: float, z: float, y: float) -> tuple[float, float] | None:
        """Return the surfaces bracketing ``y``: ``(below, above)``.

        The navigable height at a column is the distance between them, which is
        what decides whether the production capsule fits under a ceiling.
        ``None`` when the column is solid through ``y``, which the even-odd rule
        establishes first: without that test a solid column reports the full
        depth of the shell as headroom.
        """
        if not self.open_at(x, z, y):
            return None
        surfaces = self.surfaces_under(x, z)
        below = surfaces[surfaces < y]
        above = surfaces[surfaces > y]
        if below.size == 0 or above.size == 0:
            return None
        return float(below.max()), float(above.min())


def _edge(a: np.ndarray, b: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Return the 2D cross product of ``b - a`` with ``point - a``."""
    return (b[:, 0] - a[:, 0]) * (point[1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (point[0] - a[:, 0])


def load_world_mesh(glb_path: str | Path, contract: FrameContract) -> WorldCollisionMesh:
    """Read a collision GLB and map it into Godot world metres."""
    path = Path(glb_path)
    if not path.exists():
        raise CollisionMeshError("no collision mesh at %s" % path)
    mesh = read_glb(path)
    triangles = engine_frame_to_world(mesh.positions, contract)[
        np.asarray(mesh.indices).reshape(-1, 3)
    ]
    plan = triangles[:, :, list(PLAN_AXES)]
    bounds_xy = np.column_stack([plan[:, :, 0].min(axis=1), plan[:, :, 0].max(axis=1),
                                 plan[:, :, 1].min(axis=1), plan[:, :, 1].max(axis=1)])
    return WorldCollisionMesh(
        triangles=triangles,
        plan=plan,
        bounds_xy=bounds_xy,
        md5=file_md5(path),
        path=str(path),
    )


def file_md5(path: str | Path) -> str:
    """Return the hex MD5 of a file, used to tie a plan to its mesh."""
    import hashlib

    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def godot_transform_literal(matrix: np.ndarray) -> str:
    """Return a 3x4 matrix as a ``Transform3D(...)`` literal.

    Rows first, then the translation, matching
    ``emit_scene_contract.godot_transform_string``: ``str_to_var`` reads three
    consecutive numbers as one row, so the parsed basis's columns are
    ``g[0][0], g[1][0], g[2][0]``.  Emitting columns instead yields the
    transpose -- a valid transform that renders the room on its side.
    """
    array = np.asarray(matrix, dtype=np.float64)
    if array.shape != (3, 4):
        raise CollisionMeshError("expected a 3x4 matrix, got %r" % (array.shape,))
    values = [float(v) for row in array for v in row[:3]] + [float(v) for v in array[:, 3]]
    return "Transform3D(%s)" % ", ".join(_float32_literal(value) for value in values)


def _float32_literal(value: float) -> str:
    """Round to what a float32 round-trip keeps; Godot stores transforms as float32."""
    rounded = float(np.float32(value))
    text = repr(rounded)
    return text if "e" not in text and "." in text else "%.7g" % rounded


def load_contract_and_mesh(manifest_path: str | Path, glb_path: str | Path):
    """Convenience loader returning ``(contract, mesh, node_transform)``."""
    contract = contract_from_path(manifest_path)
    mesh = load_world_mesh(glb_path, contract)
    return contract, mesh, collision_node_transform(contract)
