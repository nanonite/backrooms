#!/usr/bin/env python3
"""
downscale_textures.py — Downscale extracted frames to PS1 resolution (64x64).

Uses nearest-neighbor scaling for period-correct pixelated PS1 look.
Reorganizes output into assets/textures/ with simplified naming.

Usage:
    python3 scripts/downscale_textures.py

Input:
    data/textures/{module}_{face}.jpg

Output:
    assets/textures/{short_name}_{face}.png
"""

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_DIR = Path(__file__).parent.parent / "data" / "textures"
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "textures"

TARGET_SIZE = 64

# Shorten module names for final asset naming
NAME_MAP = {
    "corridor_straight": "corridor",
    "corridor_corner": "corner",
    "corridor_t": "t_junction",
    "corridor_x": "x_intersection",
    "room_large": "room",
    "dead_end": "dead_end",
}

FACES = ["front", "side", "ceiling", "floor"]


def downscale(src: Path, dest: Path) -> bool:
    """Downscale image to 64x64 using nearest-neighbor scaling."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src),
        "-vf", f"scale={TARGET_SIZE}:{TARGET_SIZE}:flags=neighbor",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Input directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Target size: {TARGET_SIZE}x{TARGET_SIZE}")
    print()

    processed = 0
    skipped = 0

    for module, short in NAME_MAP.items():
        for face in FACES:
            src = INPUT_DIR / f"{module}_{face}.jpg"
            dest = OUTPUT_DIR / f"{short}_{face}.png"

            if not src.exists():
                print(f"[WARN] {src.name} not found, skipping")
                continue

            if dest.exists():
                print(f"[SKIP] {dest.name}")
                skipped += 1
                continue

            print(f"[DOWNSCALE] {src.name} → {dest.name}", end=" ... ")
            if downscale(src, dest):
                print("ok")
                processed += 1
            else:
                print("FAILED")

    print(f"\nDone: {processed} processed, {skipped} skipped")
    print(f"Textures at: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
