"""Fill candidates: which library modules fit each walkable cell envelope."""

from __future__ import annotations

import math
from typing import Any

from gmap_geometry import EPS, Rect, polygon_rect
from gmap_library import Library, LibraryModule, Point, Socket, bbox

NOTE = "Structural map only; not playable until cells are filled and module metadata is operator-accepted."
SOCKET_TOLERANCE_M = 0.5
FIT_EPSILON_M = 1e-6


def rotate_vector(vector: Point, quarter_turns: int) -> Point:
    x, z = vector
    for _ in range(quarter_turns % 4):
        x, z = -z, x
    return x, z


def rotate_point(point: Point, centre: Point, quarter_turns: int) -> Point:
    dx, dz = rotate_vector((point[0] - centre[0], point[1] - centre[1]), quarter_turns)
    return centre[0] + dx, centre[1] + dz


def place_footprint(
    module: LibraryModule, quarter_turns: int, rect: Rect
) -> tuple[tuple[Point, ...], Point]:
    """Rotated footprint at the envelope's min corner, and the applied translation."""
    x0, z0, x1, z1 = bbox(module.footprint)
    centre = ((x0 + x1) / 2.0, (z0 + z1) / 2.0)
    turned = tuple(rotate_point(p, centre, quarter_turns) for p in module.footprint)
    min_x, min_z, _, _ = bbox(turned)
    shift = (rect[0] - min_x, rect[1] - min_z)
    return tuple((x + shift[0], z + shift[1]) for x, z in turned), shift


def inside(points: tuple[Point, ...], rect: Rect) -> bool:
    return all(
        rect[0] - FIT_EPSILON_M <= x <= rect[2] + FIT_EPSILON_M
        and rect[1] - FIT_EPSILON_M <= z <= rect[3] + FIT_EPSILON_M
        for x, z in points
    )


def socket_lands(
    socket: Socket, port: dict[str, Any], placed: Point, normal: Point
) -> bool:
    near = math.hypot(placed[0] - port["pos_xz"][0], placed[1] - port["pos_xz"][1])
    return (
        socket.compatibility_type == port["compatibility_type"]
        and near <= SOCKET_TOLERANCE_M + EPS
        and math.hypot(normal[0] - port["normal"][0], normal[1] - port["normal"][1]) <= FIT_EPSILON_M
    )


def alignable(
    module: LibraryModule, quarter_turns: int, rect: Rect, ports: list[dict[str, Any]]
) -> bool:
    """One 1 m-lattice translation inside the envelope that lands every port."""
    if not ports:
        return True
    tested = [s for s in module.sockets if s.tested]
    if len(tested) < len(ports):
        return False
    x0, z0, x1, z1 = bbox(module.footprint)
    centre = ((x0 + x1) / 2.0, (z0 + z1) / 2.0)
    placed_box, base = place_footprint(module, quarter_turns, rect)
    _, _, px1, pz1 = bbox(placed_box)
    turned = [
        (s, rotate_point(s.pos, centre, quarter_turns), rotate_vector(s.normal, quarter_turns))
        for s in tested
    ]
    for dx in range(int(rect[2] - px1 + FIT_EPSILON_M) + 1):
        for dz in range(int(rect[3] - pz1 + FIT_EPSILON_M) + 1):
            if all(
                any(
                    socket_lands(s, port, (p[0] + base[0] + dx, p[1] + base[1] + dz), n)
                    for s, p, n in turned
                )
                for port in ports
            ):
                return True
    return False


def candidate(
    module: LibraryModule, turns: int, rect: Rect, ports: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "module_id": module.module_id,
        "version": module.version,
        "rotation_deg": 90 * turns,
        "footprint_fits": True,
        "tested_socket_count": module.tested_socket_count,
        "required_port_count": len(ports),
        "ports_alignable": alignable(module, turns, rect, ports),
        "layout_usable": module.layout_usable,
    }


def cell_candidates(library: Library, rect: Rect, ports: list[dict[str, Any]]) -> list[dict]:
    found = []
    for module in library.modules:
        for turns in range(4):
            footprint, _ = place_footprint(module, turns, rect)
            if inside(footprint, rect):
                found.append(candidate(module, turns, rect, ports))
    return found


def build_fill(document: dict[str, Any], map_sha256: str, library: Library) -> dict[str, Any]:
    cells = []
    for cell in sorted(document["cells"], key=lambda c: c["cell_id"]):
        if cell["role"] == "void":
            cells.append({"cell_id": cell["cell_id"], "cell_status": "void", "candidates": []})
            continue
        rect = polygon_rect(cell["envelope_xz"])
        found = cell_candidates(library, rect, cell["required_ports"]) if rect else []
        status = "module_candidates" if found else "shape_room_pending"
        cells.append({"cell_id": cell["cell_id"], "cell_status": status, "candidates": found})
    return {
        "schema_version": 1,
        "map_id": document["map_id"],
        "generator_version": document["generator_version"],
        "map_file": {"name": f"{document['map_id']}.json", "sha256": map_sha256},
        "library_index": dict(document["library_index"]),
        "note": NOTE,
        "playable": False,
        "cells": cells,
    }
