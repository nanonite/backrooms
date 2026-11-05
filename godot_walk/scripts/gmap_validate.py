"""Schema, hash and rule validation for generative map documents."""

from __future__ import annotations

import sys
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
    v8_library = None
    if document["generator_version"] == GENERATOR_VERSION_V8:
        v8_library, library_errors = _load_library_for_validation(document, root)
        errors += library_errors
    library_unavailable = (
        document["generator_version"] == GENERATOR_VERSION_V8 and v8_library is None
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
        ):
            base = {
                **document,
                "cells": map_cells,
                "edges": [e for e in edges if e.get("kind") != "diagonal"],
            }
            errors += module_errors(base, map_rects, root, v8_library)
        else:
            errors += module_errors(document, rects, root, v8_library)
    if document["generator_version"] in STAGE2_VERSIONS:
        errors += stage2_errors(document)
    if document["generator_version"] in (GENERATOR_VERSION_V7, GENERATOR_VERSION_V8):
        errors += landmark_errors(document)
    if (
        document["generator_version"]
        in (
            GENERATOR_VERSION_V5,
            GENERATOR_VERSION_V6,
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
            GENERATOR_VERSION_V8,
        )
        and not library_unavailable
    ):
        errors += palette_errors(document, root, v8_library)
    roles = {cell["cell_id"]: cell["role"] for cell in cells}
    walkable = sorted(c for c, role in roles.items() if role != "void")
    if document["generator_version"] in (
        GENERATOR_VERSION_V6,
        GENERATOR_VERSION_V61,
        GENERATOR_VERSION_V7,
        GENERATOR_VERSION_V8,
    ):
        tree_walkable = [
            c
            for c in walkable
            if not next(x for x in cells if x["cell_id"] == c).get("diagonal_passage")
        ]
        tree_edges = [e for e in edges if e.get("kind") != "diagonal"]
        errors += check_tree(tree_walkable, tree_edges)
        errors += diagonal_errors(document)
        if document["generator_version"] in (
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
            GENERATOR_VERSION_V8,
        ):
            errors += reservation_errors(document)
    else:
        errors += check_tree(walkable, edges)
    errors += check_branch(walkable, edges)
    errors += check_figures(roles, rects) + check_voids(
        roles, edges, document["void_budget"]
    )
    if document["generator_version"] == GENERATOR_VERSION_V8 and v8_library is not None:
        errors += light_errors(document, v8_library)
    return errors


def validate_document(document: dict[str, Any], root: Path = ROOT) -> Errors:
    """All errors for a map: schema first (rules need a well-formed document)."""
    errors = schema_errors(document, load_json(root / SCHEMA_PATH))
    if errors:
        return errors
    return (
        check_hashes(document, root)
        + check_rules_listed(document)
        + rule_errors(document, root)
    )
