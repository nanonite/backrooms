"""Generate a deterministic synthetic picture set for CPU-only intake checks.

The images contain simple coloured geometry, not a real room. A real
operator-supplied picture set and its seed review remain the human step.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_OUTPUT = Path("data/pictures/synthetic-picture-set-221")
DEFAULT_SIZE = (320, 240)
BACKGROUNDS = ((18, 22, 28), (28, 24, 18), (20, 28, 24))
WALLS = ((92, 84, 64), (72, 80, 88), (88, 72, 72))
LAMPS = ((220, 214, 176), (176, 208, 220), (220, 176, 176))


def create_picture_set(
    directory: Path,
    count: int = 3,
    size: tuple[int, int] = DEFAULT_SIZE,
) -> list[Path]:
    """Write `count` deterministic PNGs and return them in name order."""
    if count < 1:
        raise ValueError("A picture set needs at least one image")
    if directory.exists() or directory.is_symlink():
        raise FileExistsError(f"Refusing to overwrite picture set: {directory}")
    directory.mkdir(parents=True)
    width, height = size
    paths = []
    for index in range(1, count + 1):
        slot = (index - 1) % len(BACKGROUNDS)
        image = Image.new("RGB", size, BACKGROUNDS[slot])
        draw = ImageDraw.Draw(image)
        _draw_synthetic_room(draw, width, height, index, slot)
        path = directory / f"img_{index:04d}.png"
        image.save(path, format="PNG")
        paths.append(path)
    return paths


def _draw_synthetic_room(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    index: int,
    slot: int,
) -> None:
    horizon = int(height * 0.42)
    draw.rectangle([0, horizon, width, height], fill=(44, 44, 42))
    draw.rectangle(
        [int(width * 0.08), horizon - int(height * 0.18), int(width * 0.92), horizon],
        outline=WALLS[slot],
        width=max(2, width // 80),
    )
    lamp_y = max(4, horizon - int(height * 0.30))
    draw.rectangle(
        [int(width * (0.18 + 0.12 * slot)), lamp_y, int(width * 0.46), lamp_y + 6],
        fill=LAMPS[slot],
    )
    draw.line(
        [
            int(width * (0.12 + 0.04 * index)),
            height - 8,
            int(width * 0.50),
            horizon + 4,
            int(width * (0.86 - 0.03 * index)),
            height - 8,
        ],
        fill=(120, 116, 104),
        width=max(2, width // 60),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--width", type=int, default=DEFAULT_SIZE[0])
    parser.add_argument("--height", type=int, default=DEFAULT_SIZE[1])
    arguments = parser.parse_args()
    if arguments.width < 1 or arguments.height < 1:
        parser.error("Image dimensions must be positive")
    paths = create_picture_set(
        arguments.output,
        arguments.count,
        (arguments.width, arguments.height),
    )
    print(
        json.dumps(
            {
                "output": arguments.output.as_posix(),
                "image_count": len(paths),
                "images": [path.name for path in paths],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
