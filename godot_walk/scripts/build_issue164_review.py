"""Build the #164 layout diagram, contact sheet, and local review page."""

from __future__ import annotations

import html
import json
from typing import Any

from issue149_layout_core import ROOT
from PIL import Image, ImageDraw, ImageFont

EVIDENCE = ROOT / "godot_walk/evidence/2026-10-24-issue-164"
CATALOG = EVIDENCE / "catalog_snapshot.json"
LAYOUT = EVIDENCE / "layout_three_room.json"
MANIFEST = EVIDENCE / "capture_manifest.json"


def build() -> None:
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    modules = {item["id"]: item for item in catalog["modules"]}
    _layout_diagram(layout, modules)
    _contact_sheet(manifest["views"])
    _review_page(layout, manifest["views"])


def _layout_diagram(layout: dict[str, Any], modules: dict[str, Any]) -> None:
    footprints = [
        _world_polygon(
            placement, modules[placement["module_id"]]["visual_placement_envelope_xz"]
        )
        for placement in layout["placements"]
    ]
    points = [point for footprint in footprints for point in footprint]
    minimum_x = min(point[0] for point in points)
    maximum_x = max(point[0] for point in points)
    minimum_z = min(point[1] for point in points)
    maximum_z = max(point[1] for point in points)
    scale = min(800 / (maximum_x - minimum_x), 330 / (maximum_z - minimum_z))
    project = lambda point: (
        35 + (point[0] - minimum_x) * scale,
        400 - (point[1] - minimum_z) * scale,
    )
    colors = {
        "godot_later_bay_column_bounded_v1": "#8fc8bf",
        "godot_early_pocket_pass_through_v1": "#9ebacb",
        "godot_source_textured_large_room_hall_end_v1": "#e6c674",
    }
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="470" viewBox="0 0 1180 470">',
        '<rect width="1180" height="470" fill="#f4f6f4"/>',
        '<text x="28" y="34" font-family="sans-serif" font-size="22" font-weight="700" fill="#17232a">Issue 164 | three distinct authored room designs</text>',
        '<text x="28" y="58" font-family="sans-serif" font-size="13" fill="#43545c">The room-to-room connections are authored proposals. The source videos do not establish these adjacencies.</text>',
    ]
    for placement, footprint in zip(layout["placements"], footprints):
        module_id = placement["module_id"]
        polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(project, footprint))
        lines.append(
            f'<polygon points="{polygon}" fill="{colors[module_id]}" fill-opacity="0.78" stroke="#22333a" stroke-width="1.4"/>'
        )
        center = [
            sum(point[0] for point in footprint) / len(footprint),
            sum(point[1] for point in footprint) / len(footprint),
        ]
        x, y = project(center)
        lines.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#14232a">{placement["instance_id"]}</text>'
        )
    for edge in layout["connections"]:
        position = _socket_world(edge["from"], layout, modules)
        x, y = project(position)
        lines.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#fff" stroke="#34756f" stroke-width="2.5"/>'
        )
        right = _socket_world(edge["to"], layout, modules)
        if abs(position[0] - right[0]) > 0.001 or abs(position[1] - right[1]) > 0.001:
            lines.append(
                f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{project(right)[0]:.1f}" y2="{project(right)[1]:.1f}" stroke="#34756f" stroke-width="2"/>'
            )
    lines.extend(
        [
            '<line x1="895" y1="84" x2="895" y2="438" stroke="#ccd5d1"/>',
            '<text x="920" y="105" font-family="sans-serif" font-size="16" font-weight="700" fill="#17232a">Finite layout</text>',
            '<text x="920" y="132" font-family="sans-serif" font-size="13" fill="#263a40">3 designs | seed-164 chain accepted</text>',
            '<text x="920" y="158" font-family="sans-serif" font-size="12" fill="#263a40">R000: accepted #160 column module</text>',
            '<text x="920" y="181" font-family="sans-serif" font-size="12" fill="#263a40">R001: #149 pocket pass-through</text>',
            '<text x="920" y="204" font-family="sans-serif" font-size="12" fill="#263a40">R002: accepted #163 room with</text>',
            '<text x="920" y="222" font-family="sans-serif" font-size="12" fill="#263a40">the authored #164 hall-end adapter</text>',
            '<circle cx="928" cy="254" r="5" fill="#fff" stroke="#34756f" stroke-width="2.5"/><text x="944" y="258" font-family="sans-serif" font-size="12" fill="#263a40">authored socket pair</text>',
            '<line x1="920" y1="286" x2="957" y2="286" stroke="#d6534d" stroke-width="2" stroke-dasharray="4 3"/><text x="967" y="290" font-family="sans-serif" font-size="12" fill="#263a40">walk route, then retraced</text>',
            '<text x="920" y="332" font-family="sans-serif" font-size="12" fill="#a13832">Accepted for this layout; not generalized.</text>',
            '<text x="920" y="352" font-family="sans-serif" font-size="12" fill="#43545c">Registration and scale calibration remain false.</text>',
            '<text x="920" y="383" font-family="sans-serif" font-size="12" fill="#43545c">No Hunyuan output was produced for #163.</text>',
            "</svg>",
        ]
    )
    (EVIDENCE / "layout_three_room.svg").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _contact_sheet(captures: list[dict[str, Any]]) -> None:
    tile_width, tile_height, caption_height = 480, 300, 48
    columns = 2
    rows = (len(captures) + columns - 1) // columns
    sheet = Image.new(
        "RGB", (columns * tile_width, rows * (tile_height + caption_height)), "#182329"
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, record in enumerate(captures):
        image_path = ROOT / "godot_walk" / record["path"].removeprefix("res://")
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            image.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
        x = (index % columns) * tile_width
        y = (index // columns) * (tile_height + caption_height)
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + tile_height + 7), record["id"], fill="#eff4f0", font=font)
        draw.text(
            (x + 8, y + tile_height + 24),
            f"camera {_point(record['eye'])} -> {_point(record['target'])}",
            fill="#afc2bd",
            font=font,
        )
    sheet.save(EVIDENCE / "contact_sheet.jpg", quality=92, optimize=True)


def _review_page(layout: dict[str, Any], captures: list[dict[str, Any]]) -> None:
    figures = []
    for capture in captures:
        path = html.escape(capture["path"].removeprefix("res://"), quote=True)
        label = html.escape(capture["id"])
        figures.append(
            f'<figure><img src="../../{path}" alt="{label}"><figcaption>{label}</figcaption></figure>'
        )
    command = "godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue164_three_room_walkthrough.tscn"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Issue 164 Three-room Review</title><style>
body{{margin:0;background:#f4f6f4;color:#17232a;font:16px/1.5 system-ui,sans-serif}}main{{max-width:1200px;margin:0 auto;padding:28px}}h1{{margin:0;font-size:27px}}h2{{margin-top:30px;font-size:20px}}p{{max-width:930px;color:#40535a}}.status{{padding:12px 16px;background:#fff0d9;border-left:4px solid #d98a35}}.diagram{{width:100%;height:auto;background:#fff;border:1px solid #ccd5d1}}.captures{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}figure{{margin:0;background:#fff;border:1px solid #ccd5d1;padding:8px}}img{{display:block;width:100%;height:auto}}figcaption{{padding:8px 2px}}code{{overflow-wrap:anywhere}}@media(max-width:700px){{main{{padding:16px}}.captures{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Issue 164 | three-room walkthrough</h1>
<p class="status">Operator accepted this exact seed-164 chain as coherent and walkable. The new connector is specific to this authored layout and has not been generalized to other videos.</p>
<p>The chain contains three distinct designs, two traversable connection pairs, and one shared player. #163 is an authored source-textured room. No Hunyuan output was produced. Registration and scale calibration remain false.</p>
<h2>Layout</h2><img class="diagram" src="layout_three_room.svg" alt="Three-room authored layout diagram">
<h2>Connection review captures</h2><p>The first two views show the new connection from opposite sides. The remaining views show the new room entrance and its authored column.</p><div class="captures">{"".join(figures)}</div>
<h2>Walkthrough</h2><p>From the workspace root:</p><p><code>{html.escape(command)}</code></p><p>Use WASD and mouse to walk. Press R to reset to the safe spawn.</p>
<h2>Operator review</h2><p>Accepted: the pocket-to-third-room doorway feels coherent and walkable. The operator identified this assembly as the target for a repeatable workflow across different input videos. This decision does not establish source-video connectivity or calibrated scale.</p><p><a href="operator_review.json">Read the recorded review</a>.</p>
<p>See <a href="REPORT.md">REPORT.md</a> and <a href="COMMANDS.md">COMMANDS.md</a> for test and resource evidence. Contact sheet: <a href="contact_sheet.jpg">contact_sheet.jpg</a>.</p>
</main></body></html>"""
    (EVIDENCE / "index.html").write_text(page, encoding="utf-8")


def _world_polygon(
    placement: dict[str, Any], polygon: list[list[float]]
) -> list[list[float]]:
    return [_world_xz(placement, point) for point in polygon]


def _world_xz(placement: dict[str, Any], point: list[float]) -> list[float]:
    x, z = point
    if placement["transform"]["yaw_degrees"] == 180:
        x, z = -x, -z
    origin = placement["transform"]["position"]
    return [origin[0] + x, origin[2] + z]


def _socket_world(
    endpoint: dict[str, str], layout: dict[str, Any], modules: dict[str, Any]
) -> list[float]:
    placement = next(
        item
        for item in layout["placements"]
        if item["instance_id"] == endpoint["instance_id"]
    )
    module = modules[placement["module_id"]]
    socket = next(
        item for item in module["sockets"] if item["id"] == endpoint["socket_id"]
    )
    return _world_xz(
        placement, [socket["local_floor_center"][0], socket["local_floor_center"][2]]
    )


def _point(values: list[float]) -> str:
    return "(" + ", ".join(f"{value:.2f}" for value in values) + ")"


if __name__ == "__main__":
    build()
