"""Deterministic SVG review rendering of a generative map. Not a game asset."""

from __future__ import annotations

from typing import Any

from gmap_geometry import Rect, polygon_rect

SCALE = 10
MARGIN = 20
FILLS = {"ground": "#bdbdbd", "threshold": "#d2b48c", "figure": "#ffd700", "void": "none"}
MODULE_FILLS = {"ground": "#a9dfbf", "figure": "#f5b041"}  # library module leaf cells (gmap-0.3.0)
MODULE_STROKE = "#117864"
UNTESTED_STROKE = "#e67e22"


def px(value: float, origin: float) -> int:
    return int((value - origin) * SCALE) + MARGIN


def cell_svg(cell: dict[str, Any], rect: Rect, ox: float, oz: float) -> list[str]:
    x, z = px(rect[0], ox), px(rect[1], oz)
    width, height = (rect[2] - rect[0]) * SCALE, (rect[3] - rect[1]) * SCALE
    stroke = "#000000"
    dash = ' stroke-dasharray="4 3"' if cell["role"] == "void" else ""
    if cell.get("mode") == "degenerate":
        dash = ' stroke-dasharray="8 3 2 3"'
        stroke = "#8e44ad"
    label = f"{cell['cell_id']} t{cell['rarity_tier']}" if cell["role"] != "void" else cell["cell_id"]
    if cell.get("mode") == "degenerate":
        label += " degenerate"
    module = cell.get("module")
    fill = FILLS[cell["role"]]
    if module:
        fill, stroke, dash = MODULE_FILLS[cell["role"]], MODULE_STROKE, ' stroke-dasharray="10 2"'
        label += " module"
    lines = [
        (
            f'<rect x="{x}" y="{z}" width="{width}" height="{height}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>'
        ),
        f'<text x="{x + 4}" y="{z + 14}" font-family="monospace" font-size="11">{label}</text>',
    ]
    if module:
        name = module["module_id"].replace("&", "&amp;").replace("<", "&lt;")
        lines.append(f'<text x="{x + 4}" y="{z + 27}" font-family="monospace" font-size="9">{name} r{module["rotation_deg"]}</text>')
    return lines


def render_svg(document: dict[str, Any]) -> str:
    rects = {c["cell_id"]: polygon_rect(c["envelope_xz"]) for c in document["cells"]}
    ox = min(r[0] for r in rects.values())
    oz = min(r[1] for r in rects.values())
    width = px(max(r[2] for r in rects.values()), ox) + MARGIN
    height = px(max(r[3] for r in rects.values()), oz) + MARGIN
    ports = {p["port_id"]: p for c in document["cells"] for p in c["required_ports"]}
    body = [f'<title>{document["map_id"]} (structural map, not playable)</title>']
    for cell in document["cells"]:
        body += cell_svg(cell, rects[cell["cell_id"]], ox, oz)
    for edge in document["edges"]:
        a, b = ports[edge["from"]], ports[edge["to"]]
        dash = ' stroke-dasharray="3 3"' if edge["connector"] != "direct" else ""
        colour = "#c0392b"
        if edge.get("connection_status") == "proposed_untested":
            dash, colour = ' stroke-dasharray="6 2"', UNTESTED_STROKE
        pa, pb = a["pos_xz"], b["pos_xz"]
        ca = rects[edge["from"].split(":")[0]]
        cb = rects[edge["to"].split(":")[0]]
        points = [
            ((ca[0] + ca[2]) / 2, (ca[1] + ca[3]) / 2),
            (pa[0], pa[1]),
            (pb[0], pb[1]),
            ((cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2),
        ]
        path = " ".join(f"{px(x, ox)},{px(z, oz)}" for x, z in points)
        body.append(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="1.5"{dash}/>')
    for port in sorted(ports.values(), key=lambda p: p["port_id"]):
        body.append(f'<circle cx="{px(port["pos_xz"][0], ox)}" cy="{px(port["pos_xz"][1], oz)}" r="3" fill="#c0392b"/>')
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    return "\n".join([header, '<rect width="100%" height="100%" fill="#ffffff"/>', *body, "</svg>"]) + "\n"
