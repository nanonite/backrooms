"""gmap-0.2.0 rules: standard doorway margins, degenerate corner doorways and their budget."""

from __future__ import annotations

from typing import Any

from gmap_degenerate import ORIGIN_CELL, corner_cells
from gmap_geometry import Rect, Vec
from gmap_rules import Errors, err

STANDARD_RULE = "standard_doorway_margin"
DEGENERATE_RULE = "degenerate_only_in_degenerate_cells"


def check_lattice_ports(cells: list[dict[str, Any]], step: float) -> Errors:
    """Ports must sit on the lattice's port step (0.5 m in gmap-0.2.0)."""
    errors = []
    for cell in cells:
        for port in cell["required_ports"]:
            if not all(abs(v / step - round(v / step)) <= 1e-9 for v in port["pos_xz"]):
                errors.append(err("ports_on_lattice", "port_off_step", port["port_id"]))
    return errors


def check_placements(document: dict[str, Any], rects: dict[str, Rect]) -> Errors:
    """Judge every port against its own cell's envelope corners.

    A standard port keeps >= 1.5 m from both ends of its envelope side. A degenerate port
    is one that does not, is recorded as such, and sits in a degenerate cell. The neighbour
    of a corner doorway keeps a standard port: its wall continues past the doorway.
    """
    errors: Errors = []
    for cell in document["cells"]:
        mode = cell.get("mode", "standard")
        if cell["cell_id"] not in rects:
            continue
        for port in cell["required_ports"]:
            normal: Vec = tuple(port["normal"])  # type: ignore[assignment]
            owners = corner_cells({cell["cell_id"]: rects[cell["cell_id"]]}, {cell["cell_id"]: normal}, tuple(port["pos_xz"]))
            label = port.get("placement", "standard")
            if label == "standard" and owners:
                errors.append(err(STANDARD_RULE, "standard_port_margin", f"{port['port_id']}: corner within 1.5 m"))
            elif label == "degenerate" and not owners:
                errors.append(err(DEGENERATE_RULE, "degenerate_label_unneeded", port["port_id"]))
            elif label == "degenerate" and mode != "degenerate":
                errors.append(err(DEGENERATE_RULE, "degenerate_in_standard_cell", f"{port['port_id']} in {cell['cell_id']}"))
    return errors


def check_budget(document: dict[str, Any]) -> Errors:
    budget = document.get("degenerate_budget")
    if budget is None:
        return [err(DEGENERATE_RULE, "degenerate_budget_missing", "degenerate_budget is required in gmap-0.2.0")]
    errors: Errors = []
    degenerate = sorted(c["cell_id"] for c in document["cells"] if c.get("mode", "standard") == "degenerate")
    if len(degenerate) != budget["used"]:
        errors.append(err(DEGENERATE_RULE, "degenerate_budget_used", f"{len(degenerate)} cells, used={budget['used']}"))
    if budget["used"] > budget["max"]:
        errors.append(err(DEGENERATE_RULE, "degenerate_budget_exceeded", f"used {budget['used']} > max {budget['max']}"))
    origin = document["cells"][0]["cell_id"] if document["cells"] else ORIGIN_CELL
    for cell in document["cells"]:
        if cell.get("mode", "standard") == "degenerate" and (
            cell["role"] in ("figure", "void") or cell["cell_id"] == origin
        ):
            errors.append(err(DEGENERATE_RULE, "degenerate_cell_not_allowed", cell["cell_id"]))
    return errors


def margin_errors(document: dict[str, Any], rects: dict[str, Rect]) -> Errors:
    return check_placements(document, rects) + check_budget(document)
