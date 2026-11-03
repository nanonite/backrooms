"""Stage 0 growth: a tree of lattice rectangles joined by doorway edges."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from gmap_geometry import (
    SIDES,
    Rect,
    Vec,
    check_port_on_contact,
    contact_port,
    far_enough,
    flush_rects,
    oriented_sizes,
    overlaps,
)

PORT_TYPE = "level_doorway_2m_v1"
GROUND_CLASSES = [(3, 6), (3, 10), (6, 6), (8, 8), (8, 12)]
DEGREE_WEIGHTS = {0: 3, 1: 3, 2: 2, 3: 1}
TRIES_PER_FRONTIER = 50


class GenerationError(ValueError):
    """The generator cannot complete a map and fails closed."""


class RetryAttempt(Exception):
    """This attempt broke a rule; regenerate with the next seed stream."""


@dataclass
class Port:
    port_id: str
    pos: Vec
    normal: Vec
    placement: str = "standard"


@dataclass
class Cell:
    cell_id: str
    rect: Rect
    ports: list[Port] = field(default_factory=list)
    role: str = "ground"
    tier: int = 0
    mode: str = "standard"


@dataclass
class Draft:
    cells: dict[str, Cell] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (from_port, to_port, connector)
    centred: bool = False  # gmap-0.2.0: ports at the exact overlap centre
    margin: float = 1.0  # minimum port distance from an overlap end while growing/assigning

    def walkable(self) -> list[Cell]:
        return [cell for cell in self.cells.values() if cell.role != "void"]

    def port_cell(self, port_id: str) -> str:
        return port_id.split(":")[0]

    def degree(self, cell_id: str) -> int:
        return sum(
            1
            for a, b, connector in self.edges
            if connector == "direct" and cell_id in (self.port_cell(a), self.port_cell(b))
        )

    def new_id(self) -> str:
        return f"c{len(self.cells):02d}"

    def free_for(self, rect: Rect) -> bool:
        return not any(overlaps(rect, cell.rect) for cell in self.cells.values())


def weighted_index(rng: random.Random, weights: list[int]) -> int:
    pick = rng.randrange(sum(weights))
    for index, weight in enumerate(weights):
        if pick < weight:
            return index
        pick -= weight
    raise AssertionError("unreachable")


def connect(draft: Draft, parent: Cell, child: Cell, connector: str) -> None:
    """Add the edge and one required port on each cell at the snapped overlap centre."""
    found = contact_port(parent.rect, child.rect, draft.centred)
    if found is None:
        raise GenerationError(f"{parent.cell_id} and {child.cell_id} cannot share a doorway")
    pos, normal = found
    opposite = (-normal[0] + 0, -normal[1] + 0)
    port_a = Port(f"{parent.cell_id}:p{len(parent.ports)}", pos, normal)
    port_b = Port(f"{child.cell_id}:p{len(child.ports)}", pos, opposite)
    parent.ports.append(port_a)
    child.ports.append(port_b)
    draft.edges.append((port_a.port_id, port_b.port_id, connector))


def placements(
    draft: Draft, parent: Cell, normal: Vec, size: tuple[int, int]
) -> list[Rect]:
    """Free flush rectangles whose doorway would not crowd the parent's ports."""
    existing = [port.pos for port in parent.ports]
    result = []
    for rect in flush_rects(parent.rect, normal, *size):
        found = contact_port(parent.rect, rect, draft.centred)
        if (
            found
            and check_port_on_contact(parent.rect, found[0], found[1], rect, draft.margin) is None
            and draft.free_for(rect)
            and far_enough(found[0], existing)
        ):
            result.append(rect)
    return result


def try_place(rng: random.Random, draft: Draft, parent: Cell) -> bool:
    normal = rng.choice(SIDES)
    size = rng.choice(GROUND_CLASSES)
    width, depth = rng.choice(oriented_sizes(size))
    options = placements(draft, parent, normal, (width, depth))
    if not options:
        return False
    child = Cell(draft.new_id(), rng.choice(options))
    draft.cells[child.cell_id] = child
    connect(draft, parent, child, "direct")
    return True


def grow_step(rng: random.Random, draft: Draft) -> None:
    pool = [cell for cell in draft.cells.values() if draft.degree(cell.cell_id) < 4]
    while pool:
        weights = [DEGREE_WEIGHTS[draft.degree(cell.cell_id)] for cell in pool]
        parent = pool[weighted_index(rng, weights)]
        for _ in range(TRIES_PER_FRONTIER):
            if try_place(rng, draft, parent):
                return
        pool.remove(parent)
    raise GenerationError("growth stalled: no frontier cell accepts a new cell")


def grow(rng: random.Random, cell_target: int, centred: bool = False, margin: float = 1.0) -> Draft:
    draft = Draft(centred=centred, margin=margin)
    width, depth = rng.choice(oriented_sizes(rng.choice(GROUND_CLASSES)))
    draft.cells["c00"] = Cell("c00", (0, 0, width, depth))
    while len(draft.cells) < cell_target:
        grow_step(rng, draft)
    return draft
