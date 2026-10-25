"""Make a labelled contact sheet of direct source-frame material crops."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EVIDENCE = Path(__file__).resolve().parent
SOURCE = EVIDENCE / "source_textures"
OUTPUT = EVIDENCE / "source_textures_contact.jpg"
TILES = (("wallpaper", "wallpaper.png"), ("floor", "floor.png"),
         ("ceiling", "ceiling.png"), ("column face", "column_face.png"))
TILE_SIZE = (420, 300)
HEADER_HEIGHT = 42


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite contact sheet: {OUTPUT}")
    canvas = Image.new("RGB", (TILE_SIZE[0] * 2, (TILE_SIZE[1] + HEADER_HEIGHT) * 2), "#282821")
    draw = ImageDraw.Draw(canvas)
    for index, (label, filename) in enumerate(TILES):
        image_path = SOURCE / filename
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        with Image.open(image_path) as source:
            thumbnail = source.convert("RGB")
            thumbnail.thumbnail(TILE_SIZE, Image.Resampling.NEAREST)
        x = index % 2 * TILE_SIZE[0]
        y = index // 2 * (TILE_SIZE[1] + HEADER_HEIGHT)
        draw.text((x + 12, y + 12), label, fill="#fff2c8", font=ImageFont.load_default(size=20))
        canvas.paste(thumbnail, (x, y + HEADER_HEIGHT))
    canvas.save(OUTPUT, quality=92)
    print(f"SOURCE_TEXTURE_CONTACT: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
