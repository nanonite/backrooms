"""Schema, hash and rule validation for generative map documents."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, sha256_file
from gmap_build import (
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
    GENERATOR_VERSION_V11,
    GENERATOR_VERSION_V12,
    GENERATOR_VERSION_V13,
    GENERATOR_VERSION_V61,
    MARGIN_VERSIONS,
    MODULE_VERSIONS,
    STAGE2_VERSIONS,
    rule_ids,
)
from gmap_diagonal_rules import diagonal_errors
from gmap_diagonal_site_rules import reservation_errors
from gmap_landmark_rules import landmark_errors
from gmap_library import Library, load_library
from gmap_light import light_errors
from gmap_margin_rules import check_lattice_ports, margin_errors
from gmap_module_rules import module_errors
from gmap_palette import palette_errors
from gmap_palette_registry import load_registry_file
from gmap_reverb import reverb_errors
from gmap_rules import (
    Errors,
    check_branch,
    check_edges,
    check_figures,
    check_lattice,
    check_overlaps,
    check_tree,
    check_voids,
    err,
    parse_rects,
    port_index,
)
from gmap_stage2 import stage2_errors
from gmap_surface import surface_errors
from library_index import load_json

SCHEMA_PATH = Path("godot_walk/room_catalog/generative_map.schema.json")


def schema_errors(document: dict[str, Any], schema: dict[str, Any]) -> Errors:
    validator = Draft202012Validator(schema)
    return [
        err(
            "schema",
            "schema",
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}",
        )
        for e in sorted(
            validator.iter_errors(document),
            key=lambda e: list(map(str, e.absolute_path)),
        )
    ]


def check_hashes(document: dict[str, Any], root: Path) -> Errors:
    errors = []
    for key, code in (
        ("library_index", "stale_index_hash"),
        ("catalog_snapshot", "stale_snapshot_hash"),
    ):
        ref = document[key]
        path = root / ref["path"]
        if not path.is_file():
            errors.append(err(key, code, f"{ref['path']} is missing"))
        elif sha256_file(path) != ref["sha256"]:
            errors.append(
                err(key, code, f"{ref['path']} no longer matches its recorded hash")
            )
    if document.get("generator_version") == GENERATOR_VERSION_V13:
        from gmap_template import consolidated_records

        references = [("template", document["template"])]
        references.extend(
            (f"module_metadata:{entry['module_id']}", entry)
            for entry in document["module_metadata"]
        )
        for label, reference in references:
            if not isinstance(reference, dict) or not isinstance(
                reference.get("path"), str
            ):
                errors.append(err("template", "metadata_reference_invalid", label))
                continue
            path = root / reference["path"]
            if not path.is_file() or sha256_file(path) != reference.get("sha256"):
                errors.append(err("template", "stale_metadata_reference", label))
        try:
            authoritative = consolidated_records(root)
        except (OSError, ValueError, TypeError) as error:
            errors.append(
                err(
                    "module_metadata_pins",
                    "module_metadata_catalog_invalid",
                    str(error),
                )
            )
            authoritative = {}
        placed = {
            cell["module"]["module_id"]: cell
            for cell in document["cells"]
            if cell.get("module")
        }
        pinned = {entry["module_id"]: entry for entry in document["module_metadata"]}
        if len(pinned) != len(document["module_metadata"]):
            errors.append(
                err(
                    "module_metadata_pins",
                    "duplicate_module_metadata_pin",
                    "module ids must be unique",
                )
            )
        if set(pinned) != set(placed):
            errors.append(
                err(
                    "module_metadata_pins",
                    "module_metadata_coverage_mismatch",
                    "pins must match modules placed in cells",
                )
            )
        for module_id, cell in placed.items():
            expected = authoritative.get(module_id)
            if expected is None:
                errors.append(
                    err("module_metadata_pins", "module_metadata_missing", module_id)
                )
                continue
            wanted = {"module_id": module_id, **expected["reference"]}
            if pinned.get(module_id) != wanted:
                errors.append(
                    err(
                        "module_metadata_pins",
                        "module_metadata_pin_mismatch",
                        module_id,
                    )
                )
            if cell.get("module_profile") != expected["reference"]:
                errors.append(
                    err(
                        "module_metadata_pins",
                        "module_profile_reference_mismatch",
                        module_id,
                    )
                )
        door_ids = {
            door["port_id"] for cell in document["cells"] for door in cell["doors"]
        }
        for edge in document["edges"]:
            if edge.get("door_id") not in door_ids or edge.get("door_id") not in (
                edge["from"],
                edge["to"],
            ):
                errors.append(err("door_policy", "edge_door_id_mismatch", edge["from"]))
        errors += check_template_values(document, root)
    return errors


def check_template_values(document: dict[str, Any], root: Path = ROOT) -> Errors:
    """Re-derive and compare every field projected from pinned template metadata."""
    from gmap_template import add_template_fields

    expected = deepcopy(document)
    for field in ("template", "module_metadata"):
        expected.pop(field, None)
    derived_fields = (
        "module_profile",
        "mood",
        "absorption",
        "volume",
        "doors",
        "mutation",
    )
    for cell in expected["cells"]:
        for field in derived_fields:
            cell.pop(field, None)
    for edge in expected["edges"]:
        edge.pop("door_id", None)
    try:
        add_template_fields(expected, root)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        return [err("template", "template_values_unavailable", str(error))]

    errors: Errors = []
    for field in ("template", "module_metadata"):
        if document.get(field) != expected.get(field):
            errors.append(err("template", "template_value_mismatch", field))
    fields_by_cell = {
        cell["cell_id"]: cell for cell in expected["cells"]
    }
    for cell in document["cells"]:
        generated = fields_by_cell[cell["cell_id"]]
        for field in derived_fields:
            if cell.get(field) != generated.get(field):
                errors.append(
                    err(
                        "template",
                        "template_cell_value_mismatch",
                        f"{cell['cell_id']}.{field}",
                    )
                )
    for edge, generated in zip(document["edges"], expected["edges"], strict=True):
        if edge.get("door_id") != generated.get("door_id"):
            errors.append(
                err("template", "template_edge_value_mismatch", edge["from"])
            )
    return errors


def check_rules_listed(document: dict[str, Any]) -> Errors:
    missing = sorted(
        set(rule_ids(document["generator_version"])) - set(document["rules"])
    )
    return [err("rules", "rules_incomplete", ", ".join(missing))] if missing else []


def _load_library_for_validation(
    document: dict[str, Any], root: Path
) -> tuple[Library | None, Errors]:
    """Load the V0.8 dependency once, reporting a blocked library instead of raising."""
    ref = document["library_index"]
    path = root / ref["path"]
    if not path.is_file():
        return None, [
            err(
                "library_index",
                "library_index_unavailable",
                f"{ref['path']} is missing",
            )
        ]
    try:
        return load_library(path, root), []
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        OverflowError,
    ) as error:
        # Malformed index JSON can fail at any structure access; report it as unavailable.
        return None, [
            err(
                "library_index",
                "library_index_unavailable",
                f"{ref['path']} could not be loaded: {error}",
            )
        ]


def rule_errors(document: dict[str, Any], root: Path = ROOT) -> Errors:
    cells, edges = document["cells"], document["edges"]
    rects, errors = parse_rects(cells)
    light_library = None
    if document["generator_version"] in (
        GENERATOR_VERSION_V8,
        GENERATOR_VERSION_V9,
        GENERATOR_VERSION_V10,
        GENERATOR_VERSION_V11,
        GENERATOR_VERSION_V12,
        GENERATOR_VERSION_V13,
    ):
        light_library, library_errors = _load_library_for_validation(document, root)
        errors += library_errors
    library_unavailable = (
        document["generator_version"]
        in (
            GENERATOR_VERSION_V8,
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        )
        and light_library is None
    )
    map_cells = [c for c in cells if not c.get("diagonal_passage")]
    map_rects = {
        key: value
        for key, value in rects.items()
        if key in {c["cell_id"] for c in map_cells}
    }
    errors += check_lattice(
        map_cells, document["lattice"]["unit_m"], document["lattice"].get("port_step_m")
    )
    errors += check_overlaps(map_rects)
    ports, port_problems = port_index(cells)
    errors += port_problems + check_edges(edges, ports, rects)
    if document["generator_version"] in MARGIN_VERSIONS:
        margin_cells = cells
        margin_document = document
        margin_rects = rects
        if document["generator_version"] in (
            GENERATOR_VERSION_V6,
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
            GENERATOR_VERSION_V8,
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        ):
            margin_cells = [
                {
                    **c,
                    "required_ports": [
                        p
                        for p in c["required_ports"]
                        if min(abs(p["normal"][0]), abs(p["normal"][1])) < 0.5
                    ],
                }
                for c in cells
                if not c.get("diagonal_passage")
            ]
            margin_document = {**document, "cells": margin_cells}
            margin_rects = {c["cell_id"]: rects[c["cell_id"]] for c in margin_cells}
        errors += check_lattice_ports(
            margin_cells, document["lattice"].get("port_step_m", 1.0)
        )
        errors += margin_errors(margin_document, margin_rects)
    if document["generator_version"] in MODULE_VERSIONS and not library_unavailable:
        if document["generator_version"] in (
            GENERATOR_VERSION_V6,
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
            GENERATOR_VERSION_V8,
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        ):
            base = {
                **document,
                "cells": map_cells,
                "edges": [
                    e
                    for e in edges
                    if e.get("kind") not in ("diagonal", "elevation_loop")
                ],
            }
            errors += module_errors(base, map_rects, root, light_library)
        else:
            errors += module_errors(document, rects, root, light_library)
    if document["generator_version"] in STAGE2_VERSIONS:
        errors += stage2_errors(document)
    if document["generator_version"] in (
        GENERATOR_VERSION_V7,
        GENERATOR_VERSION_V8,
        GENERATOR_VERSION_V9,
        GENERATOR_VERSION_V10,
        GENERATOR_VERSION_V11,
        GENERATOR_VERSION_V12,
        GENERATOR_VERSION_V13,
    ):
        errors += landmark_errors(document)
    palette_issues: Errors = []
    if (
        document["generator_version"]
        in (
            GENERATOR_VERSION_V5,
            GENERATOR_VERSION_V6,
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
            GENERATOR_VERSION_V8,
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        )
        and not library_unavailable
    ):
        checks_document = document
        if document["generator_version"] in (
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        ):
            from gmap_elevation import strip_elevation

            checks_document = strip_elevation(document)
        palette_issues = palette_errors(checks_document, root, light_library)
        errors += palette_issues
    palette_registry_blocked = any(
        error["code"]
        in {
            "palette_registry_missing",
            "stale_palette_registry",
            "palette_registry_invalid",
            "palette_registry_not_canonical",
        }
        for error in palette_issues
    )
    if (
        document["generator_version"]
        in (
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        )
        and not library_unavailable
        and not palette_registry_blocked
    ):
        ref = document.get("palette_registry")
        path = root / ref["path"] if ref else None
        if path is not None and path.is_file() and sha256_file(path) == ref["sha256"]:
            try:
                errors += surface_errors(document, load_registry_file(path))
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append(
                    err(
                        "surface_layer",
                        "surface_registry_invalid",
                        f"{ref['path']} could not be loaded: {error}",
                    )
                )
    roles = {cell["cell_id"]: cell["role"] for cell in cells}
    walkable = sorted(c for c, role in roles.items() if role != "void")
    if document["generator_version"] in (
        GENERATOR_VERSION_V6,
        GENERATOR_VERSION_V61,
        GENERATOR_VERSION_V7,
        GENERATOR_VERSION_V8,
        GENERATOR_VERSION_V9,
        GENERATOR_VERSION_V10,
        GENERATOR_VERSION_V11,
        GENERATOR_VERSION_V12,
        GENERATOR_VERSION_V13,
    ):
        tree_walkable = [
            c
            for c in walkable
            if not next(x for x in cells if x["cell_id"] == c).get("diagonal_passage")
        ]
        tree_edges = [
            e for e in edges if e.get("kind") not in ("diagonal", "elevation_loop")
        ]
        errors += check_tree(tree_walkable, tree_edges)
        errors += diagonal_errors(document)
        if document["generator_version"] in (
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
            GENERATOR_VERSION_V8,
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        ):
            errors += reservation_errors(document)
    else:
        errors += check_tree(walkable, edges)
    errors += check_branch(walkable, edges)
    errors += check_figures(roles, rects) + check_voids(
        roles, edges, document["void_budget"]
    )
    if (
        document["generator_version"]
        in (
            GENERATOR_VERSION_V8,
            GENERATOR_VERSION_V9,
            GENERATOR_VERSION_V10,
            GENERATOR_VERSION_V11,
            GENERATOR_VERSION_V12,
            GENERATOR_VERSION_V13,
        )
        and light_library is not None
    ):
        errors += light_errors(document, light_library)
    if document["generator_version"] in (
        GENERATOR_VERSION_V10,
        GENERATOR_VERSION_V11,
        GENERATOR_VERSION_V12,
        GENERATOR_VERSION_V13,
    ):
        from gmap_elevation import elevation_errors

        errors += elevation_errors(document)
    if document["generator_version"] in (
        GENERATOR_VERSION_V11,
        GENERATOR_VERSION_V12,
        GENERATOR_VERSION_V13,
    ):
        errors += reverb_errors(document)
    return errors


def validate_document(document: dict[str, Any], root: Path = ROOT) -> Errors:
    """All errors for a map: schema first (rules need a well-formed document)."""
    schema_path = (
        Path("godot_walk/room_catalog/generative_map_v2.schema.json")
        if document.get("schema_version") == 2
        else SCHEMA_PATH
    )
    errors = schema_errors(document, load_json(root / schema_path))
    if errors:
        return errors
    return (
        check_hashes(document, root)
        + check_rules_listed(document)
        + rule_errors(document, root)
    )
