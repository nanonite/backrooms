"""Build a labeled #150 review sheet from the capture report's listed views."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ISSUE_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = ISSUE_DIR / "captures" / "bevy"
REPORT = CAPTURE_DIR / "bevy_capture_report.json"
OUTPUT = ISSUE_DIR / "candidate_contact_sheet.jpg"
CAPTIONS = {
    "south_room_end": "South authored end, looking inward",
    "north_room_end": "North authored end, looking inward",
    "west_room_end": "West authored end, looking inward",
    "east_room_end": "East authored end, looking inward",
    "column_south_face": "Column south face, authored cover",
    "column_north_face": "Column north face, authored cover",
    "column_west_face": "Column west face, authored cover",
    "column_east_face": "Column east face, authored cover",
    "registered_frame_0152_anchor": "Registered frame-0152 camera anchor",
}
COLUMNS = 3
TILE_W, TILE_H = 320, 180
GAP, CAPTION_H = 12, 31
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def main() -> None:
    captured_views = json.loads(REPORT.read_text(encoding="utf-8"))["captured_views"]
    rows = (len(captured_views) + COLUMNS - 1) // COLUMNS
    width = GAP // 2 + COLUMNS * (TILE_W + GAP)
    height = GAP // 2 + rows * (TILE_H + CAPTION_H)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT_PATH, 11)
    for index, view_name in enumerate(captured_views):
        x = GAP // 2 + (index % COLUMNS) * (TILE_W + GAP)
        y = GAP // 2 + (index // COLUMNS) * (TILE_H + CAPTION_H)
        image_path = CAPTURE_DIR / f"{view_name}.png"
        tile = Image.open(image_path).convert("RGB").resize((TILE_W, TILE_H))
        sheet.paste(tile, (x, y))
        draw.text(
            (x + TILE_W / 2, y + TILE_H + 4),
            CAPTIONS.get(view_name, view_name),
            fill="black",
            font=font,
            anchor="mt",
        )
    sheet.save(OUTPUT, quality=92)
    print(f"wrote {OUTPUT.name} from {len(captured_views)} reported views")


if __name__ == "__main__":
    main()
