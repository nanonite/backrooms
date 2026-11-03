"""Build a display-only comparison from source, Hunyuan and Godot captures."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path("godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s")
CAPTURES = EVIDENCE / "room-captures-v4"
OUTPUT = EVIDENCE / "room_comparison_v2.jpg"
TILES = [
    (
        "Direct seed · frame 2731 · PTS 91.0 s",
        Path(
            "godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/"
            "issue169-seed-91s/frame_2731.png"
        ),
    ),
    (
        "Direct source context · frame 0820 · 27.3 s",
        Path(
            "godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/"
            "issue169-room-context-001/frame_0820.png"
        ),
    ),
    (
        "Direct source context · frame 4642 · 154.7 s",
        Path(
            "godot_walk/source_library/sources/video-b9161c467ed2d30a/frames/"
            "issue169-room-context-001/frame_4642.png"
        ),
    ),
    (
        "Hunyuan attempt 001 · rejected visual match",
        Path(
            "godot_walk/source_library/sources/video-b9161c467ed2d30a/hunyuan/"
            "attempt-001/panorama/panorama.png"
        ),
    ),
    ("Godot · spawn toward dresser", CAPTURES / "spawn_toward_dresser.png"),
    ("Godot · left oblique", CAPTURES / "left_oblique.png"),
    ("Godot · right oblique", CAPTURES / "right_oblique.png"),
    ("Godot · looking back at authored boundary", CAPTURES / "look_back_at_closed_boundary.png"),
]
TILE_SIZE = (480, 270)
LABEL_HEIGHT = 34
BACKGROUND = (24, 24, 24)
GRID_COLUMNS = 4


def main() -> None:
    output = ROOT / OUTPUT
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    rows = (len(TILES) + GRID_COLUMNS - 1) // GRID_COLUMNS
    sheet = Image.new(
        "RGB",
        (TILE_SIZE[0] * GRID_COLUMNS, (TILE_SIZE[1] + LABEL_HEIGHT) * rows),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (label, relative_path) in enumerate(TILES):
        source = Image.open(ROOT / relative_path).convert("RGB")
        tile = ImageOps.fit(source, TILE_SIZE, method=Image.Resampling.LANCZOS)
        x = (index % GRID_COLUMNS) * TILE_SIZE[0]
        y = (index // GRID_COLUMNS) * (TILE_SIZE[1] + LABEL_HEIGHT)
        sheet.paste(tile, (x, y))
        draw.text((x + 8, y + TILE_SIZE[1] + 9), label, font=font, fill=(240, 235, 225))
    sheet.save(output, quality=92)
    print(OUTPUT.as_posix())


if __name__ == "__main__":
    main()
