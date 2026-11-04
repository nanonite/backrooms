"""Stage 0 assignment: rarity tiers, figure envelopes, roles and void cells."""

from __future__ import annotations

import random

from gmap_diagonal_sites import reserved_cell_ids
from gmap_geometry import (
    SIDES,
    Rect,
    adjacent,
    aspect,
    check_port_on_contact,
    oriented_sizes,
    overlaps,
)
from gmap_grow import Cell, Draft, RetryAttempt, connect, placements

VOID_CLASSES = [(3, 3), (3, 6)]
VOID_BUDGET = {"min": 1, "max": 3}
VOID_TRIES = 50
THRESHOLD_ASPECT = 2.0


def roll_tier(rng: random.Random) -> int:
    """2d6: <=7 -> 0, 8-9 -> 1, 10-11 -> 2, 12 -> 3."""
    total = rng.randint(1, 6) + rng.randint(1, 6)
    return 0 if total <= 7 else 1 if total <= 9 else 2 if total <= 11 else 3


def keeps_ports(draft: Draft, cell: Cell, rect: Rect) -> bool:
    """Every existing doorway of `cell` stays valid for the replacement rectangle."""
    if not draft.clear_of_reservations(rect):
        return False
    for port in cell.ports:
        other = draft.cells[other_cell(draft, port.port_id)]
        if check_port_on_contact(rect, port.pos, port.normal, other.rect, draft.margin):
            return False
    return not any(
        overlaps(rect, other.rect)
        for other in draft.cells.values()
        if other is not cell
    )


def other_cell(draft: Draft, port_id: str) -> str:
    for a, b, _ in draft.edges:
        if a == port_id:
            return draft.port_cell(b)
        if b == port_id:
            return draft.port_cell(a)
    raise ValueError(f"port {port_id} is on no edge")


def figure_options(
    draft: Draft, cell: Cell, classes: list[tuple[int, int]]
) -> list[Rect]:
    x0, z0, x1, z1 = cell.rect
    options: set[Rect] = set()
    for size in classes:
        for width, depth in oriented_sizes(size):
            for nx in range(x0 - width, x1 + 1):
                for nz in range(z0 - depth, z1 + 1):
                    rect = (nx, nz, nx + width, nz + depth)
                    if keeps_ports(draft, cell, rect):
                        options.add(rect)
    return sorted(options)


def assign_tiers(
    rng: random.Random, draft: Draft, classes: list[tuple[int, int]]
) -> None:
    """Roll tiers in cell order; figure envelopes are re-drawn or demoted to tier 1."""
    for cell in draft.walkable():
        cell.tier = roll_tier(rng)
        if cell.cell_id in reserved_cell_ids(draft.reserved_diagonal_zones):
            cell.tier = 1 if cell.tier >= 2 else cell.tier
            continue
        if cell.tier < 2:
            continue
        options = figure_options(draft, cell, classes) if classes else []
        if not options:
            cell.tier = 1
            continue
        chosen = rng.choice(options)
        figures = [c for c in draft.walkable() if c.role == "figure"]
        if any(adjacent(chosen, other.rect) for other in figures):
            cell.tier = 1
            continue
        cell.rect, cell.role = chosen, "figure"


def assign_roles(draft: Draft) -> None:
    protected = reserved_cell_ids(draft.reserved_diagonal_zones)
    for cell in draft.walkable():
        if cell.role == "figure" or cell.cell_id in protected:
            continue
        threshold = (
            draft.degree(cell.cell_id) == 2 and aspect(cell.rect) >= THRESHOLD_ASPECT
        )
        cell.role = "threshold" if threshold else "ground"


def add_voids(rng: random.Random, draft: Draft) -> int:
    """Attach leaf void cells through closed_visible edges; returns how many."""
    wanted = rng.randint(VOID_BUDGET["min"], VOID_BUDGET["max"])
    placed = 0
    protected = reserved_cell_ids(draft.reserved_diagonal_zones)
    walkable = [
        cell
        for cell in draft.walkable()
        if cell.module is None and cell.cell_id not in protected
    ]  # library and reserved site endpoints have no void door
    for _ in range(wanted):
        for _ in range(VOID_TRIES):
            parent = rng.choice(walkable)
            normal = rng.choice(SIDES)
            width, depth = rng.choice(oriented_sizes(rng.choice(VOID_CLASSES)))
            options = placements(draft, parent, normal, (width, depth))
            if not options:
                continue
            void = Cell(draft.new_id(), rng.choice(options), role="void")
            draft.cells[void.cell_id] = void
            connect(draft, parent, void, "closed_visible")
            placed += 1
            break
    if placed < VOID_BUDGET["min"]:
        raise RetryAttempt("could not place the minimum number of voids")
    return placed
