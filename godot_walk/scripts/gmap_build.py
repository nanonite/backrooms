"""Assemble a generative map document from the staged draft."""

from __future__ import annotations

import random
from typing import Any

from gmap_assign import VOID_BUDGET, add_voids, assign_roles, assign_tiers
from gmap_geometry import rect_polygon
from gmap_grow import PORT_TYPE, Draft, GenerationError, RetryAttempt, grow
from gmap_library import Library, figure_classes

GENERATOR_VERSION = "gmap-0.1.0"
MAX_ATTEMPTS = 50
CELL_RANGE = (6, 20)
RULE_IDS = [
    "branch_required",
    "figure_not_adjacent",
    "no_envelope_overlap",
    "ports_on_lattice",
    "ports_on_shared_edge",
    "tree_no_loops",
    "void_visible_from_walkable",
    "voids_never_traversable",
]
CEILING = {"figure": [3.0, 6.0], "ground": [2.6, 4.8], "threshold": [2.6, 4.8], "void": [2.6, 4.8]}
PRIMITIVES_BY_STAGE = {0: ["box"], 1: ["box", "l_shape", "rectilinear_polygon"]}
STREAM_STRIDE = 1 << 32


def map_id_for(seed: int) -> str:
    return f"gmap-{seed}-{GENERATOR_VERSION}"


def attempt_rng(seed: int, attempt: int) -> random.Random:
    """Seed stream `attempt` of this seed; stream 0 is the seed itself."""
    return random.Random(seed + attempt * STREAM_STRIDE)


def attempt_once(rng: random.Random, cells: int, classes: list[tuple[int, int]]) -> Draft:
    draft = grow(rng, cells)
    assign_tiers(rng, draft, classes)
    assign_roles(draft)
    if not any(draft.degree(cell.cell_id) >= 3 for cell in draft.walkable()):
        raise RetryAttempt("branch_required: no cell of degree >= 3")
    add_voids(rng, draft)
    return draft


def generate_draft(
    seed: int, cells: int, classes: list[tuple[int, int]]
) -> tuple[Draft, int]:
    if not CELL_RANGE[0] <= cells <= CELL_RANGE[1]:
        raise GenerationError(f"--cells must be within {CELL_RANGE[0]}..{CELL_RANGE[1]}")
    for attempt in range(MAX_ATTEMPTS):
        try:
            return attempt_once(attempt_rng(seed, attempt), cells, classes), attempt
        except RetryAttempt:
            continue
    raise GenerationError(f"no valid map for seed {seed} within {MAX_ATTEMPTS} attempts")


def cell_json(cell: Any, primitives: list[str]) -> dict[str, Any]:
    return {
        "cell_id": cell.cell_id,
        "envelope_xz": rect_polygon(cell.rect),
        "ceiling_range_m": CEILING[cell.role],
        "allowed_primitives": primitives,
        "required_ports": [
            {
                "port_id": port.port_id,
                "pos_xz": list(port.pos),
                "normal": list(port.normal),
                "compatibility_type": PORT_TYPE,
            }
            for port in cell.ports
        ],
        "role": cell.role,
        "rarity_tier": cell.tier if cell.role != "void" else 0,
    }


def build_map(seed: int, library: Library, cells: int = 12, stage_max: int = 1) -> dict[str, Any]:
    if stage_max not in PRIMITIVES_BY_STAGE:
        raise GenerationError("--stage-max must be 0 or 1 in generator gmap-0.1.0")
    draft, attempt = generate_draft(seed, cells, figure_classes(library))
    primitives = PRIMITIVES_BY_STAGE[stage_max]
    return {
        "schema_version": 1,
        "map_id": map_id_for(seed),
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "attempt": attempt,
        "catalog_snapshot": dict(library.snapshot_ref),
        "library_index": dict(library.index_ref),
        "lattice": {"kind": "square", "unit_m": 1.0, "port_unit": PORT_TYPE},
        "shape_stage_max": stage_max,
        "cells": [cell_json(c, primitives) for c in draft.cells.values()],
        "edges": sorted(
            ({"from": a, "to": b, "connector": k} for a, b, k in draft.edges),
            key=lambda e: (e["from"], e["to"]),
        ),
        "distribution": {
            "tier_curve": "2d6",
            "repetition_budget": {"max_same_module_adjacent": 0, "max_same_primitive_run": 3},
        },
        "void_budget": dict(VOID_BUDGET),
        "rules": list(RULE_IDS),
        "registration_accepted": False,
        "scale_calibrated": False,
    }
