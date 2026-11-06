"""Generate deterministic worn and damaged surface textures for palettes 0.2.0 (#199).

Every output is derived from a texture already committed in the repository. The
script is CPU-only and deterministic: the seed comes from the source path, the
variant name and the script version, so rerunning it produces identical bytes.
No downloads and no GPU calls are involved.

Usage:
    python3 godot_walk/scripts/generate_surface_variants.py generate
    python3 godot_walk/scripts/generate_surface_variants.py check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, plan_write, sha256_file, write_new

SCRIPT_VERSION = "surface-variants-0.1.0"
OUTPUT_DIR = Path("godot_walk/assets/psx_extension/textures/surfaces")
MANIFEST_PATH = OUTPUT_DIR / "surface_variants.json"

# Source textures already in the repository. Each output name is explicit so the
# palette provenance check can find it in this file.
SOURCES = {
    "backrooms_yellow_wall": "godot_walk/assets/psx_extension/textures/wallpaper_source_video.png",
    "backrooms_yellow_floor": "godot_walk/assets/psx_extension/textures/floor_source_video.png",
    "backrooms_yellow_ceiling": "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    "industrial_concrete_floor": "godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/concrete_floor.png",
    "plaster_debris_wall": "godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/painted_wall.png",
}

OUTPUTS = {
    "backrooms_yellow_wall_worn": ("backrooms_yellow_wall", "worn"),
    "backrooms_yellow_wall_damaged": ("backrooms_yellow_wall", "damaged"),
    "backrooms_yellow_floor_worn": ("backrooms_yellow_floor", "worn"),
    "backrooms_yellow_floor_damaged": ("backrooms_yellow_floor", "damaged"),
    "backrooms_yellow_ceiling_worn": ("backrooms_yellow_ceiling", "worn"),
    "backrooms_yellow_ceiling_damaged": ("backrooms_yellow_ceiling", "damaged"),
    "industrial_concrete_floor_worn": ("industrial_concrete_floor", "worn"),
    "industrial_concrete_floor_damaged": ("industrial_concrete_floor", "damaged"),
    "plaster_debris_wall_worn": ("plaster_debris_wall", "worn"),
    "plaster_debris_wall_damaged": ("plaster_debris_wall", "damaged"),
}


def _seed(source_name: str, variant: str) -> int:
    text = f"{SCRIPT_VERSION}:{source_name}:{variant}"
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")


def _rgba(image: Image.Image) -> Image.Image:
    return image.convert("RGBA")


def _grime(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(max(8, (width * height) // 6000)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.randint(
            max(3, min(width, height) // 30), max(6, min(width, height) // 7)
        )
        alpha = int(rng.uniform(18, 55) * strength)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=(38, 31, 22, alpha)
        )
    return Image.alpha_composite(
        _rgba(image), overlay.filter(ImageFilter.GaussianBlur(1.2))
    )


def _stains(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(max(4, (width * height) // 18000)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius_x = rng.randint(width // 18, width // 5)
        radius_y = rng.randint(height // 22, height // 6)
        alpha = int(rng.uniform(35, 95) * strength)
        draw.ellipse(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            fill=(52, 38, 24, alpha),
        )
    return Image.alpha_composite(
        _rgba(image), overlay.filter(ImageFilter.GaussianBlur(2.0))
    )


def _cracks(image: Image.Image, rng: random.Random, count: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        points = [(x, y)]
        for _step in range(rng.randint(3, 7)):
            x = max(0, min(width - 1, x + rng.randint(-width // 10, width // 10)))
            y = max(0, min(height - 1, y + rng.randint(-height // 10, height // 10)))
            points.append((x, y))
        draw.line(
            points,
            fill=(18, 14, 10, rng.randint(80, 150)),
            width=max(1, min(width, height) // 180),
        )
    return Image.alpha_composite(_rgba(image), overlay)


def _peeling(image: Image.Image, rng: random.Random, count: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius_x = rng.randint(width // 30, width // 12)
        radius_y = rng.randint(height // 30, height // 12)
        draw.ellipse(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            fill=(188, 170, 132, rng.randint(60, 120)),
        )
        draw.arc(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            0,
            360,
            fill=(35, 28, 20, 110),
            width=max(1, min(width, height) // 200),
        )
    return Image.alpha_composite(_rgba(image), overlay)


def _speckles(image: Image.Image, rng: random.Random, count: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.randint(1, max(2, min(width, height) // 120))
        color = rng.choice(((24, 20, 15, 130), (118, 103, 78, 100), (67, 56, 42, 120)))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    return Image.alpha_composite(_rgba(image), overlay)


def _darken(image: Image.Image, factor: float) -> Image.Image:
    pixels = image.convert("RGB")
    return pixels.point(lambda value: int(value * factor))


def _variant_image(source: Image.Image, variant: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    width, height = source.size
    if variant == "worn":
        image = _grime(source, rng, 0.8)
        image = _stains(image, rng, 0.55)
        image = _cracks(image, rng, max(3, width // 90))
        image = _darken(image, 0.90)
    else:
        image = _grime(source, rng, 1.0)
        image = _stains(image, rng, 1.0)
        image = _cracks(image, rng, max(6, width // 45))
        image = _peeling(image, rng, max(2, width // 140))
        image = _speckles(image, rng, max(40, width * height // 2500))
        image = _darken(image, 0.78)
    return image.convert("RGB")


def _derived_path(output_name: str) -> Path:
    return ROOT / OUTPUT_DIR / f"{output_name}.png"


def derive_bytes(output_name: str) -> bytes:
    source_key, variant = OUTPUTS[output_name]
    source_path = ROOT / SOURCES[source_key]
    with Image.open(source_path) as source:
        image = _variant_image(
            source.convert("RGB"), variant, _seed(source_key, variant)
        )
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def manifest_bytes() -> bytes:
    records = []
    for output_name in sorted(OUTPUTS):
        source_key, variant = OUTPUTS[output_name]
        output = _derived_path(output_name)
        records.append(
            {
                "output": (OUTPUT_DIR / f"{output_name}.png").as_posix(),
                "output_sha256": sha256_file(output),
                "source": SOURCES[source_key],
                "source_sha256": sha256_file(ROOT / SOURCES[source_key]),
                "variant": variant,
            }
        )
    document = {
        "schema_version": 1,
        "script_version": SCRIPT_VERSION,
        "generator": "godot_walk/scripts/generate_surface_variants.py",
        "records": records,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def generate() -> dict[str, Any]:
    target_dir = ROOT / OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    for output_name in sorted(OUTPUTS):
        data = derive_bytes(output_name)
        path = _derived_path(output_name)
        status = plan_write(path, data)
        if status == "create":
            write_new(path, data)
            created += 1
    path = ROOT / MANIFEST_PATH
    data = manifest_bytes()
    status = plan_write(path, data)
    if status == "create":
        write_new(path, data)
        created += 1
    return {
        "output_dir": OUTPUT_DIR.as_posix(),
        "outputs": len(OUTPUTS),
        "manifest": MANIFEST_PATH.as_posix(),
        "created": created,
    }


def check() -> list[str]:
    errors = []
    for output_name in sorted(OUTPUTS):
        path = _derived_path(output_name)
        if not path.is_file():
            errors.append(f"{path.relative_to(ROOT)}: missing")
            continue
        expected = derive_bytes(output_name)
        if path.read_bytes() != expected:
            errors.append(
                f"{path.relative_to(ROOT)}: differs from deterministic output"
            )
    if errors:
        return errors
    manifest = ROOT / MANIFEST_PATH
    if not manifest.is_file():
        errors.append(f"{MANIFEST_PATH.as_posix()}: missing")
    else:
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as error:
            errors.append(f"{MANIFEST_PATH.as_posix()}: {error}")
        else:
            expected = json.loads(manifest_bytes().decode("utf-8"))
            if document != expected:
                errors.append(
                    f"{MANIFEST_PATH.as_posix()}: differs from deterministic manifest"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        print(json.dumps(generate(), sort_keys=True))
        return 0
    errors = check()
    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
