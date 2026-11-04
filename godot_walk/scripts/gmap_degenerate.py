"""gmap-0.2.0 degenerate corner doorways: rare, seeded, budgeted, recorded.

Growth always places standard doorways (port centred in the shared edge, >= 1.5 m from
both overlap ends). Afterwards a few eligible cells may become "degenerate": on a 3 m
shared edge the port moves to the gmap-0.1.0 position, 1 m from the low end, so the 2 m
doorway touches an envelope corner. Only cells that own the touched corner(s) qualify.
"""

from __future__ import annotations

import hashlib
import random

from gmap_diagonal_sites import reserved_cell_ids
from gmap_geometry import (
    EPS,
    STANDARD_MARGIN_M,
    Rect,
    Vec,
    along,
    contact,
    far_enough,
    port_position,
)
from gmap_grow import Draft, Port

ROLL_MIN = 11
ORIGIN_CELL = "c00"
DEGENERATE_EDGE_M = 3


def degenerate_rng(seed: int, attempt: int, version: str) -> random.Random:
    """Separate sha256-derived stream; never Python hash()."""
    digest = hashlib.sha256(f"{seed}:{attempt}:degenerate:{version}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def roll_2d6(rng: random.Random) -> int:
    return rng.randint(1, 6) + rng.randint(1, 6)


def side_span(rect: Rect, normal: Vec) -> tuple[float, float]:
    """Low and high end of the rectangle's side that faces `normal`."""
    return (rect[1], rect[3]) if normal[0] else (rect[0], rect[2])


def corner_cells(
    cells: dict[str, Rect],
    normals: dict[str, Vec],
    pos: Vec,
    margin: float = STANDARD_MARGIN_M,
) -> list[str]:
    """Cells whose envelope corner on this side lies within `margin` (1.5 m) of the port (sorted)."""
    found = []
    for cell_id, rect in cells.items():
        low, high = side_span(rect, normals[cell_id])
        where = along(pos, normals[cell_id])
        if where - low < margin - EPS or high - where < margin - EPS:
            found.append(cell_id)
    return sorted(found)


def port_lookup(draft: Draft) -> dict[str, tuple[Port, str]]:
    return {p.port_id: (p, c.cell_id) for c in draft.cells.values() for p in c.ports}


def hug_move(
    draft: Draft,
    edge: tuple[str, str, str],
    allowed: set[str],
    protected: set[str] | None = None,
) -> tuple[Vec, list[str]] | None:
    """The gmap-0.1.0 port position for a 3 m shared edge and the cells that own the
    touched corner, when every one of them is in `allowed`; else None."""
    ports = port_lookup(draft)
    (a, cell_a), (b, cell_b) = ports[edge[0]], ports[edge[1]]
    if protected and {cell_a, cell_b} & protected:
        return None
    if draft.cells[cell_a].module or draft.cells[cell_b].module:
        return None  # a module's port is fixed by its socket; never degenerate
    shared = contact(draft.cells[cell_a].rect, draft.cells[cell_b].rect)
    if shared is None or abs(shared[3] - shared[2] - DEGENERATE_EDGE_M) > EPS:
        return None
    normal, coord, low, _ = shared
    pos = port_position(normal, coord, low + 1)
    if pos == a.pos:
        return None
    owners = corner_cells(
        {cell_a: draft.cells[cell_a].rect, cell_b: draft.cells[cell_b].rect},
        {cell_a: a.normal, cell_b: b.normal},
        pos,
    )
    if not owners or not set(owners) <= allowed:
        return None
    others = [
        p.pos for c in (cell_a, cell_b) for p in draft.cells[c].ports if p not in (a, b)
    ]
    return (pos, owners) if far_enough(pos, others) else None


def hug_moves(
    draft: Draft, cell_id: str, allowed: set[str], protected: set[str] | None = None
) -> list[tuple[str, str, str]]:
    return [
        edge
        for edge in sorted(draft.edges)
        if cell_id in (edge[0].split(":")[0], edge[1].split(":")[0])
        and hug_move(draft, edge, allowed, protected)
    ]


def apply_moves(
    draft: Draft, cell_id: str, allowed: set[str], protected: set[str] | None = None
) -> int:
    """Move every eligible edge's port pair (re-checked one by one); returns how many moved.

    Each port is labelled by its own cell: degenerate where that cell owns the touched
    corner, standard for the neighbour whose wall continues past the doorway."""
    moved = 0
    for edge in hug_moves(draft, cell_id, allowed, protected):
        found = hug_move(
            draft, edge, allowed, protected
        )  # earlier moves may have crowded this one
        if found is None:
            continue
        pos, owners = found
        ports = port_lookup(draft)
        for port_id in edge[:2]:
            port, owner = ports[port_id]
            port.pos = pos
            port.placement = "degenerate" if owner in owners else "standard"
        moved += 1
    return moved


def assign_degenerate(rng: random.Random, draft: Draft, maximum: int) -> int:
    """Mark up to `maximum` cells degenerate; returns how many were marked."""
    used, chosen = 0, set()
    protected = reserved_cell_ids(draft.reserved_diagonal_zones)
    for cell in draft.walkable():
        if used >= maximum:
            break
        if (
            cell.cell_id == ORIGIN_CELL
            or cell.role == "figure"
            or cell.cell_id in protected
        ):
            continue
        if not hug_moves(draft, cell.cell_id, chosen | {cell.cell_id}, protected):
            continue
        if roll_2d6(rng) < ROLL_MIN:
            continue
        chosen.add(cell.cell_id)
        cell.mode = "degenerate"
        apply_moves(draft, cell.cell_id, chosen, protected)
        used += 1
    return used
