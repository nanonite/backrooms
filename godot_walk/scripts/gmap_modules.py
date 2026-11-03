"""gmap-0.3.0: library modules as leaf cells joined through their tested socket (issue 188).

Each usable module has exactly one tested socket and every tested pair already spends it, so a
module only ever enters a map as a LEAF cell attached to a generated parent cell. That joint is
a new connection, recorded `proposed_untested`; nothing here claims the #160 / #168 approval.

Geometry. For a rotation the module's rotated footprint bounding box (bw x bd) is ceiled to the
1 m lattice for the cell (W x D). The socket sits on the bbox side its outward normal faces; the
bbox is flush with that cell side. Along the wall the socket lands on the 0.5 m port lattice, so the
module can slide inside the ceil slack. The module is then moved LANDING_CLEARANCE_M away from
the parent: library walls stand just outside the footprint, so an exact landing would put the
library wall's inner face in the same plane as the parent's outer wall face (z-fighting).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from doorway_sizes import port_margin_m
from gmap_geometry import (
    EPS,
    PORT_STEP_M,
    WIDE_PORT_SEPARATION_M,
    Rect,
    Vec,
    adjacent,
    check_port_on_contact,
    flush_rects,
    far_enough,
    port_position,
)
from gmap_grow import PORT_TYPE, Cell, Draft, Port, RetryAttempt, weighted_index
from gmap_library import Library, LibraryModule, Socket, bbox
from gmap_transform import rotate_vector

MODULE_BUDGET = {"min": 1, "max": 2}
MODULE_TRIES = 50
TIER_WEIGHTS = {0: 4, 1: 3, 2: 2, 3: 1}
LANDING_CLEARANCE_M = 0.02
DIGITS = 6
FORM_ROLES = ("figure", "ground")


@dataclass(frozen=True)
class Layout:
    """One module in one rotation: cell size, tested socket and where it sits in the bbox."""

    module: LibraryModule
    turns: int
    size: tuple[int, int]
    bbox_size: tuple[float, float]
    bbox_min: tuple[float, float]  # of the rotated footprint, about the module origin
    socket: Socket
    socket_rel: tuple[float, float]  # rotated socket position from the bbox min
    outward: Vec  # rotated outward normal: from the module toward its parent


def tested_socket(module: LibraryModule) -> Socket | None:
    tested = sorted((s for s in module.sockets if s.tested), key=lambda s: s.socket_id)
    return tested[0] if tested else None


def usable_modules(library: Library) -> list[LibraryModule]:
    return sorted(
        (
            m
            for m in library.modules
            if m.layout_usable
            and m.form_role in FORM_ROLES
            and m.rarity_tier in TIER_WEIGHTS
            and tested_socket(m) is not None
        ),
        key=lambda m: m.module_id,
    )


def layout_for(module: LibraryModule, turns: int) -> Layout | None:
    """Cell size and socket geometry in one rotation; None if the socket is not on the bbox edge."""
    socket = tested_socket(module)
    if socket is None:
        return None
    points = [rotate_vector(p, turns) for p in module.footprint]
    x0, z0, x1, z1 = bbox(tuple(points))
    sx, sz = rotate_vector(socket.pos, turns)
    nx, nz = rotate_vector(socket.normal, turns)
    outward = (round(nx), round(nz))
    edge = {(1, 0): x1 - sx, (-1, 0): sx - x0, (0, 1): z1 - sz, (0, -1): sz - z0}.get(outward)
    if edge is None or abs(edge) > 1e-6:
        return None
    width, depth = round(x1 - x0, DIGITS), round(z1 - z0, DIGITS)
    size = (math.ceil(width - 1e-9), math.ceil(depth - 1e-9))
    return Layout(module, turns, size, (width, depth), (x0, z0), socket, (sx - x0, sz - z0), outward)


def lattice_positions(low: float, high: float) -> list[float]:
    """Port-lattice (0.5 m) values within [low, high], tolerant of float noise."""
    first = math.ceil(low / PORT_STEP_M - 1e-6)
    last = math.floor(high / PORT_STEP_M + 1e-6)
    return [k * PORT_STEP_M for k in range(first, last + 1)]


def landing(layout: Layout, rect: Rect, along: float) -> tuple[Vec, tuple[float, float]]:
    """(port position on the shared edge, translation_xz) for the socket landing at `along`."""
    cx0, cz0, cx1, cz1 = rect
    width, depth = layout.bbox_size
    ox, oz = layout.socket_rel
    nx, nz = layout.outward
    if nx:
        coord = cx1 if nx > 0 else cx0
        bbox_x = cx1 - width if nx > 0 else cx0
        bbox_z = along - oz
    else:
        coord = cz1 if nz > 0 else cz0
        bbox_z = cz1 - depth if nz > 0 else cz0
        bbox_x = along - ox
    translation = (
        bbox_x - layout.bbox_min[0] - nx * LANDING_CLEARANCE_M,
        bbox_z - layout.bbox_min[1] - nz * LANDING_CLEARANCE_M,
    )
    port = port_position((-nx, -nz), coord, along)
    return port, (round(translation[0], DIGITS) + 0.0, round(translation[1], DIGITS) + 0.0)


def along_candidates(layout: Layout, rect: Rect) -> list[float]:
    """Wall coordinates where the socket may land with the bbox still inside `rect`."""
    nx, _ = layout.outward
    width, depth = layout.bbox_size
    if nx:
        low = rect[1] + layout.socket_rel[1]
        slack = (rect[3] - rect[1]) - depth
    else:
        low = rect[0] + layout.socket_rel[0]
        slack = (rect[2] - rect[0]) - width
    return lattice_positions(low - EPS, low + slack + EPS)


def module_options(draft: Draft, parent: Cell, layout: Layout) -> list[tuple[Rect, Vec, tuple[float, float]]]:
    """Every (cell rect, port position, translation) that places the module as a leaf of `parent`."""
    side: Vec = (-layout.outward[0], -layout.outward[1])  # parent -> child
    compat = layout.socket.compatibility_type
    margin = port_margin_m(compat)
    figure = layout.module.form_role == "figure"
    standard = [p.pos for p in parent.ports if p.compatibility_type == PORT_TYPE]
    wide = [p.pos for p in parent.ports if p.compatibility_type != PORT_TYPE]
    separation = 2.0 if compat == PORT_TYPE else WIDE_PORT_SEPARATION_M
    options = []
    for rect in flush_rects(parent.rect, side, *layout.size):
        if not draft.free_for(rect):
            continue
        others = [c for c in draft.cells.values() if c is not parent and adjacent(rect, c.rect)]
        if any(c.role != "void" for c in others):  # library walls overhang; keep neighbours off
            continue
        if figure and parent.role == "figure":
            continue
        for along in along_candidates(layout, rect):
            port, translation = landing(layout, rect, along)
            if check_port_on_contact(parent.rect, port, side, rect, margin) is not None:
                continue
            if far_enough(port, standard, separation) and far_enough(port, wide, WIDE_PORT_SEPARATION_M):
                options.append((rect, port, translation))
    return sorted(options)


def add_module_cell(
    draft: Draft, parent: Cell, layout: Layout, rect: Rect, port: Vec, translation: tuple[float, float]
) -> Cell:
    module = layout.module
    cell = Cell(
        draft.new_id(),
        rect,
        role=str(module.form_role),
        tier=int(module.rarity_tier),  # type: ignore[arg-type]
        module={
            "module_id": module.module_id,
            "version": module.version,
            "rotation_deg": 90 * layout.turns,
            "translation_xz": [translation[0], translation[1]],
            "socket_id": layout.socket.socket_id,
            "metadata_record": dict(module.metadata_record or {}),
        },
    )
    draft.cells[cell.cell_id] = cell
    side: Vec = (-layout.outward[0], -layout.outward[1])
    compat = layout.socket.compatibility_type
    port_a = Port(f"{parent.cell_id}:p{len(parent.ports)}", port, side, compatibility_type=compat)
    port_b = Port(f"{cell.cell_id}:p0", port, layout.outward, compatibility_type=compat)
    parent.ports.append(port_a)
    cell.ports.append(port_b)
    draft.edges.append((port_a.port_id, port_b.port_id, "direct"))
    draft.untested.add((port_a.port_id, port_b.port_id))
    return cell


def try_module(rng: random.Random, draft: Draft, module: LibraryModule) -> bool:
    parents = [c for c in draft.walkable() if c.module is None and c.role in ("ground", "figure")]
    for _ in range(MODULE_TRIES):
        parent = rng.choice(parents)
        layout = layout_for(module, rng.randrange(4))
        if layout is None:
            continue
        options = module_options(draft, parent, layout)
        if not options:
            continue
        add_module_cell(draft, parent, layout, *rng.choice(options))
        return True
    return False


def attach_modules(rng: random.Random, draft: Draft, library: Library) -> int:
    """Attach 1..2 distinct usable modules as leaf cells; returns how many were placed."""
    wanted = rng.randint(MODULE_BUDGET["min"], MODULE_BUDGET["max"])
    usable = usable_modules(library)
    placed = 0
    for _ in range(wanted):
        pool = [m for m in usable if not any(c.module and c.module["module_id"] == m.module_id for c in draft.cells.values())]
        while pool:
            module = pool[weighted_index(rng, [TIER_WEIGHTS[int(m.rarity_tier)] for m in pool])]  # type: ignore[arg-type]
            if try_module(rng, draft, module):
                placed += 1
                break
            pool.remove(module)
    if placed < MODULE_BUDGET["min"]:
        raise RetryAttempt("could not place the minimum number of library modules")
    return placed
