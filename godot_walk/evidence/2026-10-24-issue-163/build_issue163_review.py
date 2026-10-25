"""Build the source/candidate contact sheet and local review page."""

from __future__ import annotations

import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EVIDENCE = Path(__file__).resolve().parent
SOURCE = EVIDENCE / "room_large_frame_0013.png"
CAPTURE_DIR = EVIDENCE / "captures_final"
MANIFEST = CAPTURE_DIR / "capture_manifest.json"
SHEET = EVIDENCE / "candidate_contact_sheet.jpg"
PAGE = EVIDENCE / "index.html"
TILE_SIZE = (400, 225)
TILE_HEADER = 42
VIEWS = (
    ("source_frame", "Source video · frame 0013", SOURCE),
    ("spawn_column", "Godot · spawn view", CAPTURE_DIR / "spawn_column.png"),
    ("column_south", "Godot · column south face", CAPTURE_DIR / "column_south.png"),
    ("column_west", "Godot · column west face", CAPTURE_DIR / "column_west.png"),
    ("open_passage", "Godot · open passage", CAPTURE_DIR / "open_passage.png"),
    ("hallway_end", "Godot · hallway end", CAPTURE_DIR / "hallway_end.png"),
    ("hallway_return", "Godot · hallway return", CAPTURE_DIR / "hallway_return.png"),
    ("room_corner", "Godot · room corner", CAPTURE_DIR / "room_corner.png"),
)


def main() -> int:
    _require_new_outputs()
    captures = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _build_contact_sheet()
    _build_page(captures)
    print(f"ISSUE163_REVIEW_READY: {PAGE}")
    return 0


def _require_new_outputs() -> None:
    for path in (SHEET, PAGE):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite review artifact: {path}")
    if not MANIFEST.is_file() or not SOURCE.is_file():
        raise FileNotFoundError("Source image or final capture manifest is missing")


def _build_contact_sheet() -> None:
    title_height = 84
    sheet = Image.new("RGB", (TILE_SIZE[0] * 3, title_height + (TILE_SIZE[1] + TILE_HEADER) * 3), "#22231f")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=18)
    small_font = ImageFont.load_default(size=14)
    draw.text((20, 14), "#163 · room_large source-frame room prototype", fill="#f4e7c2", font=font)
    draw.text((20, 44), "Direct video frame and authored Godot views · no Hunyuan panorama output · scale uncalibrated", fill="#cfc4a4", font=small_font)
    for index, (_view_id, label, path) in enumerate(VIEWS):
        x = index % 3 * TILE_SIZE[0]
        y = title_height + index // 3 * (TILE_SIZE[1] + TILE_HEADER)
        draw.rectangle((x, y, x + TILE_SIZE[0], y + TILE_HEADER), fill="#383a33")
        draw.text((x + 12, y + 12), label, fill="#f4e7c2", font=small_font)
        with Image.open(path) as source:
            tile = source.convert("RGB")
            tile.thumbnail(TILE_SIZE, Image.Resampling.LANCZOS)
            sheet.paste(tile, (x, y + TILE_HEADER))
    sheet.save(SHEET, quality=92)


def _build_page(captures: dict) -> None:
    images = "\n".join(_image_panel(label, path) for _, label, path in VIEWS)
    capture_rows = "\n".join(
        f"<li>{html.escape(view['view_id'])}: {view['width']}×{view['height']}</li>"
        for view in captures["poses"]
    )
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Issue 163 room review</title>
<style>
body{{font:16px system-ui,sans-serif;background:#22231f;color:#eee8d6;max-width:1240px;margin:2rem auto;padding:0 1rem}}
h1,h2{{color:#f4e7c2}} .notice{{padding:1rem;background:#3c382b;border-left:4px solid #e7c45d}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:1rem}}
figure{{margin:0;background:#30312b;padding:.6rem}} img{{max-width:100%;height:auto}} figcaption{{padding:.4rem}}
code{{background:#363730;padding:.2rem .35rem}} a{{color:#b6e1d2}}
</style>
<h1>Issue 163 · another source-video room</h1>
<div class="notice"><b>Review candidate; not accepted.</b> This room uses direct crops from frame 0013 of <code>data/videos/room_large.mp4</code>. The local Panogen attempts stopped at the GPU memory guard before producing a panorama; no SceneGen mesh was created. Authored boundaries and collision are separate from the source-textured visuals. Physical scale and registration remain unaccepted.</div>
<p><a href="candidate_contact_sheet.jpg">Contact sheet</a> · <a href="source_candidates_contact.jpg">Source-video candidates</a> · <a href="source_textures_contact.jpg">Direct-source texture crops</a> · <a href="layout_proposal.svg">Authored layout proposal</a></p>
<h2>Evidence views</h2><div class="grid">{images}</div>
<h2>Walkthrough</h2>
<p>From the workspace root:</p>
<pre><code>godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://evidence/2026-10-24-issue-163/issue163_room.tscn</code></pre>
<p>Use WASD and mouse; Escape releases the pointer. F6 toggles the packaged URSC material pass.</p>
<h2>Mechanical and render evidence</h2>
<ul><li>Godot 4.6.3; Vulkan captures use 960×540, 75° FOV, 12 settle frames.</li>
<li>Bounded route: 35.73 m out-and-back; 100% floor support; zero SafetyNet contacts.</li>
<li>Boundary removal and floor removal both fail the mechanical verifier, as expected.</li>
<li>Capture preflight and process resource measurements are in <code>captures_final_status.json</code>.</li>
<li>Per-view IDs and positions: <code>captures_final/capture_manifest.json</code>.</li></ul>
<h2>Source and constraints</h2>
<p><a href="REPORT.md">Full evidence report</a> · <a href="operator_review.json">Operator decision</a> · <a href="SOURCE_SELECTION.md">Source selection</a> · <a href="source_manifest.json">Source hashes and frames</a> · <a href="worldgen/">Panogen attempt logs and resource samples</a> · <a href="mechanics_final/physics_candidate.json">Walk verification</a></p>
<p><code>registration_accepted=false</code>; <code>scale_calibrated=false</code>. Authored layout dimensions are a design convention, not recovered video geometry. The open passage is local room geometry, not a tested connector to another module.</p>
</html>"""
    PAGE.write_text(page, encoding="utf-8")


def _image_panel(label: str, path: Path) -> str:
    relative = path.relative_to(EVIDENCE).as_posix()
    return f'<figure><img src="{html.escape(relative)}" alt="{html.escape(label)}"><figcaption>{html.escape(label)}</figcaption></figure>'


if __name__ == "__main__":
    raise SystemExit(main())
