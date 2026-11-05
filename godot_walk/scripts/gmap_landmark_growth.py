"""Growth-time placement of the gmap-0.7.0 landmark cell."""

from __future__ import annotations

import random

from gmap_geometry import SIDES
from gmap_grow import Cell, Draft, connect, placements
from gmap_landmark import envelope_size, port_normals

CENTER_EPS = 1e-7


def _centered_on_parent(
    rect: tuple[int, int, int, int], parent: Cell, normal: tuple[int, int]
) -> bool:
    if normal[0]:
        return (
            abs((rect[1] + rect[3] - parent.rect[1] - parent.rect[3]) / 2) <= CENTER_EPS
        )
    return abs((rect[0] + rect[2] - parent.rect[0] - parent.rect[2]) / 2) <= CENTER_EPS


def _options(draft: Draft, plan: dict) -> list[tuple[Cell, tuple[int, int, int, int]]]:
    found = []
    size = envelope_size(plan)
    for parent in draft.cells.values():
        if parent.role == "void" or parent.module or draft.degree(parent.cell_id) >= 4:
            continue
        for side in SIDES:
            if side not in port_normals(plan):
                continue
            for rect in placements(draft, parent, side, size):
                if _centered_on_parent(rect, parent, side):
                    found.append((parent, rect))
    return found


def place_landmark(rng: random.Random, draft: Draft, plan: dict) -> bool:
    """Place the landmark on its declared port midpoint as one ordinary tree child."""
    options = _options(draft, plan)
    if not options:
        return False
    parent, rect = rng.choice(options)
    metadata = {key: value for key, value in plan.items() if key != "target_step"}
    metadata["status"] = "placed"
    child = Cell(draft.new_id(), rect, landmark=metadata)
    draft.cells[child.cell_id] = child
    connect(draft, parent, child, "direct")
    draft.landmark_cell_id = child.cell_id
    return True
