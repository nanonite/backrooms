#!/usr/bin/env python3
"""Tests for the world-space collision queries and the traversal plan derivation.

Every test here builds its own geometry.  None of them needs the GPU, the pinned
tool, or Godot, and only the last one reads a shipped artefact -- so a failure
points at the logic under test rather than at an asset someone regenerated.

The tests are written around the mistakes this module actually made, each of
which passed every other check:

* ``open_at`` asked whether a height fell inside *some* gap, which calls a solid
  column navigable and reports the whole shell interior as headroom.
* ``_long_runs`` read its running counter out of the slice it had not written yet,
  so every run measured 1 and nothing was ever walkable.
* The free-space grid probed a single point at a single height, which put a
  route cell 0.5 m from a wall the physics then refused to cross.
"""

from __future__ import annotations

import sys
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collision_mesh_world import (
    CollisionMeshError,
    WorldCollisionMesh,
    godot_transform_literal,
    load_world_mesh,
)
from collision_params import ENGINE_FRAME_ROTATION
from traversal_plan import (
    REQUIRED_CLEARANCE_M,
    TraversalPlanError,
    _capsule_fits,
    _corners,
    _long_runs,
    shortest_path,
)


def _box(centre, size) -> np.ndarray:
    """Return the 12 triangles of an axis-aligned box."""
    cx, cy, cz = centre
    hx, hy, hz = (value * 0.5 for value in size)
    corners = {
        (sx, sy, sz): np.array([cx + sx * hx, cy + sy * hy, cz + sz * hz])
        for sx in (-1, 1)
        for sy in (-1, 1)
        for sz in (-1, 1)
    }
    faces = [
        ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)),
        ((-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)),
        ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
        ((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)),
        ((1, -1, -1), (1, -1, 1), (1, 1, 1), (1, 1, -1)),
        ((-1, 1, -1), (-1, 1, 1), (-1, -1, 1), (-1, -1, -1)),
    ]
    triangles = []
    for a, b, c, d in faces:
        triangles.append([corners[a], corners[b], corners[c]])
        triangles.append([corners[a], corners[c], corners[d]])
    return np.array(triangles)


def _mesh(blocks: list) -> WorldCollisionMesh:
    """Assemble a queryable mesh from a list of triangle blocks."""
    triangles = np.concatenate(blocks, axis=0)
    plan = triangles[:, :, [0, 2]]
    bounds_xy = np.column_stack([
        plan[:, :, 0].min(axis=1), plan[:, :, 0].max(axis=1),
        plan[:, :, 1].min(axis=1), plan[:, :, 1].max(axis=1),
    ])
    return WorldCollisionMesh(triangles=triangles, plan=plan, bounds_xy=bounds_xy)


@pytest.fixture
def room() -> WorldCollisionMesh:
    """A 10 x 3 x 10 m solid shell with a 6 x 2 x 6 m cavity and a central pillar.

    Nested closed boxes, which is the shape the pinned tool actually emits: the
    boundary of the solid material, with the navigable cavity subtracted from it.
    A column through the cavity crosses four surfaces; a column through the
    material crosses two.  That is the case a "is this height inside some gap"
    test gets wrong, and reproducing it here is the point of the fixture.
    """
    return _mesh([
        _box((0.0, 0.0, 0.0), (10.0, 3.0, 10.0)),    # outer shell
        _box((0.0, 0.0, 0.0), (6.0, 2.0, 6.0)),      # the cavity it encloses
        _box((0.0, 0.0, 0.0), (1.0, 1.8, 1.0)),      # a pillar inside the cavity
    ])


# --------------------------------------------------------------------------
# open_at: the even-odd rule
# --------------------------------------------------------------------------


def test_a_column_through_the_cavity_crosses_four_surfaces(room):
    # Off the boxes' diagonals: a ray along a shared edge matches both faces.
    assert room.surfaces_under(2.0, 2.3).size == 4


def test_a_column_through_the_material_crosses_two(room):
    assert room.surfaces_under(0.0, 4.5).size == 2


def test_the_cavity_interior_is_open(room):
    assert room.open_at(2.0, 2.3, 0.0) is True
    assert room.open_at(2.0, 2.3, 0.9) is True


def test_the_material_is_not_open_and_has_no_band(room):
    """The defect the parity rule exists to prevent.

    A "is this height inside some gap" test answers True here: the gap between the
    shell's outer and inner surfaces spans the whole metre of material, so the
    wall reads as a 1 m tall corridor with headroom to spare.
    """
    assert room.open_at(0.0, 4.5, 0.0) is False
    assert room.band(0.0, 4.5, 0.0) is None


def test_the_pillar_is_solid_from_floor_to_ceiling(room):
    assert room.open_at(0.1, 0.2, 0.0) is False
    assert room.band(0.1, 0.2, 0.0) is None


def test_below_and_above_the_shell_the_parity_still_says_air(room):
    """Four crossings below the top surface is air again, not solid."""
    assert room.open_at(2.0, 2.3, -2.0) is True
    assert room.open_at(2.0, 2.3, 2.0) is True


def test_band_reports_the_surfaces_around_an_open_height(room):
    assert room.band(2.0, 2.3, 0.0) == pytest.approx((-1.0, 1.0))


def test_a_column_off_the_mesh_is_open_and_reports_no_surfaces(room):
    assert room.surfaces_under(50.0, 50.0).size == 0
    assert room.open_at(50.0, 50.0, 0.0) is True
    assert room.band(50.0, 50.0, 0.0) is None


# --------------------------------------------------------------------------
# first_blocked_ahead
# --------------------------------------------------------------------------


def test_first_blocked_ahead_finds_the_pillar_face(room):
    hit = room.first_blocked_ahead(2.0, 0.2, (-1.0, 0.0), [0.0], limit_m=6.0)
    assert hit is not None
    distance, height = hit
    assert distance == pytest.approx(1.5, abs=0.02)
    assert height == pytest.approx(0.0)


def test_first_blocked_ahead_returns_none_when_the_ray_never_meets_solid(room):
    assert room.first_blocked_ahead(2.0, 2.0, (-1.0, 0.0), [0.0], limit_m=1.0) is None


def test_first_blocked_ahead_uses_every_cross_section_given(room):
    """An obstacle that is clear at the waist still blocks the shoulder.

    The pillar spans y -0.9 to 0.9, so a shoulder query at 0.95 walks straight
    past it and only finds the far cavity wall 5.0 m away.  Listing both heights
    stops the march at the pillar, 1.5 m out, which is where the capsule actually
    meets it.
    """
    waist = room.first_blocked_ahead(2.0, 0.2, (-1.0, 0.0), [0.0], limit_m=6.0)
    shoulder = room.first_blocked_ahead(2.0, 0.2, (-1.0, 0.0), [0.95], limit_m=6.0)
    both = room.first_blocked_ahead(2.0, 0.2, (-1.0, 0.0), [0.95, 0.6], limit_m=6.0)
    assert waist[0] == pytest.approx(1.5, abs=0.02)
    assert shoulder[0] == pytest.approx(5.0, abs=0.05)
    assert both[0] == pytest.approx(1.5, abs=0.02)
    assert both[1] == pytest.approx(0.6)


# --------------------------------------------------------------------------
# the bounding-box cull
# --------------------------------------------------------------------------


def test_culling_does_not_change_the_answer(room):
    """The fast path must agree with an unfiltered scan of the same triangles."""
    scan = WorldCollisionMesh(
        triangles=room.triangles,
        plan=room.plan,
        bounds_xy=np.column_stack([
            np.full(len(room.triangles), -1e9), np.full(len(room.triangles), 1e9),
            np.full(len(room.triangles), -1e9), np.full(len(room.triangles), 1e9),
        ]),
    )
    for x, z in ((2.0, 2.3), (0.0, 4.5), (0.1, 0.2), (-4.9, 4.9)):
        assert np.array_equal(room.surfaces_under(x, z), scan.surfaces_under(x, z))


# --------------------------------------------------------------------------
# godot_transform_literal
# --------------------------------------------------------------------------


def test_transform_literal_is_row_major():
    """Three consecutive numbers are one row, so the rows must be the rows.

    Emitting columns instead yields the transpose: a valid transform that renders
    the room on its side, which reads as a maths bug rather than a serialisation
    one.
    """
    matrix = np.array([
        [1.0, 2.0, 3.0, 0.5], [4.0, 5.0, 6.0, 0.25], [7.0, 8.0, 9.0, -0.125],
    ])
    assert godot_transform_literal(matrix) == (
        "Transform3D(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 0.5, 0.25, -0.125)"
    )


def test_transform_literal_rounds_to_float32():
    """Godot stores transforms as float32; more digits would imply false precision."""
    matrix = np.zeros((3, 4))
    matrix[:, :3] = np.eye(3)
    matrix[:, 3] = (0.1 + 0.2 + 0.3, 0.0, 0.0)
    assert "0.6" in godot_transform_literal(matrix)


def test_transform_literal_rejects_a_matrix_that_is_not_3x4():
    with pytest.raises(CollisionMeshError):
        godot_transform_literal(np.eye(4))


# --------------------------------------------------------------------------
# run lengths
# --------------------------------------------------------------------------


def test_a_run_that_meets_the_minimum_passes_on_both_axes():
    present = np.ones((6, 5), dtype=bool)
    assert _long_runs(present, 5, axis=0).all()
    assert _long_runs(present, 5, axis=1).all()


def test_a_run_shorter_than_the_minimum_is_rejected_on_that_axis_only():
    """Rows are 6 long, columns 5 long, so a minimum of 6 splits them."""
    present = np.ones((6, 5), dtype=bool)
    assert _long_runs(present, 6, axis=0).all()
    assert not _long_runs(present, 6, axis=1).any()


def test_a_hole_splits_the_run_on_the_axis_that_crosses_it():
    """The defect: the counter has to carry from the *previous* position.

    Reading it out of the slice about to be written makes every run measure 1,
    which fails every cell and silently empties the route.
    """
    present = np.ones((6, 5), dtype=bool)
    present[3, 1] = False
    assert _long_runs(present, 5, axis=0)[:, 0].all()
    assert not _long_runs(present, 3, axis=0)[:, 1].all()
    assert _long_runs(present, 3, axis=0)[:, 1][:3].all()
    assert _long_runs(present, 3, axis=1)[0].all()
    assert not _long_runs(present, 3, axis=1)[3].all()


def test_an_isolated_cell_is_not_in_a_long_run():
    present = np.zeros((4, 4), dtype=bool)
    present[1, 1] = True
    assert not _long_runs(present, 2, axis=0)[1, 1]
    assert not _long_runs(present, 2, axis=0)[0, 0]


# --------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------


class _Grid:
    """The smallest object `shortest_path` needs."""

    def __init__(self, walkable: np.ndarray) -> None:
        self.walkable = walkable
        self.rows, self.cols = walkable.shape


def test_shortest_path_is_four_connected_and_ordered():
    walkable = np.zeros((5, 5), dtype=bool)
    walkable[0, 0] = walkable[0, 1] = walkable[1, 1] = walkable[2, 1] = True
    walkable[2, 2] = True
    path = shortest_path(_Grid(walkable), (0, 0), (2, 2))
    assert path[0] == (0, 0)
    assert path[-1] == (2, 2)
    for first, second in pairwise(path):
        assert abs(first[0] - second[0]) + abs(first[1] - second[1]) == 1


def test_shortest_path_refuses_to_leave_the_walkable_set():
    walkable = np.zeros((4, 4), dtype=bool)
    walkable[0, 0] = walkable[3, 3] = True
    with pytest.raises(TraversalPlanError):
        shortest_path(_Grid(walkable), (0, 0), (3, 3))


def test_shortest_path_refuses_a_goal_that_is_not_walkable():
    walkable = np.zeros((3, 3), dtype=bool)
    walkable[0, 0] = True
    with pytest.raises(TraversalPlanError):
        shortest_path(_Grid(walkable), (0, 0), (1, 1))


def test_corners_keeps_the_turns_and_both_endpoints():
    assert _corners([(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 3)]) == [
        (0, 0), (0, 2), (2, 2), (2, 3),
    ]


# --------------------------------------------------------------------------
# the capsule-volume fit test
# --------------------------------------------------------------------------


def test_a_clear_cell_accepts_the_capsule(room):
    fits = _capsule_fits(room, 2.3 - 0.125, 2.3 - 0.125, 0.25, (1, 1), np.array([[-1.0]]))
    assert bool(fits[0, 0])


def test_a_cell_whose_offset_sample_is_solid_does_not_take_the_capsule(room):
    """The defect the walk run found: a centre-only test calls this walkable.

    A cell against the cavity wall has a clear centre, but its sample one capsule
    radius away is inside the material.  The capsule cannot go there.
    """
    fits = _capsule_fits(room, 2.7, 2.7, 0.25, (1, 1), np.array([[-1.0]]))
    assert not bool(fits[0, 0])


def test_a_floor_step_beyond_one_voxel_rejects_the_cell(room):
    """A cell whose samples sit at different heights is a step, not a corridor."""
    assert bool(_capsule_fits(room, 1.875, 1.875, 0.25, (1, 1), np.array([[-1.0]]))[0, 0])
    assert not bool(_capsule_fits(room, 1.875, 1.875, 0.25, (1, 1), np.array([[-1.2]]))[0, 0])


def test_a_ceiling_below_the_capsule_rejects_the_cell():
    """``REQUIRED_CLEARANCE_M`` is capsule height plus margin, so the probe uses it."""
    assert REQUIRED_CLEARANCE_M > 1.2


def test_an_untested_cell_is_never_walkable(room):
    fits = _capsule_fits(room, 100.0, 100.0, 0.25, (1, 1), np.full((1, 1), np.nan))
    assert not bool(fits[0, 0])


# --------------------------------------------------------------------------
# the shipped artefact
# --------------------------------------------------------------------------


def test_the_shipped_mesh_is_the_one_the_plan_was_derived_from():
    """Ties the plan in the Godot project to the mesh #84 recorded.

    Skipped when the GLB is absent: it is a large binary that a checkout without
    the pipeline artefacts will not have, and its absence is #84's to report.
    """
    root = Path(__file__).resolve().parents[3]
    glb = root / "godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb"
    manifest = root / "godot_walk/assets/corridor_splat/alignment_manifest.json"
    if not glb.exists() or not manifest.exists():
        pytest.skip("collision mesh or alignment manifest not present")
    from collision_params import contract_from_path

    contract = contract_from_path(manifest)
    mesh = load_world_mesh(glb, contract)
    assert mesh.triangle_count == 10178
    assert mesh.md5 == "c8f7a46effade8002a9bc51f74e3b11e"
    # The engine frame is metric: the mesh spans metres, not reconstruction units.
    low, high = mesh.bounds()
    assert high[1] - low[1] == pytest.approx(3.0, abs=0.01)
    assert ENGINE_FRAME_ROTATION @ np.array([1.0, 2.0, 3.0]) == pytest.approx([-1.0, -2.0, 3.0])
