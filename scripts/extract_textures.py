#!/usr/bin/env python3
"""
extract_textures.py — Extract texture frames from Backrooms module videos.

For each module video, extracts representative frames for each face type:
  - front: walls facing the camera
  - side: side walls
  - ceiling: drop ceiling tiles
  - floor: carpet tiles

Usage:
    python3 scripts/extract_textures.py

Output:
    data/textures/{module}_{face}.jpg  — individual frames
    data/textures/preview.html         — thumbnail grid for review
"""

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VIDEO_DIR = Path(__file__).parent.parent / "data" / "videos"
TEXTURE_DIR = Path(__file__).parent.parent / "data" / "textures"

# Timestamps (seconds) to sample from each ~5s video.
# Adjusted per module type to capture the best face views.
MODULE_TIMESTAMPS = {
    "corridor_straight": {
        "front": 1.0,    # looking down corridor
        "side": 0.5,     # side wall visible
        "ceiling": 0.3,  # ceiling tiles
        "floor": 2.0,    # carpet tiles
    },
    "corridor_corner": {
        "front": 1.5,    # corner walls
        "side": 0.5,     # side wall before turn
        "ceiling": 0.3,
        "floor": 2.0,
    },
    "corridor_t": {
        "front": 2.0,    # T-junction walls
        "side": 0.5,     # side corridor wall
        "ceiling": 0.3,
        "floor": 1.0,
    },
    "corridor_x": {
        "front": 1.0,    # one corridor face
        "side": 2.5,     # perpendicular corridor (mid-rotation)
        "ceiling": 0.3,
        "floor": 1.0,
    },
    "room_large": {
        "front": 1.5,    # far wall
        "side": 0.5,     # side wall
        "ceiling": 0.3,
        "floor": 2.0,
    },
    "dead_end": {
        "front": 3.0,    # blank end wall
        "side": 1.0,     # side corridor wall
        "ceiling": 0.3,
        "floor": 2.0,
    },
}

MODULES = sorted(MODULE_TIMESTAMPS.keys())
FACES = ["front", "side", "ceiling", "floor"]


def extract_frame(video: Path, timestamp: float, dest: Path) -> bool:
    """Extract a single frame at given timestamp using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", str(video),
        "-vframes", "1",
        "-q:v", "2",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_preview_html() -> str:
    """Generate an HTML preview page with all extracted textures."""
    rows = []
    for module in MODULES:
        cells = []
        for face in FACES:
            fname = f"{module}_{face}.jpg"
            cells.append(f"""
            <div class="cell">
                <img src="{fname}" alt="{module} {face}">
                <span>{module}<br>{face}</span>
            </div>""")
        rows.append('<div class="row">' + "".join(cells) + '</div>')

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Backrooms Texture Preview</title>
    <style>
        body {{ background: #1a1a1a; color: #ccc; font-family: monospace; margin: 20px; }}
        h1 {{ color: #d4a017; }}
        .row {{ display: flex; gap: 10px; margin-bottom: 10px; }}
        .cell {{ text-align: center; }}
        .cell img {{ width: 256px; height: 144px; object-fit: cover; border: 1px solid #444; }}
        .cell span {{ font-size: 11px; color: #888; }}
    </style>
</head>
<body>
    <h1>Backrooms Module Textures</h1>
    {"".join(rows)}
</body>
</html>"""


def main():
    TEXTURE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Extracting textures from: {VIDEO_DIR}")
    print(f"Output directory: {TEXTURE_DIR}")
    print()

    extracted = 0
    skipped = 0

    for module in MODULES:
        video = VIDEO_DIR / f"{module}.mp4"
        if not video.exists():
            print(f"[WARN] {video.name} not found, skipping")
            continue

        timestamps = MODULE_TIMESTAMPS[module]
        for face, ts in timestamps.items():
            dest = TEXTURE_DIR / f"{module}_{face}.jpg"
            if dest.exists():
                print(f"[SKIP] {dest.name}")
                skipped += 1
                continue

            print(f"[EXTRACT] {module}/{face} @ {ts}s", end=" ... ")
            if extract_frame(video, ts, dest):
                print("ok")
                extracted += 1
            else:
                print("FAILED")

    # Generate preview
    preview = TEXTURE_DIR / "preview.html"
    preview.write_text(generate_preview_html())
    print(f"\nPreview: {preview}")
    print(f"\nDone: {extracted} extracted, {skipped} skipped")
    print(f"Textures at: {TEXTURE_DIR}")


if __name__ == "__main__":
    main()
