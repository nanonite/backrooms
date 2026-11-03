"""Schema, hash and rule validation for generative map documents."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, sha256_file  # noqa: E402
from gmap_build import GENERATOR_VERSION_V5, MARGIN_VERSIONS, MODULE_VERSIONS, STAGE2_VERSIONS, rule_ids  # noqa: E402
from gmap_margin_rules import check_lattice_ports, margin_errors  # noqa: E402
from gmap_module_rules import module_errors  # noqa: E402
from gmap_palette import palette_errors  # noqa: E402
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
    errors += check_lattice(cells, document["lattice"]["unit_m"], document["lattice"].get("port_step_m"))
    errors += check_overlaps(rects)
    ports, port_problems = port_index(cells)
    errors += port_problems + check_edges(edges, ports, rects)
    if document["generator_version"] in MARGIN_VERSIONS:
        errors += check_lattice_ports(cells, document["lattice"].get("port_step_m", 1.0))
        errors += margin_errors(document, rects)
    if document["generator_version"] in MODULE_VERSIONS:
        errors += module_errors(document, rects, root)
    if document["generator_version"] in STAGE2_VERSIONS:
        errors += stage2_errors(document)
    if document["generator_version"] == GENERATOR_VERSION_V5:
        errors += palette_errors(document, root)
    roles = {cell["cell_id"]: cell["role"] for cell in cells}
    walkable = sorted(c for c, role in roles.items() if role != "void")
    errors += check_tree(walkable, edges) + check_branch(walkable, edges)
    errors += check_figures(roles, rects) + check_voids(roles, edges, document["void_budget"])
    return errors


def validate_document(document: dict[str, Any], root: Path = ROOT) -> Errors:
    """All errors for a map: schema first (rules need a well-formed document)."""
    errors = schema_errors(document, load_json(root / SCHEMA_PATH))
    if errors:
        return errors
    return check_hashes(document, root) + check_rules_listed(document) + rule_errors(document, root)
