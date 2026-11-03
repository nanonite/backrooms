"""Schema, hash and rule validation for generative map documents."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, sha256_file  # noqa: E402
from gmap_build import GENERATOR_VERSION_V5, GENERATOR_VERSION_V6, MARGIN_VERSIONS, MODULE_VERSIONS, STAGE2_VERSIONS, rule_ids  # noqa: E402
from gmap_margin_rules import check_lattice_ports, margin_errors  # noqa: E402
from gmap_module_rules import module_errors  # noqa: E402
from gmap_palette import palette_errors  # noqa: E402
from gmap_diagonal_rules import diagonal_errors  # noqa: E402
from gmap_stage2 import stage2_errors  # noqa: E402
from gmap_rules import (  # noqa: E402
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
from library_index import load_json  # noqa: E402

SCHEMA_PATH = Path("godot_walk/room_catalog/generative_map.schema.json")


def schema_errors(document: dict[str, Any], schema: dict[str, Any]) -> Errors:
    validator = Draft202012Validator(schema)
    return [
        err("schema", "schema", f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}")
        for e in sorted(validator.iter_errors(document), key=lambda e: list(map(str, e.absolute_path)))
    ]


def check_hashes(document: dict[str, Any], root: Path) -> Errors:
    errors = []
    for key, code in (("library_index", "stale_index_hash"), ("catalog_snapshot", "stale_snapshot_hash")):
        ref = document[key]
        path = root / ref["path"]
        if not path.is_file():
            errors.append(err(key, code, f"{ref['path']} is missing"))
        elif sha256_file(path) != ref["sha256"]:
            errors.append(err(key, code, f"{ref['path']} no longer matches its recorded hash"))
    return errors


def check_rules_listed(document: dict[str, Any]) -> Errors:
    missing = sorted(set(rule_ids(document["generator_version"])) - set(document["rules"]))
    return [err("rules", "rules_incomplete", ", ".join(missing))] if missing else []


def rule_errors(document: dict[str, Any], root: Path = ROOT) -> Errors:
    cells, edges = document["cells"], document["edges"]
    rects, errors = parse_rects(cells)
    map_cells = [c for c in cells if not c.get("diagonal_passage")]
    map_rects = {key: value for key, value in rects.items() if key in {c["cell_id"] for c in map_cells}}
    errors += check_lattice(map_cells, document["lattice"]["unit_m"], document["lattice"].get("port_step_m"))
    errors += check_overlaps(map_rects)
    ports, port_problems = port_index(cells)
    errors += port_problems + check_edges(edges, ports, rects)
    if document["generator_version"] in MARGIN_VERSIONS:
        margin_cells = cells
        margin_document = document
        margin_rects = rects
        if document["generator_version"] == GENERATOR_VERSION_V6:
            margin_cells = [{**c, "required_ports": [p for p in c["required_ports"] if min(abs(p["normal"][0]), abs(p["normal"][1])) < 0.5]}
                            for c in cells if not c.get("diagonal_passage")]
            margin_document = {**document, "cells": margin_cells}
            margin_rects = {c["cell_id"]: rects[c["cell_id"]] for c in margin_cells}
        errors += check_lattice_ports(margin_cells, document["lattice"].get("port_step_m", 1.0))
        errors += margin_errors(margin_document, margin_rects)
    if document["generator_version"] in MODULE_VERSIONS:
        if document["generator_version"] == GENERATOR_VERSION_V6:
            base = {**document, "cells": map_cells, "edges": [e for e in edges if e.get("kind") != "diagonal"]}
            errors += module_errors(base, map_rects, root)
        else:
            errors += module_errors(document, rects, root)
    if document["generator_version"] in STAGE2_VERSIONS:
        errors += stage2_errors(document)
    if document["generator_version"] in (GENERATOR_VERSION_V5, GENERATOR_VERSION_V6):
        errors += palette_errors(document, root)
    roles = {cell["cell_id"]: cell["role"] for cell in cells}
    walkable = sorted(c for c, role in roles.items() if role != "void")
    if document["generator_version"] == GENERATOR_VERSION_V6:
        tree_walkable = [c for c in walkable if not next(x for x in cells if x["cell_id"] == c).get("diagonal_passage")]
        tree_edges = [e for e in edges if e.get("kind") != "diagonal"]
        errors += check_tree(tree_walkable, tree_edges)
        errors += diagonal_errors(document)
    else:
        errors += check_tree(walkable, edges)
    errors += check_branch(walkable, edges)
    errors += check_figures(roles, rects) + check_voids(roles, edges, document["void_budget"])
    return errors


def validate_document(document: dict[str, Any], root: Path = ROOT) -> Errors:
    """All errors for a map: schema first (rules need a well-formed document)."""
    errors = schema_errors(document, load_json(root / SCHEMA_PATH))
    if errors:
        return errors
    return check_hashes(document, root) + check_rules_listed(document) + rule_errors(document, root)
