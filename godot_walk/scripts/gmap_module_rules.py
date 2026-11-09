"""gmap-0.3.0 rules: library modules as proposed, untested leaf cells (issue 188)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from deterministic_json import sha256_file
from gmap_fill import SOCKET_TOLERANCE_M
from gmap_geometry import Rect, adjacent, near
from gmap_library import Library, LibraryModule, bbox, load_library
from gmap_modules import LANDING_CLEARANCE_M, MODULE_BUDGET, OVERHANG_MARGIN_M
from gmap_rules import CONNECTION_STATUSES, Errors, err
from gmap_transform import rotate_vector, world_point

BUDGET_RULE = "module_budget"
LEAF_RULE = "module_leaf_proposed_untested"
LANDING_RULE = "module_socket_landing"
ONCE_RULE = "module_usable_once"
# The module sits LANDING_CLEARANCE_M off the parent wall, so a bbox that fills its cell overhangs the far side by that much.
INSIDE_EPSILON_M = LANDING_CLEARANCE_M + 1e-6


def module_cells(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [cell for cell in document["cells"] if cell.get("module")]


def check_budget(document: dict[str, Any], cells: list[dict[str, Any]]) -> Errors:
    errors: Errors = []
    budget = document.get("module_budget")
    if budget is None:
        return [
            err(
                BUDGET_RULE,
                "module_budget_missing",
                "module_budget is required in gmap-0.3.0",
            )
        ]
    if (budget["min"], budget["max"]) != (MODULE_BUDGET["min"], MODULE_BUDGET["max"]):
        errors.append(
            err(
                BUDGET_RULE,
                "module_budget_changed",
                f"{budget['min']}..{budget['max']}",
            )
        )
    if budget["used"] != len(cells):
        errors.append(
            err(
                BUDGET_RULE,
                "module_budget_used",
                f"{len(cells)} module cells, used={budget['used']}",
            )
        )
    if not budget["min"] <= len(cells) <= budget["max"]:
        errors.append(
            err(BUDGET_RULE, "module_budget_range", f"{len(cells)} module cells")
        )
    return errors


def check_once(cells: list[dict[str, Any]]) -> Errors:
    seen: dict[str, str] = {}
    errors: Errors = []
    for cell in cells:
        module_id = cell["module"]["module_id"]
        if module_id in seen:
            errors.append(
                err(
                    ONCE_RULE,
                    "module_placed_twice",
                    f"{module_id} in {seen[module_id]} and {cell['cell_id']}",
                )
            )
        seen[module_id] = cell["cell_id"]
    return errors


def check_records(
    document: dict[str, Any], cells: list[dict[str, Any]], root: Path
) -> Errors:
    """Every recorded metadata file must still hash to what the map says."""
    errors: Errors = []
    records = [
        ("library_index", r)
        for r in document["library_index"].get("metadata_records", [])
    ]
    records += [(c["cell_id"], c["module"]["metadata_record"]) for c in cells]
    for owner, record in records:
        path = root / record["path"]
        if not path.is_file():
            errors.append(
                err(
                    LEAF_RULE,
                    "stale_metadata_record",
                    f"{owner}: {record['path']} is missing",
                )
            )
        elif sha256_file(path) != record["sha256"]:
            errors.append(
                err(
                    LEAF_RULE,
                    "stale_metadata_record",
                    f"{owner}: {record['path']} no longer matches its hash",
                )
            )
    return errors


def lookup(library: Library, module_id: str, version: int) -> LibraryModule | None:
    return next(
        (
            m
            for m in library.modules
            if (m.module_id, m.version) == (module_id, version)
        ),
        None,
    )


def check_cell(
    cell: dict[str, Any], rect: Rect, library: Library, edges: dict[str, dict[str, str]]
) -> Errors:
    """One module cell: usable module, leaf, landed socket, footprint inside, status recorded."""
    label, placement = cell["cell_id"], cell["module"]
    module = lookup(library, placement["module_id"], placement["version"])
    if module is None:
        return [
            err(
                LANDING_RULE,
                "module_unknown",
                f"{label}: {placement['module_id']} is not in the library index",
            )
        ]
    errors: Errors = []
    if not module.layout_usable:
        errors.append(
            err(LEAF_RULE, "module_not_layout_usable", f"{label}: {module.module_id}")
        )
    if cell["role"] != module.form_role or cell["rarity_tier"] != module.rarity_tier:
        errors.append(
            err(
                LEAF_RULE,
                "module_role_mismatch",
                f"{label}: role/tier differ from the accepted metadata",
            )
        )
    if cell.get("mode", "standard") != "standard":
        errors.append(err(LEAF_RULE, "module_cell_not_standard", label))
    if placement["metadata_record"] != module.metadata_record:
        errors.append(
            err(
                LEAF_RULE,
                "stale_metadata_record",
                f"{label}: record differs from the one the library reads",
            )
        )
    if placement["rotation_deg"] not in (0, 90, 180, 270):
        return errors + [
            err(
                LANDING_RULE, "module_rotation", f"{label}: {placement['rotation_deg']}"
            )
        ]
    if len(cell["required_ports"]) != 1:
        return errors + [
            err(
                LEAF_RULE,
                "module_not_leaf",
                f"{label}: {len(cell['required_ports'])} ports",
            )
        ]
    errors += check_socket(cell, rect, module, edges)
    return errors


def check_socket(
    cell: dict[str, Any],
    rect: Rect,
    module: LibraryModule,
    edges: dict[str, dict[str, str]],
) -> Errors:
    label, placement = cell["cell_id"], cell["module"]
    port = cell["required_ports"][0]
    socket = next(
        (s for s in module.sockets if s.socket_id == placement["socket_id"]), None
    )
    if socket is None or not socket.tested:
        return [
            err(
                LANDING_RULE,
                "module_socket_untested",
                f"{label}: {placement['socket_id']}",
            )
        ]
    errors: Errors = []
    turns = placement["rotation_deg"] // 90
    placed = world_point(
        socket.pos, placement["rotation_deg"], tuple(placement["translation_xz"])
    )
    miss = math.hypot(placed[0] - port["pos_xz"][0], placed[1] - port["pos_xz"][1])
    normal = rotate_vector(socket.normal, turns)
    if miss > SOCKET_TOLERANCE_M + 1e-9:
        errors.append(err(LANDING_RULE, "socket_misses_port", f"{label}: {miss:.3f} m"))
    if math.hypot(normal[0] - port["normal"][0], normal[1] - port["normal"][1]) > 1e-6:
        errors.append(err(LANDING_RULE, "socket_normal_mismatch", label))
    if socket.compatibility_type != port["compatibility_type"]:
        errors.append(
            err(
                LANDING_RULE,
                "socket_type_mismatch",
                f"{label}: {socket.compatibility_type} vs {port['compatibility_type']}",
            )
        )
    points = [
        world_point(p, placement["rotation_deg"], tuple(placement["translation_xz"]))
        for p in module.footprint
    ]
    x0, z0, x1, z1 = bbox(tuple(points))
    if (
        x0 < rect[0] - INSIDE_EPSILON_M
        or z0 < rect[1] - INSIDE_EPSILON_M
        or x1 > rect[2] + INSIDE_EPSILON_M
        or z1 > rect[3] + INSIDE_EPSILON_M
    ):
        errors.append(err(LANDING_RULE, "footprint_outside_cell", label))
    edge = edges.get(port["port_id"])
    if edge is None or edge.get("connection_status") not in CONNECTION_STATUSES:
        errors.append(err(LEAF_RULE, "edge_not_proposed_untested", label))
    elif edge["connector"] != "direct":
        errors.append(err(LEAF_RULE, "module_edge_not_direct", label))
    return errors


def check_isolation(
    document: dict[str, Any],
    cells: list[dict[str, Any]],
    rects: dict[str, Rect],
    margin: float = 0.0,
) -> Errors:
    """A module cell touches no walkable cell but its parent: library walls overhang their footprint.
    With a `margin` (gmap-0.4.0) no other room may come within it, corners included."""
    roles = {c["cell_id"]: c["role"] for c in document["cells"]}
    errors: Errors = []
    for cell in cells:
        port_id = cell["required_ports"][0]["port_id"] if cell["required_ports"] else ""
        parents = {
            end.split(":")[0]
            for edge in document["edges"]
            if port_id in (edge["from"], edge["to"])
            for end in (edge["from"], edge["to"])
            if end != port_id
        }
        for other, rect in sorted(rects.items()):
            if (
                other != cell["cell_id"]
                and other not in parents
                and roles[other] != "void"
                and cell["cell_id"] in rects
                and (
                    near(rects[cell["cell_id"]], rect, margin)
                    if margin
                    else adjacent(rects[cell["cell_id"]], rect)
                )
            ):
                errors.append(
                    err(
                        LEAF_RULE,
                        "module_touches_neighbour",
                        f"{cell['cell_id']} touches {other}",
                    )
                )
    return errors


def check_untested_edges(edges: list[dict[str, str]], module_ports: set[str]) -> Errors:
    """Only module joints may carry connection_status, and it must be a known value."""
    errors: Errors = []
    for edge in edges:
        status = edge.get("connection_status")
        if status is None:
            continue
        if status not in CONNECTION_STATUSES:
            errors.append(
                err(
                    LEAF_RULE,
                    "connection_status_unknown",
                    f"{edge['from']} -> {edge['to']}: {status}",
                )
            )
        elif not {edge["from"], edge["to"]} & module_ports:
            errors.append(
                err(
                    LEAF_RULE,
                    "connection_status_on_generated_edge",
                    f"{edge['from']} -> {edge['to']}",
                )
            )
    return errors


def module_errors(
    document: dict[str, Any],
    rects: dict[str, Rect],
    root: Path,
    library: Library | None = None,
) -> Errors:
    cells = module_cells(document)
    errors = (
        check_budget(document, cells)
        + check_once(cells)
        + check_records(document, cells, root)
    )
    margin = (
        OVERHANG_MARGIN_M
        if document["generator_version"]
        in (
            "gmap-0.4.0",
            "gmap-0.5.0",
            "gmap-0.6.0",
            "gmap-0.6.1",
            "gmap-0.7.0",
            "gmap-0.8.0",
            "gmap-0.9.0",
            "gmap-0.10.0",
        )
        else 0.0
    )
    errors += check_isolation(document, cells, rects, margin)
    if library is None:
        library = load_library(root / document["library_index"]["path"], root)
    edges = {
        end: edge for edge in document["edges"] for end in (edge["from"], edge["to"])
    }
    for cell in cells:
        if cell["cell_id"] in rects:
            errors += check_cell(cell, rects[cell["cell_id"]], library, edges)
    ports = {c["required_ports"][0]["port_id"] for c in cells if c["required_ports"]}
    return errors + check_untested_edges(document["edges"], ports)
