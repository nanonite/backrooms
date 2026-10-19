#!/usr/bin/env python3
"""Freeze a registered raw video frame and its #100 COLMAP camera record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from hunyuan_source import build_metadata, extract_frame  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--colmap-model", type=Path, required=True)
    parser.add_argument("--alignment-manifest", type=Path, required=True)
    parser.add_argument("--dataparser-transforms", type=Path, required=True)
    parser.add_argument("--registered-images", type=Path, required=True)
    parser.add_argument("--frame-number", type=int, required=True, help="1-based video frame number")
    parser.add_argument("--target-world", type=float, nargs=3, required=True)
    parser.add_argument("--frame-out", type=Path, required=True)
    parser.add_argument("--metadata-out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = build_metadata(args)
    video_info = metadata["source_video"]
    command, frame_hash = extract_frame(
        args.video.resolve(),
        args.frame_number,
        args.frame_out,
        (video_info["height"], video_info["width"]),
    )
    metadata["selected_frame"]["seed_png_sha256"] = frame_hash
    metadata["extraction_command"] = command
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print("Registered frame %s at %.6f s; source FOV %.4f degrees" % (
        metadata["selected_frame"]["registered_image"],
        metadata["selected_frame"]["timestamp_seconds"],
        metadata["camera"]["approx_horizontal_fov_degrees"],
    ))


if __name__ == "__main__":
    main()
