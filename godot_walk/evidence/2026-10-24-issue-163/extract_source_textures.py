"""Extract plainly documented PSX material samples from the direct video frame."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
SOURCE = EVIDENCE / "room_large_frame_0013.png"
EXPECTED_SOURCE_SHA256 = "b75558f58ac9ccd169e444c9978b961179ca5bc2b0d77db97acd81aa65e842ae"
OUTPUT = EVIDENCE / "source_textures"
CROPS = {
    "wallpaper": (1490, 390, 1830, 650),
    "floor": (1060, 810, 1430, 1040),
    "ceiling": (790, 10, 1050, 155),
    "column_face": (466, 330, 590, 720),
}


def main() -> int:
    if _sha256(SOURCE) != EXPECTED_SOURCE_SHA256:
        raise ValueError("Source frame hash differs from source_manifest.json")
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite source crops: {OUTPUT}")
    with Image.open(SOURCE) as image:
        if image.size != (1920, 1080):
            raise ValueError(f"Unexpected source frame dimensions: {image.size}")
        OUTPUT.mkdir(parents=True)
        records = [_save_crop(image, name, bounds) for name, bounds in CROPS.items()]
    manifest = {
        "source_frame": SOURCE.relative_to(ROOT).as_posix(),
        "source_frame_sha256": EXPECTED_SOURCE_SHA256,
        "source_video": "data/videos/room_large.mp4",
        "method": "direct rectangular pixel crops; no resizing, color edit, or synthesis",
        "crops": records,
        "registration_accepted": False,
        "scale_calibrated": False,
    }
    (OUTPUT / "crop_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"SOURCE_TEXTURES_READY: {OUTPUT}")
    return 0


def _save_crop(image: Image.Image, name: str, bounds: tuple[int, int, int, int]) -> dict:
    left, top, right, bottom = bounds
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError(f"Crop bounds outside source image: {name}={bounds}")
    crop = image.crop(bounds)
    path = OUTPUT / f"{name}.png"
    crop.save(path)
    return {
        "name": name,
        "path": path.relative_to(ROOT).as_posix(),
        "source_pixel_bounds_xyxy": list(bounds),
        "dimensions": list(crop.size),
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
