"""Extract the source-observed frame-0152 column face without alteration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[4]
ROUND = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/scenes/corridor_travel/images/frame_0152.jpg"
OUTPUT = ROUND / "source/frame_0152_column_front.png"
RUNTIME_OUTPUT = ROOT / "godot_walk/assets/psx_extension/textures/hunyuan_round3_column_front.png"
MANIFEST = ROUND / "source/crop_manifest.json"
CROP = (734, 150, 1128, 900)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"missing source frame: {SOURCE}")
    with Image.open(SOURCE) as image:
        if image.size != (1920, 1080):
            raise SystemExit(f"unexpected source dimensions: {image.size}")
        crop = image.crop(CROP)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    crop.save(OUTPUT, format="PNG", optimize=True)
    crop.save(RUNTIME_OUTPUT, format="PNG", optimize=True)
    manifest = {
        "source_frame": SOURCE.relative_to(ROOT).as_posix(),
        "source_frame_sha256": sha256(SOURCE),
        "source_size_px": [1920, 1080],
        "crop_xyxy_px": list(CROP),
        "crop_size_px": [CROP[2] - CROP[0], CROP[3] - CROP[1]],
        "operation": "direct source-video pixel crop; no grading, resizing, or generation",
        "output": OUTPUT.relative_to(ROOT).as_posix(),
        "output_sha256": sha256(OUTPUT),
        "runtime_asset": RUNTIME_OUTPUT.relative_to(ROOT).as_posix(),
        "runtime_asset_sha256": sha256(RUNTIME_OUTPUT),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"SOURCE_CROP_READY: {OUTPUT}")


if __name__ == "__main__":
    main()
