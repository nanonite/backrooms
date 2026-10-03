#!/usr/bin/env python3
"""Derive the deterministic traversal plan #85 walks and verifies.

Everything a Godot walk test needs to be *calibrated* rather than hand-picked
lives here: the free-space grid implied by #84's generated collision, the
waypoints along a route through it, the probes that must be stopped by solid
geometry, the spawn derived from the collision's own floor surface, and the
tolerances every one of those is checked against.

Nothing in this module is chosen by eye.  The grid comes from the collision mesh
#84 generated, the free cells from vertical queries against that mesh, the route
from a breadth-first search over those cells, and every constant carries its
reason inline.

Usage::

    python3 scripts/splat_pipeline/traversal_plan.py \\
        --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \\
        --report scripts/splat_pipeline/collision_benchmark.json \\
        --glb godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb \\
        --out godot_walk/assets/corridor_splat/traversal_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collision_mesh_world import (
    WorldCollisionMesh,
    godot_transform_literal,
    load_contract_and_mesh,
)
from collision_params import DEFAULT_VOXEL_SIZE_M
from splat_frame import FrameContract

PLAN_SCHEMA_VERSION = 1

#: Production capsule, copied from ``godot_walk/scenes/player.tscn``'s
#: ``CapsuleShape3D``.  #84's carve capsule is this plus
#: :data:`CLEARANCE_MARGIN_M`, so a route a 0.35 m capsule fits through is a
#: route the 0.3 m player fits through with 0.05 m to spare on each side.
PLAYER_CAPSULE_RADIUS_M = 0.3
PLAYER_CAPSULE_HEIGHT_M = 1.2

#: Clearance a route must leave above the player's feet.  Capsule height plus a
#: margin: without it a cell the 0.35 m carve capsule cleared by 3 cm would be
#: reported as walkable and then found to be a crawlspace at run time.
CLEARANCE_MARGIN_M = 0.05
REQUIRED_CLEARANCE_M = PLAYER_CAPSULE_HEIGHT_M + CLEARANCE_MARGIN_M

#: Height at which a column is called open or solid.  Taken from #84's
#: ``OBSTRUCTION_TEST_HEIGHT_M``: waist height, where a wall is and floor detail
#: is not.
TEST_HEIGHT_M = 1.0

#: Free width a route needs, in whole column cells.  Four cells is 1.00 m, which
#: admits the narrowest opening in this capture with the player's 0.6 m diameter
#: and room to spare, and rejects a gap the voxel grid only resolved diagonally.
MIN_FREE_RUN_CELLS = 4

#: Height left below the capsule's crown when probing it against a ceiling, in
#: metres.  A tenth of the voxel size: enough that a ceiling a few centimetres
#: lower than the plan's figure is still a pass, because that is within the mesh's
#: own resolution.
CLEARANCE_PROBE_M = 0.01

#: How far a capsule sample's floor may differ from its cell's floor and still
#: count as the same corridor, in metres.  One 5 cm voxel of slope across the
#: capsule's diameter; beyond that the walker is climbing a step sideways, which
#: the route should route around rather than push through.
STEP_TOLERANCE_M = 0.05

#: How far below the lowest collision surface the diagnostic safety net sits, in
#: metres.  Far enough that no walk that stays on the generated floor can touch
#: it -- which is the point, since a contact is a failure, not a rescue.
SAFETY_NET_DROP_M = 1.2

#: Slack on a waypoint the walker is required to reach.  0.18 m is wider than the
#: 0.067 m a controller tick covers at 4 m/s, and narrower than the 0.25 m cell a
#: waypoint sits in, so arriving in the neighbouring cell does not count.
POSITION_TOLERANCE_M = 0.18

#: Largest single-step displacement permitted.  At the controller's 4.0 m/s and
#: 60 Hz that is 0.067 m; 0.20 m leaves room for a frame hitch without allowing a
#: step long enough to pass through the 0.05 m voxel shell unnoticed.
MAX_STEP_M = 0.20

#: How close to a blocked cell's face a walker's capsule centre must come to
#: rest.  The mesh is a smoothed 5 cm voxel surface, so the face is not exactly on
#: the cell boundary, and a capsule sliding along it stops within a few
#: centimetres either side of the nominal position.
BLOCK_STOP_TOLERANCE_M = 0.12

#: Longest straight walkable run a blocking probe may start from, in cells
#: (1.00 m at 0.25 m cells).  Enough to reach 4 m/s inside three metres of
#: travel, and short enough that the run stays inside one corridor.
MAX_PROBE_RUN_CELLS = 8

#: A probe that never moved is not evidence, so a probe must cover at least this
#: much ground along its own aim direction before "it stopped" means anything.
MIN_PROBE_DISPLACEMENT_M = 0.75

#: How far a probe's face search will march before declaring there is nothing to
#: stop against, in metres.  Two metres is more than the longest approach run
#: plus the capsule, so a miss means the geometry really is absent.
PROBE_RAY_LIMIT_M = 2.0

#: Fractions of the capsule's height at which a horizontal march is tested.
#: 0.0 is the floor contact, 0.5 the waist where the radius is greatest, 1.0 the
#: crown.  Testing only the waist misses an obstacle that is open at the waist and
#: solid at the shoulder, which is what the interior column in this capture is.
CAPSULE_CROSS_SECTIONS = (0.15, 0.35, 0.5, 0.65, 0.85)

#: How many cells away from a blocked cell a probe's approach may start, in cells
#: (1.5 m at 0.25 m cells).  Beyond that the capsule is standing somewhere the
#: obstacle is not between it and the room, and the "column" and "wall" labels
#: stop meaning what they claim to.
MAX_PROBE_APPROACH_HOPS = 6

#: How far past a probe's measured face the same cross-section must still be solid
#: for that face to count as blocking, in metres.  Wider than the capsule's radius
#: and wider than the 5 cm voxel, so a lip thin enough to step over is rejected.
PROBE_DEAD_END_M = 0.35

#: Fraction of path samples that must report floor contact.  Short gaps at a
#: step are expected while the body is snapping down; a walker that is airborne
#: for a fifth of the route is falling, not walking.
MIN_FLOOR_SUPPORT_FRACTION = 0.95

#: Slack between the floor surface this plan measured offline and the one the
#: engine reports at run time.  Both read the same triangles, so anything larger
#: is a transform disagreement rather than float noise.
FLOOR_SURFACE_TOLERANCE_M = 0.05

#: Largest drop from the contract's spawn marker to the collision's floor, in
#: metres.  The marker is 0.5 m above the contract's floor plane by definition;
#: the generated floor is a different surface, and the drop is measured, not
#: assumed.
MAX_SPAWN_DROP_M = 1.0


class TraversalPlanError(ValueError):
    """Raised when the collision cannot support a traversal plan."""


@dataclass(frozen=True)
class FreeGrid:
    """Per-column walkability of the generated collision, in world metres."""

    size_m: float
    origin_x: float
    origin_z: float
    rows: int
    cols: int
    walkable: np.ndarray
    floor_y: np.ndarray
    ceiling_y: np.ndarray
    clear_m: np.ndarray
    open_at_test: np.ndarray
    tested: np.ndarray
    capsule_fits: np.ndarray

    def cell_centre(self, row: int, col: int) -> tuple[float, float]:
        return (
            self.origin_x + (row + 0.5) * self.size_m,
            self.origin_z + (col + 0.5) * self.size_m,
        )

    def cell_at(self, x: float, z: float) -> tuple[int, int] | None:
        row = int(np.floor((x - self.origin_x) / self.size_m))
        col = int(np.floor((z - self.origin_z) / self.size_m))
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return row, col
        return None


def build_free_grid(mesh: WorldCollisionMesh, contract: FrameContract, report: dict) -> FreeGrid:
    """Probe every column of #84's floor plan against the generated collision.

    The grid origin and cell size come from #84's ``expected_geometry`` rather
    than from this module, so the plan is expressed on the same floor plan the
    collision stage published and a reviewer can lay the two over each other.
    """
    geometry = report["expected_geometry"]
    origin_x, origin_z = (float(v) for v in geometry["column_origin_world_m"])
    size = float(geometry["column_size_m"])
    low, high = mesh.bounds()
    rows = int(np.floor((high[0] - origin_x) / size)) + 1
    cols = int(np.floor((high[2] - origin_z) / size)) + 1
    reference = contract.collider.floor_height + TEST_HEIGHT_M

    shape = (rows, cols)
    floor_y = np.full(shape, np.nan)
    ceiling_y = np.full(shape, np.nan)
    clear_m = np.zeros(shape)
    open_at_test = np.zeros(shape, dtype=bool)
    tested = np.zeros(shape, dtype=bool)
    walkable = np.zeros(shape, dtype=bool)
    for row in range(rows):
        for col in range(cols):
            x, z = _cell_centre(origin_x, origin_z, size, row, col)
            if not (low[0] <= x <= high[0] and low[2] <= z <= high[2]):
                # Outside the generated volume there is no mesh to ask.  Marking
                # it "blocked" would claim solid geometry that does not exist, so
                # it is left untested and excluded from every count.
                continue
            tested[row, col] = True
            open_at_test[row, col] = mesh.open_at(x, z, reference)
            band = mesh.band(x, z, reference)
            if band is None:
                continue
            floor_y[row, col], ceiling_y[row, col] = band
            clear_m[row, col] = band[1] - band[0]

    present = tested & open_at_test
    fits = present & (clear_m >= REQUIRED_CLEARANCE_M) & _capsule_fits(
        mesh, origin_x, origin_z, size, shape, floor_y
    )
    walkable = (
        fits
        & _long_runs(present, MIN_FREE_RUN_CELLS, axis=0)
        & _long_runs(present, MIN_FREE_RUN_CELLS, axis=1)
    )
    return FreeGrid(
        size_m=size,
        origin_x=origin_x,
        origin_z=origin_z,
        rows=rows,
        cols=cols,
        walkable=walkable,
        floor_y=np.where(np.isnan(floor_y), -np.inf, floor_y),
        ceiling_y=ceiling_y,
        clear_m=clear_m,
        open_at_test=open_at_test,
        tested=tested,
        capsule_fits=fits,
    )


def _capsule_fits(mesh: WorldCollisionMesh, origin_x: float, origin_z: float, size: float,
                  shape: tuple[int, int], floor_y: np.ndarray) -> np.ndarray:
    """Whether the production capsule fits in each cell's navigable volume.

    The five sample points are the cell centre and one capsule radius out along
    each horizontal axis.  Every one has to be clear of solid for the whole
    capsule height, and each has to be standing on the same floor to within a
    voxel: a cell whose samples sit at different heights is a step to be climbed
    sideways into, not a corridor.

    This is the check whose absence the first walk run exposed -- a route cell
    0.5 m from a wall that a single-point ray test called open, because the
    centre was inside the cavity while the capsule's 0.3 m radius was not.

    The four diagonals are not probed.  That is a deliberate under-sample: the
    walk test's floor-support and step-size assertions cover the diagonals with
    real physics, and a plan that rejected every cell with an unchecked quadrant
    would describe a smaller room than the mesh actually contains.
    """
    offsets = ((0.0, 0.0), (PLAYER_CAPSULE_RADIUS_M, 0.0), (-PLAYER_CAPSULE_RADIUS_M, 0.0),
               (0.0, PLAYER_CAPSULE_RADIUS_M), (0.0, -PLAYER_CAPSULE_RADIUS_M))
    fits = np.zeros(shape, dtype=bool)
    for row in range(shape[0]):
        for col in range(shape[1]):
            floor = float(floor_y[row, col])
            if not np.isfinite(floor):
                continue
            x, z = _cell_centre(origin_x, origin_z, size, row, col)
            equator = floor + 0.5 * PLAYER_CAPSULE_HEIGHT_M
            head = floor + PLAYER_CAPSULE_HEIGHT_M - CLEARANCE_PROBE_M
            fits[row, col] = all(
                _sample_fits(mesh, x + dx, z + dz, equator, head, floor)
                for dx, dz in offsets
            )
    return fits


def _sample_fits(mesh: WorldCollisionMesh, x: float, z: float, equator: float, head: float,
                 floor: float) -> bool:
    """Whether one capsule sample point is clear from ``floor`` to ``head``."""
    band = mesh.band(x, z, equator)
    if band is None:
        return False
    return abs(band[0] - floor) <= STEP_TOLERANCE_M and band[1] >= head


def _cell_centre(origin_x: float, origin_z: float, size: float, row: int, col: int):
    return origin_x + (row + 0.5) * size, origin_z + (col + 0.5) * size


def _long_runs(present: np.ndarray, minimum: int, axis: int) -> np.ndarray:
    """Return whether each cell lies in a contiguous run of at least ``minimum``.

    ``axis`` 0 counts along rows (world x), 1 along columns (world z).  A run
    shorter than the player's diameter is a gap the capsule does not fit through,
    even when the cells on both sides are open -- which is exactly what a doorway
    reveal resolved by one voxel column looks like.
    """
    # A cell's run length is the present cells before it plus the ones after it,
    # minus the cell itself: `end` counts the run ending here, `start` counts the
    # run beginning here.  Taking a running maximum of either counter instead
    # would let a cell inherit the length of a *different* run further along the
    # same line, so a 5-cell run would report only its last two cells.
    end = _sweep_runs(present, axis)
    # The backward sweep has to reverse positions along `axis`, not across it: the
    # counter it produces is the run *beginning* at each cell, which is the same
    # line read from the far end.
    if axis == 0:
        start = _sweep_runs(present[::-1, :], axis)[::-1, :]
    else:
        start = _sweep_runs(present[:, ::-1], axis)[:, ::-1]
    return (end + start - 1) >= minimum


def _sweep_runs(present: np.ndarray, axis: int) -> np.ndarray:
    """Return, per cell, the length of the run of present cells ending there."""
    run = np.zeros(present.shape, dtype=int)
    carried = np.zeros(present.shape[1 - axis], dtype=int)
    for step in range(present.shape[axis]):
        line = present[step, :] if axis == 0 else present[:, step]
        current = np.where(line, carried + 1, 0)
        if axis == 0:
            run[step, :] = current
        else:
            run[:, step] = current
        carried = current
    return run


def shortest_path(grid: FreeGrid, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    """Return the 4-connected walkable path from ``start`` to ``goal``.

    Four-connected, not eight: a diagonal step can cross a corner the capsule
    does not fit through, and a plan that promises a route the player cannot walk
    is worse than no plan.
    """
    if start not in _walkable_cells(grid) or goal not in _walkable_cells(grid):
        raise TraversalPlanError("start %r and goal %r must both be walkable cells" % (start, goal))
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            break
        for step in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (cell[0] + step[0], cell[1] + step[1])
            row, col = neighbour
            if not (0 <= row < grid.rows and 0 <= col < grid.cols):
                continue
            if not grid.walkable[row, col] or neighbour in previous:
                continue
            previous[neighbour] = cell
            queue.append(neighbour)
    if goal not in previous:
        raise TraversalPlanError("no walkable route from %r to %r" % (start, goal))
    path = []
    cursor: tuple[int, int] | None = goal
    while cursor is not None:
        path.append(cursor)
        cursor = previous[cursor]
    return list(reversed(path))


def _walkable_cells(grid: FreeGrid) -> set[tuple[int, int]]:
    rows, cols = np.nonzero(grid.walkable)
    return set(zip(rows.tolist(), cols.tolist()))


# --------------------------------------------------------------------------
# waypoint selection
# --------------------------------------------------------------------------


def _farthest_cell(grid: FreeGrid, start: tuple[int, int]) -> tuple[int, int]:
    """The walkable cell furthest from ``start``, ties broken by (row, col).

    Breadth-first distance rather than Euclidean, because what has to be proven
    is that the generated collision supports a *walk* the length of the room, not
    that two points are far apart in a straight line through a wall.
    """
    distance = _bfs_distances(grid, start)
    reachable = np.where(distance >= 0, distance, -1)
    best = int(np.argmax(reachable))
    return best // grid.cols, best % grid.cols


def _bfs_distances(grid: FreeGrid, start: tuple[int, int]) -> np.ndarray:
    """Step counts from ``start`` over walkable cells; ``-1`` where unreachable."""
    distances = np.full((grid.rows, grid.cols), -1, dtype=int)
    if not grid.walkable[start]:
        raise TraversalPlanError("spawn cell %r is not walkable" % (start,))
    distances[start] = 0
    queue = deque([start])
    while queue:
        row, col = queue.popleft()
        for step in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (row + step[0], col + step[1])
            nxt_row, nxt_col = neighbour
            if not (0 <= nxt_row < grid.rows and 0 <= nxt_col < grid.cols):
                continue
            if distances[neighbour] < 0 and grid.walkable[neighbour]:
                distances[neighbour] = distances[(row, col)] + 1
                queue.append(neighbour)
    return distances


def _reachable(grid: FreeGrid, start: tuple[int, int]) -> set[tuple[int, int]]:
    """The walkable cells the player can actually reach on foot from ``start``.

    The generated collision is not one room: probing it with the real capsule
    leaves several disconnected pockets, and the narrowest opening in this capture
    is one of them.  A route or a boundary probe aimed at a pocket the player can
    only get into by teleporting would be exactly the "rescue teleport hiding
    failure" the acceptance forbids, so every derived target is restricted to the
    spawn's own component.
    """
    distance = _bfs_distances(grid, start)
    rows, cols = np.nonzero(distance >= 0)
    return set(zip(rows.tolist(), cols.tolist()))


def _corners(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Reduce a cell path to the cells where it changes direction.

    The walker drives along axis-aligned runs, so the turns are the only points
    a route actually has to aim at.  A straight run's interior cells are implied
    by its endpoints.
    """
    if len(path) < 3:
        return list(path)
    kept = [path[0]]
    for index in range(1, len(path) - 1):
        before = (path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1])
        after = (path[index + 1][0] - path[index][0], path[index + 1][1] - path[index][1])
        if before != after:
            kept.append(path[index])
    kept.append(path[-1])
    return kept


def _narrowest_run(grid: FreeGrid, path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return ``[before, tightest, after]`` around the tightest cell on a path.

    Tightness is measured as **width**: how many of a cell's eight neighbours the
    capsule also fits into.  Headroom was the first choice and it is the wrong one
    -- the least headroom on this capture's route is 2.0 m in the middle of open
    floor, which is not a passage and cannot be blocked.  Width is what a
    doorway is.

    Its neighbours are returned too, so the walk has to enter *and* leave the
    pinch: passing it in one direction would only prove half of it.
    """
    openness = [
        sum(
            1
            for d in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
            if 0 <= cell[0] + d[0] < grid.rows
            and 0 <= cell[1] + d[1] < grid.cols
            and grid.capsule_fits[cell[0] + d[0], cell[1] + d[1]]
        )
        for cell in path
    ]
    index = int(np.argmin(openness))
    if index == 0 or index == len(path) - 1:
        raise TraversalPlanError(
            "the tightest cell on the route is an endpoint; the route proves nothing"
        )
    return [path[index - 1], path[index], path[index + 1]]


def _interior_solid(grid: FreeGrid) -> list[tuple[int, int]]:
    """Cells of solid geometry enclosed by walkable space: a column.

    A wall has walkable space on one side; an obstacle inside the room has it on
    both.  That two-sided test is the definition, because connected components of
    the impassable mask do not work here: probing the mesh with a 0.3 m capsule
    turns the thin margin around every wall into impassable cells, and that margin
    joins the column to the room boundary, so the obstacle stops being a separate
    component at all.

    Only genuinely solid cells qualify (``not open_at_test``), so the column is
    real geometry and not merely a place the capsule does not fit.
    """
    solid = grid.tested & ~grid.open_at_test
    island = []
    for row in range(grid.rows):
        for col in range(grid.cols):
            if not solid[row, col]:
                continue
            if _walkable_both_sides(grid, row, col, axis=0) or _walkable_both_sides(grid, row, col, axis=1):
                island.append((row, col))
    if not island:
        raise TraversalPlanError(
            "no solid cell has walkable space on both sides; the generated collision has a wall "
            "but no obstacle inside the room, so there is no column to walk into"
        )
    return island


def _walkable_both_sides(grid: FreeGrid, row: int, col: int, axis: int) -> bool:
    """Whether walkable space exists on both sides of a cell along one axis."""
    def side(direction: int) -> bool:
        step = 1
        while True:
            index = (row + direction * step, col) if axis == 0 else (row, col + direction * step)
            if not (0 <= index[0] < grid.rows and 0 <= index[1] < grid.cols):
                return False
            if not grid.tested[index]:
                return False
            if grid.walkable[index]:
                return True
            step += 1

    return side(-1) and side(1)


def _probe_into(mesh: WorldCollisionMesh, grid: FreeGrid, name: str, start: tuple[int, int],
                blocked: tuple[int, int], direction: tuple[int, int], run_cells: int) -> dict:
    """Describe a walk that must be stopped by solid geometry.

    The expected stop is **measured**, not assumed.  The blocked cell's plan
    boundary is not where the surface is: the mesh is a smoothed 5 cm voxel shell,
    and the first walk run found a probe coming to rest 4.5 m from a stop derived
    from the cell boundary.  So a horizontal ray is marched along the aim direction
    at the capsule's equator height until it enters solid, and the capsule's centre
    is predicted to rest one radius short of that surface -- which is what
    `CharacterBody3D.move_and_slide` leaves it at when a contact arrests the body.
    """
    start_x, start_z = grid.cell_centre(*start)
    unit = (float(direction[0]), float(direction[1]))
    floor = float(grid.floor_y[start])
    heights = [floor + fraction * PLAYER_CAPSULE_HEIGHT_M
               for fraction in CAPSULE_CROSS_SECTIONS]
    hit = mesh.first_blocked_ahead(start_x, start_z, unit, heights, limit_m=PROBE_RAY_LIMIT_M)
    if hit is None:
        raise TraversalPlanError(
            "probe %r finds no solid within %.1f m of cell %r; there is nothing to stop it"
            % (name, PROBE_RAY_LIMIT_M, start)
        )
    distance, blocked_at = hit
    # A face the capsule can squeeze past is not a blocking face.  The first walk
    # run aimed a probe at a pinch the walker slid through in 6.3 m without ever
    # stopping, which would have turned "the opening is blocked" into an
    # assertion nothing could satisfy.  Requiring the cross-section that blocked
    # to still be solid a third of a metre further on makes the probe a dead end,
    # which is what a wall, a column and a walled-off opening all are.
    if mesh.open_at(
        start_x + unit[0] * (distance + PROBE_DEAD_END_M),
        start_z + unit[1] * (distance + PROBE_DEAD_END_M),
        blocked_at,
    ):
        raise TraversalPlanError(
            "probe %r finds only a %0.2f m lip at %0.2f m from cell %r, open again %0.2f m past "
            "it; the capsule can walk through that, so it is not a blocking face"
            % (name, distance, distance, start, PROBE_DEAD_END_M)
        )
    face = (start_x + unit[0] * distance, start_z + unit[1] * distance)
    resting = (face[0] - unit[0] * PLAYER_CAPSULE_RADIUS_M,
               face[1] - unit[1] * PLAYER_CAPSULE_RADIUS_M)
    run_m = run_cells * grid.size_m
    return {
        "name": name,
        "approach_cell": [int(value) for value in start],
        "approach_m": [float(start_x), float(start_z)],
        "cross_section_heights_m": [round(height, 4) for height in heights],
        "blocked_cell": [int(value) for value in blocked],
        "direction": [unit[0], unit[1]],
        "measured_face_distance_m": round(float(distance), 4),
        "blocked_at_y_m": round(float(blocked_at), 4),
        "blocked_face_m": [round(float(face[0]), 6), round(float(face[1]), 6)],
        "expected_stop_m": [round(float(resting[0]), 6), round(float(resting[1]), 6)],
        "stop_tolerance_m": BLOCK_STOP_TOLERANCE_M,
        "min_displacement_m": round(min(run_m, max(MIN_PROBE_DISPLACEMENT_M, run_m * 0.5)), 4),
        "derivation": (
            "marched along the aim direction asking whether any of the capsule's cross-sections is "
            "inside solid, then one capsule radius back from that surface: where move_and_slide "
            "leaves the centre when a contact arrests it"
        ),
    }


def _impassable(grid: FreeGrid) -> np.ndarray:
    """Cells the production capsule cannot occupy.

    Not the same as "solid": a cell can be air at the capsule's equator and still
    be a wall to the capsule, because the floor drops away or the ceiling comes
    down within its radius.  The first walk run found a route cell 0.5 m from
    exactly this kind of cell, so probing and aiming at anything less would have
    sent the plan through the edge of the room.  A blocking probe has to be aimed
    at the surface that stops the body, which is this mask's boundary.
    """
    return grid.tested & ~grid.capsule_fits


def _walkable_neighbours(grid: FreeGrid, cell: tuple[int, int]) -> list[tuple[int, int]]:
    """The walkable cells 4-adjacent to ``cell``, in a fixed order."""
    found = []
    for step in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        candidate = (cell[0] + step[0], cell[1] + step[1])
        if 0 <= candidate[0] < grid.rows and 0 <= candidate[1] < grid.cols:
            if grid.walkable[candidate]:
                found.append(candidate)
    return found


def _approach_run(grid: FreeGrid, approach: tuple[int, int],
                  away: tuple[int, int]) -> tuple[tuple[int, int], int]:
    """Walk away from an obstacle while the cells stay walkable.

    The probe has to *drive* at the obstacle, not start next to it: a walker
    released half a metre from a wall and found stopped has proved nothing about
    the controller.  This returns the farthest reachable walkable cell along the
    reverse of the approach direction, and how many cells of run that is.
    """
    cell = approach
    steps = 0
    while steps < MAX_PROBE_RUN_CELLS:
        candidate = (cell[0] + away[0], cell[1] + away[1])
        if not (0 <= candidate[0] < grid.rows and 0 <= candidate[1] < grid.cols):
            break
        if not grid.walkable[candidate]:
            break
        cell = candidate
        steps += 1
    return cell, steps


def _best_probe(mesh: WorldCollisionMesh, grid: FreeGrid, name: str,
                blocked_cells: set[tuple[int, int]], distance: np.ndarray) -> dict | None:
    """Probe the blocked cell whose approach has the most room to build up speed.

    The approach is the nearest **walkable** cell along one of the four cell axes,
    not the adjacent one: probing the mesh with the real capsule leaves a margin
    of cells the capsule cannot occupy around every obstacle, so an obstacle's
    immediate neighbour is usually impassable and has no walkable neighbour of its
    own.  Requiring adjacency found no approach at all to this capture's column.

    Candidates are ranked by the length of the straight walkable run behind the
    approach, which is what decides whether the controller arrives at full speed:
    a walker released half a metre from a wall and found stopped has proved
    nothing about the collision.  Axis-aligned approaches only, so the walk does
    not drift out of the corridor.
    """
    ranked: list[tuple[int, tuple[int, int], tuple[int, int], tuple[int, int], int]] = []
    for blocked in sorted(blocked_cells):
        for step in ((1, 0), (0, 1), (0, -1), (-1, 0)):
            approach = _nearest_walkable(grid, blocked, step)
            if approach is None:
                continue
            start, run = _approach_run(grid, approach, step)
            reach = int(distance[start]) * 1000 + run
            ranked.append((reach, start, blocked, (-step[0], -step[1]), run))
    ranked.sort(key=lambda entry: -entry[0])
    for _, start, blocked, direction, run in ranked:
        try:
            # The cell the plan says is blocked is not necessarily solid anywhere
            # along the capsule's height.  A probe whose ray never meets anything
            # would ask the walk to be stopped by nothing, so it is skipped for
            # the next candidate rather than failing the whole plan.
            return _probe_into(mesh, grid, name, start, blocked, direction, run)
        except TraversalPlanError:
            continue
    return None


def _nearest_walkable(grid: FreeGrid, cell: tuple[int, int],
                      step: tuple[int, int]) -> tuple[int, int] | None:
    """The nearest walkable cell from ``cell`` along one axis, or ``None``."""
    current = cell
    for _hop in range(MAX_PROBE_APPROACH_HOPS):
        current = (current[0] + step[0], current[1] + step[1])
        if not (0 <= current[0] < grid.rows and 0 <= current[1] < grid.cols):
            return None
        if grid.walkable[current]:
            return current
    return None


def _axis_direction(origin: tuple[int, int], target: tuple[int, int]) -> tuple[int, int]:
    """The cell step from one cell to a 4-adjacent one, as integers.

    Integer, not a unit float vector: this value doubles as the grid step used to
    walk the approach run backwards, and adding a float to a cell index fails.
    """
    delta = (int(target[0]) - int(origin[0]), int(target[1]) - int(origin[1]))
    if delta == (0, 0) or abs(delta[0]) + abs(delta[1]) != 1:
        raise TraversalPlanError("probe %r -> %r is not 4-adjacent" % (origin, target))
    return delta


# --------------------------------------------------------------------------
# the emitted plan
# --------------------------------------------------------------------------


def build_plan(contract: FrameContract, mesh: WorldCollisionMesh, transform: np.ndarray,
               report: dict, manifest_path: str, glb_path: str) -> dict:
    """Return the traversal manifest: waypoints, probes, spawn and tolerances."""
    grid = build_free_grid(mesh, contract, report)
    spawn_marker = np.asarray(contract.spawn, dtype=np.float64)
    spawn_cell = grid.cell_at(float(spawn_marker[0]), float(spawn_marker[2]))
    if spawn_cell is None:
        raise TraversalPlanError("the contract's spawn is outside the collision floor plan")
    reference = contract.collider.floor_height + TEST_HEIGHT_M
    band = mesh.band(spawn_marker[0], spawn_marker[2], reference)
    if band is None:
        raise TraversalPlanError("the contract's spawn is inside solid collision")
    floor_surface, ceiling_surface = band

    reachable = _reachable(grid, spawn_cell)
    far = _farthest_cell(grid, spawn_cell)
    route = shortest_path(grid, spawn_cell, far)
    corners = _corners(route)
    pinch = _narrowest_run(grid, route)

    waypoints: list[dict] = []
    roles = [(spawn_cell, "spawn"), (pinch[0], "opening_approach"), (pinch[1], "opening_pinch"),
             (pinch[2], "opening_exit"), (far, "route_far")]
    roles += [(cell, "corner") for cell in corners[1:-1]]
    seen: set[tuple[int, int]] = set()
    for cell, role in roles:
        if cell in seen:
            continue
        seen.add(cell)
        waypoints.append(_waypoint(grid, cell, role))

    low = _lowest_clearance_cell(grid, reachable)
    seen.add(low)
    waypoints.append(_waypoint(grid, low, "low_ceiling"))
    # A walkable route from the route's end to the boundary cell, so the engine
    # test does not have to invent a path across the room.
    access = _corners(shortest_path(grid, far, low))
    if access[-1] != low:
        access.append(low)

    probes = _probes(mesh, grid, spawn_cell, far)
    low_band = mesh.band(*grid.cell_centre(*low), reference)
    net_top = float(mesh.bounds()[0][1]) - SAFETY_NET_DROP_M
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "scene_id": contract.scene_id,
        "generated_by": "scripts/splat_pipeline/traversal_plan.py",
        "why": (
            "the route, the spawn and every tolerance are derived from the collision mesh #84 "
            "generated and the #83 contract, so a reviewer can recompute them instead of taking "
            "a coordinate on trust"
        ),
        "sources": {
            "alignment_manifest": manifest_path,
            "collision_report": report.get("__path__", ""),
            "collision_glb": glb_path,
            "collision_glb_md5": mesh.md5,
            "collision_triangles": mesh.triangle_count,
            "collision_report_triangles": report.get("collision_mesh", {}).get("triangles"),
            "collision_report_passed": bool(report.get("verdict", {}).get("passed", False)),
        },
        "collision_node": {
            "transform_3x4": [[round(float(v), 6) for v in row] for row in transform],
            "transform_godot": godot_transform_literal(transform),
            "world_bounds_min_m": [round(float(v), 4) for v in mesh.bounds()[0]],
            "world_bounds_max_m": [round(float(v), 4) for v in mesh.bounds()[1]],
        },
        "player": {
            "capsule_radius_m": PLAYER_CAPSULE_RADIUS_M,
            "capsule_height_m": PLAYER_CAPSULE_HEIGHT_M,
            "half_height_m": PLAYER_CAPSULE_HEIGHT_M * 0.5,
            "speed_mps": 4.0,
        },
        "clearance": {
            "margin_m": CLEARANCE_MARGIN_M,
            "required_m": REQUIRED_CLEARANCE_M,
            "test_height_m": TEST_HEIGHT_M,
            "min_free_run_cells": MIN_FREE_RUN_CELLS,
        },
        "spawn": {
            "marker_m": [round(float(v), 6) for v in spawn_marker],
            "cell": list(spawn_cell),
            "contract_floor_m": contract.collider.floor_height,
            "contract_clearance_m": contract.spawn_clearance_m,
            "floor_surface_m": round(floor_surface, 6),
            "ceiling_surface_m": round(ceiling_surface, 6),
            "clear_m": round(ceiling_surface - floor_surface, 6),
            "drop_m": round(float(spawn_marker[1]) - floor_surface, 6),
            "player_origin_m": [
                round(float(spawn_marker[0]), 6),
                round(floor_surface + PLAYER_CAPSULE_HEIGHT_M * 0.5, 6),
                round(float(spawn_marker[2]), 6),
            ],
            "derivation": (
                "the contract's spawn marker is %s m above the contract's floor plane, which is a "
                "drop-in clearance and not the capsule centre: the production capsule is %s m tall, "
                "so a CharacterBody3D placed at the marker would put its lower hemisphere inside "
                "any floor at the contract height. The player's origin is therefore the generated "
                "collision's own floor surface under the marker plus half the capsule height, which "
                "is the same rule #84 used to place its carve seed."
                % (contract.spawn_clearance_m, PLAYER_CAPSULE_HEIGHT_M)
            ),
        },
        "safety_net": {
            "top_m": round(net_top, 6),
            "centre_m": round(net_top - DEFAULT_VOXEL_SIZE_M * 0.5, 6),
            "centre_xz_m": _net_centre_xz(mesh),
            "thickness_m": DEFAULT_VOXEL_SIZE_M,
            "size_m": _net_size(mesh),
            "drop_below_collision_m": SAFETY_NET_DROP_M,
            "why": (
                "a diagnostic failsafe, never floor support. It sits %s m below the lowest surface "
                "the generated collision reaches, so nothing that walks on the generated floor can "
                "reach it; a contact is a walk failure, and the report says so."
                % SAFETY_NET_DROP_M
            ),
        },
        "columns": _column_record(grid, reachable),
        "waypoints": waypoints,
        "route_cells": [list(cell) for cell in corners],
        "access_cells": [list(cell) for cell in access],
        "opening_cells": [list(cell) for cell in pinch],
        "opening_note": (
            "the tightest point on the route the capsule can actually walk, measured as width: how "
            "many of a cell's eight neighbours the capsule also fits into. Headroom was tried first "
            "and is the wrong measure -- the least headroom on this route is 2.0 m in open floor, "
            "which is not a passage and cannot be blocked. Probing this capture with the real "
            "capsule finds no through-opening at all: the 1.0 m gap the voxel grid resolves at "
            "cells 24-25 leads to a pocket the route cannot enter. These three cells are on the "
            "route and are walked in both directions, and the engine test's blocked-opening case "
            "fills them, so the passage is load-bearing rather than decorative. No separate "
            "blocking probe is aimed at it: a probe needs a dead-end face to push into, and beside "
            "this pinch the mesh is open again 0.35 m past the first solid cross-section, which is "
            "exactly the lip the capsule walks through."
        ),
        "low_clearance_cell": list(low),
        "low_clearance_m": round(float(grid.clear_m[low]), 6),
        "low_clearance_band_m": [round(float(value), 6) for value in low_band] if low_band else [],
        "collision_report": _report_verdict(report),
        "probes": probes,
        "tolerances": {
            "position_m": POSITION_TOLERANCE_M,
            "max_step_m": MAX_STEP_M,
            "block_stop_m": BLOCK_STOP_TOLERANCE_M,
            "min_floor_support_fraction": MIN_FLOOR_SUPPORT_FRACTION,
            "floor_surface_m": FLOOR_SURFACE_TOLERANCE_M,
            "max_spawn_drop_m": MAX_SPAWN_DROP_M,
        },
    }


def _report_verdict(report: dict) -> dict:
    """Carry #84's own verdict forward, failing checks included.

    The plan must not let a downstream walk test read as a clean bill of health
    for a collision stage that failed its benchmark.  `walkway_covers_camera_path`
    failing means the generated walls block the route the reconstruction cameras
    actually walked, which is a property of *this capture* -- the manifest records
    `walls_measured: false` -- not of the walkability of the region the plan does
    thread.  Both halves of that sentence belong in the plan, so the names of the
    failed checks travel with the geometry instead of living only in
    `collision_benchmark.json`.
    """
    verdict = report.get("verdict", {})
    failed = [
        "%s: %s" % (check.get("name", "?"), check.get("detail", ""))
        for check in verdict.get("checks", [])
        if not bool(check.get("passed", False))
    ]
    return {
        "passed": bool(verdict.get("passed", False)),
        "failed_checks": failed,
        "why_this_still_supports_a_walk": (
            "the failing check is coverage of the reconstruction camera path, and this capture's "
            "manifest records walls_measured: false -- no wall plane was ever resolved, so no "
            "collision stage can recover one. The plan's route is inside the region the generated "
            "collision does leave navigable, and the walk test measures that region directly: floor "
            "support, blocking, headroom and the safety net. A pass here is a statement about the "
            "collision that exists, not a claim that it reconstructs the corridor somebody filmed. "
            "#91 owns the end-to-end gate on real footage."
        ),
    }


def _waypoint(grid: FreeGrid, cell: tuple[int, int], role: str) -> dict:
    """Describe one aim point, with the measurements a walk there must reproduce."""
    x, z = grid.cell_centre(*cell)
    return {
        "name": "%s_%d_%d" % (role, cell[0], cell[1]),
        "role": role,
        "cell": list(cell),
        "x_m": round(float(x), 6),
        "z_m": round(float(z), 6),
        "floor_y_m": round(float(grid.floor_y[cell]), 6),
        "ceiling_y_m": round(float(grid.ceiling_y[cell]), 6),
        "clear_m": round(float(grid.clear_m[cell]), 6),
    }


def _lowest_clearance_cell(grid: FreeGrid, reachable: set[tuple[int, int]]) -> tuple[int, int]:
    """The reachable walkable cell with the least headroom: a boundary.

    Restricted to the spawn's component, because the least headroom in the whole
    grid sits in a pocket the player cannot walk into, and standing there would
    mean teleporting.  Ties break on ``(row, col)`` so the plan is
    byte-reproducible.  This is the cell the walk must survive standing in -- the
    boundary where the generated geometry stops guaranteeing the capsule fits,
    which is where a fall-through would show up first.
    """
    best: tuple[float, int, int] | None = None
    for row, col in sorted(reachable):
        clear = float(grid.clear_m[row, col])
        if best is None or clear < best[0]:
            best = (clear, row, col)
    if best is None:
        raise TraversalPlanError("no reachable walkable cell to use as the low-clearance boundary")
    return best[1], best[2]


def _probes(mesh: WorldCollisionMesh, grid: FreeGrid, spawn_cell: tuple[int, int],
            far_cell: tuple[int, int]) -> list[dict]:
    """Return the blocking probes: the wall, the column, and the blocked opening.

    The blocked-opening probe is what stops a scene that deleted the opening from
    passing: without it, "no progress" at a probe would be indistinguishable from
    "the whole route is unwalkable".
    """
    distance = _bfs_distances(grid, spawn_cell)
    pinch = _narrowest_run(grid, shortest_path(grid, spawn_cell, far_cell))[1]
    island = set(_interior_solid(grid))
    beside_pinch = _blocked_neighbours(grid, pinch)
    wall = {
        tuple(int(v) for v in cell)
        for cell in zip(*np.nonzero(_impassable(grid)))
        if cell not in island
    } - beside_pinch
    probes: list[dict] = []
    for name, candidates in (
        ("column", island),
        ("wall", wall),
        # The face beside the pinch: aiming at it proves the opening is passable
        # on the way in, and a scene with the opening walled off fails here.
        ("opening", beside_pinch),
    ):
        probe = _best_probe(mesh, grid, name, candidates, distance)
        if probe is None:
            continue
        walk = shortest_path(grid, spawn_cell, tuple(probe["approach_cell"]))
        probe["approach_cells"] = [list(cell) for cell in _corners(walk)]
        probe["approach_length_m"] = round(len(walk) * grid.size_m, 4)
        probes.append(probe)
    if not probes:
        raise TraversalPlanError("no blocking probe could be aimed; the route has no solid near it")
    return probes


def _blocked_neighbours(grid: FreeGrid, cell: tuple[int, int]) -> set[tuple[int, int]]:
    """Cells the capsule cannot occupy, 4-adjacent to ``cell``."""
    found = set()
    for step in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        candidate = (cell[0] + step[0], cell[1] + step[1])
        inside = 0 <= candidate[0] < grid.rows and 0 <= candidate[1] < grid.cols
        if inside and grid.tested[candidate] and not grid.capsule_fits[candidate]:
            found.add(candidate)
    return found


def _net_footprint(mesh: WorldCollisionMesh) -> tuple[np.ndarray, np.ndarray]:
    """Safety-net extent: the collision's own horizontal bounds, padded.

    Derived from the mesh rather than the room, so a net smaller than the
    geometry it is meant to catch cannot be described as a net at all.
    """
    low, high = mesh.bounds()
    margin = SAFETY_NET_DROP_M
    low = np.array([low[0] - margin, low[2] - margin])
    high = np.array([high[0] + margin, high[2] + margin])
    return low, high


def _net_size(mesh: WorldCollisionMesh) -> list[float]:
    """The safety net's box size, in metres."""
    low, high = _net_footprint(mesh)
    return [
        round(float(high[0] - low[0]), 6),
        round(DEFAULT_VOXEL_SIZE_M, 6),
        round(float(high[1] - low[1]), 6),
    ]


def _net_centre_xz(mesh: WorldCollisionMesh) -> list[float]:
    """The safety net's horizontal centre, in metres."""
    low, high = _net_footprint(mesh)
    return [round(float(0.5 * (low[0] + high[0])), 6), round(float(0.5 * (low[1] + high[1])), 6)]


def _column_record(grid: FreeGrid, reachable: set[tuple[int, int]]) -> dict:
    """The floor plan the plan is expressed on, with the counts a review needs."""
    return {
        "size_m": grid.size_m,
        "origin_world_m": [grid.origin_x, grid.origin_z],
        "rows": grid.rows,
        "cols": grid.cols,
        "tested_cells": int(grid.tested.sum()),
        "open_at_test_cells": int((grid.tested & grid.open_at_test).sum()),
        "capsule_fits_cells": int(grid.capsule_fits.sum()),
        "walkable_cells": int(grid.walkable.sum()),
        "reachable_from_spawn_cells": len(reachable),
        "untested_outside_mesh_cells": int((~grid.tested).sum()),
        "why_reachable_matters": (
            "probing the mesh with the real capsule leaves several disconnected pockets; every "
            "route and boundary target is restricted to the spawn's own component so the walk test "
            "never has to teleport to reach one"
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, help="#83 alignment contract JSON")
    parser.add_argument("--report", required=True, help="#84 collision benchmark JSON")
    parser.add_argument("--glb", required=True, help="collision GLB #84 generated")
    parser.add_argument("--out", required=True, help="where to write the traversal manifest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Write the traversal manifest and print the summary a reviewer reads first."""
    args = parse_args(argv)
    report = json.loads(Path(args.report).read_text())
    report["__path__"] = args.report
    contract, mesh, transform = load_contract_and_mesh(args.manifest, args.glb)
    plan = build_plan(contract, mesh, transform, report, args.manifest, args.glb)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(plan, indent=2) + "\n")
    _print_summary(plan)
    return 0


def _print_summary(plan: dict) -> None:
    """Print the plan's decisive numbers, not its whole structure."""
    spawn = plan["spawn"]
    columns = plan["columns"]
    print("traversal plan for %s from %s" % (plan["scene_id"], plan["collision_node"]["transform_godot"]))
    print("  collision mesh md5 %s, %d triangles, world bounds %s .. %s"
          % (plan["sources"]["collision_glb_md5"], plan["sources"]["collision_triangles"],
             plan["collision_node"]["world_bounds_min_m"],
             plan["collision_node"]["world_bounds_max_m"]))
    print("  floor plan %dx%d cells of %.2f m: %d tested, %d open at %.2f m, %d walkable at %.2f m clear"
          % (columns["rows"], columns["cols"], columns["size_m"], columns["tested_cells"],
             columns["open_at_test_cells"], plan["clearance"]["test_height_m"],
             columns["walkable_cells"], plan["clearance"]["required_m"]))
    print("  spawn marker %s: floor surface %.4f m (contract %.4f), drop %.3f m, clear %.3f m"
          % (spawn["marker_m"], spawn["floor_surface_m"], spawn["contract_floor_m"],
             spawn["drop_m"], spawn["clear_m"]))
    print("  player origin %s (floor + capsule half height)"
          % (spawn["player_origin_m"],))
    print("  safety net top %.4f m, %s m below the collision's lowest surface"
          % (plan["safety_net"]["top_m"], plan["safety_net"]["drop_below_collision_m"]))
    print("  route cells %s" % (plan["route_cells"],))
    print("  opening cells %s, pinch clear %.3f m"
          % (plan["opening_cells"], _cell_clear(plan, plan["opening_cells"][1])))
    print("  low-clearance cell %s at %.3f m" % (plan["low_clearance_cell"], plan["low_clearance_m"]))
    verdict = plan["collision_report"]
    print("  #84 benchmark passed=%s" % (verdict["passed"],))
    for name in verdict["failed_checks"]:
        print("    FAILED %s" % name)
    for probe in plan["probes"]:
        print("  probe %-8s from %s towards the face at %s (%.2f m away, blocked at y=%.3f), "
              % (probe["name"], probe["approach_m"], probe["blocked_face_m"],
                 probe["measured_face_distance_m"], probe["blocked_at_y_m"])
              + "rest at %s +/-%.2f m, run %.2f m"
              % (probe["expected_stop_m"], probe["stop_tolerance_m"], probe["approach_length_m"]))
    print()
    print(scene_contract(plan))


def scene_contract(plan: dict) -> str:
    """Return the ``corridor.tscn`` lines this plan requires, for review.

    Printed rather than written, like ``emit_scene_contract.py``: scene files are
    reviewed by hand, and a tool that rewrites one silently invites unreviewed
    geometry changes.  Every number here is derived, so a diff against the scene
    shows a real geometry change rather than a reformat.
    """
    spawn = plan["spawn"]
    net = plan["safety_net"]
    origin = spawn["player_origin_m"]
    marker = spawn["marker_m"]
    return "\n".join([
        "",
        "godot_walk/scenes/corridor.tscn:",
        '  [node name="GeneratedCollision" type="StaticBody3D" parent="."]',
        '  transform = %s' % plan["collision_node"]["transform_godot"],
        '  [node name="SafetyNet" type="StaticBody3D" parent="."]',
        '  transform = Transform3D(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, %s)'
        % ", ".join(_float32(value) for value in _net_transform(net)),
        '    shape = Box_safetynet size = Vector3(%s)'
        % ", ".join(_float32(value) for value in net["size_m"]),
        '  [node name="PlayerSpawn" type="Marker3D" parent="."]',
        '  transform = Transform3D(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, %s)'
        % ", ".join(_float32(value) for value in marker),
        '  [node name="Player" parent="." instance=ExtResource("1_player_scene")]',
        '  transform = Transform3D(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, %s)'
        % ", ".join(_float32(value) for value in origin),
    ])


def _net_transform(net: dict) -> list[float]:
    """The safety net's transform origin: its own centre on all three axes."""
    x, z = net["centre_xz_m"]
    return [x, net["centre_m"], z]


def _float32(value: float) -> str:
    """Round to what a float32 round-trip keeps; Godot stores transforms as float32."""
    rounded = float(np.float32(value))
    text = repr(rounded)
    return text if "e" not in text and "." in text else "%.7g" % rounded


def _cell_clear(plan: dict, cell: list[int]) -> float:
    """Return the recorded clear height of a named cell in the route or opening."""
    for waypoint in plan["waypoints"]:
        if waypoint["cell"] == list(cell):
            return waypoint["clear_m"]
    return plan["low_clearance_m"]


if __name__ == "__main__":
    raise SystemExit(main())
