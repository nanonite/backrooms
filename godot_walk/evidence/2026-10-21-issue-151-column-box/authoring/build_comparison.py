"""Place original matched captures beside the candidate for operator review."""

from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT = Path(__file__).resolve().parents[1]
VIEWS = ["patch_anchor", "column_east"]
VARIANTS = ["preserve_hunyuan", "four_sided_box"]


def main():
    sheet = Image.new("RGB", (1968, 1210), "#eeeee4")
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 16), "#151 | Four-sided box candidate | NOT SELECTED | uncalibrated", fill="black")
    for row, view in enumerate(VIEWS):
        for column, variant in enumerate(VARIANTS):
            destination = (24 + column * 984, 65 + row * 590)
            draw.text((destination[0], destination[1] - 22), f"{variant} | {view}", fill="black")
            with Image.open(OUTPUT / "captures" / variant / f"{view}.png") as capture:
                sheet.paste(capture.convert("RGB"), destination)
    sheet.save(OUTPUT / "comparison.png")


if __name__ == "__main__":
    main()
