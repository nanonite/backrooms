"""Deterministic per-room wet/dry reverb flags for gmap-0.11.0 (#204).

The reverb layer runs after the gmap-0.10.0 elevation layer. It gives every
walkable cell one boolean `reverb` flag: wet (a ringing room) or dry (a dead
pocket). The spawn cell is always dry so the first steps are clear.

Unlike the earlier layers this layer does not walk a shared RNG sequentially.
Each cell's flag comes from its own keyed draw:

    sha256("<seed>:<attempt>:reverb:gmap-0.11.0:<cell_id>")

A later mutation can therefore re-draw one cell without shifting any other
cell's result, and adding or removing a cell leaves its neighbours' draws
unchanged. The draw compares against a probability that starts at
``BASE_PROBABILITY`` and rises for larger nominal room volumes and for
double-height cells. ``room_volume_m3`` is the same nominal figure (envelope
area times the authored maximum ceiling) that the assembly exposes on each
instanced room; it is a bias heuristic, not a measured acoustic volume.

The flag is map metadata, not baked geometry: the assembly copies it to the
room's ``reverb_enabled`` metadata and the runtime may change it per cell.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

RULE = "reverb_layer"
STREAM = "reverb:gmap-0.11.0"
BASE_PROBABILITY = 0.35
VOLUME_REFERENCE_M3 = 200.0
VOLUME_FULL_BONUS_M3 = 600.0
MAX_VOLUME_BONUS = 0.20
DOUBLE_HEIGHT_M = 3.6
DOUBLE_HEIGHT_BONUS = 0.10
MAX_PROBABILITY = 0.70


def polygon_area_m2(points: list[list[float]]) -> float:
    """Area of a simple XZ polygon (shoelace), always positive."""
    area = 0.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        area += float(current[0]) * float(following[1]) - float(following[0]) * float(
            current[1]
        )
    return abs(area) / 2.0


def ceiling_height_m(cell: dict[str, Any]) -> float:
    """Authored maximum ceiling; the map knows no single built room height."""
    heights = cell.get("ceiling_range_m") or [0.0, 0.0]
    return max(float(heights[0]), float(heights[-1]))


def room_volume_m3(cell: dict[str, Any]) -> float:
    """Nominal room volume: envelope area times the authored maximum ceiling."""
    return polygon_area_m2(cell["envelope_xz"]) * ceiling_height_m(cell)


def is_double_height(cell: dict[str, Any]) -> bool:
    """True when the authored minimum ceiling already exceeds the standard room."""
    heights = cell.get("ceiling_range_m") or [0.0, 0.0]
    return float(heights[0]) >= DOUBLE_HEIGHT_M


def wet_probability(cell: dict[str, Any], spawn_id: str) -> float:
    """Per-cell wet probability before the keyed draw; zero for the spawn."""
    if cell["cell_id"] == spawn_id:
        return 0.0
    volume = room_volume_m3(cell)
    span = VOLUME_FULL_BONUS_M3 - VOLUME_REFERENCE_M3
    volume_scale = min(1.0, max(0.0, (volume - VOLUME_REFERENCE_M3) / span))
    probability = BASE_PROBABILITY + MAX_VOLUME_BONUS * volume_scale
    if is_double_height(cell):
        probability += DOUBLE_HEIGHT_BONUS
    return min(probability, MAX_PROBABILITY)


def keyed_draw(seed: int, attempt: int, cell_id: str) -> float:
    """Stable [0, 1) draw for one cell, independent of cell order or neighbours."""
    text = f"{seed}:{attempt}:{STREAM}:{cell_id}"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def reverb_for(seed: int, attempt: int, cell: dict[str, Any], spawn_id: str) -> bool:
    """The wet/dry flag for one cell; the spawn cell never draws."""
    if cell["cell_id"] == spawn_id:
        return False
    return keyed_draw(seed, attempt, cell["cell_id"]) < wet_probability(cell, spawn_id)


def assign_reverb(document: dict[str, Any]) -> None:
    """Attach one boolean reverb flag per walkable cell without touching any other layer."""
    spawn_id = document["cells"][0]["cell_id"]
    seed = int(document["seed"])
    attempt = int(document.get("attempt", 0))
    for cell in sorted(document["cells"], key=lambda item: item["cell_id"]):
        if cell["role"] == "void":
            continue
        cell["reverb"] = reverb_for(seed, attempt, cell, spawn_id)
    document["reverb_layer"] = metadata()


def metadata() -> dict[str, Any]:
    return {
        "stream": STREAM,
        "base_probability": BASE_PROBABILITY,
        "volume_reference_m3": VOLUME_REFERENCE_M3,
        "volume_full_bonus_m3": VOLUME_FULL_BONUS_M3,
        "max_volume_bonus": MAX_VOLUME_BONUS,
        "double_height_m": DOUBLE_HEIGHT_M,
        "double_height_bonus": DOUBLE_HEIGHT_BONUS,
        "max_probability": MAX_PROBABILITY,
        "selection": "per-cell keyed draw; spawn always dry",
    }


def strip_reverb(document: dict[str, Any]) -> dict[str, Any]:
    """Base copy with every reverb artifact removed, for deterministic re-derivation."""
    result = deepcopy(document)
    result.pop("reverb_layer", None)
    for cell in result["cells"]:
        cell.pop("reverb", None)
    return result


def reverb_summary(document: dict[str, Any]) -> dict[str, Any]:
    """Wet/dry counts for the map summary; legacy maps report every room dry."""
    cells = document.get("cells") if isinstance(document, dict) else None
    if not isinstance(cells, list):
        return {"layer": "absent", "stream": None, "wet": 0, "dry": 0, "wet_ratio": 0.0}
    walkable = [
        cell for cell in cells if isinstance(cell, dict) and cell.get("role") != "void"
    ]
    present = any("reverb" in cell for cell in walkable)
    wet = sum(1 for cell in walkable if cell.get("reverb") is True)
    dry = len(walkable) - wet
    ratio = round(wet / len(walkable), 6) if walkable else 0.0
    return {
        "layer": "present" if present else "absent",
        "stream": STREAM if present else None,
        "wet": wet,
        "dry": dry,
        "wet_ratio": ratio,
    }


def reverb_errors(document: dict[str, Any]) -> list[dict[str, str]]:
    """All reverb-layer errors for a gmap-0.11.0 document."""
    cells = document.get("cells")
    if not isinstance(cells, list) or not cells:
        return [_error("reverb_document_invalid", "map has no cells")]
    spawn_id = cells[0].get("cell_id") if isinstance(cells[0], dict) else ""
    errors: list[dict[str, str]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            errors.append(_error("reverb_document_invalid", "cell is not an object"))
            continue
        if cell.get("role") == "void":
            if "reverb" in cell:
                errors.append(_error("void_has_reverb", str(cell.get("cell_id", ""))))
            continue
        value = cell.get("reverb")
        if type(value) is not bool:
            errors.append(_error("reverb_flag_invalid", str(cell.get("cell_id", ""))))
        elif cell.get("cell_id") == spawn_id and value:
            errors.append(_error("spawn_is_wet", spawn_id))
    try:
        expected = strip_reverb(document)
        assign_reverb(expected)
    except (KeyError, TypeError, IndexError):
        errors.append(_error("reverb_document_invalid", "cannot re-derive the layer"))
        return errors
    expected_cells = {cell["cell_id"]: cell for cell in expected["cells"]}
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("role") == "void":
            continue
        if cell.get("reverb") != expected_cells[cell["cell_id"]].get("reverb"):
            errors.append(_error("reverb_assignment_mismatch", cell["cell_id"]))
    expected_layer = expected.get("reverb_layer", {})
    actual_layer = document.get("reverb_layer")
    if not isinstance(actual_layer, dict):
        errors.append(_error("reverb_metadata_missing", "reverb_layer"))
    else:
        for field, value in expected_layer.items():
            if actual_layer.get(field) != value:
                errors.append(_error("reverb_metadata_mismatch", field))
    return errors


def _error(code: str, message: str) -> dict[str, str]:
    return {"rule": RULE, "code": code, "message": message}
