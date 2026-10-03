#!/usr/bin/env python3
"""Pure construction of the PLY-frame -> Godot-world rotation.

Godot is right-handed and y-up.  Every reconstruction frame we have is also
right-handed but may be y-, z- or x-up.  Choosing *which* world axis the
non-up frame axes land on is a decision, so it lives in one small, testable
function rather than being re-derived per scene.

Convention: the frame's up axis becomes world +Y, the frame's declared width
axis becomes world +X, and the remaining axis becomes world +Z.  Because both
frames are right-handed that choice is forced to be det=+1 -- there is no way
to compose a proper rotation any other way without mirroring.
"""

from __future__ import annotations

import numpy as np

AXIS_NAMES = ("x", "y", "z")
AXIS_VECTORS = {name: np.eye(3)[index] for index, name in enumerate(AXIS_NAMES)}


def world_basis_for(up_axis: int, width_axis: int, up_sign: int = 1) -> np.ndarray:
    """Return the 3x3 rotation mapping frame axes onto Godot world axes.

    Column ``i`` is the Godot-world image of frame axis ``i``, so the matrix can be
    applied directly to a reconstruction-space point.

    ``up_axis`` and ``width_axis`` are 0-based indices into (x, y, z) and must
    differ; ``up_sign`` is +1 or -1 and says which way along ``up_axis`` gravity
    points.  The frame's up axis maps onto Godot's +Y and its width axis onto
    Godot's +X; the third axis is then forced by requiring a proper rotation, so
    there is no way to compose a basis that mirrors the room.
    """
    if up_axis not in (0, 1, 2) or width_axis not in (0, 1, 2):
        raise ValueError("axis indices must be 0, 1 or 2")
    if up_axis == width_axis:
        raise ValueError("up and width must be different frame axes")
    if up_sign not in (1, -1):
        raise ValueError("up_sign must be +1 or -1")

    depth_axis = remaining_axis(up_axis, width_axis)
    basis = np.zeros((3, 3))
    basis[:, width_axis] = AXIS_VECTORS["x"]
    basis[:, up_axis] = up_sign * AXIS_VECTORS["y"]
    basis[:, depth_axis] = np.cross(basis[:, width_axis], basis[:, up_axis])
    if float(np.linalg.det(basis)) < 0.0:
        basis[:, depth_axis] = -basis[:, depth_axis]
    if abs(float(np.linalg.det(basis)) - 1.0) > 1e-9:
        raise ValueError("constructed basis is not a proper rotation")
    return basis


def remaining_axis(up_axis: int, width_axis: int) -> int:
    """Return the frame axis that is neither up nor width."""
    spare = sorted({0, 1, 2} - {up_axis, width_axis})
    if len(spare) != 1:
        raise ValueError("up and width must differ")
    return spare[0]


def axis_index(name: str) -> int:
    """Return the 0-based index of an axis name ('x', 'y' or 'z')."""
    try:
        return AXIS_NAMES.index(name)
    except ValueError as error:
        raise ValueError("unknown axis %r; expected one of %s" % (name, ", ".join(AXIS_NAMES))) from error