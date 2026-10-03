#!/usr/bin/env python3
"""Emit the contract-derived Transform3D values for the Godot scene files.

The collider boxes and the spawn marker in ``godot_walk/scenes/corridor.tscn``
used to be nudged by hand until the player stopped falling through the floor.
That is precisely the loop this replaces: the room is derived from the measured
floor/ceiling planes and the observed splat extent recorded in the manifest, and
the transform strings are printed here so they can be pasted in or diffed in a
review.

Two things it deliberately does not do:

* It does not invent geometry. The room box comes from the manifest, which says
  whether its horizontal extents were *measured* or merely *observed*; when they
  were only observed, that is printed, because a reviewer needs to know the walls
  are not yet trustworthy.
* It does not write the scene file. Scene files are reviewed by hand, and a tool
  that rewrites them silently invites unreviewed geometry changes.

Usage::

    python3 scripts/splat_pipeline/emit_scene_contract.py \\
        --manifest godot_walk/assets/corridor_splat/alignment_manifest.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from splat_frame import FrameContract  # noqa: E402

WALL_THICKNESS_M = 0.2
SAFETY_NET_DROP_M = 1.3
SAFETY_NET_MARGIN_M = 3.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, help="alignment manifest JSON")
    return parser.parse_args(argv)


def godot_transform_string(contract: FrameContract) -> str:
    """Return the contract's mapping as a ``Transform3D(...)`` literal.

    The 3x3 part is emitted **row-major**, followed by the translation. Confirmed
    against the engine: `str_to_var` on a `.tscn`-style literal interprets three
    consecutive numbers as one row, so the columns of the parsed basis are
    `g[0][0], g[1][0], g[2][0]` and so on. Emitting columns instead yields the
    transpose -- a valid transform that renders the room on its side, which reads
    as a math bug rather than a serialisation bug.

    Uses `node_transform_matrix()`, whose translation is zero: the GDGS resource
    builder already subtracts the mean Gaussian centre at import, so a node
    transform must not reapply it. Note that matrix is 3x4, so each row already
    carries a translation component; slicing `[:, :3]` matters, since
    concatenating full rows interleaves the origin into the basis and silently
    produces a nonsense matrix.

    Godot stores transforms as float32, so values are rounded to what a float32
    round-trip preserves; emitting more digits would imply precision the engine
    does not have.
    """
    matrix = contract.ply_to_world.node_transform_matrix()
    rows = [list(matrix[row, :3]) for row in range(3)]
    translation = [matrix[row, 3] for row in range(3)]
    values = rows[0] + rows[1] + rows[2] + translation
    return "Transform3D(%s)" % ", ".join(_float32_literal(value) for value in values)


def _float32_literal(value: float) -> str:
    rounded = float(np.float32(value))
    text = repr(rounded)
    return text if "e" not in text and "." in text else "%.7g" % rounded


def collider_bodies(contract: FrameContract) -> list[dict]:
    """Return every collision body's name, centre and size, all in world metres.

    Walls are centred on the room's mid-height so the clear height between the
    floor's top surface and the ceiling's underside equals the measured clear
    height exactly. Walls sit just outside the room box so their inner faces
    bound it, which keeps the player's 0.6 m capsule radius inside the room.
    """
    low = np.asarray(contract.collider.min_corner)
    high = np.asarray(contract.collider.max_corner)
    size = high - low
    centre = 0.5 * (high + low)
    floor_y = contract.collider.floor_height
    ceiling_y = contract.collider.ceiling_height
    clear_height = ceiling_y - floor_y
    mid_height = 0.5 * (floor_y + ceiling_y)
    half = 0.5 * WALL_THICKNESS_M

    net_size = size + 2.0 * SAFETY_NET_MARGIN_M
    bodies = [
        {"name": "Floor", "shape": "Box_floor",
         "centre": (centre[0], floor_y - half, centre[2]),
         "size": (size[0], WALL_THICKNESS_M, size[2])},
        {"name": "SafetyNet", "shape": "Box_safetynet",
         "centre": (centre[0], floor_y - SAFETY_NET_DROP_M, centre[2]),
         "size": (net_size[0], WALL_THICKNESS_M, net_size[2])},
        {"name": "LongWallNeg", "shape": "Box_longwall",
         "centre": (centre[0], mid_height, low[2] - half),
         "size": (size[0], clear_height, WALL_THICKNESS_M)},
        {"name": "LongWallPos", "shape": "Box_longwall",
         "centre": (centre[0], mid_height, high[2] + half),
         "size": (size[0], clear_height, WALL_THICKNESS_M)},
        {"name": "EndWallNeg", "shape": "Box_endwall",
         "centre": (low[0] - half, mid_height, centre[2]),
         "size": (WALL_THICKNESS_M, clear_height, size[2])},
        {"name": "EndWallPos", "shape": "Box_endwall",
         "centre": (high[0] + half, mid_height, centre[2]),
         "size": (WALL_THICKNESS_M, clear_height, size[2])},
        {"name": "Ceiling", "shape": "Box_ceiling",
         "centre": (centre[0], ceiling_y + half, centre[2]),
         "size": (size[0], WALL_THICKNESS_M, size[2])},
    ]
    return bodies


def shape_definitions(contract: FrameContract) -> list[dict]:
    """Return the BoxShape3D sub-resources the collider bodies reference."""
    bodies = collider_bodies(contract)
    unique: dict[str, tuple[float, float, float]] = {}
    for body in bodies:
        unique.setdefault(body["shape"], body["size"])
    return [{"name": name, "size": size} for name, size in unique.items()]


def main(argv: list[str] | None = None) -> int:
    """Print the manifest-derived scene contract."""
    args = parse_args(argv)
    contract = FrameContract.load(args.manifest)
    print("scene_id: %s" % contract.scene_id)
    print("splat node transform (apply to the GaussianSplatNode):")
    print("  %s" % godot_transform_string(contract))
    print()
    print("BoxShape3D sub-resources:")
    for shape in shape_definitions(contract):
        print('  SubResource("%s") size = Vector3(%.6f, %.6f, %.6f)' % ((shape["name"],) + shape["size"]))
    print()
    print("collision bodies:")
    for body in collider_bodies(contract):
        cx, cy, cz = body["centre"]
        print('  %-14s transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.7g, %.7g, %.7g)  [%s]'
              % (body["name"], cx, cy, cz, body["shape"]))
    spawn = contract.spawn
    print()
    print('  PlayerSpawn      transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.7g, %.7g, %.7g)'
          % (spawn[0], spawn[1], spawn[2]))
    print("  (PlayerSpawn sits %.3f m above the floor at %.4f m)"
          % (contract.spawn_clearance_m, contract.collider.floor_height))
    print()
    print("landmarks (Godot world metres):")
    for name in sorted(contract.landmarks):
        point = contract.landmark(name)
        print("  %-12s %s" % (name, np.round(point, 4).tolist()))
    height = contract.landmark_distance("floor", "ceiling")
    print("  floor -> ceiling: %.4f m (declared %.4f m, tolerance %.4f m)"
          % (height, contract.scale_reference.target_metres, contract.scale_reference.tolerance_metres))
    if not bool(contract.capture.get("walls_measured", False)):
        print()
        print("NOTE: %s" % contract.capture.get("width_note", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())