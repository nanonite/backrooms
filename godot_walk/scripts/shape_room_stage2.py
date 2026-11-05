"""Shape stage 2a (issue 190): which 45-degree classes a cell may take, and the chamfers that realise one.

Classes (proposal section 5, stage 2 without diagonal ports): chamfered_box, octagon,
chamfered_polyomino and wedge. The map decides the class per cell (`eligible_classes` is
shared with the map validator); the shape room then draws the chamfers (`plan_cuts`).
"""

from __future__ import annotations

import math
import random
from typing import Any

from poetics_geometry import Point, classify_primitive
from shape_room_arms import arm_rects, primitive_for
from shape_room_chamfer import (
    CHAMFER_LENGTHS,
    Cuts,
    apply_cuts,
    clearance_ok,
    convex_vertices,
    cut_issues,
)
from shape_room_module_clear import module_sides, outline_conflicts
from shape_room_raster import RasterError, occupied_cells, outline_of
from shape_room_rng import cell_rng, version_for_map

STAGE2_CLASSES = ("chamfered_box", "chamfered_polyomino", "octagon", "wedge")
CLASS_WEIGHTS = {"chamfered_box": 3, "chamfered_polyomino": 3, "octagon": 2, "wedge": 1}
STAGE2_PROBABILITY = 0.4
OCTAGON_MAX_ASPECT = 1.25
OCTAGON_MIN_SHORT_M = 6.0
WEDGE_MIN_SIDE_M = 5.0
WEDGE_SHARE = 0.6
WEDGE_LENGTH_MIN_M = 3.5  # longer than a box chamfer (poetics_geometry.WEDGE_MIN_LEG_M)
POLYOMINO_MIN_SHORT_M = 4.0
POLYOMINO_PATTERNS = ("l_shape", "t_shape", "u_shape", "cross")
TRIES = 8
Envelope = Rect = tuple[float, float, float, float]


def box_ring(envelope: Envelope) -> list[Point]:
    x0, z0, x1, z1 = envelope
    return [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]


def wedge_lengths(short: float) -> list[float]:
    """Large chamfer legs: at least 60 percent of the short side (and over 3 m) up to the whole side."""
    low = max(WEDGE_LENGTH_MIN_M, math.ceil(short * WEDGE_SHARE * 2 - 1e-9) / 2)
    return [low + 0.5 * k for k in range(int((short - low) * 2 + 1e-9) + 1)]


def valid(
    ring: list[Point], ports: list[dict[str, Any]], cuts: Cuts, wedge: bool = False
) -> bool:
    return not cut_issues(ring, ports, cuts, wedge) and clearance_ok(
        apply_cuts(ring, cuts)
    )


def sides(envelope: Envelope) -> tuple[float, float]:
    return envelope[2] - envelope[0], envelope[3] - envelope[1]


def box_options(klass: str, envelope: Envelope) -> list[Cuts]:
    """Every chamfer set the box-based classes consider, in a fixed order."""
    short = min(sides(envelope))
    if klass == "chamfered_box":
        return [{corner: c} for corner in range(4) for c in CHAMFER_LENGTHS]
    if klass == "octagon":
        return [{corner: c for corner in range(4)} for c in CHAMFER_LENGTHS]
    return [{corner: c} for corner in range(4) for c in wedge_lengths(short)]


def box_class_ok(klass: str, envelope: Envelope) -> bool:
    width, depth = sides(envelope)
    if klass == "octagon":
        return (
            max(width, depth) / min(width, depth) <= OCTAGON_MAX_ASPECT
            and min(width, depth) >= OCTAGON_MIN_SHORT_M
        )
    if klass == "wedge":
        return min(width, depth) >= WEDGE_MIN_SIDE_M
    return True


def eligible_classes(
    envelope: Envelope, ports: list[dict[str, Any]], role: str
) -> list[str]:
    """Stage-2 classes this walkable generated cell may take (threshold cells stay stage 1)."""
    if role not in ("ground", "figure"):
        return []
    ring = box_ring(envelope)
    found = []
    for klass in ("chamfered_box", "octagon", "wedge"):
        if klass == "wedge" and len(ports) != 1:
            continue
        if box_class_ok(klass, envelope) and any(
            valid(ring, ports, cuts, klass == "wedge")
            for cuts in box_options(klass, envelope)
        ):
            found.append(klass)
    if (
        len(ports) >= 2
        and min(sides(envelope)) >= POLYOMINO_MIN_SHORT_M
        and primitive_for(ports) in POLYOMINO_PATTERNS
    ):
        found.append("chamfered_polyomino")
    return sorted(found)


def greedy_cuts(
    ring: list[Point], ports: list[dict[str, Any]], rng: random.Random, limit: int
) -> Cuts:
    order = rng.sample(convex_vertices(ring), len(convex_vertices(ring)))
    wanted = rng.randint(1, max(1, limit))
    cuts: Cuts = {}
    for vertex in order:
        if len(cuts) >= wanted:
            break
        for c in rng.sample(CHAMFER_LENGTHS, len(CHAMFER_LENGTHS)):
            if valid(ring, ports, {**cuts, vertex: c}):
                cuts[vertex] = c
                break
    return cuts


def plan_cuts(
    klass: str,
    ring: list[Point],
    ports: list[dict[str, Any]],
    envelope: Envelope,
    rng: random.Random,
) -> Cuts | None:
    """Chamfers realising `klass` on the base outline, or None (the room then stays stage 1)."""
    if klass in ("octagon", "wedge"):
        options = (
            box_options(klass, envelope)
            if len(ring) == 4 and box_class_ok(klass, envelope)
            else []
        )
        for cuts in rng.sample(options, len(options)):
            if (
                valid(ring, ports, cuts, klass == "wedge")
                and classify_primitive(apply_cuts(ring, cuts))[0] == klass
            ):
                return cuts
        return None
    for _ in range(TRIES):
        limit = 4 if klass == "chamfered_box" else len(convex_vertices(ring)) // 2
        cuts = greedy_cuts(ring, ports, rng, limit)
        if cuts and classify_primitive(apply_cuts(ring, cuts))[0] == klass:
            return cuts
    return None


def choose_class(rng: random.Random, eligible: list[str]) -> str:
    total = sum(CLASS_WEIGHTS[k] for k in eligible)
    pick = rng.randrange(total)
    for klass in eligible:
        if pick < CLASS_WEIGHTS[klass]:
            return klass
        pick -= CLASS_WEIGHTS[klass]
    raise AssertionError("unreachable")


def stage2_target(cell: dict[str, Any]) -> str | None:
    """gmap-0.4.0: the stage-2 class the map drew for this cell, if any."""
    return (
        cell.get("shape_class_target") if cell.get("shape_stage_target") == 2 else None
    )


def chamfer_cuts(
    document: dict[str, Any], cell: dict[str, Any], envelope: Rect, outline: list[Any]
) -> dict[int, float] | None:
    """Stage 2: the chamfers realising the cell's drawn class on the un-cut outline, else None (stays stage 1)."""
    target = stage2_target(cell)
    if target is None:
        return None
    fixed = cell.get("diagonal_link_chamfer")
    if fixed:
        corner = tuple(float(v) for v in fixed["corner_xz"])
        matches = [
            index
            for index, point in enumerate(outline)
            if math.dist(point, corner) <= 1e-6
        ]
        return {matches[0]: float(fixed["length_m"])} if len(matches) == 1 else None
    rng = cell_rng(
        document["seed"], f"{cell['cell_id']}:chamfer", version_for_map(document)
    )
    ports = sorted(cell["required_ports"], key=lambda p: p["port_id"])
    return plan_cuts(target, outline, ports, envelope, rng)


def suitable_width(
    document: dict[str, Any],
    cell: dict[str, Any],
    envelope: Rect,
    width: int,
    low: int,
    high: int,
) -> int | None:
    """gmap-0.4.0 arm width: the drawn one, else the next (wrapping inside [low, high]) whose arms keep
    clear of a library module's boundary planes and, for a chamfered polyomino, do not fill a rectangle;
    None when no width does (the room is then the whole envelope)."""
    ports = sorted(cell["required_ports"], key=lambda p: p["port_id"])
    sides = module_sides(document, cell)
    polyomino = stage2_target(cell) == "chamfered_polyomino"
    span = high - low + 1
    for candidate in (
        sorted(range(low, high + 1), key=lambda w: (w - width) % span)
        if low <= high
        else [width]
    ):
        try:
            outline = outline_of(occupied_cells(arm_rects(envelope, ports, candidate)))
        except RasterError:
            continue  # A split/holey arm union is not a drawable width; try the next candidate.
        if (len(outline) > 4 or not polyomino) and not outline_conflicts(
            outline, sides
        ):
            return candidate
    return None
