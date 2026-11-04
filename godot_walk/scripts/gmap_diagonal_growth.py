"""One gmap-0.6.1 growth step with optional reserved-site placement."""

from __future__ import annotations

import random

from gmap_diagonal_sites import (
    SITE_PROBABILITY,
    record_site,
    reserved_cell_ids,
    site_for_rect,
)
from gmap_geometry import SIDES, Rect, Vec, contact_port, oriented_sizes
from gmap_grow import (
    SITE_CLASSES,
    Cell,
    Draft,
    GenerationError,
    Port,
    _grow_step_legacy,
    connect,
    placements,
)


def _snap_corners(draft: Draft, parent: Cell) -> set[tuple[float, float]]:
    """Points 1 m diagonally off every corner site_for_rect could pair with.

    A site needs a child corner at exactly (+-1, +-1) from an eligible cell
    corner (gmap_diagonal_sites._candidate), so placements without one are
    skipped before the expensive site check. Same eligibility as site_for_rect;
    outputs are unchanged, only faster (#196 lever study).
    """
    reserved = reserved_cell_ids(draft.reserved_diagonal_zones)
    points = set()
    for cell in draft.cells.values():
        if (
            cell.cell_id == parent.cell_id
            or cell.role not in ("ground", "figure")
            or cell.module
            or cell.cell_id in reserved
        ):
            continue
        x0, z0, x1, z1 = cell.rect
        for cx, cz in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
            for dx in (-1, 1):
                for dz in (-1, 1):
                    points.add((cx + dx, cz + dz))
    return points


def _snaps(rect: Rect, points: set[tuple[float, float]]) -> bool:
    x0, z0, x1, z1 = rect
    return any(
        corner in points for corner in ((x0, z0), (x1, z0), (x1, z1), (x0, z1))
    )


def _site_options(
    draft: Draft, parent: Cell, child_id: str, normal: Vec, size: tuple[int, int]
) -> list[tuple[Rect, dict]]:
    sites = []
    points = _snap_corners(draft, parent)
    if not points:
        return sites
    for width, depth in oriented_sizes(size):
        for rect in placements(draft, parent, normal, (width, depth)):
            if not _snaps(rect, points):
                continue
            found = contact_port(parent.rect, rect, draft.centred)
            if found is None:
                continue
            port, outward = found
            child = Cell(
                child_id,
                rect,
                ports=[Port(f"{child_id}:p0", port, (-outward[0], -outward[1]))],
            )
            pair = site_for_rect(draft, parent, child, rect)
            if pair is not None:
                sites.append((rect, pair))
    return sites


def _all_site_options(
    draft: Draft, parent: Cell, child_id: str
) -> list[tuple[Rect, dict]]:
    found = []
    for normal in SIDES:
        for size in SITE_CLASSES:
            found.extend(_site_options(draft, parent, child_id, normal, size))
    unique = {}
    for rect, pair in found:
        key = (rect, tuple(pair["endpoint_ids"]), tuple(pair["corner_indices"]))
        unique[key] = (rect, pair)
    return [unique[key] for key in sorted(unique)]


def _place_site(
    site_rng: random.Random, draft: Draft, options: list[tuple[Cell, Rect, dict]]
) -> None:
    parent, rect, pair = site_rng.choice(options)
    child = Cell(draft.new_id(), rect)
    draft.cells[child.cell_id] = child
    connect(draft, parent, child, "direct")
    record_site(draft, pair)


def grow_step_v61(
    rng: random.Random, site_rng: random.Random, draft: Draft, site_budget: int
) -> None:
    draft.diagonal_budget = site_budget
    should_try_site = (
        len(draft.reserved_diagonal_zones) < site_budget
        and site_rng.random() < SITE_PROBABILITY
    )
    if should_try_site:
        pool = [cell for cell in draft.cells.values() if draft.degree(cell.cell_id) < 4]
        if not pool:
            raise GenerationError("growth stalled: no frontier cell accepts a new cell")
        options = [
            (parent, rect, pair)
            for parent in pool
            for rect, pair in _all_site_options(draft, parent, draft.new_id())
        ]
        if options:
            _place_site(site_rng, draft, options)
            return
    _grow_step_legacy(rng, draft)
