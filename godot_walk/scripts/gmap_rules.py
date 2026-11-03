"""Rule checks over a parsed generative map. Each returns a list of error dicts."""

from __future__ import annotations

from typing import Any

from doorway_sizes import DEFAULT_TYPE
from gmap_geometry import (
    EPS,
    MIN_PORT_SEPARATION_M,
    WIDE_PORT_SEPARATION_M,
    Rect,
    adjacent,
    check_port_on_contact,
    overlaps,
    polygon_rect,
)

Errors = list[dict[str, str]]
CONNECTORS = {"direct", "closed_visible"}
CONNECTION_STATUSES = {"proposed_untested"}


def err(rule: str, code: str, message: str) -> dict[str, str]:
    return {"rule": rule, "code": code, "message": message}


def is_lattice(value: float, unit: float) -> bool:
    steps = value / unit
    return abs(steps - round(steps)) <= EPS


def parse_rects(cells: list[dict[str, Any]]) -> tuple[dict[str, Rect], Errors]:
    rects, errors = {}, []
    for cell in cells:
        rect = polygon_rect(cell["envelope_xz"])
        if rect is None:
            errors.append(err("ports_on_lattice", "envelope_not_rectangle", cell["cell_id"]))
        else:
            rects[cell["cell_id"]] = rect
    ids = [cell["cell_id"] for cell in cells]
    for cell_id in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(err("no_envelope_overlap", "duplicate_cell_id", cell_id))
    return rects, errors


def check_lattice(cells: list[dict[str, Any]], unit: float, port_step: float | None = None) -> Errors:
    """Envelope corners on the unit lattice; ports too unless a finer `port_step` is declared."""
    errors = []
    for cell in cells:
        points = list(cell["envelope_xz"])
        if port_step is None:
            points += [p["pos_xz"] for p in cell["required_ports"]]
        if not all(is_lattice(v, unit) for point in points for v in point):
            errors.append(err("ports_on_lattice", "off_lattice", cell["cell_id"]))
    return errors


def check_overlaps(rects: dict[str, Rect]) -> Errors:
    ids = sorted(rects)
    return [
        err("no_envelope_overlap", "envelope_overlap", f"{a} overlaps {b}")
        for i, a in enumerate(ids)
        for b in ids[i + 1 :]
        if overlaps(rects[a], rects[b])
    ]


def port_index(cells: list[dict[str, Any]]) -> tuple[dict[str, tuple[str, dict]], Errors]:
    index, errors = {}, []
    for cell in cells:
        for port in cell["required_ports"]:
            if port["port_id"] in index:
                errors.append(err("ports_on_shared_edge", "duplicate_port_id", port["port_id"]))
            index[port["port_id"]] = (cell["cell_id"], port)
        for i, a in enumerate(cell["required_ports"]):
            for b in cell["required_ports"][i + 1 :]:
                gap = ((a["pos_xz"][0] - b["pos_xz"][0]) ** 2 + (a["pos_xz"][1] - b["pos_xz"][1]) ** 2) ** 0.5
                wide = a["compatibility_type"] != DEFAULT_TYPE or b["compatibility_type"] != DEFAULT_TYPE
                if gap + EPS < (WIDE_PORT_SEPARATION_M if wide else MIN_PORT_SEPARATION_M):
                    errors.append(
                        err("ports_on_shared_edge", "ports_too_close", f"{a['port_id']} {b['port_id']}")
                    )
    return index, errors


def check_edge(edge: dict[str, str], ports: dict, rects: dict[str, Rect]) -> Errors:
    label = f"{edge['from']} -> {edge['to']}"
    if edge["from"] not in ports or edge["to"] not in ports:
        return [err("ports_on_shared_edge", "edge_port_missing", label)]
    (cell_a, port_a), (cell_b, port_b) = ports[edge["from"]], ports[edge["to"]]
    if cell_a == cell_b:
        return [err("ports_on_shared_edge", "edge_self_loop", label)]
    errors = []
    if port_a["pos_xz"] != port_b["pos_xz"]:
        errors.append(err("ports_on_shared_edge", "port_misaligned", label))
    if [a + b for a, b in zip(port_a["normal"], port_b["normal"])] != [0, 0]:
        errors.append(err("ports_on_shared_edge", "normals_not_opposite", label))
    for cell, port, other in ((cell_a, port_a, cell_b), (cell_b, port_b, cell_a)):
        if cell in rects and other in rects:
            code = check_port_on_contact(rects[cell], port["pos_xz"], tuple(port["normal"]), rects[other])
            if code:
                errors.append(err("ports_on_shared_edge", code, f"{label} at {cell}"))
    return errors


def check_edges(edges: list[dict[str, str]], ports: dict, rects: dict[str, Rect]) -> Errors:
    errors = []
    used = {p for edge in edges for p in (edge["from"], edge["to"])}
    for edge in edges:
        errors += check_edge(edge, ports, rects)
        if edge["connector"] not in CONNECTORS:
            errors.append(err("ports_on_shared_edge", "unknown_connector", edge["connector"]))
    for port_id in sorted(set(ports) - used):
        errors.append(err("ports_on_shared_edge", "port_unused", port_id))
    return errors


def edge_cells(edge: dict[str, str]) -> tuple[str, str]:
    return edge["from"].split(":")[0], edge["to"].split(":")[0]


def check_tree(walkable: list[str], edges: list[dict[str, str]]) -> Errors:
    parent = {cell: cell for cell in walkable}

    def find(cell: str) -> str:
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    errors = []
    for edge in edges:
        a, b = edge_cells(edge)
        if edge["connector"] != "direct" or a not in parent or b not in parent:
            continue
        if find(a) == find(b):
            errors.append(err("tree_no_loops", "tree_loop", f"{edge['from']} -> {edge['to']}"))
        else:
            parent[find(a)] = find(b)
    if len({find(cell) for cell in walkable}) > 1:
        errors.append(err("tree_no_loops", "tree_disconnected", "walkable cells are not connected"))
    return errors


def check_branch(walkable: list[str], edges: list[dict[str, str]]) -> Errors:
    degree = dict.fromkeys(walkable, 0)
    for edge in edges:
        if edge["connector"] == "direct":
            for cell in edge_cells(edge):
                degree[cell] = degree.get(cell, 0) + 1
    if max(degree.values(), default=0) >= 3:
        return []
    return [err("branch_required", "no_branch", "no walkable cell has degree >= 3")]


def check_figures(roles: dict[str, str], rects: dict[str, Rect]) -> Errors:
    figures = sorted(c for c, role in roles.items() if role == "figure" and c in rects)
    return [
        err("figure_not_adjacent", "figure_adjacent", f"{a} touches {b}")
        for i, a in enumerate(figures)
        for b in figures[i + 1 :]
        if adjacent(rects[a], rects[b])
    ]


def check_voids(roles: dict[str, str], edges: list[dict[str, str]], budget: dict[str, int]) -> Errors:
    errors = []
    voids = sorted(c for c, role in roles.items() if role == "void")
    if not budget["min"] <= len(voids) <= budget["max"]:
        errors.append(err("voids_never_traversable", "void_budget", f"{len(voids)} voids"))
    for void in voids:
        touching = [e for e in edges if void in edge_cells(e)]
        if not touching:
            errors.append(err("void_visible_from_walkable", "void_not_visible", void))
        for edge in touching:
            other = next(c for c in edge_cells(edge) if c != void)
            if edge["connector"] != "closed_visible":
                errors.append(err("voids_never_traversable", "void_traversable", void))
            elif roles.get(other, "void") == "void":
                errors.append(err("void_visible_from_walkable", "void_not_visible", void))
    return errors
