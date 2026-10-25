"""Build the local visual review bundle for bounded #156 streaming."""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-23-issue-156"
CAPTURES = EVIDENCE / "capture_manifest.json"
TILE_WIDTH = 640
TILE_HEIGHT = 392
LABEL_HEIGHT = 32
GRID_COLUMNS = 2


def _records() -> list[dict]:
    records = json.loads(CAPTURES.read_text())
    if not records:
        raise ValueError("Capture manifest has no views")
    for record in records:
        path = ROOT / "godot_walk" / record["path"].removeprefix("res://")
        if not path.is_file():
            raise ValueError(f"Capture is missing: {record['path']}")
    return records


def _contact_sheet(records: list[dict]) -> None:
    rows = (len(records) + GRID_COLUMNS - 1) // GRID_COLUMNS
    sheet = Image.new("RGB", (GRID_COLUMNS * TILE_WIDTH, rows * TILE_HEIGHT), "#171b1d")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, record in enumerate(records):
        source = ROOT / "godot_walk" / record["path"].removeprefix("res://")
        image = Image.open(source).convert("RGB")
        image.thumbnail((TILE_WIDTH, TILE_HEIGHT - LABEL_HEIGHT))
        x = index % GRID_COLUMNS * TILE_WIDTH
        y = index // GRID_COLUMNS * TILE_HEIGHT
        sheet.paste(image, (x, y))
        draw.rectangle((x, y + TILE_HEIGHT - LABEL_HEIGHT, x + TILE_WIDTH, y + TILE_HEIGHT),
                       fill="#242c2f")
        label = f"{record['id']} | {record['room_instance']} | caps={record['frontier_caps']}"
        draw.text((x + 10, y + TILE_HEIGHT - LABEL_HEIGHT + 10), label, fill="#e8e6dc", font=font)
    sheet.save(EVIDENCE / "contact_sheet.jpg", quality=92)


def _layout_diagram() -> None:
    source = ROOT / "godot_walk/evidence/2026-10-22-issue-149/layout_seed_149.svg"
    shutil.copyfile(source, EVIDENCE / "layout_seed_149.svg")


def _capture_relative_path(record: dict) -> str:
    source = ROOT / "godot_walk" / record["path"].removeprefix("res://")
    return source.relative_to(EVIDENCE).as_posix()


def _index(records: list[dict]) -> None:
    figures = "\n".join(
        f'<figure><img src="{html.escape(_capture_relative_path(record))}" '
        f'alt="{html.escape(record["id"])}"><figcaption>{html.escape(record["id"])} '
        f'({html.escape(record["room_instance"])}) | resident: '
        f'{html.escape(", ".join(record["loaded_ids"]))} | frontier caps: '
        f'{record["frontier_caps"]}</figcaption></figure>'
        for record in records
    )
    body = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Issue 156 bounded streaming review</title>
<style>
body{{font:16px system-ui,sans-serif;background:#15191b;color:#e6e5dc;margin:24px;max-width:1400px}}
h1{{font-size:24px;font-weight:600}}p{{max-width:880px;line-height:1.5;color:#bdc5c5}}
.views{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px}}
figure{{margin:0;background:#22292b;border:1px solid #394143;padding:8px}}
img{{width:100%;height:auto;display:block}}figcaption{{padding:9px 2px 2px;font-size:14px}}
code{{color:#d8c890}}a{{color:#9bc5cf}}
</style>
<h1>Issue 156: bounded room streaming</h1>
<p>Finite seed-149 layout, streamed with the current room and its graph neighbors. Unloaded connected openings are shown with authored solid caps. This is an authored layout, not recovered source-video connectivity.</p>
<p><a href="layout_seed_149.svg">Layout diagram</a> · <a href="REPORT.md">Evidence report</a> ·
  Walkthrough command: <code>godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue156_streamed_walkthrough.tscn</code></p>
<div class="views">{figures}</div>
</html>
"""
    (EVIDENCE / "index.html").write_text(body)


def main() -> int:
    records = _records()
    _contact_sheet(records)
    _layout_diagram()
    _index(records)
    print(f"built #156 review bundle: {len(records)} views at {EVIDENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
