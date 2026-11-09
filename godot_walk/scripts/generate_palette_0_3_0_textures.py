"""Generate the deterministic tile, metal and wood textures for palettes 0.3.0 (#208).

Every output is drawn on the CPU from a fixed recipe and a seed derived from the
palette, surface and variant name. Rerunning the script produces identical bytes;
no downloads, GPU calls or source photographs are involved. The three original
0.2.0 palettes and their textures are untouched.

Usage:
    python3 godot_walk/scripts/generate_palette_0_3_0_textures.py generate
    python3 godot_walk/scripts/generate_palette_0_3_0_textures.py check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, plan_write, sha256_file, write_new

SCRIPT_VERSION = "palette-0-3-0-textures-0.1.0"
SCRIPT_PATH = "godot_walk/scripts/generate_palette_0_3_0_textures.py"
OUTPUT_DIR = Path("godot_walk/assets/psx_extension/textures/surfaces")
MANIFEST_PATH = OUTPUT_DIR / "palette_0_3_0_textures.json"
SIZE = 128
VARIANTS = ("clean", "worn", "damaged")
RECIPES = {
    "tiled_institutional_wall": ("tile", "pale tile wall"),
    "tiled_institutional_floor": ("floor_tile", "institutional floor tile"),
    "tiled_institutional_ceiling": ("ceiling_tile", "low-key ceiling tile"),
    "metal_service_floor": ("metal_grating", "service floor grating"),
    "metal_service_ceiling": ("metal_panel", "service ceiling panel"),
    "wood_parquet_floor": ("parquet", "wood parquet floor"),
}
OUTPUTS = {
    f"{name}_{variant}": (name, variant)
    for name in RECIPES
    for variant in VARIANTS
}


def _seed(name: str, variant: str) -> int:
    text = f"{SCRIPT_VERSION}:{name}:{variant}"
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")


def _rgba(image: Image.Image) -> Image.Image:
    return image.convert("RGBA")


def _jitter(rng: random.Random, colour: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, channel + rng.randint(-amount, amount))) for channel in colour)


def _speckle(image: Image.Image, rng: random.Random, count: int, colours) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.randint(1, 2)
        draw.point((x, y), fill=rng.choice(colours) + (rng.randint(30, 90),))
        if radius > 1:
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=rng.choice(colours) + (rng.randint(12, 40),),
            )
    return Image.alpha_composite(_rgba(image), overlay)


def _tiles(image: Image.Image, rng: random.Random, count: int, grout: tuple[int, int, int],
           colours: tuple[tuple[int, int, int], ...], grout_width: int = 2) -> Image.Image:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    cell_w = width / count
    cell_h = height / count
    for row in range(count):
        for column in range(count):
            x0 = round(column * cell_w)
            y0 = round(row * cell_h)
            x1 = round((column + 1) * cell_w) - 1
            y1 = round((row + 1) * cell_h) - 1
            colour = _jitter(rng, rng.choice(colours), 8)
            draw.rectangle((x0, y0, x1, y1), fill=colour)
            edge = tuple(max(0, channel - 10) for channel in colour)
            draw.line((x0, y0, x1, y0), fill=edge, width=1)
            draw.line((x0, y0, x0, y1), fill=edge, width=1)
    for index in range(count + 1):
        x = round(index * cell_w)
        y = round(index * cell_h)
        draw.line((x, 0, x, height), fill=grout, width=grout_width)
        draw.line((0, y, width, y), fill=grout, width=grout_width)
    return image


def _threads(image: Image.Image, rng: random.Random, count: int, colour: tuple[int, int, int]) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        y = rng.randrange(height)
        x0 = rng.randrange(width)
        length = rng.randint(width // 10, width // 2)
        draw.line((x0, y, min(width, x0 + length), y), fill=colour + (rng.randint(18, 50),), width=1)
    return Image.alpha_composite(_rgba(image), overlay)


def _grime(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(max(10, (width * height) // 4500)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.randint(max(3, width // 24), max(6, width // 6))
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(40, 34, 26, int(rng.uniform(18, 55) * strength)),
        )
    return Image.alpha_composite(_rgba(image), overlay.filter(ImageFilter.GaussianBlur(1.2)))


def _stains(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(max(4, (width * height) // 16000)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius_x = rng.randint(width // 16, width // 4)
        radius_y = rng.randint(height // 18, height // 5)
        draw.ellipse(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            fill=(54, 40, 25, int(rng.uniform(28, 80) * strength)),
        )
    return Image.alpha_composite(_rgba(image), overlay.filter(ImageFilter.GaussianBlur(2.0)))


def _scratches(image: Image.Image, rng: random.Random, count: int,
               colour: tuple[int, int, int], alpha: int = 110) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        length = rng.randint(width // 12, width // 3)
        if rng.random() < 0.5:
            draw.line((x, y, min(width, x + length), y), fill=colour + (alpha,), width=1)
        else:
            draw.line((x, y, x, min(height, y + length)), fill=colour + (alpha,), width=1)
    return Image.alpha_composite(_rgba(image), overlay)


def _cracks(image: Image.Image, rng: random.Random, count: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        points = [(x, y)]
        for _step in range(rng.randint(3, 7)):
            x = max(0, min(width - 1, x + rng.randint(-width // 9, width // 9)))
            y = max(0, min(height - 1, y + rng.randint(-height // 9, height // 9)))
            points.append((x, y))
        draw.line(points, fill=(20, 16, 12, rng.randint(90, 160)), width=1)
    return Image.alpha_composite(_rgba(image), overlay)


def _chips(image: Image.Image, rng: random.Random, count: int,
           fill: tuple[int, int, int]) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius_x = rng.randint(width // 40, width // 16)
        radius_y = rng.randint(height // 40, height // 16)
        draw.ellipse(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            fill=fill + (rng.randint(80, 150),),
        )
    return Image.alpha_composite(_rgba(image), overlay)


def _rust(image: Image.Image, rng: random.Random, count: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    for _ in range(count):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = rng.randint(width // 28, width // 10)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=rng.choice(((116, 58, 28, 100), (84, 40, 20, 120), (148, 82, 38, 80))),
        )
    return Image.alpha_composite(_rgba(image), overlay.filter(ImageFilter.GaussianBlur(1.0)))


def _darken(image: Image.Image, factor: float) -> Image.Image:
    return image.convert("RGB").point(lambda value: int(value * factor))


def _tile_floor(variant: str, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), (168, 166, 150))
    _tiles(
        image,
        rng,
        4,
        (84, 83, 74),
        ((178, 176, 160), (166, 165, 150), (188, 186, 168), (154, 156, 146)),
    )
    image = _speckle(image, rng, 220, ((104, 102, 92), (210, 206, 188), (132, 134, 124)))
    if variant != "clean":
        image = _grime(image, rng, 0.9 if variant == "worn" else 1.3)
        image = _scratches(image, rng, 24 if variant == "worn" else 50, (68, 66, 58), 90)
        image = _darken(image, 0.92 if variant == "worn" else 0.82)
    if variant == "damaged":
        image = _stains(image, rng, 1.0)
        image = _cracks(image, rng, 9)
        image = _chips(image, rng, 16, (52, 48, 40))
    return image.convert("RGB")


def _tile_wall(variant: str, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), (196, 202, 198))
    _tiles(
        image,
        rng,
        8,
        (128, 136, 132),
        ((206, 212, 206), (192, 200, 196), (216, 220, 212), (184, 194, 190)),
        grout_width=1,
    )
    image = _speckle(image, rng, 160, ((142, 152, 146), (230, 232, 222), (176, 186, 178)))
    if variant != "clean":
        image = _grime(image, rng, 0.8 if variant == "worn" else 1.1)
        image = _darken(image, 0.94 if variant == "worn" else 0.86)
    if variant == "damaged":
        image = _cracks(image, rng, 7)
        image = _chips(image, rng, 20, (118, 116, 104))
        image = _stains(image, rng, 0.8)
    return image.convert("RGB")


def _tile_ceiling(variant: str, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), (104, 106, 100))
    _tiles(
        image,
        rng,
        4,
        (62, 64, 60),
        ((108, 110, 102), (96, 98, 92), (116, 116, 106), (88, 92, 88)),
    )
    image = _speckle(image, rng, 180, ((58, 60, 56), (132, 132, 122), (84, 86, 80)))
    if variant != "clean":
        image = _grime(image, rng, 0.8 if variant == "worn" else 1.1)
        image = _darken(image, 0.92 if variant == "worn" else 0.80)
    if variant == "damaged":
        image = _stains(image, rng, 1.0)
        image = _cracks(image, rng, 6)
        image = _chips(image, rng, 14, (42, 42, 38))
    return image.convert("RGB")


def _metal_grating(variant: str, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), (92, 96, 98))
    draw = ImageDraw.Draw(image)
    pitch = 16
    for y in range(0, SIZE, pitch):
        draw.rectangle((0, y, SIZE - 1, y + 7), fill=(58, 62, 64))
        draw.line((0, y, SIZE - 1, y), fill=(146, 150, 148), width=1)
        draw.line((0, y + 7, SIZE - 1, y + 7), fill=(38, 40, 42), width=1)
    for x in range(0, SIZE, pitch):
        draw.line((x, 0, x, SIZE), fill=(74, 78, 80), width=2)
    image = _threads(image, rng, 90, (168, 170, 166))
    image = _speckle(image, rng, 180, ((44, 46, 46), (138, 142, 140), (80, 84, 86)))
    if variant != "clean":
        image = _grime(image, rng, 0.8 if variant == "worn" else 1.1)
        image = _scratches(image, rng, 30 if variant == "worn" else 55, (176, 178, 172), 100)
        image = _darken(image, 0.93 if variant == "worn" else 0.84)
    if variant == "damaged":
        image = _rust(image, rng, 10)
        image = _stains(image, rng, 0.8)
    return image.convert("RGB")


def _metal_panel(variant: str, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), (82, 86, 88))
    draw = ImageDraw.Draw(image)
    for x in range(0, SIZE, 32):
        draw.line((x, 0, x, SIZE), fill=(52, 56, 58), width=2)
        draw.line((x + 2, 0, x + 2, SIZE), fill=(118, 122, 120), width=1)
        for y in range(10, SIZE, 28):
            draw.ellipse((x + 3, y, x + 6, y + 3), fill=(160, 162, 158))
    image = _threads(image, rng, 70, (148, 150, 146))
    image = _speckle(image, rng, 150, ((46, 50, 52), (122, 126, 124), (70, 74, 76)))
    if variant != "clean":
        image = _grime(image, rng, 0.9 if variant == "worn" else 1.2)
        image = _darken(image, 0.92 if variant == "worn" else 0.80)
    if variant == "damaged":
        image = _rust(image, rng, 12)
        image = _cracks(image, rng, 4)
    return image.convert("RGB")


def _parquet(variant: str, rng: random.Random) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), (104, 68, 42))
    draw = ImageDraw.Draw(image)
    block = 32
    woods = ((132, 88, 54), (116, 76, 46), (150, 102, 62), (96, 62, 38), (124, 82, 50))
    for row in range(SIZE // block):
        for column in range(SIZE // block):
            base = rng.choice(woods)
            x0, y0 = column * block, row * block
            draw.rectangle((x0, y0, x0 + block - 1, y0 + block - 1), fill=base)
            horizontal = (row + column) % 2 == 0
            for line in range(2, block, 4):
                colour = _jitter(rng, base, 10)
                if horizontal:
                    draw.line((x0, y0 + line, x0 + block - 1, y0 + line), fill=colour, width=1)
                else:
                    draw.line((x0 + line, y0, x0 + line, y0 + block - 1), fill=colour, width=1)
            draw.rectangle((x0, y0, x0 + block - 1, y0 + block - 1), outline=(62, 40, 24), width=1)
            draw.line((x0, y0, x0 + block - 1, y0), fill=(168, 118, 72), width=1)
    image = _speckle(image, rng, 140, ((74, 48, 28), (162, 112, 68), (92, 58, 34)))
    if variant != "clean":
        image = _grime(image, rng, 0.7 if variant == "worn" else 1.0)
        image = _scratches(image, rng, 34 if variant == "worn" else 62, (62, 40, 24), 120)
        image = _darken(image, 0.90 if variant == "worn" else 0.78)
    if variant == "damaged":
        image = _stains(image, rng, 1.0)
        image = _cracks(image, rng, 7)
        image = _chips(image, rng, 12, (54, 34, 20))
    return image.convert("RGB")


def _draw(name: str, variant: str, rng: random.Random) -> Image.Image:
    kind, _label = RECIPES[name]
    if kind == "floor_tile":
        return _tile_floor(variant, rng)
    if kind == "tile":
        return _tile_wall(variant, rng)
    if kind == "ceiling_tile":
        return _tile_ceiling(variant, rng)
    if kind == "metal_grating":
        return _metal_grating(variant, rng)
    if kind == "metal_panel":
        return _metal_panel(variant, rng)
    return _parquet(variant, rng)


def derive_bytes(output_name: str) -> bytes:
    name, variant = OUTPUTS[output_name]
    image = _draw(name, variant, random.Random(_seed(name, variant)))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _derived_path(output_name: str) -> Path:
    return ROOT / OUTPUT_DIR / f"{output_name}.png"


def manifest_bytes() -> bytes:
    script = ROOT / SCRIPT_PATH
    records = []
    for output_name in sorted(OUTPUTS):
        name, variant = OUTPUTS[output_name]
        records.append(
            {
                "output": (OUTPUT_DIR / f"{output_name}.png").as_posix(),
                "output_sha256": sha256_file(_derived_path(output_name)),
                "source": SCRIPT_PATH,
                "source_sha256": sha256_file(script),
                "variant": variant,
                "palette": name.rsplit("_", 1)[0],
                "surface": name.rsplit("_", 1)[1],
            }
        )
    document = {
        "schema_version": 1,
        "script_version": SCRIPT_VERSION,
        "generator": SCRIPT_PATH,
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
        if path.read_bytes() != derive_bytes(output_name):
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
