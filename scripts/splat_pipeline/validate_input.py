#!/usr/bin/env python3
"""
validate_input.py — Fast intake check for the splat pipeline.

Cheap container-level checks that can be answered before decoding a single frame:
frame size, frame rate, duration, and whether the file is a video at all. Blur and
parallax proxies run when OpenCV is available and only ever warn.

This is a *fast* check, not the full judgement. It cannot see whether the scene
persists between frames, whether the camera translated, or how much of the walk
ends up reconstructed. For that, run ``capture_gate.py``, which samples the clip
boundedly and reports registered-versus-excluded coverage. This script points at
it when resolution is merely below the recommendation.

On resolution: the only hard floor is a frame too small to carry matchable
texture (320x240). Below the 1080p *recommendation* the input is accepted and
reported with what the lower resolution costs. 720p is enough to match features
reliably; it loses detail at distance, which shows up as a softer
reconstruction rather than as a failure to register, so rejecting it here threw
away usable captures.

Usage:
    python3 scripts/splat_pipeline/validate_input.py <video.mp4>

Exit codes:
    0  — all hard checks passed (soft warnings may still appear)
    1  — usage / argument error
    2  — missing prerequisites (ffprobe not found)
    3  — hard failure (unmatchably small frame, non-video, probe failure)
"""

import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Below this a frame does not carry enough texture for features to be matched
#: twice, so nothing registers. This is the only resolution limit that is
#: hard: 720p is *not* too small to reconstruct from and is not rejected here.
#: 720p matches features reliably and costs detail at distance, which shows up as
#: a softer reconstruction rather than as a failure to register.
MIN_WIDTH = 320
MIN_HEIGHT = 240

#: Advisory only, printed with the resolution so the operator can weigh it.
RECOMMENDED_HEIGHT = 1080

MIN_FPS = 1
MAX_FPS = 120
BLUR_THRESHOLD = 100.0
MOTION_THRESHOLD = 0.5
FRAME_SAMPLE_COUNT = 20
FRAME_PAIR_GAP = 15

# ---------------------------------------------------------------------------
# Hard checks (exit non-zero on failure)
# ---------------------------------------------------------------------------


def check_ffprobe() -> str:
    """Return path to ffprobe or exit with code 2 if not found."""
    result = subprocess.run(["which", "ffprobe"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write("FAIL: ffprobe not found in PATH. Install ffmpeg.\n")
        sys.exit(2)
    return result.stdout.strip()


def probe_video(video_path: Path) -> dict:
    """Run ffprobe on video and return parsed stream info dict."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"FAIL: ffprobe failed on '{video_path}'\n")
        sys.stderr.write(result.stderr)
        sys.exit(3)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"FAIL: could not parse ffprobe output: {exc}\n")
        sys.exit(3)
    return data


def find_video_stream(streams: list) -> dict:
    """Return the first video stream dict, or exit if none found."""
    for stream in streams:
        if stream.get("codec_type") == "video":
            return stream
    sys.stderr.write("FAIL: no video stream found in input.\n")
    sys.exit(3)


def check_resolution(stream: dict) -> tuple[int, int]:
    """Return ``(width, height)``, exiting only if the frame cannot match features.

    The floor is a feature budget, not a fidelity one: below roughly 320x240
    there is not enough texture for a feature to be found in one frame and
    matched in another, so the reconstruction cannot register at any quality
    setting. Resolution *above* that floor is reported and never rejected, and
    the recommended height is printed as an advisory -- conflating resolution
    with reconstruction quality is what made 720p captures unusable here.
    """
    width = stream.get("width", 0)
    height = stream.get("height", 0)
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        sys.stderr.write(
            f"FAIL: input is {width}x{height}; a frame this small does not carry\n"
            f"      enough texture for features to be matched twice. Minimum is\n"
            f"      {MIN_WIDTH}x{MIN_HEIGHT}. Re-capture at 1280x720 or higher.\n"
        )
        sys.exit(3)
    if height < RECOMMENDED_HEIGHT:
        print(
            f"NOTE: {width}x{height} is below the {RECOMMENDED_HEIGHT}p recommendation.\n"
            f"      It is enough to match features on nearby surfaces; it costs detail\n"
            f"      at distance, which softens the reconstruction rather than stopping\n"
            f"      it from registering. Proceed, and re-shoot only if the result is\n"
            f"      soft at range. For a full account of this capture, run:\n"
            f"        python3 scripts/splat_pipeline/capture_gate.py <video>\n"
        )
    return width, height


def check_framerate(stream: dict) -> float:
    """Return frame rate or exit if unreadable / out of range."""
    r_frame_rate = stream.get("r_frame_rate", "")
    avg_frame_rate = stream.get("avg_frame_rate", "0/1")
    # Prefer r_frame_rate, fall back to avg_frame_rate
    rate_str = r_frame_rate or avg_frame_rate or "0/1"
    try:
        num, den = rate_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    except (ValueError, ZeroDivisionError):
        sys.stderr.write(f"FAIL: could not parse frame rate '{rate_str}'.\n")
        sys.exit(3)
    if fps < MIN_FPS or fps > MAX_FPS:
        sys.stderr.write(
            f"FAIL: frame rate {fps:.1f} fps is outside "
            f"acceptable range [{MIN_FPS}–{MAX_FPS}].\n"
        )
        sys.exit(3)
    return fps


def _parse_duration(raw: str | None, source: str) -> float | None:
    """Try to convert a ffprobe duration string to float seconds."""
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw == "" or raw.lower() == "n/a":
        return None
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return None
    if value <= 0:
        return None
    return value


def check_duration(stream: dict, fmt_info: dict | None) -> float:
    """Return duration in seconds. Tries stream then format container."""
    stream_raw = stream.get("duration")
    duration = _parse_duration(stream_raw, "stream")
    if duration is not None:
        return duration

    if fmt_info is not None:
        format_raw = fmt_info.get("format", {}).get("duration")
        if format_raw is not None:
            duration = _parse_duration(format_raw, "container")
            if duration is not None:
                print(
                    "NOTE: stream duration absent; "
                    f"using container duration ({duration:.1f}s)."
                )
                return duration

    print(
        "WARN: could not determine video duration from ffprobe "
        "(stream and container duration both unavailable or invalid)."
    )
    return 0.0


def run_hard_checks(video_path: Path) -> dict:
    """Execute all hard checks. Returns metadata dict. Exits on failure."""
    _ = check_ffprobe()

    probe = probe_video(video_path)
    streams = probe.get("streams", [])
    stream = find_video_stream(streams)

    width, height = check_resolution(stream)
    fps = check_framerate(stream)
    duration = check_duration(stream, probe)

    frame_count = stream.get("nb_frames")
    codec = stream.get("codec_name", "unknown")
    pixel_format = stream.get("pix_fmt", "unknown")

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "codec": codec,
        "pixel_format": pixel_format,
        "frame_count": frame_count,
    }


# ---------------------------------------------------------------------------
# Soft checks (OpenCV-based blur / motion proxies)
# ---------------------------------------------------------------------------


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def sample_frames(video_path: Path, count: int = FRAME_SAMPLE_COUNT) -> list:
    """Extract evenly-spaced frames from the video and return them as BGR arrays."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print("WARN: OpenCV could not open video for frame sampling.")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = []
    if total_frames > 0 and total_frames > count:
        step = max(1, total_frames // count)
        indices = list(range(0, total_frames, step))[:count]
    else:
        indices = list(range(count))

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


def compute_blur_score(frame) -> float:
    """Variance-of-Laplacian sharpness metric. Higher = sharper."""
    import cv2
    import numpy as np
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def compute_motion_score(prev_frame, curr_frame) -> float:
    """Mean optical-flow magnitude between two frames (Farneback)."""
    import cv2
    import numpy as np
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )
    magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return float(np.mean(magnitude))


def run_soft_checks(video_path: Path) -> None:
    """Run blur and motion proxy checks. Warns on soft failures."""
    if not opencv_available():
        print("NOTE: OpenCV (cv2) not available — skipping blur and parallax checks.")
        print("      Install opencv-python to enable automated quality heuristics.")
        return

    import numpy as np

    frames = sample_frames(video_path)
    if len(frames) < 3:
        print("WARN: too few frames sampled for quality heuristics.")
        return

    # Blur check — mean variance-of-Laplacian across sampled frames
    blur_scores = [compute_blur_score(f) for f in frames]
    mean_blur = float(np.mean(blur_scores))
    print(f"Blur proxy (mean Laplacian variance): {mean_blur:.1f}")
    if mean_blur < BLUR_THRESHOLD:
        print(
            f"WARN: mean sharpness {mean_blur:.1f} is below threshold "
            f"{BLUR_THRESHOLD}. Video may be too blurry. "
            f"Expect poor feature extraction — consider re-recording."
        )

    # Motion / parallax check — optical flow between frame pairs
    motion_scores = []
    gap = FRAME_PAIR_GAP
    for i in range(0, len(frames) - gap, gap):
        score = compute_motion_score(frames[i], frames[i + gap])
        motion_scores.append(score)
    if motion_scores:
        mean_motion = float(np.mean(motion_scores))
        print(f"Motion proxy (mean optical-flow magnitude): {mean_motion:.2f}")
        if mean_motion < MOTION_THRESHOLD:
            print(
                f"WARN: mean optical flow {mean_motion:.2f} is low. "
                f"The camera may not be translating enough — "
                f"pure pan/rotation produces zero parallax and will "
                f"reconstruct to nothing."
            )
    else:
        print("WARN: could not compute motion scores between frame pairs.")


# ---------------------------------------------------------------------------
# Manual checklist (never automated)
# ---------------------------------------------------------------------------


MANUAL_CHECKLIST = """
+-------------------------------------------------------------+
|  MANUAL CHECKLIST — verify BEFORE running the pipeline:     |
|                                                             |
|  [ ] STATIC SCENE — no people, no cars, no wind/water.      |
|      Moving content will corrupt the reconstruction.        |
|                                                             |
|  [ ] REAL PARALLAX — camera TRANSLATED through space, not   |
|      just panned/rotated in place. Walk-through or orbit.   |
|                                                             |
|  [ ] EVEN LIGHTING — no auto-exposure swings, no flashing   |
|      lights, no abrupt brightness changes.                  |
|                                                             |
|  [ ] LOW MOTION BLUR — slow, smooth camera movement.        |
|      Fast whip-pans produce unrecoverable blur.             |
|                                                             |
|  [ ] COVERAGE — every surface the player will see appears   |
|      from at least 2–3 distinct angles in the video.        |
|                                                             |
|  [ ] DESIGN RULE — the splat is reliable ONLY near where    |
|      the real camera went. Confine the player to roughly    |
|      the captured camera path volume.                       |
+-------------------------------------------------------------+
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def print_usage() -> None:
    sys.stderr.write(
        f"Usage: {sys.argv[0]} <video.mp4>\n\n"
        f"Validate a video file for Gaussian-splat reconstruction.\n"
        f"  Hard checks (exit non-zero): resolution, frame rate, codec probe.\n"
        f"  Soft checks (warn only):    blur proxy, motion/parallax proxy.\n"
        f"  Always prints:              manual static-scene checklist.\n"
        f"\nOptions:\n"
        f"  -h, --help                  Show this help message and exit.\n"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    if sys.argv[1] in ("--help", "-h"):
        print_usage()
        sys.exit(0)

    video_path = Path(sys.argv[1]).expanduser().resolve()

    if not video_path.exists():
        sys.stderr.write(f"FAIL: file not found: '{video_path}'\n")
        sys.exit(1)

    if not video_path.is_file():
        sys.stderr.write(f"FAIL: not a regular file: '{video_path}'\n")
        sys.exit(1)

    # --- Hard checks ---
    meta = run_hard_checks(video_path)
    print(f"File:     {video_path}")
    print(f"Codec:    {meta['codec']}")
    print(f"Res:      {meta['width']}x{meta['height']}")
    print(f"FPS:      {meta['fps']:.1f}")
    print(f"Duration: {meta['duration']:.1f}s")
    print(f"Frames:   {meta.get('frame_count', 'unknown')}")
    print(f"Pix fmt:  {meta['pixel_format']}")
    print()

    # --- Soft checks ---
    run_soft_checks(video_path)

    # --- Manual checklist ---
    print(MANUAL_CHECKLIST)

    print("Hard checks passed.")


if __name__ == "__main__":
    main()
