#!/usr/bin/env python3
"""Extract tileable surface textures from a video clip.

Workflow:
1. Extract video frames with ffmpeg.
2. Browse frames in an OpenCV window.
3. Choose target surface type via keyboard.
4. Click 4 corners on the selected plane.
5. Rectify perspective to 512x512 staging image.
6. Produce 128x128 RGBA texture PNG.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import cv2
except ModuleNotFoundError:
    cv2 = None

SURFACE_CEILING = "ceiling"
SURFACE_WALL = "wall"
SURFACE_FLOOR = "floor"
PATTERNED_SURFACES = {SURFACE_CEILING, SURFACE_WALL}

STAGING_SIZE = 512
OUTPUT_SIZE = 128
MIN_REPEAT_PERIOD = 8
PEAK_STRENGTH_THRESHOLD = 3.0


class ExtractionError(RuntimeError):
    """Raised when extraction fails."""


@dataclass
class SurfaceSelection:
    surface: str
    frame: np.ndarray
    points: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract perspective-corrected 128x128 surface textures from video frames.",
    )
    parser.add_argument("--video", type=Path, help="Input video file path")
    parser.add_argument("--output", type=Path, help="Output PNG path")
    parser.add_argument("--fps", type=float, default=2.0, help="Frame extraction FPS (default: 2.0)")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run helper-function self tests and exit",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.self_test:
        return
    if args.video is None or args.output is None:
        raise ExtractionError("--video and --output are required unless --self-test is used")
    if args.fps <= 0:
        raise ExtractionError("--fps must be greater than 0")
    if not args.video.exists():
        raise ExtractionError(f"Video not found: {args.video}")
    if not args.video.is_file():
        raise ExtractionError(f"Video path is not a file: {args.video}")


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise ExtractionError("ffmpeg not found in PATH; install ffmpeg and retry")


def require_cv2() -> Any:
    if cv2 is None:
        raise ExtractionError("opencv-python is not installed; install it and retry")
    return cv2


def extract_frames(video_path: Path, fps: float, frame_dir: Path) -> list[Path]:
    frame_pattern = frame_dir / "%06d.png"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        str(frame_pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown ffmpeg error"
        raise ExtractionError(f"ffmpeg frame extraction failed: {stderr}")

    frames = sorted(frame_dir.glob("*.png"))
    if not frames:
        raise ExtractionError("No frames were extracted; verify input video and --fps")
    return frames


def order_points_clockwise(points: np.ndarray) -> np.ndarray:
    if points.shape != (4, 2):
        raise ValueError("Expected shape (4,2)")

    pts = points.astype(np.float32)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)

    top_left = pts[np.argmin(sums)]
    bottom_right = pts[np.argmax(sums)]
    top_right = pts[np.argmin(diffs)]
    bottom_left = pts[np.argmax(diffs)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def detect_repeat_period_1d(signal: np.ndarray, min_period: int, max_period: Optional[int]) -> tuple[Optional[int], float]:
    vector = np.asarray(signal, dtype=np.float32)
    if vector.ndim != 1 or vector.size < (min_period * 2):
        return None, 0.0

    centered = vector - float(vector.mean())
    fft_mag = np.abs(np.fft.rfft(centered))
    if fft_mag.size < 3:
        return None, 0.0

    fft_mag[0] = 0.0
    n = vector.size
    max_p = max_period or (n // 2)
    max_p = max(min(n // 2, max_p), min_period)

    best_period = None
    best_peak = 0.0
    baseline_values: list[float] = []

    for period in range(min_period, max_p + 1):
        frequency = n / float(period)
        idx = int(round(frequency))
        if idx <= 0 or idx >= fft_mag.size:
            continue
        value = float(fft_mag[idx])
        baseline_values.append(value)
        if value > best_peak:
            best_peak = value
            best_period = period

    if best_period is None:
        return None, 0.0

    baseline = float(np.mean(baseline_values)) if baseline_values else 0.0
    score = best_peak / (baseline + 1e-6)
    return best_period, score


def detect_repeat_period_2d(gray: np.ndarray) -> tuple[Optional[tuple[int, int]], float]:
    if gray.ndim != 2:
        raise ValueError("Expected 2D grayscale image")

    proj_x = gray.mean(axis=0)
    proj_y = gray.mean(axis=1)

    period_x, score_x = detect_repeat_period_1d(proj_x, MIN_REPEAT_PERIOD, None)
    period_y, score_y = detect_repeat_period_1d(proj_y, MIN_REPEAT_PERIOD, None)

    if period_x is None or period_y is None:
        return None, min(score_x, score_y)

    confidence = min(score_x, score_y)
    return (period_x, period_y), confidence


def centered_crop(image: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = image.shape[:2]
    crop_w = max(1, min(width, w))
    crop_h = max(1, min(height, h))

    x0 = max(0, (w - crop_w) // 2)
    y0 = max(0, (h - crop_h) // 2)
    return image[y0 : y0 + crop_h, x0 : x0 + crop_w]


def extract_tileable_region(staging_bgr: np.ndarray, surface: str) -> np.ndarray:
    cv = require_cv2()
    if surface == SURFACE_FLOOR:
        return staging_bgr

    gray = cv.cvtColor(staging_bgr, cv.COLOR_BGR2GRAY)
    period, confidence = detect_repeat_period_2d(gray)

    if period is None or confidence < PEAK_STRENGTH_THRESHOLD:
        print(
            f"[WARN] Weak repeat-period detection for {surface} (confidence={confidence:.2f}); "
            "using centered square fallback",
            file=sys.stderr,
        )
        side = min(staging_bgr.shape[0], staging_bgr.shape[1])
        return centered_crop(staging_bgr, side, side)

    period_x, period_y = period
    return centered_crop(staging_bgr, period_x, period_y)


def warp_surface(frame_bgr: np.ndarray, points: np.ndarray) -> np.ndarray:
    cv = require_cv2()
    source = order_points_clockwise(points)
    destination = np.array(
        [
            [0, 0],
            [STAGING_SIZE - 1, 0],
            [STAGING_SIZE - 1, STAGING_SIZE - 1],
            [0, STAGING_SIZE - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv.getPerspectiveTransform(source, destination)
    return cv.warpPerspective(frame_bgr, matrix, (STAGING_SIZE, STAGING_SIZE))


def to_output_rgba(image_bgr: np.ndarray) -> np.ndarray:
    cv = require_cv2()
    resized_bgr = cv.resize(image_bgr, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv.INTER_AREA)
    return cv.cvtColor(resized_bgr, cv.COLOR_BGR2BGRA)


def select_quad_points(frame_bgr: np.ndarray, surface: str) -> Optional[np.ndarray]:
    cv = require_cv2()
    window = f"Select 4 corners ({surface})"
    annotated = frame_bgr.copy()
    points: list[tuple[int, int]] = []

    def redraw() -> None:
        view = annotated.copy()
        for idx, point in enumerate(points):
            cv.circle(view, point, 5, (0, 255, 255), -1)
            cv.putText(view, str(idx + 1), (point[0] + 6, point[1] - 6), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        if len(points) > 1:
            for i in range(len(points) - 1):
                cv.line(view, points[i], points[i + 1], (0, 255, 255), 2)
        help_text = "Click 4 corners. [r] reset [enter] confirm [esc] cancel"
        cv.putText(view, help_text, (10, 24), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv.imshow(window, view)

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))
            redraw()

    cv.namedWindow(window, cv.WINDOW_NORMAL)
    cv.setMouseCallback(window, on_mouse)
    redraw()

    while True:
        key = cv.waitKey(20) & 0xFF
        if key in (13, 10) and len(points) == 4:
            cv.destroyWindow(window)
            return np.array(points, dtype=np.float32)
        if key == ord("r"):
            points.clear()
            redraw()
        if key in (27, ord("q")):
            cv.destroyWindow(window)
            return None


def browse_and_select(frames: list[Path]) -> SurfaceSelection:
    cv = require_cv2()
    if not frames:
        raise ExtractionError("No frames to browse")

    window = "Frame Browser"
    frame_index = 0

    cv.namedWindow(window, cv.WINDOW_NORMAL)

    while True:
        frame_path = frames[frame_index]
        frame_bgr = cv.imread(str(frame_path), cv.IMREAD_COLOR)
        if frame_bgr is None:
            raise ExtractionError(f"Failed to read frame: {frame_path}")

        display = frame_bgr.copy()
        text = f"Frame {frame_index + 1}/{len(frames)}  [c] ceiling [w] wall [f] floor [n] next [q] quit"
        cv.putText(display, text, (10, 24), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv.putText(display, frame_path.name, (10, 52), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv.imshow(window, display)

        key = cv.waitKey(0) & 0xFF
        if key == ord("n"):
            frame_index = (frame_index + 1) % len(frames)
            continue
        if key == ord("q"):
            cv.destroyWindow(window)
            raise ExtractionError("User cancelled frame selection")

        if key in (ord("c"), ord("w"), ord("f")):
            surface = {
                ord("c"): SURFACE_CEILING,
                ord("w"): SURFACE_WALL,
                ord("f"): SURFACE_FLOOR,
            }[key]
            points = select_quad_points(frame_bgr, surface)
            if points is None:
                continue

            cv.destroyWindow(window)
            return SurfaceSelection(surface=surface, frame=frame_bgr, points=points)


def run_self_tests() -> None:
    pts = np.array([[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.float32)
    ordered = order_points_clockwise(pts[[2, 0, 3, 1]])
    assert np.allclose(ordered[0], [100, 100])
    assert np.allclose(ordered[1], [200, 100])
    assert np.allclose(ordered[2], [200, 200])
    assert np.allclose(ordered[3], [100, 200])

    size = 256
    period = 32
    x = np.arange(size)
    synthetic = np.sin(2 * np.pi * x / period)
    detected, score = detect_repeat_period_1d(synthetic, min_period=8, max_period=80)
    assert detected is not None
    assert abs(detected - period) <= 1
    assert score > 1.0

    # OpenCV encoders expect BGRA channel order for 4-channel buffers.
    if cv2 is not None:
        source = np.array([[[10, 20, 30]]], dtype=np.uint8)  # B, G, R
        bgra = to_output_rgba(source)
        assert bgra.shape == (OUTPUT_SIZE, OUTPUT_SIZE, 4)
        assert int(bgra[0, 0, 0]) == 10
        assert int(bgra[0, 0, 1]) == 20
        assert int(bgra[0, 0, 2]) == 30
        assert int(bgra[0, 0, 3]) == 255

    print("Self-test passed")


def main() -> int:
    args = parse_args()

    try:
        if args.self_test:
            run_self_tests()
            return 0

        validate_args(args)
        ensure_ffmpeg_available()
        require_cv2()

        output_path: Path = args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="backrooms_frames_") as temp_dir:
            frame_dir = Path(temp_dir)
            print(f"[INFO] Extracting frames from {args.video} at {args.fps} FPS")
            frames = extract_frames(args.video, args.fps, frame_dir)
            print(f"[INFO] Extracted {len(frames)} frames")
            print("[INFO] Frame browser controls: [c] ceiling, [w] wall, [f] floor, [n] next, [q] quit")

            selection = browse_and_select(frames)
            staged = warp_surface(selection.frame, selection.points)
            texture_source = extract_tileable_region(staged, selection.surface)
            rgba_texture = to_output_rgba(texture_source)

            if not require_cv2().imwrite(str(output_path), rgba_texture):
                raise ExtractionError(f"Failed to write output image: {output_path}")

        print(f"[OK] Wrote texture: {output_path}")
        return 0

    except ExtractionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if cv2 is not None and isinstance(exc, cv2.error):
            print(f"[ERROR] OpenCV failure: {exc}", file=sys.stderr)
            return 1
        raise
    except KeyboardInterrupt:
        print("[ERROR] Interrupted by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
