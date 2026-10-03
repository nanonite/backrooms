#!/usr/bin/env python3
"""Bounded frame reading: decode a sample of a clip, never all of it.

Two decode strategies, because they trade against each other:

* **stream** -- one ffmpeg pass with ``select='not(mod(n,S))'``. Cheap in wall
  time (measured ~2 ms per source frame at 640x360 here) and it *visits* every
  frame to reach each sample, so a long clip costs a full decode pass.
* **seek** -- one short ffmpeg invocation per wanted frame. Touches only the
  frames kept, at ~140 ms each, which is cheaper than a full pass only when the
  clip is sampled sparsely (about every 70th frame).

Whichever runs, the retained set is bounded by the budget and the report states
how many frames were visited as well as how many were kept, so "bounded work" is
a number rather than an intention.

Decoded frames are greyscale at the *analysis* resolution, which is what the
metrics in :mod:`frame_metrics` are defined against. Source resolution is
untouched here -- it is COLMAP's business, and it is preserved in every
extraction command this module produces.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from video_probe import VideoMetadata

#: ffmpeg invocations are short; the timeout only exists so a wedged process
#: cannot hang an unattended pipeline.
DECODE_TIMEOUT_SECONDS = 600


class FrameReadError(RuntimeError):
    """A decode could not run, or produced no usable frames."""


@dataclass(frozen=True)
class AnalysisSize:
    """Greyscale analysis frame size, with the scale factor that produced it."""

    width: int
    height: int
    source_width: int
    source_height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def scale(self) -> float:
        return self.width / self.source_width if self.source_width else 1.0

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "source_width": self.source_width,
            "source_height": self.source_height,
            "scale": round(self.scale, 4),
        }


@dataclass(frozen=True)
class DecodeStats:
    """What a decode did, and what it cost, in the units a report can print."""

    mode: str
    reason: str
    clip_frames: int
    requested: int
    retained: int
    visited: int
    seconds: float

    @property
    def retained_fraction(self) -> float:
        """Share of the clip's frames that were kept."""
        return self.retained / self.clip_frames if self.clip_frames else 0.0

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "clip_frames": self.clip_frames,
            "requested": self.requested,
            "retained": self.retained,
            "visited": self.visited,
            "seconds": round(self.seconds, 3),
            "retained_fraction": round(self.retained_fraction, 4),
        }


@dataclass(frozen=True)
class DecodedFrames:
    """Decoded analysis frames with the indices they came from."""

    indices: tuple[int, ...]
    frames: tuple[np.ndarray, ...]
    stats: DecodeStats


def require_ffmpeg() -> str:
    """Return the ffmpeg path, or raise with the fix rather than the symptom."""
    found = shutil.which("ffmpeg")
    if not found:
        raise FrameReadError(
            "ffmpeg is not on PATH. Sampling needs it to decode a bounded set of "
            "frames; install ffmpeg and re-run."
        )
    return found


def analysis_size(metadata: VideoMetadata, max_pixels: int) -> AnalysisSize:
    """Analysis size preserving aspect ratio, capped at ``max_pixels``.

    Dimensions are forced even because 4:2:0 chroma subsampling rounds odd
    dimensions, and an odd analysis frame makes the block grid ragged.
    """
    scale = min(1.0, math.sqrt(max_pixels / metadata.total_pixels))
    width = max(2, int(metadata.width * scale) // 2 * 2)
    height = max(2, int(metadata.height * scale) // 2 * 2)
    return AnalysisSize(width=width, height=height, source_width=metadata.width, source_height=metadata.height)


def candidate_stride(
    clip_frames: int,
    motion_px_per_frame: float,
    analysis_frame_width: int,
    max_candidates: int,
    min_stride: int = 1,
    max_stride: int = 240,
) -> int:
    """Frames between candidates, from measured motion and the candidate cap.

    Two constraints decide this and they can disagree. The stride must be wide
    enough that consecutive samples are far apart in pixels, or the samples
    differ by sensor noise and no translation is measurable; and narrow enough
    that the clip's frames divided by the stride stays within the candidate
    budget, or more frames get scored than the budget allows.
    """
    motion_per_sample = max(motion_px_per_frame, 1e-6)
    stride_for_motion = int(round(motion_per_sample / max(1e-6, analysis_frame_width * 0.02)))
    stride_for_cap = max(1, math.ceil(clip_frames / max(1, max_candidates)))
    return int(max(min_stride, min(max_stride, max(stride_for_motion, stride_for_cap))))


def _run_ffmpeg(command: list[str], expected_bytes: int) -> bytes:
    """Run one ffmpeg command, raising with ffmpeg's own message on failure."""
    try:
        result = subprocess.run(command, capture_output=True, timeout=DECODE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise FrameReadError(f"ffmpeg timed out after {DECODE_TIMEOUT_SECONDS}s") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1] if detail else "no error output"
        raise FrameReadError(f"ffmpeg failed: {tail}")
    if not result.stdout:
        raise FrameReadError("ffmpeg produced no frame data")
    if len(result.stdout) < expected_bytes:
        raise FrameReadError(
            f"ffmpeg returned {len(result.stdout)} bytes, expected at least {expected_bytes}"
        )
    return result.stdout


def _frames_from_raw(raw: bytes, size: AnalysisSize) -> list[np.ndarray]:
    """Split a raw greyscale stream into per-frame arrays."""
    frame_bytes = size.pixels
    count = len(raw) // frame_bytes
    return list(np.frombuffer(raw, dtype=np.uint8).reshape(count, size.height, size.width))


def _stream_command(ffmpeg: str, video: Path, size: AnalysisSize, stride: int) -> list[str]:
    filter_chain = f"select='not(mod(n\\,{stride}))',scale={size.width}:{size.height}"
    return [
        ffmpeg, "-v", "error", "-i", str(video), "-vf", filter_chain,
        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]


def _seek_command(ffmpeg: str, video: Path, size: AnalysisSize, timestamp: float) -> list[str]:
    return [
        ffmpeg, "-v", "error", "-ss", f"{timestamp:.4f}", "-i", str(video),
        "-frames:v", "1", "-vf", f"scale={size.width}:{size.height}",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]


def stream_candidates(
    video: str | Path, size: AnalysisSize, stride: int, clip_frames: int
) -> DecodedFrames:
    """Decode every ``stride``-th frame in one pass."""
    ffmpeg = require_ffmpeg()
    started = time.monotonic()
    raw = _run_ffmpeg(_stream_command(ffmpeg, Path(video), size, stride), size.pixels)
    frames = _frames_from_raw(raw, size)
    elapsed = time.monotonic() - started
    last_index = (len(frames) - 1) * stride if frames else 0
    stats = DecodeStats(
        mode="stream",
        reason=f"single pass keeping every {stride}th frame",
        clip_frames=clip_frames,
        requested=len(frames),
        retained=len(frames),
        visited=min(clip_frames, last_index + 1) if clip_frames else last_index + 1,
        seconds=elapsed,
    )
    indices = tuple(i * stride for i in range(len(frames)))
    return DecodedFrames(indices=indices, frames=tuple(frames), stats=stats)


#: Rate assumed when a container reports no usable frame rate, so a seek
#: timestamp can still be formed.
FALLBACK_FPS = 25.0


def frame_timestamp(index: int, fps: float) -> float:
    """Seek target that lands on frame ``index``: its own presentation timestamp.

    An accurate ``-ss`` returns the first frame at or after the target, so the
    target must be ``index / fps`` exactly. Seeking to the middle of the frame
    interval returns the frame *after* the one asked for -- measured on
    ``accepted_walkthrough``, a mid-frame seek for indices 1, 40 and 94 differs
    from the stream-decoded frame of that index by 7.6, 50.7 and 47.5 mean grey
    levels, while this timestamp matches it exactly. The same offset also fails
    outright on the last frame of a clip, where nothing follows it.

    Every seek in this module goes through here, so the convention has one
    definition rather than one per call site.
    """
    return index / (fps if fps > 0 else FALLBACK_FPS)


def seek_candidates(
    video: str | Path, size: AnalysisSize, indices: list[int], fps: float
) -> DecodedFrames:
    """Decode exactly the requested frame indices, one seek each."""
    ffmpeg = require_ffmpeg()
    started = time.monotonic()
    frames: list[np.ndarray] = []
    kept: list[int] = []
    for index in indices:
        raw = _run_ffmpeg(_seek_command(ffmpeg, Path(video), size, frame_timestamp(index, fps)), size.pixels)
        decoded = _frames_from_raw(raw, size)
        if decoded:
            frames.append(decoded[0])
            kept.append(index)
    stats = DecodeStats(
        mode="seek",
        reason=f"{len(indices)} seeks, one per kept frame",
        clip_frames=0,
        requested=len(indices),
        retained=len(kept),
        visited=len(kept),
        seconds=time.monotonic() - started,
    )
    return DecodedFrames(indices=tuple(kept), frames=tuple(frames), stats=stats)


def decode_burst(
    video: str | Path, size: AnalysisSize, start_seconds: float, length: int
) -> list[np.ndarray]:
    """Decode ``length`` contiguous frames starting at ``start_seconds``."""
    ffmpeg = require_ffmpeg()
    command = [
        ffmpeg, "-v", "error", "-ss", f"{start_seconds:.3f}", "-i", str(video),
        "-frames:v", str(length), "-vf", f"scale={size.width}:{size.height}",
        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    return _frames_from_raw(_run_ffmpeg(command, size.pixels), size)