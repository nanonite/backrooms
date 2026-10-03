#!/usr/bin/env python3
"""Score generated collision geometry against the acceptance criteria.

Each check is a separate measurement with a number attached, because the failure
this task exists to prevent is a collision that *looks* right.  A watertight
mesh with correct winding can still place a wall where the person walked, and a
room-shaped box can still have no floor under the route; neither shows up in a
file listing.

The checks fall into two families, and the distinction matters:

* **Self-consistency** -- watertight, consistent winding, within budget.  A mesh
  can satisfy all of these and still describe a room that was never observed.
* **Agreement with the reconstruction and the contract** -- floor support along
  the camera path, walls where the splat shows surface, open space where it does
  not, a carve capsule that fits, a navigable region inside the observed room.
  These need the splat and the #83 contract, and they are the ones that fail.

Every threshold here is a named constant with its reason recorded, so a reader
can see what was demanded rather than inferring it from a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from collision_params import CollisionSettings, world_to_engine_frame
from glb_mesh import TriangleMesh
from splat_columns import ColumnGrid
from splat_frame import FrameContract
from splat_transform_cli import ToolRun
from voxel_octree import VoxelOctree

#: Fraction of the reconstruction's camera positions that must have collision
#: floor directly beneath them.  Below this the route is unsupported and a player
#: falls; the camera walked it, so any failure here is real.
MIN_FLOOR_SUPPORT = 0.98

#: Fraction of camera positions that must stand in *navigable* space at chest
#: height.  Floor support alone is not traversability: this is the check that
#: catches a wall drawn where somebody walked.
MIN_CAMERA_TRAVERSABLE = 0.90

#: Height above the floor at which a column is tested for obstruction.  Chest, not
#: eye: the eye sits above furniture a body passes under, and testing at eye
#: height reports head-height clutter as walls.
OBSTRUCTION_TEST_HEIGHT_M = 1.00

#: Offset below a camera position at which floor support is tested, in metres.
#: One voxel above the contract's floor plane: the collision's floor surface
#: sits at most half a voxel below the measured sheet.
FLOOR_PROBE_HEIGHT_M = 0.05

#: Fraction of splat-obstructed columns that must end up solid.  A wall the
#: reconstruction saw but the collision ignored is a wall a player walks through.
MIN_WALL_RECALL = 0.80

#: Fraction of collision-navigable columns that must be columns the splat saw as
#: open.  The inverse of the above, and the one that catches a collision sealing
#: space in which nothing was ever observed.
MIN_OPENING_PRECISION = 0.60

#: Navigable volume as a fraction of the contract's room volume.  Below the floor
#: the room filled in; above the ceiling the shell leaked and "navigable" means
#: the whole unobserved exterior.
MIN_NAVIGABLE_FRACTION = 0.02
MAX_NAVIGABLE_FRACTION = 0.90

#: Allowed slack between a measured clear height and the contract's, in metres.
#: The carve re-inflates the navigable region by its own capsule, so a region
#: measured just under the ceiling is expected; anything beyond the slack is a
#: leak, and a generous clear height at the spawn means the shell never closed.
CLEAR_HEIGHT_SLACK_M = 0.30

#: Mesh topology thresholds, as exact counts rather than fractions: a closed
#: surface has zero boundary edges and zero edges shared by three faces.
MAX_BOUNDARY_EDGES = 0
MAX_NON_MANIFOLD_EDGES = 0

#: Fraction of triangles that must face the navigable side, measured against the
#: voxel field.  The mesh ships without vertex normals, so this is a winding
#: check; it is what tells a physics engine which side the player is on.
MIN_NORMAL_AGREEMENT = 0.80


@dataclass(frozen=True)
class Check:
    """One acceptance criterion, its verdict, the number behind it and why."""

    name: str
    passed: bool
    detail: str
    metrics: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        record = {"name": self.name, "passed": self.passed, "detail": self.detail}
        if self.metrics:
            record["metrics"] = self.metrics
        return record


@dataclass(frozen=True)
class CollisionVerdict:
    """The full set of checks, plus the per-column collision solidity they used.

    ``columns_solid`` is kept rather than recomputed on demand because it is the
    per-column answer #85 needs to place waypoints, and recomputing it would mean
    a second scan that could disagree with the one the verdict was built from.
    """

    scene_id: str
    checks: tuple[Check, ...]
    columns_solid: np.ndarray
    column_origin_world_m: tuple[float, float]
    column_size_m: float

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_json(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "passed": self.passed,
            "checks": [check.to_json() for check in self.checks],
        }


def validate(
    contract: FrameContract,
    settings: CollisionSettings,
    voxel: VoxelOctree,
    mesh: TriangleMesh,
    run: ToolRun,
    columns: ColumnGrid,
    camera_positions=None,
) -> CollisionVerdict:
    """Run every check and return the verdict.

    ``camera_positions`` are the reconstruction cameras in Godot world metres.
    Without them the camera-path checks report "not measured" and are counted as
    failures, because collision that has no evidence of covering the route anyone
    actually walked has not been validated.
    """
    probe = _Probe(contract, settings, voxel, columns)
    checks = (
        _check_stages(run),
        _check_room_not_filled(probe),
        _check_floor_support(probe, camera_positions),
        _check_walkway_covers_camera_path(probe, camera_positions),
        _check_walls_block(probe),
        _check_openings_preserved(probe),
        _check_capsule_clearance(probe),
        _check_mesh_topology(mesh),
        _check_mesh_normals(probe, mesh),
        _check_budget(settings, run, mesh),
    )
    return CollisionVerdict(
        scene_id=contract.scene_id,
        checks=checks,
        columns_solid=probe.column_solid,
        column_origin_world_m=columns.origin,
        column_size_m=columns.size_m,
    )


class _Probe:
    """Cached measurements against the voxel field, in the contract's world metres.

    Every expensive scan happens once here so the checks stay short and, more
    importantly, so they all agree: a verdict assembled from three independent
    scans of the same field could disagree with itself.
    """

    def __init__(
        self,
        contract: FrameContract,
        settings: CollisionSettings,
        voxel: VoxelOctree,
        columns: ColumnGrid,
    ) -> None:
        self.contract = contract
        self.settings = settings
        self.voxel = voxel
        self.columns = columns
        self.resolution = float(voxel.resolution)
        self.floor_level = float(contract.collider.floor_height)
        self.occupancy = voxel.occupancy(voxel.header.grid_min, voxel.header.grid_max)
        self.empty = np.argwhere(~self.occupancy)
        self.navigable_m3 = len(self.empty) * self.resolution ** 3
        self.navigable_low, self.navigable_high = self._navigable_bounds()
        self.column_solid = self._column_solidity()

    def solid_at(self, point) -> bool:
        """Whether the collision is solid at a Godot world point."""
        return self.voxel.is_solid(world_to_engine_frame(point, self.contract))

    def _navigable_bounds(self):
        """Return the navigable region's engine-frame bounds.

        An empty navigable set has no bounds; the callers treat a zero volume as
        a failure, so returning the grid origin keeps them from having to special
        case a collapse that ``room_not_filled`` already reports.
        """
        origin = np.asarray(self.voxel.header.grid_min)
        if len(self.empty) == 0:
            return origin.copy(), origin.copy()
        return (
            origin + self.empty.min(axis=0) * self.resolution,
            origin + (self.empty.max(axis=0) + 1) * self.resolution,
        )

    def _column_solidity(self) -> np.ndarray:
        """Return, per floor-plan column, whether the collision is solid at chest height."""
        cells = np.argwhere(np.ones(self.columns.shape, dtype=bool))
        points = self.columns.cell_centre(cells)
        points[:, 1] = self.floor_level + OBSTRUCTION_TEST_HEIGHT_M
        solid = np.array([self.solid_at(point) for point in points])
        return solid.reshape(self.columns.shape)


def _check_stages(run: ToolRun) -> Check:
    """Fail when a navigation stage silently did nothing.

    Both stages leave a usable-looking file behind when they bail out: an unsealed
    shell skips the exterior fill and carves a pocket, which exports a perfectly
    valid collision mesh for a room the size of a fist.
    """
    skipped = []
    if run.exterior_fill_skipped:
        skipped.append("exterior fill")
    if run.carve_skipped:
        skipped.append("carve")
    metrics = {
        "exterior_fill_skipped": run.exterior_fill_skipped,
        "carve_skipped": run.carve_skipped,
        "seed_was_unoccupied": run.seed_was_unoccupied,
    }
    if skipped:
        return Check(
            "stages_applied",
            False,
            "splat-transform skipped %s, so the mesh was not built from a sealed shell"
            % " and ".join(skipped),
            metrics,
        )
    return Check("stages_applied", True, "exterior fill and carve both ran", metrics)


def _check_room_not_filled(probe: _Probe) -> Check:
    """Require a navigable volume that is neither absent nor unbounded."""
    contract = probe.contract
    low = np.asarray(contract.collider.min_corner)
    high = np.asarray(contract.collider.max_corner)
    room_m3 = float(np.prod(np.maximum(high - low, 1e-9)))
    fraction = probe.navigable_m3 / room_m3
    span = float(probe.navigable_high[2] - probe.navigable_low[2])
    clear_height = float(contract.collider.ceiling_height - contract.collider.floor_height)
    metrics = {
        "navigable_m3": round(probe.navigable_m3, 3),
        "room_m3": round(room_m3, 3),
        "navigable_fraction": round(fraction, 4),
        "navigable_clear_height_m": round(span, 4),
        "contract_clear_height_m": round(clear_height, 4),
    }
    if fraction < MIN_NAVIGABLE_FRACTION:
        return Check("room_not_filled", False, "the navigable volume collapsed (%.1f%% of the room)" % (100 * fraction), metrics)
    if fraction > MAX_NAVIGABLE_FRACTION:
        return Check(
            "room_not_filled",
            False,
            "the navigable volume is %.1f%% of the room; the shell leaked and unobserved space was "
            "declared walkable" % (100 * fraction),
            metrics,
        )
    return Check("room_not_filled", True, "navigable volume is %.1f%% of the observed room" % (100 * fraction), metrics)


def _check_floor_support(probe: _Probe, camera_positions) -> Check:
    """Require collision floor under the reconstruction's camera path."""
    if camera_positions is None or len(camera_positions) == 0:
        return Check(
            "floor_supported",
            False,
            "no camera positions were supplied, so floor support along the walked route is unmeasured",
            {"cameras": 0},
        )
    positions = np.asarray(camera_positions, dtype=np.float64)
    probes = positions.copy()
    probes[:, 1] = probe.floor_level + FLOOR_PROBE_HEIGHT_M
    supported = np.array([probe.solid_at(point) for point in probes])
    metrics = {
        "cameras": int(len(positions)),
        "floor_supported": int(supported.sum()),
        "floor_support_fraction": round(float(supported.mean()), 4),
    }
    if supported.mean() < MIN_FLOOR_SUPPORT:
        return Check(
            "floor_supported",
            False,
            "collision floor is present under %d of %d camera positions (%.1f%%, need %.0f%%)"
            % (int(supported.sum()), len(positions), 100 * supported.mean(), 100 * MIN_FLOOR_SUPPORT),
            metrics,
        )
    return Check("floor_supported", True, "collision floor is present under all %d camera positions" % len(positions), metrics)


def _check_walkway_covers_camera_path(probe: _Probe, camera_positions) -> Check:
    """Require the route the camera walked to be navigable, not merely floored."""
    if camera_positions is None or len(camera_positions) == 0:
        return Check(
            "walkway_covers_camera_path",
            False,
            "no camera positions were supplied, so traversal of the walked route is unmeasured",
            {"cameras": 0},
        )
    positions = np.asarray(camera_positions, dtype=np.float64).copy()
    positions[:, 1] = probe.floor_level + OBSTRUCTION_TEST_HEIGHT_M
    free = np.array([not probe.solid_at(point) for point in positions])
    metrics = {
        "cameras": int(len(positions)),
        "navigable": int(free.sum()),
        "traversable_fraction": round(float(free.mean()), 4),
        "test_height_m": OBSTRUCTION_TEST_HEIGHT_M,
    }
    if free.mean() < MIN_CAMERA_TRAVERSABLE:
        return Check(
            "walkway_covers_camera_path",
            False,
            "%d of %d camera positions are inside solid collision at %.2f m above the floor "
            "(%.1f%% traversable, need %.0f%%): the generated walls block the route that was "
            "actually walked" % (int((~free).sum()), len(positions), OBSTRUCTION_TEST_HEIGHT_M,
                                100 * free.mean(), 100 * MIN_CAMERA_TRAVERSABLE),
            metrics,
        )
    return Check(
        "walkway_covers_camera_path",
        True,
        "%.1f%% of camera positions are in navigable space" % (100 * free.mean()),
        metrics,
    )


def _check_walls_block(probe: _Probe) -> Check:
    """Require the columns the splat saw surface in to be solid."""
    obstructed = probe.columns.has_floor & probe.columns.obstructed
    total = int(obstructed.sum())
    if total == 0:
        return Check(
            "walls_block",
            False,
            "no column carries obstruction-band splats, so there is no observed wall anywhere to block",
            {"obstructed_columns": 0},
        )
    solid = int((obstructed & probe.column_solid).sum())
    recall = solid / total
    metrics = {"obstructed_columns": total, "solid": solid, "recall": round(recall, 4)}
    return Check(
        "walls_block",
        recall >= MIN_WALL_RECALL,
        "%d of %d splat-obstructed columns are solid in the collision (%.1f%%, need %.0f%%)"
        % (solid, total, 100 * recall, 100 * MIN_WALL_RECALL),
        metrics,
    )


def _check_openings_preserved(probe: _Probe) -> Check:
    """Require navigable columns to be columns the splat saw as open."""
    open_columns = probe.columns.has_floor & ~probe.columns.obstructed
    navigable = ~probe.column_solid
    open_total = int(open_columns.sum())
    navigable_total = int(navigable.sum())
    if open_total == 0 or navigable_total == 0:
        return Check(
            "openings_preserved",
            False,
            "the plan has %d splat-open and %d navigable columns; nothing can be compared"
            % (open_total, navigable_total),
            {"open_columns": open_total, "navigable_columns": navigable_total},
        )
    both = int((open_columns & navigable).sum())
    precision = both / navigable_total
    recall = both / open_total
    metrics = {
        "open_columns": open_total,
        "navigable_columns": navigable_total,
        "both": both,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }
    return Check(
        "openings_preserved",
        precision >= MIN_OPENING_PRECISION,
        "%d of %d navigable columns are columns the splat saw as open (%.1f%% precision, need "
        "%.0f%%); %.1f%% of splat-open columns survived" % (both, navigable_total, 100 * precision,
                                                             100 * MIN_OPENING_PRECISION, 100 * recall),
        metrics,
    )


def _check_capsule_clearance(probe: _Probe) -> Check:
    """Require the production player capsule, plus margin, to fit at the spawn.

    Bounded on both sides.  Below the capsule height is a player who does not fit;
    above the contract's clear height plus slack is a *leak* -- the spawn stands
    somewhere the shell never closed, and a generous "clear height" there is the
    opposite of good news.
    """
    settings = probe.settings
    spawn = np.asarray(probe.contract.spawn, dtype=np.float64)
    centre = np.array([spawn[0], probe.floor_level + 0.5 * settings.capsule_height_m, spawn[2]])
    samples = _capsule_surface(settings.capsule_radius_m, settings.capsule_height_m)
    blocked = sum(1 for offset in samples if probe.solid_at(centre + offset))
    clearance = _clear_height(probe, spawn)
    clear_height = float(probe.contract.collider.ceiling_height - probe.contract.collider.floor_height)
    ceiling_limit = clear_height - (spawn[1] - probe.floor_level) + CLEAR_HEIGHT_SLACK_M
    metrics = {
        "capsule_radius_m": settings.capsule_radius_m,
        "capsule_height_m": settings.capsule_height_m,
        "samples": int(len(samples)),
        "blocked": int(blocked),
        "clear_height_above_spawn_m": round(clearance, 4),
        "clear_height_limit_m": round(ceiling_limit, 4),
    }
    problems = []
    if blocked:
        problems.append("%d of %d capsule surface samples are solid at the spawn" % (blocked, len(samples)))
    if clearance < settings.capsule_height_m:
        problems.append("only %.3f m of clear height, need %.3f m" % (clearance, settings.capsule_height_m))
    if clearance > ceiling_limit:
        problems.append(
            "%.3f m of clear height exceeds the room's %.3f m plus slack: the shell never closed above "
            "the spawn" % (clearance, clear_height)
        )
    return Check(
        "capsule_clearance",
        not problems,
        "; ".join(problems) if problems else "the carve capsule fits at the spawn with %.3f m of clear "
        "height above it" % clearance,
        metrics,
    )


def _check_mesh_topology(mesh: TriangleMesh) -> Check:
    """Require a closed, non-degenerate surface."""
    edges = mesh.edge_manifoldness()
    areas = _triangle_areas(mesh)
    degenerate = int((areas <= 0.0).sum())
    metrics = dict(edges, degenerate_triangles=degenerate, triangles=mesh.triangle_count)
    passed = edges["boundary"] <= MAX_BOUNDARY_EDGES and edges["non_manifold"] <= MAX_NON_MANIFOLD_EDGES
    return Check(
        "mesh_watertight",
        passed,
        "%d boundary edges, %d edges shared by three or more faces, %d degenerate triangles"
        % (edges["boundary"], edges["non_manifold"], degenerate),
        metrics,
    )


def _check_mesh_normals(probe: _Probe, mesh: TriangleMesh) -> Check:
    """Require the winding to face the navigable side, checked against the voxels.

    A collision surface's useful normal points *out of the solid and into the
    space the player occupies* -- that is the side a capsule approaching the wall
    is on, and the side an engine needs to decide which face it crossed.  So the
    test is: free just ahead of the triangle along its normal, solid just behind.
    Getting this backwards reports a correct mesh as inverted, which is why the
    polarity is stated rather than inferred.
    """
    centroid = mesh.triangles().mean(axis=1)
    normal = mesh.face_normals()
    offset = 0.75 * probe.resolution
    agree = 0
    tested = 0
    for centre, direction in zip(centroid, normal):
        if not np.isfinite(direction).all():
            continue
        tested += 1
        if not probe.voxel.is_solid(centre + direction * offset) and probe.voxel.is_solid(
            centre - direction * offset
        ):
            agree += 1
    fraction = agree / max(tested, 1)
    metrics = {
        "triangles": tested,
        "facing_navigable": agree,
        "fraction": round(fraction, 4),
        "signed_volume_m3": round(mesh.signed_volume(), 4),
    }
    return Check(
        "mesh_normals_face_walkable",
        fraction >= MIN_NORMAL_AGREEMENT,
        "%d of %d triangles face out of the solid into navigable space (%.1f%%, need %.0f%%); the "
        "mesh carries no vertex normals, so this is a winding check"
        % (agree, tested, 100 * fraction, 100 * MIN_NORMAL_AGREEMENT),
        metrics,
    )


def _check_budget(settings: CollisionSettings, run: ToolRun, mesh: TriangleMesh) -> Check:
    """Require the run to stay inside its declared triangle and memory budgets."""
    breaches = []
    if mesh.triangle_count > settings.max_triangles:
        breaches.append("%d triangles over the %d budget" % (mesh.triangle_count, settings.max_triangles))
    if run.peak_cpu_bytes > settings.max_peak_cpu_bytes:
        breaches.append("%.2f GiB CPU peak over the %.2f GiB budget" % (
            run.peak_cpu_bytes / 1024 ** 3, settings.max_peak_cpu_bytes / 1024 ** 3))
    if run.peak_gpu_bytes > settings.max_peak_gpu_bytes:
        breaches.append("%.2f GiB GPU peak over the %.2f GiB budget" % (
            run.peak_gpu_bytes / 1024 ** 3, settings.max_peak_gpu_bytes / 1024 ** 3))
    metrics = {
        "triangles": mesh.triangle_count,
        "max_triangles": settings.max_triangles,
        "peak_cpu_bytes": run.peak_cpu_bytes,
        "peak_gpu_bytes": run.peak_gpu_bytes,
        "elapsed_s": round(run.elapsed_s, 3),
    }
    return Check(
        "within_budget",
        not breaches,
        "; ".join(breaches) if breaches else "triangle, CPU-memory and GPU-memory budgets all met",
        metrics,
    )


def _capsule_surface(radius: float, height: float, rings: int = 5, segments: int = 12) -> np.ndarray:
    """Sample points on a capsule's surface, excluding the poles.

    Poles are omitted because the carve's capsule is 2D-lifted: a sample exactly
    at a cap can sit a hair outside the region the carve guarantees, and reporting
    that as a clearance failure would be measuring the sampler.
    """
    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    rows = [
        [
            radius * np.sin(np.pi * ring / rings) * np.cos(angle),
            -0.5 * height + height * ring / rings,
            radius * np.sin(np.pi * ring / rings) * np.sin(angle),
        ]
        for ring in range(1, rings)
        for angle in angles
    ]
    return np.asarray(rows)


def _clear_height(probe: _Probe, column_point, limit_m: float = 8.0) -> float:
    """Return how far collision-free space extends above a world point.

    The height is accumulated into the probe point rather than added to it in
    place: ``point = np.array(column_point)`` inside the loop rebuilds the point
    from the original every iteration, so ``point[1] += step`` would probe the
    same voxel 160 times and report an 8 m ceiling for every column.
    """
    base = np.asarray(column_point, dtype=np.float64)
    steps = int(limit_m / probe.resolution)
    for step in range(1, steps + 1):
        point = base.copy()
        point[1] += step * probe.resolution
        if probe.solid_at(point):
            return round((step - 1) * probe.resolution, 6)
    return round(limit_m, 6)


def _triangle_areas(mesh: TriangleMesh) -> np.ndarray:
    """Return each triangle's area, in square units of the mesh's own frame."""
    corners = mesh.triangles()
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return 0.5 * np.linalg.norm(cross, axis=1)