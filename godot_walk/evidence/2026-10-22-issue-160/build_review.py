"""Build a contact sheet and authored-only socket diagram for Chainlink #160."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

EVIDENCE = Path(__file__).resolve().parent
CAPTURE_WIDTH = 480
CAPTURE_HEIGHT = 270
CELL_HEIGHT = 310
SCALE = 52
ORIGIN = (340, 590)
COLUMN_POLYGON = [(-4.4, -1.2), (0.0, -1.2), (3.5, 1.2),
                  (3.5, 5.6), (-0.3, 5.6), (-4.1, 3.7)]
POCKET_RECT = [(3.5, -3.8), (9.5, -3.8), (9.5, 10.0), (3.5, 10.0)]


def manifest() -> list[dict]:
    return json.loads((EVIDENCE / "capture_manifest.json").read_text())


def contact_sheet() -> None:
    records = manifest()
    columns = 3
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * CAPTURE_WIDTH, rows * CELL_HEIGHT), "#1b2024")
    draw = ImageDraw.Draw(sheet)
    for index, record in enumerate(records):
        column, row = index % columns, index // columns
        left, top = column * CAPTURE_WIDTH, row * CELL_HEIGHT
        draw.text((left + 10, top + 8), f'{record["room"]} | {record["id"]}', fill="white")
        image_path = EVIDENCE / record["path"].removeprefix("res://evidence/2026-10-22-issue-160/")
        with Image.open(image_path) as capture:
            image = capture.convert("RGB").resize((CAPTURE_WIDTH, CAPTURE_HEIGHT), Image.Resampling.LANCZOS)
            sheet.paste(image, (left, top + 32))
    sheet.save(EVIDENCE / "contact_sheet.jpg", quality=92)


def layout_svg() -> None:
    width, height = 1100, 860

    def pixel(point: tuple[float, float]) -> tuple[int, int]:
        return round(ORIGIN[0] + SCALE * point[0]), round(ORIGIN[1] - SCALE * point[1])

    column_points = " ".join(f"{x},{y}" for x, y in map(pixel, COLUMN_POLYGON))
    pocket_points = " ".join(f"{x},{y}" for x, y in map(pixel, POCKET_RECT))
    socket = pixel((3.5, 3.1))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#171b1e"/>
<text x="28" y="36" fill="#f2f4f5" font-family="sans-serif" font-size="23">#160 authored assembly proposal (engine units, uncalibrated)</text>
<text x="28" y="68" fill="#c8d0d5" font-family="sans-serif" font-size="15">Geometry is a design arrangement, not a recovered floor plan. Video connectivity remains unknown.</text>
<polygon points="{column_points}" fill="#495b4a" stroke="#d5dbb9" stroke-width="4"/>
<polygon points="{pocket_points}" fill="#3d5262" stroke="#a8c9df" stroke-width="4"/>
<text x="95" y="350" fill="white" font-family="sans-serif" font-size="22">Bounded later-bay column room</text>
<text x="435" y="140" fill="white" font-family="sans-serif" font-size="22">Early-pocket module</text>
<line x1="{socket[0]}" y1="{socket[1]-SCALE}" x2="{socket[0]}" y2="{socket[1]+SCALE}" stroke="#f3dc81" stroke-width="9"/>
<circle cx="{socket[0]}" cy="{socket[1]}" r="10" fill="#f3dc81"/>
<text x="{socket[0]+18}" y="{socket[1]-18}" fill="#f3dc81" font-family="sans-serif" font-size="17">Authored paired sockets, 2.0 x 2.1</text>
<line x1="28" y1="744" x2="68" y2="744" stroke="#d5dbb9" stroke-width="4"/>
<text x="80" y="750" fill="#e8ebed" font-family="sans-serif" font-size="15">Column polygon: #159 proposed envelope</text>
<line x1="430" y1="744" x2="470" y2="744" stroke="#a8c9df" stroke-width="4"/>
<text x="482" y="750" fill="#e8ebed" font-family="sans-serif" font-size="15">Pocket bounds: #148 authored room</text>
<text x="28" y="790" fill="#e8ebed" font-family="sans-serif" font-size="16">The modules touch only through new authored visual/collision openings and a level threshold.</text>
<text x="28" y="818" fill="#f3dc81" font-family="sans-serif" font-size="16">This connector is not source-observed; do not infer room count, source connectivity, or scale.</text>
</svg>'''
    (EVIDENCE / "authored_assembly_layout.svg").write_text(svg)


def review_html() -> None:
    rows = []
    for record in manifest():
        image = record["path"].removeprefix("res://")
        rows.append(
            f'<figure><img src="../../{image}" alt="{record["room"]} {record["id"]}">'
            f'<figcaption>{record["room"]} | {record["id"]}</figcaption></figure>'
        )
    content = "\n".join(rows)
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Issue 160 review</title>
<style>body{{font:15px sans-serif;background:#171b1e;color:#edf1f2;margin:24px}}main{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}figure{{margin:0}}img{{width:100%;height:auto}}figcaption{{padding:6px 0}}a{{color:#e4cb78}}</style>
<h1>Issue 160 room and connector review</h1><p>Authored arrangement only; source room connectivity and scale remain unknown.</p>
<p><a href="contact_sheet.jpg">Contact sheet</a> | <a href="authored_assembly_layout.svg">Authored layout</a> | <a href="REPORT.md">Report</a></p><main>{content}</main></html>'''
    (EVIDENCE / "index.html").write_text(page)


if __name__ == "__main__":
    contact_sheet()
    layout_svg()
    review_html()
