"""Build contact sheet, layout diagram and local review page for #149."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps
from issue149_protected_hashes import write_protected_hashes

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-22-issue-149"
LAYOUT = EVIDENCE / "layout_seed_149.json"
CAPTURE_MANIFEST = EVIDENCE / "capture_manifest.json"
CATALOG = ROOT / "godot_walk/room_catalog/catalog.json"


def main() -> int:
    layout = json.loads(LAYOUT.read_text())
    catalog = json.loads(CATALOG.read_text())
    captures = json.loads(CAPTURE_MANIFEST.read_text())
    _contact_sheet(captures)
    _layout_diagram(layout, catalog)
    write_protected_hashes(
        ROOT,
        EVIDENCE,
        ROOT / "godot_walk/evidence/2026-10-22-issue-160/provenance.json",
    )
    _review_page(layout, captures)
    print(f"built #149 review page for {layout['layout_id']} with {len(captures)} captures")
    return 0


def _contact_sheet(captures: list[dict[str, Any]]) -> None:
    columns = 3
    tile_width, image_height, caption_height = 480, 270, 52
    rows = (len(captures) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * (image_height + caption_height)), "#171d20")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, record in enumerate(captures):
        source = ROOT / "godot_walk" / record["path"].removeprefix("res://")
        with Image.open(source) as image:
            tile = ImageOps.fit(image.convert("RGB"), (tile_width, image_height), method=Image.Resampling.LANCZOS)
        x = (index % columns) * tile_width
        y = (index // columns) * (image_height + caption_height)
        sheet.paste(tile, (x, y))
        status = "#160 accepted-pair regression" if record["group"] == "issue160-regression" else "#149 provisional"
        draw.text((x + 10, y + image_height + 6), f"{status} | {record['id']}", fill="#eef3f0", font=font)
        eye = _short_vector(record["eye"])
        target = _short_vector(record["target"])
        draw.text((x + 10, y + image_height + 24), f"eye {eye} -> {target} | fov {record['fov']:.0f}", fill="#9db1ad", font=font)
    sheet.save(EVIDENCE / "contact_sheet.jpg", quality=92, optimize=True)


def _layout_diagram(layout: dict[str, Any], catalog: dict[str, Any]) -> None:
    modules = {item["id"]: item for item in catalog["modules"]}
    footprints = [
        _world_polygon(placement, modules[placement["module_id"]]["visual_placement_envelope_xz"])
        for placement in layout["placements"]
    ]
    points = [point for footprint in footprints for point in footprint]
    minimum_x, maximum_x = min(p[0] for p in points), max(p[0] for p in points)
    minimum_z, maximum_z = min(p[1] for p in points), max(p[1] for p in points)
    map_width, map_height = 780.0, 340.0
    scale = min(map_width / (maximum_x - minimum_x), map_height / (maximum_z - minimum_z))

    def project(point: list[float]) -> tuple[float, float]:
        return 30 + (point[0] - minimum_x) * scale, 410 - (point[1] - minimum_z) * scale

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470">',
        '<rect width="1200" height="470" fill="#f4f6f4"/>',
        '<text x="28" y="34" font-family="sans-serif" font-size="22" font-weight="700" fill="#17232a">Seed 149 | authored finite-layout proposal</text>',
        '<text x="28" y="58" font-family="sans-serif" font-size="13" fill="#43545c">R000 reuses the #160 column; every generated opening is provisional. The exact accepted pair is shown separately as a regression.</text>',
    ]
    connector_lines = []
    for edge in layout["connections"]:
        left = _endpoint_world(edge["from"], layout, modules)
        x, y = project(left)
        connector_lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#f4f6f4" stroke="#34756f" stroke-width="2"/>')
    for placement, footprint in zip(layout["placements"], footprints):
        module_id = placement["module_id"]
        fill = "#8fc8bf" if module_id == "godot_later_bay_column_bounded_v1" else "#f1c96b" if "three_way" in module_id else "#9ebacb" if "pass_through" in module_id else "#d4d8cf"
        polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in (project(point) for point in footprint))
        out.append(f'<polygon points="{polygon}" fill="{fill}" fill-opacity="0.78" stroke="#22333a" stroke-width="1.2"/>')
        center = [sum(point[0] for point in footprint) / len(footprint), sum(point[1] for point in footprint) / len(footprint)]
        x, y = project(center)
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#14232a">{placement["instance_id"]}</text>')
    out.extend(connector_lines)
    route = layout["walk_route_xz"][: (len(layout["walk_route_xz"]) + 1) // 2]
    route_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in (project(point) for point in route))
    out.append(f'<polyline points="{route_points}" fill="none" stroke="#d6534d" stroke-width="1.5" stroke-dasharray="3 3"/>')
    out.extend(_layout_legend(layout))
    out.append("</svg>")
    (EVIDENCE / "layout_seed_149.svg").write_text("\n".join(out) + "\n")


def _layout_legend(layout: dict[str, Any]) -> list[str]:
    counts = layout["module_counts"]
    repeated = layout["repeated_instances"]
    branch_side = layout["topology"]["branch_side"]
    panel = [
        '<line x1="858" y1="82" x2="858" y2="438" stroke="#ccd5d1"/>',
        '<text x="880" y="100" font-family="sans-serif" font-size="16" font-weight="700" fill="#17232a">Generated graph</text>',
        f'<text x="880" y="127" font-family="sans-serif" font-size="13" fill="#263a40">{len(layout["placements"])} placed modules / {len(counts)} distinct design IDs</text>',
        f'<text x="880" y="150" font-family="sans-serif" font-size="13" fill="#263a40">{repeated} repeated instances; {len(layout["connections"])} authored links</text>',
        f'<text x="880" y="173" font-family="sans-serif" font-size="13" fill="#263a40">One {branch_side} three-opening provisional branch</text>',
        f'<text x="880" y="196" font-family="sans-serif" font-size="13" fill="#263a40">{layout["topology"]["dead_end_count"]} degree-1 ends (spawn plus two leaves)</text>',
        '<rect x="880" y="224" width="16" height="12" fill="#8fc8bf"/><text x="904" y="235" font-family="sans-serif" font-size="12" fill="#263a40">#160 bounded column module</text>',
        '<rect x="880" y="247" width="16" height="12" fill="#9ebacb"/><text x="904" y="258" font-family="sans-serif" font-size="12" fill="#263a40">pocket pass-through, pending review</text>',
        '<rect x="880" y="270" width="16" height="12" fill="#f1c96b"/><text x="904" y="281" font-family="sans-serif" font-size="12" fill="#263a40">pocket three-way, pending review</text>',
        '<rect x="880" y="293" width="16" height="12" fill="#d4d8cf"/><text x="904" y="304" font-family="sans-serif" font-size="12" fill="#263a40">single-socket terminal, pending review</text>',
        '<circle cx="897" cy="330" r="4" fill="#f4f6f4" stroke="#34756f" stroke-width="2"/><text x="922" y="334" font-family="sans-serif" font-size="12" fill="#263a40">authored socket junction</text>',
        '<line x1="880" y1="353" x2="914" y2="353" stroke="#d6534d" stroke-width="1.5" stroke-dasharray="3 3"/><text x="922" y="357" font-family="sans-serif" font-size="12" fill="#263a40">walk route, then retraced</text>',
        '<text x="880" y="393" font-family="sans-serif" font-size="12" fill="#a13832">Source footage does not establish</text>',
        '<text x="880" y="411" font-family="sans-serif" font-size="12" fill="#a13832">these room adjacencies or branches.</text>',
        '<text x="880" y="434" font-family="sans-serif" font-size="12" fill="#43545c">Registration and scale calibration remain false.</text>',
    ]
    return panel


def _world_polygon(placement: dict[str, Any], polygon: list[list[float]]) -> list[list[float]]:
    return [_world_xz(placement, point) for point in polygon]


def _short_vector(point: list[float]) -> str:
    return "(" + ",".join(f"{value:.1f}" for value in point) + ")"


def _world_xz(placement: dict[str, Any], point: list[float]) -> list[float]:
    yaw = placement["transform"]["yaw_degrees"] % 360
    x, z = point
    rotated = {0: [x, z], 90: [z, -x], 180: [-x, -z], 270: [-z, x]}[yaw]
    origin = placement["transform"]["position"]
    return [origin[0] + rotated[0], origin[2] + rotated[1]]


def _endpoint_world(endpoint: dict[str, str], layout: dict[str, Any], modules: dict[str, Any]) -> list[float]:
    placement = next(item for item in layout["placements"] if item["instance_id"] == endpoint["instance_id"])
    module = modules[placement["module_id"]]
    socket = next(item for item in module["sockets"] if item["id"] == endpoint["socket_id"])
    local = socket["local_floor_center"]
    return _world_xz(placement, [local[0], local[2]])


def _review_page(layout: dict[str, Any], captures: list[dict[str, Any]]) -> None:
    tiles = []
    for item in captures:
        source = html.escape(item["path"].removeprefix("res://"), quote=True)
        label = html.escape(item["id"])
        status = "#160 pair regression" if item["group"] == "issue160-regression" else "#149 review candidate"
        tiles.append(f'<figure><img src="../../{source}" alt="{label}"><figcaption><strong>{status}</strong><br>{label}</figcaption></figure>')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>#149 Seeded Walkthrough Review</title><style>
body{{margin:0;background:#f4f6f4;color:#17232a;font:16px/1.45 system-ui,sans-serif}}main{{max-width:1200px;margin:0 auto;padding:28px}}h1{{font-size:26px;margin:0 0 8px}}h2{{font-size:19px;margin:30px 0 12px}}p{{max-width:900px;color:#40535a}}.strip{{padding:12px 16px;background:#fff0d9;border-left:4px solid #d98a35}}.diagram{{width:100%;height:auto;border:1px solid #ccd5d1;background:white}}.captures{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}figure{{margin:0;background:#fff;border:1px solid #ccd5d1;padding:8px}}img{{display:block;width:100%;height:auto}}figcaption{{padding:8px 2px 2px;color:#35474e}}code{{font-size:14px;overflow-wrap:anywhere}}@media(max-width:700px){{main{{padding:16px}}.captures{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Seed {layout['seed']} | {len(layout['placements'])} placements</h1>
<p class="strip">Provisional layout proposal. The operator-accepted #160 column-to-pocket assembly remains a separate regression reference. New openings, placements, branch, and dead ends are not approved.</p>
<p>This build uses {layout['unique_module_designs']} distinct module designs and {layout['repeated_instances']} repeated instances. It has one {layout['topology']['branch_side']} three-opening branch, two authored terminal leaves, and no cycles. The source footage does not establish these adjacencies. Registration and scale calibration remain false.</p>
<h2>Layout</h2><img class="diagram" src="layout_seed_149.svg" alt="Seeded authored layout diagram">
<h2>Matched captures</h2><div class="captures">{''.join(tiles)}</div>
<h2>Walkthrough</h2><p>From the workspace root:</p><p><code>godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue149_generated_walkthrough.tscn -- --layout=res://evidence/2026-10-22-issue-149/layout_seed_149.json</code></p>
<p>Walk with WASD and mouse. Press R to return to the safe spawn. Review <a href="REPORT.md">REPORT.md</a> and <a href="COMMANDS.md">COMMANDS.md</a> for mechanical and resource evidence.</p>
</main></body></html>'''
    (EVIDENCE / "index.html").write_text(page)


if __name__ == "__main__":
    raise SystemExit(main())
