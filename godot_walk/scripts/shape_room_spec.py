"""Build one deterministic shape-room spec for a map cell (proposal section 5, stages 0-2)."""

from __future__ import annotations

from typing import Any

from doorway_sizes import DEFAULT_TYPE, doorway_size
from gmap_geometry import polygon_rect
from poetics_geometry import classify_primitive, num, signed_area
from shape_room_arms import arm_rects, arm_width_range, primitive_for
from shape_room_chamfer import apply_cuts, inscribed_rects, lamp_points_polygon
from shape_room_checks import (
    ShapeRoomError,
    check_room,
    require_valid,
)
from shape_room_raster import Cell, Rect, decompose, occupied_cells, outline_of, solid_at
from shape_room_rng import GENERATOR_VERSION_V2, GENERATOR_VERSION_V3, GENERATOR_VERSION_V5, V4_PLUS, cell_rng, version_for_map
from shape_room_palette import palette_materials
from shape_room_module_clear import clear_ceiling, module_top_planes
from shape_room_stage2 import chamfer_cuts, stage2_target, suitable_width

BOX_PROBABILITY = 0.5
THRESHOLD_ARM_WIDTH_M = 3
WIDE_ARM_WIDTH_M = 4  # an arm that carries a 2.4 m doorway needs >= 0.5 m of wall beside it
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
    target = stage2_target(cell)
    if target:
        return "arms" if target == "chamfered_polyomino" else "box"  # box-based classes cut the whole envelope
    if document["shape_stage_max"] < 1:
        return "box"
    if cell["role"] == "threshold":
        return "arms"
    return "box" if coin < BOX_PROBABILITY else "arms"


def has_wide_port(cell: dict[str, Any]) -> bool:
    return any(p.get("compatibility_type", DEFAULT_TYPE) != DEFAULT_TYPE for p in cell["required_ports"])


def draw(document: dict[str, Any], cell: dict[str, Any], envelope: Rect) -> dict[str, Any]:
    """Seeded choices in a fixed draw order: construction coin, arm width, ceiling height."""
    rng = cell_rng(document["seed"], cell["cell_id"], version_for_map(document))
    coin = rng.random()
    low, high = arm_width_range(envelope)
    width = rng.randint(low, high)
    lo_c, hi_c = cell["ceiling_range_m"]
    ceiling = snap_tenth(rng.randint(round(lo_c * 10), round(hi_c * 10)) / 10)
    construction = choose_construction(document, cell, coin)
    if version_for_map(document) in V4_PLUS:  # wall tops must not share a plane with the library room's
        ceiling = clear_ceiling(ceiling, lo_c, hi_c, module_top_planes(document, cell))
    if cell["role"] == "threshold":
        width = THRESHOLD_ARM_WIDTH_M
    if has_wide_port(cell) and construction == "arms":
        if min(envelope[2] - envelope[0], envelope[3] - envelope[1]) < WIDE_ARM_WIDTH_M:
            construction = "box"  # no room for a 4 m arm: the whole envelope is the room
        else:
            width = max(width, WIDE_ARM_WIDTH_M)
    if version_for_map(document) in V4_PLUS and construction == "arms":
        fitted = suitable_width(document, cell, envelope, width, max(low, WIDE_ARM_WIDTH_M if has_wide_port(cell) else low), high)
        construction, width = ("box", width) if fitted is None else ("arms", fitted)
    return {"construction": construction, "arm_width_m": width, "ceiling_height_m": ceiling}


def doorway_records(
    cell: dict[str, Any], links: dict[str, tuple[str, str]], typed: bool = False
) -> list[dict[str, Any]]:
    """Doorway records; `typed` (shape-room-0.3.0) also names each doorway's compatibility type."""
    records = []
    for port in sorted(cell["required_ports"], key=lambda p: p["port_id"]):
        if port["port_id"] not in links:
            raise ShapeRoomError(f"{cell['cell_id']}: port {port['port_id']} is on no edge")
        other, connector = links[port["port_id"]]
        width, height = doorway_size(port["compatibility_type"])
        record = {
            "port_id": port["port_id"],
            "pos_xz": [num(v) for v in port["pos_xz"]],
            "normal": list(port["normal"]),
            "width_m": width,
            "height_m": height,
            "kind": "open" if connector == "direct" else "closed_visible",
            "to_cell_id": other.split(":")[0],
            "to_port_id": other,
        }
        if typed:
            record["compatibility_type"] = port["compatibility_type"]
        records.append(record)
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


def lamps(geometry: dict[str, Any]) -> list[list[float]]:
    if geometry["chamfers"]:  # diagonal walls: Euclidean inset from the cut outline
        return lamp_points_polygon(geometry["outline"], LAMP_PITCH_M, LAMP_ANCHOR_M, LAMP_INSET_M)
    return lamp_points(geometry["cells"], geometry["rects"])


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
    cell: dict[str, Any], envelope: Rect, choices: dict[str, Any], waived: set[str] | None = None,
    document: dict[str, Any] | None = None,
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
    cuts = chamfer_cuts(document, cell, envelope, outline) if document is not None else None
    chamfers: list[dict[str, Any]] = []
    if cuts:
        chamfers = [{"corner": [num(outline[i][0]), num(outline[i][1])], "length_m": c} for i, c in sorted(cuts.items())]
        rects, base = inscribed_rects(cells, outline, cuts), outline
        if not rects:
            raise ShapeRoomError(f"{cell['cell_id']}: no raster rectangle lies wholly inside the chamfered outline")
        outline = apply_cuts(base, cuts)
    primitive_class, stage = classify_primitive(outline)
    if primitive_class not in cell["allowed_primitives"]:
        raise ShapeRoomError(f"{cell['cell_id']}: {primitive_class} is not an allowed primitive")
    return {
        "cells": cells, "arms": generated, "outline": outline, "rects": rects, "chamfers": chamfers,
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
    v2 = version in (GENERATOR_VERSION_V2, GENERATOR_VERSION_V3, *V4_PLUS)
    choices = draw(document, cell, envelope)
    geometry = room_geometry(cell, envelope, choices, set(degenerate_ports(cell)) if v2 else None, document)
    doorways = doorway_records(cell, links, version in (GENERATOR_VERSION_V3, *V4_PLUS))
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
        "lamps_xz": lamps(geometry),
        "material_source": "palette_registry" if version == GENERATOR_VERSION_V5 else "kit_default",
        "materials": palette_materials(cell) if version == GENERATOR_VERSION_V5 else MATERIALS,
        "features": feature_records(doorways),
        "registration_accepted": False,
        "scale_calibrated": False,
    }
    if v2:
        spec.update(mode_fields(cell))
    if geometry["chamfers"]:
        spec["chamfers"] = geometry["chamfers"]
    return spec
