"""Create a contact sheet from only views recorded in the Bevy capture report."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ISSUE_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = ISSUE_DIR / "generated/captures/assembled_connector"
REPORT = CAPTURE_DIR / "bevy_capture_report.json"
OUTPUT = CAPTURE_DIR / "candidate_contact_sheet.jpg"
CAPTIONS = {
    "later_bay_approach": "#150 room, approaching authored threshold",
    "doorway_from_later_bay": "Doorway from later-bay side",
    "connector_midpoint": "Authored hall midpoint",
    "pocket_entry": "Early-pocket entry",
    "pocket_far_end": "Pocket interior, looking back",
    "pocket_return": "Pocket side return view",
    "column_to_connector": "Existing #150 column toward connector",
    "connector_return": "Authored hall, return direction",
}
COLUMNS = 2
TILE_W, TILE_H = 480, 270
GAP, CAPTION_H = 16, 34
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def main() -> None:
    captured_views = json.loads(REPORT.read_text(encoding="utf-8"))["captured_views"]
    rows = (len(captured_views) + COLUMNS - 1) // COLUMNS
    width = GAP // 2 + COLUMNS * (TILE_W + GAP)
    height = GAP // 2 + rows * (TILE_H + CAPTION_H)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT_PATH, 14)
    for index, view_name in enumerate(captured_views):
        x = GAP // 2 + (index % COLUMNS) * (TILE_W + GAP)
        y = GAP // 2 + (index // COLUMNS) * (TILE_H + CAPTION_H)
        tile = Image.open(CAPTURE_DIR / f"{view_name}.png").convert("RGB")
        sheet.paste(tile.resize((TILE_W, TILE_H)), (x, y))
        draw.text(
            (x + TILE_W / 2, y + TILE_H + 5),
            CAPTIONS.get(view_name, view_name),
            fill="black",
            font=font,
            anchor="mt",
        )
    sheet.save(OUTPUT, quality=92)
    print(f"wrote {OUTPUT.name} from {len(captured_views)} report-listed views")


if __name__ == "__main__":
    main()
