"""Safe one-metre leaf adjustments for gmap-0.6.0 diagonal candidates."""

from __future__ import annotations

import copy
import math
from typing import Any

from doorway_sizes import port_margin_m
from gmap_diagonal_candidates import candidate_pairs
from gmap_geometry import check_port_on_contact, overlaps, polygon_rect, rect_polygon


def _edge_ports(
    document: dict[str, Any], cell_id: str
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    edge = next(
        (
            e
            for e in document["edges"]
            if e["connector"] == "direct"
            and cell_id in (e["from"].split(":")[0], e["to"].split(":")[0])
        ),
        None,
    )
    if edge is None:
        return None
    ports = {p["port_id"]: p for c in document["cells"] for p in c["required_ports"]}
    own_id = edge["from"] if edge["from"].split(":")[0] == cell_id else edge["to"]
    other_id = edge["to"] if own_id == edge["from"] else edge["from"]
    return ports[own_id], ports[other_id], other_id.split(":")[0]


def _move_valid(document: dict[str, Any], cell_id: str, dx: int, dz: int) -> bool:
    cell = next(c for c in document["cells"] if c["cell_id"] == cell_id)
    edge_ports = _edge_ports(document, cell_id)
    rect = polygon_rect(cell["envelope_xz"])
    if edge_ports is None or rect is None:
        return False
    own, other, other_id = edge_ports
    shifted = (rect[0] + dx, rect[1] + dz, rect[2] + dx, rect[3] + dz)
    if _overlaps_other_cell(document, cell_id, shifted):
        return False
    other_cell = next(c for c in document["cells"] if c["cell_id"] == other_id)
    if other_cell.get("module"):
        return False
    other_rect = polygon_rect(other_cell["envelope_xz"])
    own_pos = [own["pos_xz"][0] + dx, own["pos_xz"][1] + dz]
    if other_rect is None or _contacts_changed(
        shifted, other_rect, own, other, own_pos
    ):
        return False
    return not _near_other_ports(cell, other_cell, own, other, own_pos)


def _overlaps_other_cell(
    document: dict[str, Any], cell_id: str, shifted: tuple[float, float, float, float]
) -> bool:
    for item in document["cells"]:
        bounds = polygon_rect(item["envelope_xz"])
        if item["cell_id"] != cell_id and bounds and overlaps(shifted, bounds):
            return True
    return False


def _contacts_changed(
    shifted: tuple[float, float, float, float],
    other_rect: tuple[float, float, float, float],
    own: dict[str, Any],
    other: dict[str, Any],
    own_pos: list[float],
) -> bool:
    if check_port_on_contact(
        shifted,
        own_pos,
        tuple(own["normal"]),
        other_rect,
        port_margin_m(own["compatibility_type"]),
    ):
        return True
    return check_port_on_contact(
        other_rect,
        own_pos,
        tuple(other["normal"]),
        shifted,
        port_margin_m(other["compatibility_type"]),
    )


def _near_other_ports(
    cell: dict[str, Any],
    other_cell: dict[str, Any],
    own: dict[str, Any],
    other: dict[str, Any],
    own_pos: list[float],
) -> bool:
    for owner in (cell, other_cell):
        others = [
            port
            for port in owner["required_ports"]
            if port["port_id"] not in (own["port_id"], other["port_id"])
        ]
        if any(math.dist(own_pos, port["pos_xz"]) < 2.0 - 1e-7 for port in others):
            return True
    return False


def _move_leaf(
    document: dict[str, Any], cell_id: str, dx: int, dz: int
) -> dict[str, Any] | None:
    trial = copy.deepcopy(document)
    cell = next(c for c in trial["cells"] if c["cell_id"] == cell_id)
    edge_ports = _edge_ports(trial, cell_id)
    rect = polygon_rect(cell["envelope_xz"])
    if edge_ports is None or rect is None:
        return None
    own, other, _ = edge_ports
    cell["envelope_xz"] = rect_polygon(
        (rect[0] + dx, rect[1] + dz, rect[2] + dx, rect[3] + dz)
    )
    for port in (own, other):
        port["pos_xz"] = [port["pos_xz"][0] + dx, port["pos_xz"][1] + dz]
    return trial


def nudge_to_budget(document: dict[str, Any], budget: int) -> list[str]:
    from gmap_diagonal_candidates import _pair_capacity

    moved: list[str] = []
    for _ in range(6):
        current = candidate_pairs(document)
        if _pair_capacity(current) >= budget:
            break
        current_score = (_pair_capacity(current), len(current))
        moved_cell = _try_leaf_moves(document, current_score, moved)
        if moved_cell == "":
            break
        moved.append(moved_cell)
    return moved


def _try_leaf_moves(
    document: dict[str, Any], current_score: tuple[int, int], moved: list[str]
) -> str:
    from gmap_diagonal_candidates import _pair_capacity

    for cell in sorted(document["cells"], key=lambda item: item["cell_id"]):
        cell_id = cell["cell_id"]
        if not _is_movable_leaf(document, cell, cell_id, moved):
            continue
        edge_ports = _edge_ports(document, cell_id)
        if edge_ports is None:
            continue
        for dx, dz in _leaf_shifts(edge_ports[0]["normal"]):
            if not _move_valid(document, cell_id, dx, dz):
                continue
            trial = _move_leaf(document, cell_id, dx, dz)
            if trial is None:
                continue
            pairs = candidate_pairs(trial)
            if (_pair_capacity(pairs), len(pairs)) > current_score:
                document.clear()
                document.update(trial)
                return cell_id
    return ""


def _is_movable_leaf(
    document: dict[str, Any], cell: dict[str, Any], cell_id: str, moved: list[str]
) -> bool:
    if (
        cell_id in moved
        or cell["role"] not in ("ground", "figure")
        or cell.get("module")
    ):
        return False
    degree = sum(
        cell_id in (edge["from"].split(":")[0], edge["to"].split(":")[0])
        for edge in document["edges"]
    )
    return degree == 1


def _leaf_shifts(normal: list[float]) -> tuple[tuple[int, int], tuple[int, int]]:
    return ((0, -1), (0, 1)) if abs(normal[0]) > 0.5 else ((-1, 0), (1, 0))
