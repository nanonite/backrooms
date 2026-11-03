"""Build one deterministic shape-room spec for a map cell (proposal section 5, stage 0-1)."""

from __future__ import annotations

from typing import Any

from gmap_geometry import polygon_rect
from poetics_geometry import classify_primitive, num, signed_area
from shape_room_arms import arm_rects, arm_width_range, primitive_for
from shape_room_checks import (
    DOORWAY_HEIGHT_M,
    DOORWAY_WIDTH_M,
    ShapeRoomError,
    check_room,
    require_valid,
)
from shape_room_raster import Cell, Rect, decompose, occupied_cells, outline_of, solid_at
from shape_room_rng import GENERATOR_VERSION_V2, cell_rng, version_for_map

BOX_PROBABILITY = 0.5
THRESHOLD_ARM_WIDTH_M = 3
LAMP_PITCH_M = 4.0
LAMP_ANCHOR_M = 1.5
LAMP_INSET_M = 1.0
TEXTURE_ROOT = "res://assets/psx_extension/textures/"
MATERIALS = {
    "wallpaper_texture": TEXTURE_ROOT + "wallpaper_source_video.png",
    "floor_texture": TEXTURE_ROOT + "floor_source_video.png",
    "ceiling_texture": TEXTURE_ROOT + "ceiling_source_video.png",
    "trim_color": [0.37, 0.34, 0.23],
    "lamp_color": [1.0, 0.97, 0.76],
}


def snap_tenth(value: float) -> float:
    return round(value * 10) / 10


def choose_construction(document: dict[str, Any], cell: dict[str, Any], coin: float) -> str:
    if document["shape_stage_max"] < 1:
        return "box"
    if cell["role"] == "threshold":
        return "arms"
    return "box" if coin < BOX_PROBABILITY else "arms"


def draw(document: dict[str, Any], cell: dict[str, Any], envelope: Rect) -> dict[str, Any]:
    """Seeded choices in a fixed draw order: construction coin, arm width, ceiling height."""
    rng = cell_rng(document["seed"], cell["cell_id"], version_for_map(document))
    coin = rng.random()
    low, high = arm_width_range(envelope)
    width = rng.randint(low, high)
    lo_c, hi_c = cell["ceiling_range_m"]
    ceiling = snap_tenth(rng.randint(round(lo_c * 10), round(hi_c * 10)) / 10)
    construction = choose_construction(document, cell, coin)
    if cell["role"] == "threshold":
        width = THRESHOLD_ARM_WIDTH_M
    return {"construction": construction, "arm_width_m": width, "ceiling_height_m": ceiling}


def doorway_records(cell: dict[str, Any], links: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    records = []
    for port in sorted(cell["required_ports"], key=lambda p: p["port_id"]):
        if port["port_id"] not in links:
            raise ShapeRoomError(f"{cell['cell_id']}: port {port['port_id']} is on no edge")
        other, connector = links[port["port_id"]]
        records.append(
            {
                "port_id": port["port_id"],
                "pos_xz": [num(v) for v in port["pos_xz"]],
                "normal": list(port["normal"]),
                "width_m": DOORWAY_WIDTH_M,
                "height_m": DOORWAY_HEIGHT_M,
                "kind": "open" if connector == "direct" else "closed_visible",
                "to_cell_id": other.split(":")[0],
                "to_port_id": other,
            }
        )
    return records


def lamp_inset_ok(cells: set[Cell], x: float, z: float) -> bool:
    steps = [i * 0.5 + 0.25 for i in range(-int(LAMP_INSET_M * 2), int(LAMP_INSET_M * 2))]
    return all(solid_at(cells, x + dx, z + dz) for dx in steps for dz in steps)


def lamp_points(cells: set[Cell], rects: list[Rect]) -> list[list[float]]:
    """Ceiling panels on a 4 m grid, inset 1 m from every wall; one in the biggest rect if none fit."""
    min_x, min_z = min(r[0] for r in rects), min(r[1] for r in rects)
    max_x, max_z = max(r[2] for r in rects), max(r[3] for r in rects)
    points = []
    x = min_x + LAMP_ANCHOR_M
    while x <= max_x:
        z = min_z + LAMP_ANCHOR_M
        while z <= max_z:
            if lamp_inset_ok(cells, x, z):
                points.append([num(x), num(z)])
            z += LAMP_PITCH_M
        x += LAMP_PITCH_M
    if points:
        return points
    big = max(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    return [[num((big[0] + big[2]) / 2), num((big[1] + big[3]) / 2)]]


def feature_records(doorways: list[dict[str, Any]]) -> list[dict[str, str]]:
    kinds = ["floor", "walls", "ceiling", "ceiling_lamp_grid"]
    names = [(kind, kind) for kind in kinds]
    names += [("doorway", f"doorway:{d['port_id']}") for d in doorways]
    return [{"feature_id": name, "kind": kind, "sign": "symbol"} for kind, name in names]


def degenerate_ports(cell: dict[str, Any]) -> list[str]:
    """Port ids whose doorway touches an envelope corner (only in a degenerate cell)."""
    if cell.get("mode", "standard") != "degenerate":
        return []
    return sorted(p["port_id"] for p in cell["required_ports"] if p.get("placement") == "degenerate")


def mode_fields(cell: dict[str, Any]) -> dict[str, Any]:
    """shape-room-0.2.0: the cell's mode and its recorded degenerate features."""
    ports = degenerate_ports(cell)
    return {
        "mode": "degenerate" if cell.get("mode", "standard") == "degenerate" else "standard",
        "degenerate_features": ["corner_doorway"] if ports else [],
        "degenerate_port_ids": ports,
    }


def room_geometry(
    cell: dict[str, Any], envelope: Rect, choices: dict[str, Any], waived: set[str] | None = None
) -> dict[str, Any]:
    """Arms (or the envelope), raster, outline and decomposed rects; fails closed on any invariant."""
    ports = sorted(cell["required_ports"], key=lambda p: p["port_id"])
    if choices["construction"] == "box":
        generated = [envelope]
    else:
        generated = arm_rects(envelope, ports, choices["arm_width_m"])
    cells = occupied_cells(generated)
    outline = outline_of(cells)
    rects = decompose(cells)
    require_valid(cell["cell_id"], check_room(envelope, ports, generated, cells, outline, waived))
    primitive_class, stage = classify_primitive(outline)
    if primitive_class not in cell["allowed_primitives"]:
        raise ShapeRoomError(f"{cell['cell_id']}: {primitive_class} is not an allowed primitive")
    return {
        "cells": cells, "arms": generated, "outline": outline, "rects": rects,
        "primitive": primitive_for(ports), "primitive_class": primitive_class, "stage": stage,
    }


def cell_envelope(cell: dict[str, Any]) -> Rect:
    rect = polygon_rect(cell["envelope_xz"])
    if rect is None:
        raise ShapeRoomError(f"{cell['cell_id']}: envelope is not a rectangle")
    return float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])


def rect_json(rect: Rect) -> list[float]:
    return [num(v) for v in rect]


def build_spec(
    document: dict[str, Any],
    map_sha256: str,
    cell: dict[str, Any],
    original_status: str,
    links: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    envelope = cell_envelope(cell)
    version = version_for_map(document)
    v2 = version == GENERATOR_VERSION_V2
    choices = draw(document, cell, envelope)
    geometry = room_geometry(cell, envelope, choices, set(degenerate_ports(cell)) if v2 else None)
    doorways = doorway_records(cell, links)
    is_arms = choices["construction"] == "arms"
    spec = {
        "schema_version": 1,
        "generator_version": version,
        "map_id": document["map_id"],
        "map_sha256": map_sha256,
        "cell_id": cell["cell_id"],
        "role": cell["role"],
        "rarity_tier": cell["rarity_tier"],
        "original_cell_status": original_status,
        "primitive": geometry["primitive"],
        "primitive_class": geometry["primitive_class"],
        "shape_stage": geometry["stage"],
        "construction": choices["construction"],
        "arm_width_m": choices["arm_width_m"] if is_arms else None,
        "envelope_xz": [[num(v) for v in p] for p in cell["envelope_xz"]],
        "arms_xz": [rect_json(r) for r in geometry["arms"]],
        "rects": [rect_json(r) for r in geometry["rects"]],
        "outline_xz": [[num(x), num(z)] for x, z in geometry["outline"]],
        "area_m2": num(abs(signed_area(geometry["outline"]))),
        "ceiling_height_m": choices["ceiling_height_m"],
        "doorways": doorways,
        "lamps_xz": lamp_points(geometry["cells"], geometry["rects"]),
        "material_source": "kit_default",
        "materials": MATERIALS,
        "features": feature_records(doorways),
        "registration_accepted": False,
        "scale_calibrated": False,
    }
    if v2:
        spec.update(mode_fields(cell))
    return spec
