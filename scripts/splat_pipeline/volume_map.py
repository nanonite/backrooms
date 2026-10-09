#!/usr/bin/env python3
"""Map the calibrated volumes of a walkable splat scene and score the envelope.

The bounded-world bar for the synthetic Backrooms PoC (#101) is: the player
spawns near the middle of a *supported* region, can walk a meaningful loop
inside it, and every reachable heading shows floor, walls and ceiling -- not
black gaps and not Gaussian debris.  This script measures the four volumes that
decide whether a scene meets that bar, then scores the walkable envelope the
generated collision actually leaves the player.

Volumes, all in Godot world metres:

* ``observed``    -- the contract's measured room (the calibrated observed
  volume).  For this synthetic asset its horizontal extents are observation
  bounds, not measured wall planes (``walls_measured: false``).
* ``cameras``     -- the 192 registered capture cameras mapped through the
  contract.  The only region the footage ever saw.
* ``collision``   -- the generated collision mesh #84 wrote.  The only region
  the player can physically be.
* ``walkable``    -- the spawn-connected component of the collision's free
  grid: the region the player can actually reach on foot.  This is the
  experience boundary the PoC must enclose visually.

The enclosure score asks, for every walkable cell, whether the *splat* puts
support on the floor below, the ceiling above and the four walls around it.
A cell the collision calls navigable but the splat leaves open is a black gap
waiting to happen in the player's view, so the score is per-cell and reported
as a percentage -- the same shape as #91's camera-path coverage, so the two can
be reconciled directly.

Usage::

    python3 scripts/splat_pipeline/volume_map.py \
        --manifest  godot_walk/assets/corridor_splat/alignment_manifest.json \
        --report    scripts/splat_pipeline/collision_benchmark.json \
        --glb       godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb \
        --ply       godot_walk/assets/corridor_splat/corridor.ply \
        --clean-ply godot_walk/assets/corridor_splat/corridor_clean.ply \
        --out       godot_walk/evidence/<run>/volume_map.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collision_mesh_world import load_world_mesh
from collision_params import contract_from_path
from glb_mesh import read_glb
from splat_frame import FrameContract
from traversal_plan import (
    PLAYER_CAPSULE_HEIGHT_M,
    REQUIRED_CLEARANCE_M,
    TEST_HEIGHT_M,
    FreeGrid,
    _capsule_fits,
    _cell_centre,
    _long_runs,
    build_free_grid,
)

#: How far outside a cell's own footprint wall support may sit and still count
#: as "the wall is there".  A wall is a surface, not a point: the splat that
#: builds it is a few centimetres thick and the cell is 0.25 m, so support up to
#: one cell away is the same wall, not a gap.
WALL_SUPPORT_RADIUS_M = 0.35

#: How far above the floor a splat may sit and still be floor rather than wall.
#: The corridor's clear height is ~2.15 m; a fifth of it separates "the floor
#: continues" from "this is a wall".
FLOOR_BAND_M = 0.45

#: How far below the ceiling a splat may sit and still be ceiling.
CEILING_BAND_M = 0.45

#: Minimum splats for a direction to count as supported.  One splat is a
#: floater, not a surface; this is deliberately small because the score is
#: about *presence* of support, and the screenshots carry the judgement of
#: whether it reads as a surface.
MIN_SUPPORT_SPLATS = 3


def read_ply_positions(path: str | Path) -> np.ndarray:
    """Read just the vertex positions of a binary-little-endian 3DGS PLY."""
    with open(path, "rb") as handle:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += handle.readline()
        text = header.decode("ascii", "replace")
        count = None
        properties: list[str] = []
        in_vertex = False
        for line in text.splitlines():
            parts = line.split()
            if parts[:2] == ["element", "vertex"]:
                count = int(parts[2])
                in_vertex = True
            elif parts and parts[0] == "element":
                in_vertex = False
            elif in_vertex and parts[:1] == ["property"]:
                if parts[1] != "list":
                    properties.append(parts[2])
        if count is None:
            raise ValueError("no vertex element in %s" % path)
        if properties[:3] != ["x", "y", "z"]:
            raise ValueError("unexpected PLY property order: %r" % properties[:3])
        # Every property the header declares before the first non-vertex
        # element is a scalar float32 in a nerfstudio PLY; read the whole block
        # and keep the first three columns.
        dtype = np.dtype([(name, "<f4") for name in properties])
        data = np.fromfile(handle, dtype=dtype, count=count)
    return np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)


def ply_to_world(points_ply: np.ndarray, contract: FrameContract) -> np.ndarray:
    """Map raw PLY coordinates to Godot world metres (the #83 contract)."""
    mapper = contract.ply_to_world
    rotation = mapper.rotation()
    origin = np.asarray(mapper.origin_ply_units, dtype=np.float64)
    return (points_ply - origin) @ rotation.T * mapper.metres_per_unit


def reachable_component(grid: FreeGrid, start: tuple[int, int]) -> np.ndarray:
    """Return the 4-connected walkable component containing ``start``."""
    seen = np.zeros(grid.walkable.shape, dtype=bool)
    if not grid.walkable[start]:
        return seen
    queue = deque([start])
    seen[start] = True
    while queue:
        row, col = queue.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, col + dc
            if (
                0 <= nr < grid.rows
                and 0 <= nc < grid.cols
                and grid.walkable[nr, nc]
                and not seen[nr, nc]
            ):
                seen[nr, nc] = True
                queue.append((nr, nc))
    return seen


def _support_mask(
    centres: np.ndarray,
    axis: int,
    low: float,
    high: float,
    bounds: dict[int, tuple[float, float]],
) -> np.ndarray:
    """Boolean mask of splats inside a slab around a cell.

    ``axis`` is the world axis the slab is thin on (1 = y for floor/ceiling);
    ``bounds`` maps each remaining world axis to its (min, max) extent.
    """
    in_band = (centres[:, axis] >= low) & (centres[:, axis] <= high)
    in_foot = np.ones(len(centres), dtype=bool)
    for a, (lo, hi) in bounds.items():
        in_foot &= (centres[:, a] >= lo) & (centres[:, a] <= hi)
    return in_band & in_foot


def score_cell_enclosure(
    centres: np.ndarray,
    grid: FreeGrid,
    row: int,
    col: int,
) -> dict[str, bool]:
    """Whether the splat supports floor, ceiling and four walls at one cell.

    Floor and ceiling are slabs through the cell's own column.  Walls are
    slabs one cell thick on each side of the cell, spanning the clear height,
    so a wall counts when the splat puts surface there -- and a missing wall is
    exactly the black gap the PoC must not show the player.
    """
    x, z = grid.cell_centre(row, col)
    floor = float(grid.floor_y[row, col])
    ceiling = float(grid.ceiling_y[row, col])
    half = grid.size_m * 0.5
    clear_low = floor + FLOOR_BAND_M
    clear_high = ceiling - CEILING_BAND_M

    floor_mask = _support_mask(
        centres, 1, floor - FLOOR_BAND_M, floor + FLOOR_BAND_M,
        {0: (x - half, x + half), 2: (z - half, z + half)},
    )
    ceiling_mask = _support_mask(
        centres, 1, ceiling - CEILING_BAND_M, ceiling + CEILING_BAND_M,
        {0: (x - half, x + half), 2: (z - half, z + half)},
    )

    walls = {}
    for name, (axis, lo, hi) in {
        "wall_north": (2, z - half - WALL_SUPPORT_RADIUS_M, z - half + WALL_SUPPORT_RADIUS_M),
        "wall_south": (2, z + half - WALL_SUPPORT_RADIUS_M, z + half + WALL_SUPPORT_RADIUS_M),
        "wall_east": (0, x + half - WALL_SUPPORT_RADIUS_M, x + half + WALL_SUPPORT_RADIUS_M),
        "wall_west": (0, x - half - WALL_SUPPORT_RADIUS_M, x - half + WALL_SUPPORT_RADIUS_M),
    }.items():
        other = [a for a in range(3) if a != axis]
        in_band = (centres[:, axis] >= lo) & (centres[:, axis] <= hi)
        in_height = (centres[:, 1] >= clear_low) & (centres[:, 1] <= clear_high)
        # The wall slab spans the cell's own extent on the remaining horizontal
        # axis, so it is the face of this cell, not the neighbour's.
        span = [a for a in other if a != 1][0]
        in_span = (centres[:, span] >= x - half) & (centres[:, span] <= x + half) \
            if span == 0 else (centres[:, span] >= z - half) & (centres[:, span] <= z + half)
        walls[name] = int(np.count_nonzero(in_band & in_height & in_span)) >= MIN_SUPPORT_SPLATS

    return {
        "floor": int(np.count_nonzero(floor_mask)) >= MIN_SUPPORT_SPLATS,
        "ceiling": int(np.count_nonzero(ceiling_mask)) >= MIN_SUPPORT_SPLATS,
        **walls,
    }


def score_envelope(centres: np.ndarray, grid: FreeGrid, component: np.ndarray) -> dict:
    """Aggregate per-cell enclosure over the walkable component."""
    cells = np.argwhere(component)
    per_cell = [score_cell_enclosure(centres, grid, int(r), int(c)) for r, c in cells]
    keys = ["floor", "ceiling", "wall_north", "wall_south", "wall_east", "wall_west"]
    counts = {key: sum(1 for cell in per_cell if cell[key]) for key in keys}
    enclosed = sum(1 for cell in per_cell if all(cell[key] for key in keys))
    total = len(per_cell)
    return {
        "cells": total,
        "supported": counts,
        "supported_pct": {key: round(100.0 * counts[key] / total, 1) for key in keys},
        "fully_enclosed_cells": enclosed,
        "fully_enclosed_pct": round(100.0 * enclosed / total, 1) if total else 0.0,
    }


#: Eye height above the local generated floor for the visual-enclosure score.
#: The production capsule is 1.2 m tall with the camera (Head) 0.5 m above the
#: capsule centre (#101), so the eye rides 1.1 m above the floor surface.
EYE_ABOVE_FLOOR_M = 1.1

#: Half-angle of the per-heading support cone. Eight compass headings at 45
#: degrees with a 22.5-degree half-angle tile the horizon without overlap; the
#: production FOV is 75 degrees, so a heading that passes here reads as a
#: surfaced view, not a sliver.
VIEW_CONE_HALF_ANGLE_RAD = float(np.deg2rad(22.5))

#: Farthest a wall surface may sit and still enclose the view. Backrooms rooms
#: read at 2-8 m; beyond 12 m the surface is haze at PSX resolution, not a wall.
VIEW_MAX_RANGE_M = 12.0

#: Minimum splats inside one heading cone to call it a surface. One splat is a
#: floater; eight coincident splats in a 45-degree cone at wall height is the
#: smallest cluster the screenshots show as a readable patch.
VIEW_MIN_SUPPORT_SPLATS = 8

#: Vertical band for wall support: above the floor skirting, below the ceiling
#: cove, so floor/ceiling splats cannot stand in for a missing wall.
VIEW_WALL_LOW_M = 0.3
VIEW_WALL_HIGH_M = 0.2

#: Eight compass headings (x, z) matching capture_walk_envelope.gd.
VIEW_HEADINGS = (
    ("e", (1.0, 0.0)),
    ("ne", (0.70710678, 0.70710678)),
    ("n", (0.0, 1.0)),
    ("nw", (-0.70710678, 0.70710678)),
    ("w", (-1.0, 0.0)),
    ("sw", (-0.70710678, -0.70710678)),
    ("s", (0.0, -1.0)),
    ("se", (0.70710678, -0.70710678)),
)


def score_cell_views(
    centres: np.ndarray,
    grid: FreeGrid,
    row: int,
    col: int,
) -> dict[str, dict]:
    """Nearest splat-supported surface per compass heading from one cell.

    The eye stands at the production height (floor + 1.1 m). For each heading,
    splats in the wall band within a 22.5-degree cone and 12 m range count as
    support; the nearest such distance is the measurement, and the heading
    passes when at least VIEW_MIN_SUPPORT_SPLATS splats hold it. A heading
    with no support inside 12 m is the black gap the PoC must not show.
    """
    x, z = grid.cell_centre(row, col)
    floor = float(grid.floor_y[row, col])
    ceiling = float(grid.ceiling_y[row, col])
    eye = np.array([x, floor + EYE_ABOVE_FLOOR_M, z])
    low_y = floor + VIEW_WALL_LOW_M
    high_y = ceiling - VIEW_WALL_HIGH_M
    in_band = (centres[:, 1] >= low_y) & (centres[:, 1] <= high_y)
    out: dict[str, dict] = {}
    for name, (dx, dz) in VIEW_HEADINGS:
        heading = np.array([dx, dz])
        rel = centres[:, [0, 2]] - eye[[0, 2]]
        dist = np.hypot(rel[:, 0], rel[:, 1])
        with np.errstate(divide="ignore", invalid="ignore"):
            cosang = np.where(
                dist > 1e-9,
                (rel[:, 0] * heading[0] + rel[:, 1] * heading[1])
                / np.maximum(dist, 1e-9),
                -1.0,
            )
        cos_limit = float(np.cos(VIEW_CONE_HALF_ANGLE_RAD))
        in_cone = in_band & (dist > 1e-9) & (cosang >= cos_limit) & (dist <= VIEW_MAX_RANGE_M)
        count = int(np.count_nonzero(in_cone))
        nearest = round(float(np.min(dist[in_cone])), 3) if count else None
        out[name] = {
            "supported": bool(count >= VIEW_MIN_SUPPORT_SPLATS),
            "support_splats": count,
            "nearest_m": nearest,
        }
    return out


def score_visual_enclosure(
    centres: np.ndarray, grid: FreeGrid, component: np.ndarray
) -> dict:
    """Aggregate the per-heading view score over the walkable component."""
    cells = np.argwhere(component)
    names = [name for name, _ in VIEW_HEADINGS]
    per_heading_supported = {name: 0 for name in names}
    fully = 0
    nearest_lists: dict[str, list] = {name: [] for name in names}
    total = len(cells)
    for r, c in cells:
        views = score_cell_views(centres, grid, int(r), int(c))
        if all(views[name]["supported"] for name in names):
            fully += 1
        for name in names:
            if views[name]["supported"]:
                per_heading_supported[name] += 1
            if views[name]["nearest_m"] is not None:
                nearest_lists[name].append(views[name]["nearest_m"])
    nearest_median = {
        name: (round(float(np.median(nearest_lists[name])), 3) if nearest_lists[name] else None)
        for name in names
    }
    return {
        "cells": total,
        "supported": per_heading_supported,
        "supported_pct": {
            name: round(100.0 * per_heading_supported[name] / total, 1) for name in names
        },
        "nearest_surface_median_m": nearest_median,
        "fully_supported_cells": fully,
        "fully_supported_pct": round(100.0 * fully / total, 1) if total else 0.0,
    }


def component_bounds(grid: FreeGrid, component: np.ndarray) -> dict:
    """World bounds and area of the walkable component."""
    cells = np.argwhere(component)
    xs, zs = [], []
    for row, col in cells:
        x, z = grid.cell_centre(int(row), int(col))
        xs.append(x)
        zs.append(z)
    return {
        "x_min": round(min(xs), 3),
        "x_max": round(max(xs), 3),
        "z_min": round(min(zs), 3),
        "z_max": round(max(zs), 3),
        "width_x_m": round(max(xs) - min(xs), 3),
        "width_z_m": round(max(zs) - min(zs), 3),
        "area_m2": round(len(cells) * grid.size_m * grid.size_m, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--glb", required=True)
    parser.add_argument("--ply", required=True)
    parser.add_argument("--clean-ply", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    contract = contract_from_path(args.manifest)
    benchmark = json.loads(Path(args.report).read_text())
    mesh = load_world_mesh(args.glb, contract)
    grid = build_free_grid(mesh, contract, benchmark)

    spawn_cell = (37, 28)
    component = reachable_component(grid, spawn_cell)

    source = ply_to_world(read_ply_positions(args.ply), contract)
    clean = ply_to_world(read_ply_positions(args.clean_ply), contract)

    low, high = mesh.bounds()
    collider = contract.collider
    observed = {
        "x_min": collider.min_corner[0], "x_max": collider.max_corner[0],
        "y_min": collider.min_corner[1], "y_max": collider.max_corner[1],
        "z_min": collider.min_corner[2], "z_max": collider.max_corner[2],
    }
    cameras = contract.cameras

    result = {
        "volumes": {
            "observed_room_m": {k: round(float(v), 3) for k, v in observed.items()},
            "camera_path_m": {
                "count": cameras.count,
                "x_min": round(cameras.world_min[0], 3), "x_max": round(cameras.world_max[0], 3),
                "y_min": round(cameras.world_min[1], 3), "y_max": round(cameras.world_max[1], 3),
                "z_min": round(cameras.world_min[2], 3), "z_max": round(cameras.world_max[2], 3),
            },
            "collision_m": {
                "x_min": round(float(low[0]), 3), "x_max": round(float(high[0]), 3),
                "y_min": round(float(low[1]), 3), "y_max": round(float(high[1]), 3),
                "z_min": round(float(low[2]), 3), "z_max": round(float(high[2]), 3),
            },
        },
        "walkable": {
            "walkable_cells": int(np.count_nonzero(grid.walkable)),
            "reachable_from_spawn_cells": int(np.count_nonzero(component)),
            "spawn_cell": list(spawn_cell),
            "bounds": component_bounds(grid, component),
        },
        "enclosure": {
            "source": score_envelope(source, grid, component),
            "clean": score_envelope(clean, grid, component),
        },
        "visual_enclosure": {
            "source": score_visual_enclosure(source, grid, component),
            "clean": score_visual_enclosure(clean, grid, component),
        },
        "splat_counts": {
            "source": int(len(source)),
            "clean": int(len(clean)),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
