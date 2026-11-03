"""gmap-0.4.0: per-cell shape stage choice and the stage-2 classes each cell may take (issue 190).

Cells, envelopes, edges and ports are unchanged in kind; only the allowed room outlines grow.
`allowed_primitives` of an eligible ground/figure cell gains its stage-2 classes, and the seeded
choice is recorded as `shape_stage_target` (+ `shape_class_target` at stage 2). Module cells,
void cells and thresholds keep the stage-1 list.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from gmap_geometry import polygon_rect
from gmap_rules import Errors, err
from shape_room_stage2 import STAGE2_CLASSES, STAGE2_PROBABILITY, choose_class, eligible_classes

RULE = "shape_stage2_eligibility"
STAGE1_PRIMITIVES = ["box", "l_shape", "rectilinear_polygon"]
PRIMITIVES_BY_STAGE = {0: ["box"], 1: STAGE1_PRIMITIVES}


def stage_rng(seed: int, attempt: int, version: str) -> random.Random:
    """Separate sha256-derived stream; never Python hash()."""
    digest = hashlib.sha256(f"{seed}:{attempt}:shape_stage:{version}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))


def cell_eligible(cell: dict[str, Any]) -> list[str]:
    rect = polygon_rect(cell["envelope_xz"])
    if rect is None or cell.get("module"):
        return []
    return eligible_classes(tuple(float(v) for v in rect), cell["required_ports"], cell["role"])  # type: ignore[arg-type]


def assign_stage2(seed: int, attempt: int, version: str, cells: list[dict[str, Any]], stage_max: int) -> dict[str, dict[str, Any]]:
    """cell_id -> fields to merge into the cell: allowed_primitives, shape_stage_target (+ class)."""
    rng = stage_rng(seed, attempt, version)
    base = PRIMITIVES_BY_STAGE[min(stage_max, 1)]
    fields: dict[str, dict[str, Any]] = {}
    for cell in cells:
        if cell["role"] == "void" or cell.get("module"):
            fields[cell["cell_id"]] = {"allowed_primitives": list(base)}
            continue
        eligible = cell_eligible(cell) if stage_max >= 2 else []
        record: dict[str, Any] = {"allowed_primitives": [*base, *eligible], "shape_stage_target": min(stage_max, 1)}
        if cell["role"] in ("ground", "figure"):
            roll = rng.random()  # drawn for every ground/figure cell, eligible or not
            if eligible and roll < STAGE2_PROBABILITY:
                record["shape_stage_target"] = 2
                record["shape_class_target"] = choose_class(rng, eligible)
        fields[cell["cell_id"]] = record
    return fields


def stage2_errors(document: dict[str, Any]) -> Errors:
    """gmap-0.4.0: the allowed stage-2 classes are exactly the eligible ones; the target is one of them."""
    errors: Errors = []
    stage_max = document["shape_stage_max"]
    for cell in document["cells"]:
        label = cell["cell_id"]
        if cell.get("diagonal_passage"):
            if cell.get("shape_stage_target") != 2 or cell.get("shape_class_target") != "diagonal_passage":
                errors.append(err(RULE, "diagonal_passage_target_invalid", label))
            continue
        if cell.get("diagonal_link_chamfer"):
            if cell.get("shape_stage_target") != 2 or cell.get("shape_class_target") != "chamfered_box" or "chamfered_box" not in cell["allowed_primitives"]:
                errors.append(err(RULE, "diagonal_source_target_invalid", label))
            continue
        listed = sorted(set(cell["allowed_primitives"]) & set(STAGE2_CLASSES))
        expected = cell_eligible(cell) if stage_max >= 2 and cell["role"] != "void" else []
        if listed != expected:
            errors.append(err(RULE, "stage2_classes_not_eligible", f"{label}: lists {listed}, eligible {expected}"))
        has_target = "shape_stage_target" in cell
        if has_target == (cell["role"] == "void" or bool(cell.get("module"))):
            errors.append(err(RULE, "shape_stage_target_missing" if not has_target else "shape_stage_target_unexpected", label))
            continue
        if not has_target:
            continue
        target, klass = cell["shape_stage_target"], cell.get("shape_class_target")
        if target > stage_max or (target == 2) != (klass is not None):
            errors.append(err(RULE, "shape_stage_target_invalid", f"{label}: stage {target}, class {klass}"))
        elif klass is not None and klass not in listed:
            errors.append(err(RULE, "shape_class_target_not_allowed", f"{label}: {klass}"))
    return errors
