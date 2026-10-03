#!/usr/bin/env python3
"""Derive collision-generation settings from the calibrated frame contract.

Every number the collision stage needs -- voxel size, capsule size, seed
position, bounds -- comes from here, and every one of them is either read out of
the contract or a named constant with its reason recorded.  Nothing is a bare
literal at the call site, because a bare literal is exactly how the previous
three attempts at this task silently assumed one reconstruction unit was one
metre.

Two conversions are load-bearing and easy to get wrong:

* **metres to reconstruction units.** The contract's ``metres_per_unit`` is
  5.128 for this scene, not 1.0.  ``splat-transform`` is handed a *scaled*
  splat (``-s metres_per_unit``) so that every option it exposes -- voxel size,
  capsule height, fill radius -- is in the same metres the Godot scene uses.
  :func:`voxel_size_in_raw_units` reports the raw-unit equivalent so the setting
  is recorded in both, as the task requires.

* **reconstruction frame to PlayCanvas engine frame.**  The tool stores its
  voxel and collision-mesh output in the engine frame, which is the source PLY
  frame rotated 180 degrees about z.  This was measured, not read off a doc: a
  one-Gaussian probe PLY written at ``(1, 2, 3)`` produced ``gridBounds`` around
  ``(-1.1, -2.1, 2.9)``, and a dense probe blob at the same point reported the
  ``--seed-pos`` value ``-1,-2,3`` as occupied while ``1,2,3`` was unoccupied.
  :data:`ENGINE_FRAME_ROTATION` is that rotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from splat_frame import FrameContract

#: The production player capsule, read from ``godot_walk/scenes/player.tscn``
#: (``CapsuleShape3D_player``: radius 0.3, height 1.2 metres).  Recorded as a
#: constant rather than parsed so that the collision stage cannot silently change
#: when the player shape does -- ``tests/test_collision.py`` re-reads the scene
#: and fails if these drift from it.
PLAYER_CAPSULE_RADIUS_M = 0.3
PLAYER_CAPSULE_HEIGHT_M = 1.2

#: Scene file the capsule constants above were read from, for the drift test.
PLAYER_SCENE_PATH = "godot_walk/scenes/player.tscn"

#: Extra clearance added to the player capsule before carving, in metres.  One
#: voxel of slack: the carve capsule is the *guaranteed* free volume, so a player
#: exactly filling it would scrape geometry it is supposed to walk past.  Anything
#: larger starts admitting navigable space the camera never observed.
CLEARANCE_MARGIN_M = 0.05

#: Default voxel edge length in metres.  5 cm resolves the thinnest feature this
#: task must preserve -- a doorway reveal -- with room to spare while keeping the
#: room's navigable volume to a few million voxels, which is what bounds the
#: memory of the validation scan.
DEFAULT_VOXEL_SIZE_M = 0.05

#: Minimum accumulated opacity in a voxel for it to count as solid.  The tool's
#: own default; lowered it and thin walls stop registering, raised it and walls
#: grow holes the exterior fill then leaks through.
DEFAULT_VOXEL_OPACITY = 0.1

#: Coarse grid for ``--filter-cluster``, in metres.  The tool's default is 1.0
#: *world unit*, which on a metre-scaled splat is a 1 m grid -- coarse enough that
#: a 2.4 m room resolves to two voxels across and the seed lands on the floor.
DEFAULT_CLUSTER_RESOLUTION_M = 0.25

#: Remaining ``--filter-cluster`` parameters, which the tool documents as the
#: opacity a cluster voxel needs to be solid and the minimum Gaussian
#: contribution at a cluster voxel centre to keep a splat.
CLUSTER_OPACITY = 0.999
CLUSTER_MIN_CONTRIBUTION = 0.1

#: Dilation ``--voxel-external-fill`` applies before flooding the exterior, in
#: metres.  Measured on the corridor_travel fixture, sweeping 0.4 .. 3.2 m:
#: below 1.0 m the shell is not sealed -- at 0.4 m the tool reports "seed
#: reachable from outside" and skips the fill, leaving 1,187 m3 of navigable
#: space where the room holds 640 m3 -- and between 0.6 and 0.95 m the fill runs
#: but the carve seed ends up buried ("blocked after dilation, no free cell
#: within 26 voxels").  At 1.0 m and above both stages succeed and the navigable
#: region stabilises at 2.50 m of clear height; 1.2 m is the smallest of the
#: sealed values with margin over the threshold.  The tool's own default of 1.6
#: is in world units and, on a 2.4 m room, is two thirds of the ceiling height.
DEFAULT_EXTERIOR_FILL_RADIUS_M = 1.2

#: ``--collision-mesh`` shape.  ``smooth`` is marching cubes with a coplanar
#: merge, which is the right choice for a character collider: it produced a
#: watertight 12,342-triangle mesh here, where ``faces`` emits two triangles per
#: exposed voxel face and is meant to agree exactly with raycasts against the
#: voxel data, which Godot does not consume.
DEFAULT_MESH_SHAPE = "smooth"

#: Triangle budget for the collision mesh.  Measured 12,342 at the settings
#: below; the headroom covers a busier scene before the mesh is rejected rather
#: than shipped.
MAX_TRIANGLES = 200_000

#: Peak resident memory budget for the tool, in bytes.  Measured 563 MB of CPU
#: and 33 MB of GPU at these settings; the limit is on the mutable voxel grid,
#: whose size scales with the room volume divided by the cube of the voxel size.
MAX_PEAK_CPU_BYTES = 4 * 1024 ** 3
MAX_PEAK_GPU_BYTES = 2 * 1024 ** 3

#: Rotation from the reconstruction PLY frame into the PlayCanvas engine frame
#: that ``splat-transform`` writes its voxel and collision output in: 180 degrees
#: about z, about the PLY origin (not the centroid).
ENGINE_FRAME_ROTATION = np.array(
    [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]
)


class CollisionError(ValueError):
    """Raised when settings cannot be derived, or derived values are unusable."""


@dataclass(frozen=True)
class CollisionSettings:
    """Every option the collision stage runs with, all in calibrated metres."""

    voxel_size_m: float
    voxel_opacity: float
    cluster_resolution_m: float
    cluster_opacity: float
    cluster_min_contribution: float
    exterior_fill_radius_m: float
    capsule_height_m: float
    capsule_radius_m: float
    seed_engine_frame_m: tuple[float, float, float]
    mesh_shape: str
    max_triangles: int
    max_peak_cpu_bytes: int
    max_peak_gpu_bytes: int

    def validate(self) -> None:
        """Reject settings that cannot produce usable collision."""
        if self.voxel_size_m <= 0.0:
            raise CollisionError("voxel_size_m must be positive")
        if not 0.0 < self.voxel_opacity <= 1.0:
            raise CollisionError("voxel_opacity must be in (0, 1]")
        if self.cluster_resolution_m <= 0.0:
            raise CollisionError("cluster_resolution_m must be positive")
        if self.capsule_radius_m < PLAYER_CAPSULE_RADIUS_M:
            raise CollisionError(
                "carve capsule radius %.3f m is below the production player radius %.3f m; "
                "the collision would be tighter than the thing walking through it"
                % (self.capsule_radius_m, PLAYER_CAPSULE_RADIUS_M)
            )
        if self.capsule_height_m < PLAYER_CAPSULE_HEIGHT_M:
            raise CollisionError(
                "carve capsule height %.3f m is below the production player height %.3f m"
                % (self.capsule_height_m, PLAYER_CAPSULE_HEIGHT_M)
            )
        if self.mesh_shape not in ("smooth", "faces"):
            raise CollisionError("mesh_shape must be 'smooth' or 'faces'")
        if self.max_triangles <= 0:
            raise CollisionError("max_triangles must be positive")

    def to_json(self) -> dict:
        """Return a JSON-serialisable record of every setting."""
        return {
            "voxel_size_m": self.voxel_size_m,
            "voxel_opacity": self.voxel_opacity,
            "cluster_resolution_m": self.cluster_resolution_m,
            "cluster_opacity": self.cluster_opacity,
            "cluster_min_contribution": self.cluster_min_contribution,
            "exterior_fill_radius_m": self.exterior_fill_radius_m,
            "capsule_height_m": self.capsule_height_m,
            "capsule_radius_m": self.capsule_radius_m,
            "clearance_margin_m": CLEARANCE_MARGIN_M,
            "seed_engine_frame_m": list(self.seed_engine_frame_m),
            "mesh_shape": self.mesh_shape,
            "max_triangles": self.max_triangles,
            "max_peak_cpu_bytes": self.max_peak_cpu_bytes,
            "max_peak_gpu_bytes": self.max_peak_gpu_bytes,
        }


def settings_from_contract(
    contract: FrameContract,
    voxel_size_m: float = DEFAULT_VOXEL_SIZE_M,
    exterior_fill_radius_m: float = DEFAULT_EXTERIOR_FILL_RADIUS_M,
    cluster_resolution_m: float = DEFAULT_CLUSTER_RESOLUTION_M,
    mesh_shape: str = DEFAULT_MESH_SHAPE,
) -> CollisionSettings:
    """Derive the full option set for one scene from its frame contract.

    The seed is the contract's spawn raised to the centre of the *carve* capsule,
    because that is the point the tool floods from; putting the seed at floor
    level instead would start the flood inside the floor slab.
    """
    if contract.scene_id == "":
        raise CollisionError("the contract carries no scene_id")
    half_height = 0.5 * (PLAYER_CAPSULE_HEIGHT_M + CLEARANCE_MARGIN_M)
    seed_world = np.array(
        [contract.spawn[0], contract.collider.floor_height + half_height, contract.spawn[2]]
    )
    settings = CollisionSettings(
        voxel_size_m=voxel_size_m,
        voxel_opacity=DEFAULT_VOXEL_OPACITY,
        cluster_resolution_m=cluster_resolution_m,
        cluster_opacity=CLUSTER_OPACITY,
        cluster_min_contribution=CLUSTER_MIN_CONTRIBUTION,
        exterior_fill_radius_m=exterior_fill_radius_m,
        capsule_height_m=PLAYER_CAPSULE_HEIGHT_M + CLEARANCE_MARGIN_M,
        capsule_radius_m=PLAYER_CAPSULE_RADIUS_M + CLEARANCE_MARGIN_M,
        seed_engine_frame_m=_as_triple(world_to_engine_frame(seed_world, contract)),
        mesh_shape=mesh_shape,
        max_triangles=MAX_TRIANGLES,
        max_peak_cpu_bytes=MAX_PEAK_CPU_BYTES,
        max_peak_gpu_bytes=MAX_PEAK_GPU_BYTES,
    )
    settings.validate()
    return settings


def voxel_size_in_raw_units(voxel_size_m: float, contract: FrameContract) -> float:
    """Return the voxel edge length in the reconstruction PLY's own units.

    Recorded next to the metric value because "raw 0.15" is not 0.15 m: on this
    scene one raw unit is 5.128 m, so a 5 cm voxel is 0.00975 raw units.  A
    reader comparing a setting against the PLY needs this number, and a reader
    who assumed 1:1 would place the grid roughly five times too coarse.
    """
    metres_per_unit = contract.ply_to_world.metres_per_unit
    if metres_per_unit <= 0.0:
        raise CollisionError("metres_per_unit must be positive")
    return voxel_size_m / metres_per_unit


def world_to_engine_frame(point_world, contract: FrameContract) -> np.ndarray:
    """Map a Godot world point into the frame the collision output is written in.

    Inverts the contract's mapping and then applies :data:`ENGINE_FRAME_ROTATION`.
    """
    world = np.asarray(point_world, dtype=np.float64)
    if world.shape != (3,):
        raise CollisionError("expected a 3-component point, got %r" % (world.shape,))
    frame_units = contract.ply_to_world.origin_ply_units + (
        np.linalg.inv(contract.ply_to_world.rotation()) @ (world / contract.ply_to_world.metres_per_unit)
    )
    return ENGINE_FRAME_ROTATION @ (frame_units * contract.ply_to_world.metres_per_unit)


def engine_frame_to_world(point_engine, contract: FrameContract) -> np.ndarray:
    """Map collision-mesh points from the engine frame back into Godot world metres.

    Accepts a single point or an ``(N, 3)`` block, because the callers that need
    every triangle of the mesh at once are the ones that would otherwise loop
    over ten thousand of them.
    """
    engine = np.atleast_2d(np.asarray(point_engine, dtype=np.float64))
    if engine.ndim != 2 or engine.shape[1] != 3:
        raise CollisionError("expected (3,) or (N, 3) points, got %r" % (engine.shape,))
    ply_to_world = contract.ply_to_world
    # world = rotation * (R180 * engine - origin) * metres_per_unit, written out
    # so a whole mesh maps in one call.  ``test_collision.py`` asserts this equals
    # ``PlyToWorld.world_point`` per point.
    rotated = ENGINE_FRAME_ROTATION.T @ engine.T
    offset = (ply_to_world.rotation() @ np.asarray(ply_to_world.origin_ply_units, dtype=np.float64)) * (
        ply_to_world.metres_per_unit
    )
    world = (ply_to_world.rotation() @ rotated).T - offset
    return world[0] if np.ndim(point_engine) == 1 else world


def collision_node_transform(contract: FrameContract) -> np.ndarray:
    """Return the 3x4 Godot transform for a node carrying the collision mesh.

    Unlike the splat node this transform is **not** translation-free: Godot's
    glTF importer applies no centroid subtraction, so the contract's
    ``origin_ply_units`` has to be carried here.

    Its basis is a **pure rotation**: the contract's rotation composed with
    :data:`ENGINE_FRAME_ROTATION`.  The tool voxelizes a splat that has already
    been scaled into metres (``tool.build_argv`` multiplies the PLY by
    ``metres_per_unit`` before writing it), so the engine frame is already
    metric and multiplying again would stretch the collision by
    ``metres_per_unit`` -- 5.128x on this scene, which lands the floor metres
    below the room and leaves nothing for the player to stand on.  The
    translation keeps ``metres_per_unit`` because it converts the contract's raw
    PLY offset into metres.

    This is the same mapping as :func:`engine_frame_to_world` written as a
    matrix, and ``test_collision.py`` asserts the two agree, because they were
    once derived independently and disagreed.
    """
    ply_to_world = contract.ply_to_world
    basis = ply_to_world.rotation() @ ENGINE_FRAME_ROTATION.T
    translation = -(ply_to_world.rotation() @ np.asarray(ply_to_world.origin_ply_units)) * (
        ply_to_world.metres_per_unit
    )
    out = np.zeros((3, 4))
    out[:, :3] = basis
    out[:, 3] = translation
    return out


def room_bounds_in_engine_frame(contract: FrameContract) -> tuple[np.ndarray, np.ndarray]:
    """Return the contract's room corners in the collision output's frame."""
    low = np.minimum(
        world_to_engine_frame(contract.collider.min_corner, contract),
        world_to_engine_frame(contract.collider.max_corner, contract),
    )
    high = np.maximum(
        world_to_engine_frame(contract.collider.min_corner, contract),
        world_to_engine_frame(contract.collider.max_corner, contract),
    )
    return low, high


def contract_from_path(path: str | Path) -> FrameContract:
    """Load a frame contract, naming the file in any error it raises."""
    resolved = Path(path)
    if not resolved.exists():
        raise CollisionError("no alignment contract at %s" % resolved)
    return FrameContract.load(resolved)


def _as_triple(values) -> tuple[float, float, float]:
    """Round a 3-vector to millimetres and return it as a tuple.

    Rounding matters because these values are printed into a command line and
    recorded in a manifest: a seed written with 17 significant digits implies a
    precision the voxel grid does not have, and hides which one was used.
    """
    array = np.asarray(values, dtype=np.float64).round(3)
    return float(array[0]), float(array[1]), float(array[2])