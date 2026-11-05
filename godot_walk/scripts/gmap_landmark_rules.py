"""Static map-contract checks for gmap-0.7.0 landmarks."""

from __future__ import annotations

import math
from typing import Any

from gmap_geometry import polygon_rect
from gmap_landmark import (
    LANDMARKS,
    PORT_TYPE,
    cell_landmark,
    draw_plan,
    envelope_size,
    map_landmark,
    port_facet_indices,
    port_normals,
)
from gmap_rules import Errors, err

RULE = "landmark_contract"
EPS = 1e-6


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= EPS
    return left == right


def _metadata_errors(record: dict[str, Any], cell: dict[str, Any]) -> Errors:
    errors: Errors = []
    expected = cell_landmark(
        {"class": record["class"], "rotation_deg": _rotation_offset(record)}
    )
    for key in (
        "class",
        "inradius_m",
        "circumradius_m",
        "rotation_deg",
        "port_facet_indices",
        "status",
    ):
        if not _same(record.get(key), expected.get(key)):
            errors.append(err(RULE, "landmark_metadata_mismatch", f"{key} differs"))
    if cell.get("landmark") != expected:
        errors.append(err(RULE, "landmark_cell_metadata_mismatch", cell["cell_id"]))
    return errors


def _rotation_offset(record: dict[str, Any]) -> float:
    base = float(LANDMARKS[record["class"]]["rotation"])
    return (float(record["rotation_deg"]) - base) % 360.0


def _geometry_errors(cell: dict[str, Any], record: dict[str, Any]) -> Errors:
    errors: Errors = []
    rect = polygon_rect(cell["envelope_xz"])
    if rect is None:
        return [err(RULE, "landmark_envelope_not_rectangular", cell["cell_id"])]
    plan = {"class": record["class"], "rotation_deg": _rotation_offset(record)}
    expected_size = envelope_size(plan)
    if (rect[2] - rect[0], rect[3] - rect[1]) != expected_size:
        errors.append(err(RULE, "landmark_envelope_size_mismatch", cell["cell_id"]))
    ports = cell["required_ports"]
    if len(ports) > len(port_normals(plan)):
        errors.append(err(RULE, "landmark_port_count_exceeded", cell["cell_id"]))
    for port in ports:
        normal = tuple(port["normal"])
        if normal not in port_normals(plan):
            errors.append(err(RULE, "landmark_port_on_non_port_facet", port["port_id"]))
            continue
        axis = 0 if normal[0] else 1
        side = (
            rect[2]
            if normal == (1, 0)
            else rect[0]
            if normal == (-1, 0)
            else rect[3]
            if normal == (0, 1)
            else rect[1]
        )
        offset = port["pos_xz"][1] if axis == 0 else port["pos_xz"][0]
        expected_offset = (
            (rect[1] + rect[3]) / 2 if axis == 0 else (rect[0] + rect[2]) / 2
        )
        if (
            abs(port["pos_xz"][axis] - side) > EPS
            or abs(offset - expected_offset) > EPS
        ):
            errors.append(
                err(RULE, "landmark_port_not_facet_midpoint", port["port_id"])
            )
        if (
            port["compatibility_type"] != PORT_TYPE
            or port.get("placement", "standard") != "standard"
        ):
            errors.append(err(RULE, "landmark_port_not_standard", port["port_id"]))
        length = (
            2
            * float(LANDMARKS[record["class"]]["inradius"])
            * math.tan(math.pi / int(LANDMARKS[record["class"]]["sides"]))
        )
        if length < 3.0:
            errors.append(
                err(
                    RULE,
                    "landmark_facet_too_short",
                    f"{record['class']}: {length:.3f} m",
                )
            )
    return errors


def landmark_errors(document: dict[str, Any]) -> Errors:
    errors: Errors = []
    cells = document["cells"]
    landmark_cells = [cell for cell in cells if cell.get("landmark")]
    record = document.get("landmark")
    plan = draw_plan(
        document["seed"], document.get("attempt", 0), document["growth_cell_target"]
    )
    if plan is None:
        if (
            record is not None
            or landmark_cells
            or any(cell.get("shape_stage_target") == 3 for cell in cells)
        ):
            errors.append(
                err(
                    RULE,
                    "landmark_draw_mismatch",
                    "map has a landmark although the named stream drew none",
                )
            )
        return errors
    if record is None:
        return [
            err(
                RULE,
                "landmark_draw_missing",
                "named stream drew a landmark but map metadata is absent",
            )
        ]
    expected_record = map_landmark(
        plan, record["status"], record.get("cell_id"), record.get("reason")
    )
    if record != expected_record:
        errors.append(
            err(
                RULE,
                "landmark_draw_mismatch",
                "class, target step, rotation, facets or status differs from the named stream",
            )
        )
    if len(landmark_cells) > 1:
        errors.append(err(RULE, "multiple_landmarks", str(len(landmark_cells))))
    if record["status"] == "unplaced":
        if landmark_cells:
            errors.append(
                err(RULE, "unplaced_landmark_has_cell", landmark_cells[0]["cell_id"])
            )
        return errors
    if len(landmark_cells) != 1:
        return errors + [
            err(RULE, "placed_landmark_cell_missing", str(record.get("cell_id")))
        ]
    cell = landmark_cells[0]
    if record.get("cell_id") != cell["cell_id"]:
        errors.append(err(RULE, "landmark_cell_reference_mismatch", cell["cell_id"]))
    if (
        cell.get("shape_stage_target") != 3
        or record["class"] not in cell["allowed_primitives"]
    ):
        errors.append(err(RULE, "landmark_stage_target_invalid", cell["cell_id"]))
    if (
        cell.get("module")
        or cell.get("mode", "standard") == "degenerate"
        or cell.get("diagonal_link_chamfer")
    ):
        errors.append(err(RULE, "landmark_excluded_feature", cell["cell_id"]))
    neighbors = {
        port.split(":")[0]
        for edge in document["edges"]
        if edge.get("kind") != "diagonal"
        and cell["cell_id"] in (edge["from"].split(":")[0], edge["to"].split(":")[0])
        for port in (edge["from"], edge["to"])
        if port.split(":")[0] != cell["cell_id"]
    }
    modules = {record["cell_id"] for record in cells if record.get("module")}
    if neighbors & modules:
        errors.append(
            err(
                RULE,
                "landmark_module_connection",
                ", ".join(sorted(neighbors & modules)),
            )
        )
    growth_step = (
        int(cell["cell_id"][1:])
        if cell["cell_id"].startswith("c") and cell["cell_id"][1:].isdigit()
        else 0
    )
    if growth_step < record["target_step"]:
        errors.append(err(RULE, "landmark_before_target_step", cell["cell_id"]))
    reserved = {
        cell_id
        for zone in document.get("diagonal_links", {}).get(
            "reserved_diagonal_zones", []
        )
        for cell_id in zone["endpoint_ids"]
    }
    diagonal_endpoints = {
        port.split(":")[0]
        for edge in document["edges"]
        if edge.get("kind") == "diagonal"
        for port in (edge["from"], edge["to"])
    }
    if cell["cell_id"] in reserved | diagonal_endpoints:
        errors.append(err(RULE, "landmark_diagonal_endpoint", cell["cell_id"]))
    plan = {"class": record["class"], "rotation_deg": _rotation_offset(record)}
    if record.get("port_facet_indices") != port_facet_indices(plan):
        errors.append(err(RULE, "landmark_port_facet_indices", cell["cell_id"]))
    errors += _metadata_errors(record, cell)
    errors += _geometry_errors(cell, record)
    return errors
