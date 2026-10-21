#!/usr/bin/env python3
"""Build a two-anchor baseline/candidate sheet for the Blender round trip."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[4]
ROUND = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "godot_walk/evidence/2026-10-20-issue-150/captures/bevy"
CANDIDATE = ROUND / "captures/candidate"
OUTPUT = ROUND / "candidate_contact_sheet.jpg"
VIEWS = ("registered_frame_0152_anchor", "column_east_face")
IMAGE_SIZE = (720, 405)
GUTTER = 28


def load_font(size: int):
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(str(font_path), size) if font_path.is_file() else ImageFont.load_default()


def paste_view(canvas: Image.Image, draw: ImageDraw.ImageDraw, path: Path, x: int, y: int, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"missing matched capture: {path}")
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert("RGB"), IMAGE_SIZE)
    draw.text((x, y), label, fill=(31, 33, 29), font=load_font(20))
    canvas.paste(image, (x, y + 32))


def main() -> None:
    width = GUTTER * 3 + IMAGE_SIZE[0] * 2
    row_height = IMAGE_SIZE[1] + 68
    height = GUTTER * 3 + 55 + row_height * len(VIEWS)
    canvas = Image.new("RGB", (width, height), (239, 239, 230))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (GUTTER, GUTTER),
        "#153 | #150 baseline vs Blender visual-only repair",
        fill=(31, 33, 29),
        font=load_font(25),
    )
    for row, view in enumerate(VIEWS):
        y = GUTTER + 52 + row * row_height
        paste_view(canvas, draw, BASELINE / f"{view}.png", GUTTER, y, f"#150 baseline | {view}")
        paste_view(
            canvas,
            draw,
            CANDIDATE / f"{view}.png",
            GUTTER * 2 + IMAGE_SIZE[0],
            y,
            f"#153 overlay | {view}",
        )
    canvas.save(OUTPUT, quality=92, optimize=True)


if __name__ == "__main__":
    main()
