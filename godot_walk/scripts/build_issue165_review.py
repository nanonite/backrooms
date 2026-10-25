"""Build the offline #165 source-versus-adaptation review bundle."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-25-issue-165"
SOURCE_MANIFEST = EVIDENCE / "source_frames/extraction_manifest.json"
CAPTURE_MANIFEST = EVIDENCE / "captures/v2/capture_manifest.json"
OUTPUTS = [
	EVIDENCE / "source_reference_contact_sheet_v2.jpg",
	EVIDENCE / "adapted_room_contact_sheet_v2.jpg",
	EVIDENCE / "source_vs_adaptation_contact_sheet_v2.jpg",
	EVIDENCE / "authored_layout_proposal_v2.svg",
	EVIDENCE / "index_v2.html",
]
THUMBNAIL = (640, 360)
BACKGROUND = (22, 22, 22)


def main() -> int:
    _require_fresh_outputs()
    sources = _read_json(SOURCE_MANIFEST)
    captures = _read_json(CAPTURE_MANIFEST)
    source_by_id = {frame["frame_id"]: frame for frame in sources["frames"]}
    pairs = _resolve_pairs(source_by_id, captures["views"])
    _write_source_sheet(sources["frames"])
    _write_candidate_sheet(captures["views"])
    _write_pair_sheet(pairs)
    _write_layout_diagram()
    _write_review_page(pairs, sources, captures)
    print(f"ISSUE165_REVIEW_BUNDLE pairs={len(pairs)} outputs={len(OUTPUTS)}")
    return 0


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing review input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_fresh_outputs() -> None:
    existing = [path.relative_to(ROOT).as_posix() for path in OUTPUTS if path.exists()]
    if existing:
        raise FileExistsError("Refusing to overwrite review output(s): " + ", ".join(existing))


def _resolve_pairs(source_by_id: dict, views: list[dict]) -> list[tuple[dict, dict]]:
    pairs = []
    for view in views:
        source = source_by_id.get(view.get("source_frame_id"))
        if source is None:
            raise ValueError(f"Capture refers to missing source frame: {view.get('source_frame_id')}")
        candidate_path = ROOT / "godot_walk" / view["path"].removeprefix("res://")
        if not (ROOT / source["path"]).is_file() or not candidate_path.is_file():
            raise FileNotFoundError(f"Missing source or capture image for {view['id']}")
        pairs.append((source, view))
    return pairs


def _load_thumbnail(path: str) -> Image.Image:
    base = ROOT / "godot_walk" if path.startswith("res://") else ROOT
    source_path = base / path.removeprefix("res://")
    with Image.open(source_path) as source:
        image = source.convert("RGB")
        image.thumbnail(THUMBNAIL)
        frame = Image.new("RGB", THUMBNAIL, BACKGROUND)
        frame.paste(image, ((THUMBNAIL[0] - image.width) // 2, (THUMBNAIL[1] - image.height) // 2))
        return frame


def _font() -> ImageFont.ImageFont:
    return ImageFont.load_default()


def _write_source_sheet(frames: list[dict]) -> None:
    _write_grid(
        OUTPUTS[0],
        [(frame["path"], f"{frame['frame_id']} · t={frame['timestamp_seconds']:.3f}s · direct source") for frame in frames],
        columns=2,
    )


def _write_candidate_sheet(views: list[dict]) -> None:
    _write_grid(
        OUTPUTS[1],
        [(view["path"], f"{view['id']} · source context {view['source_frame_id']}") for view in views],
        columns=3,
    )


def _write_pair_sheet(pairs: list[tuple[dict, dict]]) -> None:
    label_height = 28
    tile_height = THUMBNAIL[1] + label_height
    canvas = Image.new("RGB", (THUMBNAIL[0] * 2, tile_height * len(pairs)), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    for index, (source, view) in enumerate(pairs):
        top = index * tile_height
        canvas.paste(_load_thumbnail(source["path"]), (0, top))
        canvas.paste(_load_thumbnail(view["path"]), (THUMBNAIL[0], top))
        draw.text((8, top + THUMBNAIL[1] + 7), f"Source {source['frame_id']} · not a registered camera match", fill="white", font=_font())
        draw.text((THUMBNAIL[0] + 8, top + THUMBNAIL[1] + 7), f"Authored candidate · {view['id']}", fill="white", font=_font())
    canvas.save(OUTPUTS[2], quality=92)


def _write_grid(path: Path, entries: list[tuple[str, str]], columns: int) -> None:
    label_height = 28
    tile_height = THUMBNAIL[1] + label_height
    rows = (len(entries) + columns - 1) // columns
    canvas = Image.new("RGB", (THUMBNAIL[0] * columns, tile_height * rows), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    for index, (image_path, label) in enumerate(entries):
        x = index % columns * THUMBNAIL[0]
        y = index // columns * tile_height
        canvas.paste(_load_thumbnail(image_path), (x, y))
        draw.text((x + 8, y + THUMBNAIL[1] + 7), label, fill="white", font=_font())
    canvas.save(path, quality=92)


def _write_layout_diagram() -> None:
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="820" viewBox="0 0 960 820">
<rect width="100%" height="100%" fill="#f4f1e8"/>
<text x="70" y="38" font-family="sans-serif" font-size="24" font-weight="bold">Issue 165 authored L-corridor proposal (uncalibrated)</text>
<text x="70" y="66" font-family="sans-serif" font-size="14">The orthogonal boundary, turn, and obstacle completion are design choices, not recovered floor-plan facts.</text>
<g transform="translate(500 240) scale(70 -70)">
  <path d="M-6 -2 L0 -2 L0 -7 L4 -7 L4 2 L-6 2 Z" fill="#e6d39a" stroke="#302820" stroke-width="0.055"/>
  <rect x="-6.08" y="2.08" width="10.16" height="9.16" fill="none" stroke="#151515" stroke-width="0.025" stroke-dasharray="0.10 0.05"/>
  <rect x="-2.95" y="-0.45" width="0.9" height="0.9" fill="#9b8650" stroke="#231c12" stroke-width="0.035"/>
  <polyline points="-5,0 -4,1.15 -1,1.15 0.8,0.5 2,-2.8 2,-5.8 2,-2.8 0.8,0.5 -1,1.15 -4,1.15 -5,0" fill="none" stroke="#b44b26" stroke-width="0.035" stroke-dasharray="0.12 0.07"/>
  <circle cx="-5" cy="0" r="0.11" fill="#166534"/>
</g>
<g font-family="sans-serif" font-size="13" fill="#302820">
 <text x="142" y="266">safe spawn</text>
 <text x="360" y="222">column observed; hidden box faces authored</text>
 <text x="250" y="360">main leg</text>
 <text x="675" y="455">turn leg</text>
 <text x="620" y="700">authored closed far cap</text>
 <text x="635" y="721">dashed rectangle = conservative render AABB</text>
</g>
<g font-family="sans-serif" font-size="14">
 <circle cx="44" cy="765" r="7" fill="#166534"/><text x="60" y="770">safe spawn</text>
 <line x1="190" y1="765" x2="230" y2="765" stroke="#b44b26" stroke-width="3" stroke-dasharray="8 5"/><text x="240" y="770">tested route and return</text>
 <rect x="470" y="756" width="18" height="18" fill="#9b8650" stroke="#231c12"/><text x="500" y="770">source-observed column, box completion authored</text>
 <line x1="32" y1="792" x2="72" y2="792" stroke="#151515" stroke-width="2"/><text x="82" y="797">all six boundary edges closed; no sockets or connectors</text>
</g>
</svg>'''
    OUTPUTS[3].write_text(svg, encoding="utf-8")


def _write_review_page(pairs: list[tuple[dict, dict]], source_manifest: dict, capture_manifest: dict) -> None:
    cards = []
    for source, view in pairs:
        source_relative = Path(source["path"]).relative_to(EVIDENCE.relative_to(ROOT)).as_posix()
        candidate_path = Path("godot_walk") / view["path"].removeprefix("res://")
        candidate_relative = candidate_path.relative_to(EVIDENCE.relative_to(ROOT)).as_posix()
        cards.append(f"""
<article class="pair"><h2>{html.escape(view['id'])}</h2>
 <p>Source anchor: {html.escape(source['frame_id'])}, t={source['timestamp_seconds']:.3f}s. Perspective is not registered or matched.</p>
 <div class="images"><figure><img src="{html.escape(source_relative)}" alt="Direct source frame {html.escape(source['frame_id'])}"><figcaption>Direct source frame {html.escape(source['frame_id'])}</figcaption></figure>
 <figure><img src="{html.escape(candidate_relative)}" alt="Authored candidate view {html.escape(view['id'])}"><figcaption>Godot candidate view {html.escape(view['id'])}</figcaption></figure></div></article>""")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chainlink #165 · supervised video-to-PSX transfer review</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#141414;color:#eee}}main{{max-width:1400px;margin:auto;padding:24px}}h1,h2{{line-height:1.2}}a{{color:#f0c674}}.notice{{background:#2a261b;border-left:4px solid #d99a3b;padding:14px}}.images{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}figure{{margin:0;background:#222;padding:8px}}img{{width:100%;height:auto;display:block}}figcaption{{padding:8px 0 0}}.pair{{border-top:1px solid #555;padding:18px 0}}code{{overflow-wrap:anywhere}}@media(max-width:850px){{.images{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Chainlink #165 · source video to bounded PSX room</h1>
<div class="notice"><strong>Review scope:</strong> inspect the new <code>corridor_corner.mp4</code> adaptation. The candidate is provisional; it does not inherit #163/#164 design approval.</div>
<h2>Source and adaptation</h2><p>The source frames are decoded directly from the original 1920×1080, {source_manifest['metadata']['fps']:g} fps video. Candidate views use the same material profile and controller as the existing Godot project.</p>
<p>Each pair uses a source frame as context only. The camera positions are not registered, pose-matched, or scale-calibrated. The authored L-shaped boundary is a design choice, not a recovered plan. The source footage is synthetic and has visible ceiling/geometry discontinuities.</p>
<p><a href="source_reference_contact_sheet_v2.jpg">Source frame sheet</a> · <a href="adapted_room_contact_sheet_v2.jpg">Adapted room sheet</a> · <a href="source_vs_adaptation_contact_sheet_v2.jpg">Paired comparison sheet</a> · <a href="authored_layout_proposal_v2.svg">Authored layout proposal</a> · <a href="../../room_catalog/adaptations/corridor-corner-v2.json">Transfer adaptation v2 record</a> · <a href="../../room_catalog/adaptations/room-large-v1.json">Accepted #163/#164 record</a> · <a href="REPORT.md">Report</a> · <a href="COMMANDS.md">Commands</a></p>
<h2>Authored layout and walkthrough</h2><p>The candidate has one completed box column, an L-shaped walkable union, a closed visible shell, and separate boundary/obstacle collision. It has no connector. Walk the full turn and backtrack before judging whether the source appearance and authored footprint work together.</p>
<p>FPS walkthrough: <code>godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue165_corridor_corner_transfer.tscn</code> · WASD to move, mouse to look, Escape to release the pointer, R to reset.</p>
<h2>Operator question</h2><p>Does this authored L-shaped room, with direct source-cropped wallpaper/floor/ceiling and a completed four-sided column, feel like a useful playable adaptation of <code>corridor_corner.mp4</code> despite the unregistered layout?</p>
<h2>View comparisons</h2>{''.join(cards)}
<footer><p>Capture bundle: {len(capture_manifest['views'])} views at the project resolution; scene ready in {capture_manifest['scene_ready_ms']} ms. This is one supervised transfer example, not a universal or unattended ingestion claim.</p></footer>
</main></body></html>"""
    OUTPUTS[4].write_text(page, encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as error:
        print(f"issue165 review build failed: {error}", file=sys.stderr)
        raise SystemExit(2)
