#!/usr/bin/env python3
"""Video container metadata, read with ffprobe.

Every bounded-decoding decision -- how many frames exist, how far apart they
are, whether a seek lands inside the clip -- starts here, so this module reads
metadata and nothing else. It performs no decoding, allocates no arrays, and
raises :class:`VideoProbeError` instead of exiting, so callers decide what a
failed probe means.

``frame_count`` is not always present in a container (streamed or remuxed MP4
frequently omits ``nb_frames``). When it is missing the count is derived from
the frame rate and duration and marked inexact, because a sampling plan that
treats an estimate as exact would either truncate the clip or run off its end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: ffprobe is asked for JSON once; both streams and the container are needed
#: because duration and frame count each live in a different place.
PROBE_TIMEOUT_SECONDS = 60


class VideoProbeError(RuntimeError):
    """The video could not be probed, or carries no usable video stream."""


@dataclass(frozen=True)
class VideoMetadata:
    """What the container says about a video before anything is decoded."""

    path: Path
    width: int
    height: int
    fps: float
    duration_seconds: float
    frame_count: int
    frame_count_is_exact: bool
    codec: str
    pixel_format: str

    @property
    def total_pixels(self) -> int:
        """Pixel count of one full-resolution frame."""
        return self.width * self.height

    @property
    def megapixels(self) -> float:
        """Full-resolution frame size in megapixels, for feature-budget reports."""
        return self.total_pixels / 1_000_000.0

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "total_pixels": self.total_pixels,
            "megapixels": round(self.megapixels, 3),
            "fps": round(self.fps, 3),
            "duration_seconds": round(self.duration_seconds, 3),
            "frame_count": self.frame_count,
            "frame_count_is_exact": self.frame_count_is_exact,
            "codec": self.codec,
            "pixel_format": self.pixel_format,
        }


def require_ffprobe() -> str:
    """Return the ffprobe path, or raise with the fix rather than the symptom."""
    found = shutil.which("ffprobe")
    if not found:
        raise VideoProbeError(
            "ffprobe is not on PATH. Install ffmpeg (which provides ffprobe) "
            "and re-run; sampling cannot size a bounded plan without it."
        )
    return found


def _rate_to_float(raw: str) -> float:
    """Convert an ffprobe ``num/den`` rate, or a bare float, to a number."""
    text = (raw or "").strip()
    if not text or text.lower() == "n/a":
        return 0.0
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            den = float(denominator)
            return float(numerator) / den if den else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _positive_float(raw) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def find_video_stream(probe: dict) -> dict:
    """Return the first video stream, or raise when the file has none."""
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise VideoProbeError("no video stream found; the input is not a video capture")


def _stream_frame_count(stream: dict) -> tuple[int, bool]:
    """Return ``(count, is_exact)`` from ``nb_frames`` alone."""
    raw = stream.get("nb_frames")
    if raw in (None, "", "N/A"):
        return 0, False
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return 0, False
    return (count, True) if count > 0 else (0, False)


def _derive_frame_count(stream: dict, fps: float, duration: float) -> int:
    """Estimate a frame count from rate and duration when the container omits it."""
    if fps > 0 and duration > 0:
        return int(round(fps * duration))
    return 0


def probe_video(path: str | Path) -> VideoMetadata:
    """Probe ``path`` and return its metadata.

    Raises :class:`VideoProbeError` for a missing file, a missing ffprobe, an
    unparsable probe, a file with no video stream, or a stream with no usable
    frame size.
    """
    video_path = Path(path).expanduser()
    if not video_path.is_file():
        raise VideoProbeError(f"file not found: {video_path}")

    ffprobe = require_ffprobe()
    command = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", str(video_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise VideoProbeError(f"ffprobe timed out after {PROBE_TIMEOUT_SECONDS}s on {video_path}") from exc
    if result.returncode != 0:
        raise VideoProbeError(f"ffprobe failed on {video_path}: {result.stderr.strip()}")
    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VideoProbeError(f"could not parse ffprobe output for {video_path}: {exc}") from exc

    stream = find_video_stream(probe)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise VideoProbeError(f"video stream in {video_path} reports no frame size")

    fps = _rate_to_float(stream.get("avg_frame_rate")) or _rate_to_float(stream.get("r_frame_rate"))
    duration = _positive_float(stream.get("duration"))
    if duration <= 0:
        duration = _positive_float(probe.get("format", {}).get("duration"))
    count, is_exact = _stream_frame_count(stream)
    if not is_exact:
        count = _derive_frame_count(stream, fps, duration)
    if count <= 0:
        raise VideoProbeError(f"could not determine a frame count for {video_path}")

    return VideoMetadata(
        path=video_path,
        width=width,
        height=height,
        fps=fps,
        duration_seconds=duration,
        frame_count=count,
        frame_count_is_exact=is_exact,
        codec=str(stream.get("codec_name") or "unknown"),
        pixel_format=str(stream.get("pix_fmt") or "unknown"),
    )