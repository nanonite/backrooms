#!/usr/bin/env python3
"""
cull_blurry.py — Variance-of-Laplacian blur culling for extracted frames.

Reads all JPEG/PNG images from <scene_dir>/images/, computes a sharpness score
for each, and removes the blurriest frames (default: bottom 18th percentile).
Rerunning on an already-culled directory is safe (idempotent).

Usage:
    python3 scripts/splat_pipeline/cull_blurry.py <scene_dir> [--percentile 18] [--dry-run]

Exit codes:
    0  — culling completed (or no work needed on idempotent rerun)
    1  — usage / argument error
    2  — missing prerequisites (OpenCV / numpy not installed)
    3  — empty images directory or no readable frames
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_PERCENTILE = 18
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def check_prerequisites() -> None:
    missing = []
    try:
        import cv2  # noqa: F401
    except ImportError:
        missing.append("opencv-python (cv2)")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    if missing:
        names = " and ".join(missing)
        sys.stderr.write(
            f"FAIL: {names} not installed. "
            f"Install with: pip install opencv-python numpy\n"
        )
        sys.exit(2)


def resolve_images_dir(scene_dir: Path) -> Path:
    if scene_dir.name == "images" and scene_dir.is_dir():
        return scene_dir
    images_dir = scene_dir / "images"
    if not images_dir.is_dir():
        sys.stderr.write(
            f"FAIL: images directory not found at '{images_dir}'. "
            f"Run ffmpeg frame extraction first.\n"
        )
        sys.exit(1)
    return images_dir


def collect_images(images_dir: Path, extensions: set[str]) -> list[Path]:
    frames = sorted(
        p
        for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    )
    if not frames:
        sys.stderr.write(
            f"FAIL: no images ({', '.join(sorted(extensions))}) "
            f"found in '{images_dir}'.\n"
        )
        sys.exit(3)
    return frames


def compute_sharpness(image_path: Path) -> float:
    import cv2

    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        sys.stderr.write(f"WARN: could not read '{image_path}', skipping.\n")
        return float("nan")
    return cv2.Laplacian(img, cv2.CV_64F).var()


def score_frames(frames: list[Path]) -> dict[Path, float]:
    scores: dict[Path, float] = {}
    for f in frames:
        scores[f] = compute_sharpness(f)
    return scores


def cull_blurry(
    frames: list[Path],
    scores: dict[Path, float],
    percentile: float,
    dry_run: bool,
) -> tuple[int, int]:
    import numpy as np

    valid_scores = [s for s in scores.values() if not np.isnan(s)]
    if not valid_scores:
        sys.stderr.write("FAIL: no readable frames to score.\n")
        sys.exit(3)

    threshold = float(np.percentile(valid_scores, percentile))
    kept = 0
    removed = 0

    for frame, score in scores.items():
        if np.isnan(score) or score < threshold:
            if not dry_run:
                os.remove(frame)
            removed += 1
        else:
            kept += 1

    return kept, removed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cull blurry frames by variance-of-Laplacian sharpness."
    )
    parser.add_argument(
        "scene_dir",
        type=str,
        help="Path to the scene directory (must contain images/ subdirectory).",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=DEFAULT_PERCENTILE,
        help=(
            f"Drop frames below this sharpness percentile "
            f"(default: {DEFAULT_PERCENTILE}). "
            f"Lower = remove fewer frames."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed without deleting files.",
    )
    parser.add_argument(
        "--ext",
        nargs="+",
        default=sorted(IMAGE_EXTENSIONS),
        help="Image extensions to consider (default: .jpg .jpeg .png).",
    )
    return parser.parse_args(argv)


def parse_extensions(raw_exts: list[str]) -> set[str]:
    result: set[str] = set()
    for ext in raw_exts:
        ext = ext.strip().lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        result.add(ext)
    return result


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)
    check_prerequisites()

    scene_dir = Path(args.scene_dir).expanduser().resolve()
    if not scene_dir.is_dir():
        sys.stderr.write(f"FAIL: directory not found: '{scene_dir}'\n")
        sys.exit(1)

    extensions = parse_extensions(args.ext)
    images_dir = resolve_images_dir(scene_dir)
    frames = collect_images(images_dir, extensions)
    scores = score_frames(frames)
    kept, removed = cull_blurry(frames, scores, args.percentile, args.dry_run)

    verb = "would keep" if args.dry_run else "kept"
    action = "would remove" if args.dry_run else "removed"
    print(
        f"{verb} {kept} / {len(frames)} frames "
        f"({action} {removed}) "
        f"[percentile={args.percentile:.0f}]"
    )


if __name__ == "__main__":
    main()
