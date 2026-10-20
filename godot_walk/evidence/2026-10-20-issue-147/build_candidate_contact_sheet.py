"""Build candidate_contact_sheet.jpg from the views listed in the Bevy capture report.

Only files named in `captured_views` are tiled, so stray PNGs left in the capture
directory cannot appear on the sheet under a misleading label.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ISSUE_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = ISSUE_DIR / "captures" / "bevy"
CAPTURE_REPORT = CAPTURE_DIR / "bevy_capture_report.json"
OUTPUT = ISSUE_DIR / "candidate_contact_sheet.jpg"

ANCHOR_VIEW = "candidate_camera_at_frame_0152"
COLUMNS = 4
TILE_W, TILE_H = 320, 180
GAP = 12
CAPTION_H = 27
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def caption_for(view: str) -> str:
    if view == ANCHOR_VIEW:
        return "frame-0152 camera anchor (Bevy render)"
    return f"{view}.png"


def main() -> None:
    views = json.loads(CAPTURE_REPORT.read_text())["captured_views"]
    # Anchor view first so it sits next to the source-pipeline sheet's last tile.
    views = sorted(views, key=lambda view: view != ANCHOR_VIEW)
    rows = -(-len(views) // COLUMNS)
    width = GAP // 2 + COLUMNS * (TILE_W + GAP)
    height = GAP // 2 + rows * (TILE_H + CAPTION_H)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT_PATH, 11)
    for index, view in enumerate(views):
        x = GAP // 2 + (index % COLUMNS) * (TILE_W + GAP)
        y = GAP // 2 + (index // COLUMNS) * (TILE_H + CAPTION_H)
        tile = Image.open(CAPTURE_DIR / f"{view}.png").convert("RGB").resize((TILE_W, TILE_H))
        sheet.paste(tile, (x, y))
        draw.text((x + TILE_W / 2, y + TILE_H + 4), caption_for(view), fill="black", font=font, anchor="mt")
    sheet.save(OUTPUT, quality=90)
    print(f"wrote {OUTPUT.relative_to(ISSUE_DIR)} with {len(views)} views")


if __name__ == "__main__":
    main()
