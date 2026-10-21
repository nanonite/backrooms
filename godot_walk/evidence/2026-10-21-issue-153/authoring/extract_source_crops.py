#!/usr/bin/env python3
"""Extract two unmodified texture samples from source video frame 0152."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "data/scenes/corridor_travel/images/frame_0152.jpg"
OUTPUT = Path(__file__).resolve().parents[1] / "source"
CROPS = {
    "column_face": (780, 300, 1100, 700),
    "wallpaper_panel": (1290, 410, 1770, 710),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"source frame is missing: {SOURCE}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as image:
        image = image.convert("RGB")
        source_size = list(image.size)
        records = []
        for name, bounds in CROPS.items():
            if bounds[2] > image.width or bounds[3] > image.height:
                raise SystemExit(f"crop {name} extends beyond source frame {source_size}")
            output_path = OUTPUT / f"frame_0152_{name}.png"
            image.crop(bounds).save(output_path, format="PNG", optimize=False)
            records.append(
                {
                    "id": name,
                    "frame_id_1_based": 152,
                    "source_path": SOURCE.relative_to(ROOT).as_posix(),
                    "source_sha256": sha256(SOURCE),
                    "source_size_px": source_size,
                    "crop_xyxy_px": list(bounds),
                    "operation": "direct pixel crop; no grading, resizing, or generation",
                    "output_path": output_path.relative_to(ROOT).as_posix(),
                    "output_sha256": sha256(output_path),
                }
            )
    manifest = {
        "schema_version": 1,
        "source_role": "original #100 source-video frame; not a Gaussian or Hunyuan render",
        "crops": records,
    }
    (OUTPUT / "crop_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
