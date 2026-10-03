#!/usr/bin/env python3
"""Write the frames a bounded selection chose, at the source resolution.

The gate decides *which* frames are worth reconstructing and reports the frame
indices it chose; this writes them out. Two properties matter and both are
deliberate:

* **The cost is the selection, not the clip.** One ffmpeg invocation per chosen
  frame, each seeking to that frame's timestamp. A 900-frame clip and a
  96-frame clip that both select 150 frames cost the same 150 invocations, and
  neither decodes or stores the frames in between. The alternative -- streaming
  the clip and discarding -- visits every frame, which is exactly the unbounded
  work the sampling budget exists to avoid.
* **The source resolution is preserved.** Every measurement in the gate was made
  on downscaled *analysis* frames, which is the right place to measure and the
  wrong place to reconstruct from. COLMAP's features come from these written
  frames, so they are written at the source resolution the probe reported. The
  scaling factor that separated analysis from source is reported so a reader can
  tell the two regimes apart.

Usage:
    python3 scripts/splat_pipeline/sample_frames.py <video.mp4> <report.json> --out <dir>

    <report.json> is the ``--json`` output of ``capture_gate.py``. Passing the
    report rather than re-deciding the selection keeps this step from disagreeing
    with the verdict an operator already read.

Options:
    --out DIR            where frames are written (default: <video dir>/images)
    --image-format EXT   jpg | png (default: jpg)
    --jpeg-quality N     JPEG quality 2, matching Stage A (default: 2)
    --dry-run            report what would be written, and write nothing
    -h, --help           show this message

Exit codes:
    0  frames written
    1  usage error, or the report does not describe a selection
    2  a prerequisite is missing (ffmpeg)
    3  a frame could not be extracted
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from frame_reader import FrameReadError, require_ffmpeg, frame_timestamp

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_MISSING_TOOL = 2
EXIT_EXTRACT_FAILED = 3

#: Per-frame ffmpeg timeout. Short by design: a seek that has not finished in
#: half a minute is wedged, and an unattended pipeline should stop rather than
#: hold the next stage open.
EXTRACT_TIMEOUT_SECONDS = 120

#: Frame name template. Fixed-width and sequential because ``cull_blurry.py``,
#: ``colmap_dataset.py`` and ``run_pipeline.sh`` all glob ``frame_*.jpg``.
FRAME_TEMPLATE = "frame_%04d"

#: Written beside the frames so the registration report can map a COLMAP image
#: name back to the source frame it came from.
MANIFEST_NAME = "frames.json"


class SelectionError(RuntimeError):
    """The report does not describe a frame selection this step can write."""


class ExtractionFailed(SelectionError):
    """A selected frame could not be written, so the output would be incomplete.

    Separate from :class:`SelectionError` because the two demand different
    responses: a bad report is an operator mistake and is retried after fixing
    it, while a frame ffmpeg cannot produce is a capture problem that re-running
    will hit again.
    """


@dataclass(frozen=True)
class ExtractionReport:
    """What was written, what it cost, and how it relates to the clip."""

    video: str
    output_dir: str
    frames_written: int
    frames_expected: int
    source_frame_indices: tuple[int, ...]
    source_resolution: str
    analysis_resolution: str
    analysis_scale: float
    image_format: str
    jpeg_quality: int
    invocations: int
    seconds: float
    skipped: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "video": self.video,
            "output_dir": self.output_dir,
            "frames_written": self.frames_written,
            "frames_expected": self.frames_expected,
            "source_frame_indices": list(self.source_frame_indices),
            "source_resolution": self.source_resolution,
            "analysis_resolution": self.analysis_resolution,
            "analysis_scale": round(self.analysis_scale, 4),
            "image_format": self.image_format,
            "jpeg_quality": self.jpeg_quality,
            "ffmpeg_invocations": self.invocations,
            "seconds": round(self.seconds, 2),
            "skipped": list(self.skipped),
        }


def selected_indices(report: dict) -> tuple[int, ...]:
    """Frame indices the gate selected, in time order.

    Raises :class:`SelectionError` rather than defaulting to something, because
    an empty selection written out silently would produce an ``images/``
    directory that Stage B then fails on with no indication why.
    """
    selection = report.get("selection")
    if not isinstance(selection, dict):
        raise SelectionError("report has no 'selection' section; run capture_gate.py --json first")
    indices = selection.get("selected")
    if not isinstance(indices, list) or not indices:
        status = (report.get("verdict") or {}).get("status", "unknown")
        raise SelectionError(f"report selected no frames (verdict: {status})")
    try:
        return tuple(sorted(int(index) for index in indices))
    except (TypeError, ValueError) as exc:
        raise SelectionError(f"selection contains a non-integer frame index: {exc}") from exc


def _analysis_scale(report: dict) -> tuple[str, str, float]:
    """``(source_resolution, analysis_resolution, scale)`` from the report."""
    metadata = report.get("metadata") or {}
    size = (report.get("scan") or {}).get("analysis_size") or {}
    source = f"{metadata.get('width', 0)}x{metadata.get('height', 0)}"
    analysis = f"{size.get('width', 0)}x{size.get('height', 0)}"
    scale = float(size.get("scale") or 1.0)
    return source, analysis, scale


def _extract_one(
    ffmpeg: str, video: Path, index: int, fps: float, destination: Path, jpeg_quality: int
) -> None:
    """Seek to one frame and write it as a single image."""
    # frame_timestamp is the single definition of where a frame lives in time;
    # see its docstring for why a half-frame offset returns the wrong frame.
    command = [ffmpeg, "-y", "-v", "error", "-noautorotate"]
    command += ["-ss", f"{frame_timestamp(index, fps):.6f}", "-i", str(video), "-frames:v", "1"]
    if destination.suffix.lower() in (".jpg", ".jpeg"):
        command += ["-q:v", str(jpeg_quality)]
    command.append(str(destination))
    try:
        result = subprocess.run(command, capture_output=True, timeout=EXTRACT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise ExtractionFailed(
            f"ffmpeg timed out after {EXTRACT_TIMEOUT_SECONDS}s on frame {index}"
        ) from exc
    if result.returncode != 0 or not destination.is_file():
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1] if detail else "no error output"
        raise ExtractionFailed(f"could not extract frame {index}: {tail}")


def _write_manifest(output_dir: Path, entries: list[dict]) -> Path:
    """Record which source frame each written file came from."""
    path = output_dir / MANIFEST_NAME
    path.write_text(json.dumps({"frames": entries}, indent=2) + "\n", encoding="utf-8")
    return path


#: Glob matching every file this script has ever written, so a re-run removes the
#: previous extraction in full. Keyed on the ``frame_`` prefix rather than the
#: template's digits, because a template like ``frame_%04d`` only matches a
#: four-digit index and would leave a stale ``frame_0999.jpg`` behind.
STALE_FRAME_GLOBS = ("frame_*.jpg", "frame_*.jpeg", "frame_*.png")


def _clear_previous(output_dir: Path) -> int:
    """Delete frames from a previous extraction so none survive into this run.

    Stale frames are the worst kind of quiet failure here: Stage B matches
    features against every file in the directory, so a leftover frame from an
    earlier, larger selection would be reconstructed from and would not be in
    the selection report that explains the reconstruction.
    """
    removed = 0
    for pattern in STALE_FRAME_GLOBS:
        for stale in output_dir.glob(pattern):
            stale.unlink()
            removed += 1
    return removed


def extract_selection(
    report: dict,
    video: str | Path,
    output_dir: str | Path,
    image_format: str = "jpg",
    jpeg_quality: int = 2,
    dry_run: bool = False,
) -> ExtractionReport:
    """Write every frame the gate selected, one seek each, at source resolution.

    ``report`` supplies the selection and the metadata the gate measured; this
    function does not re-measure anything, so the frames written are exactly the
    frames the verdict described.
    """
    video_path = Path(video).expanduser()
    if not video_path.is_file():
        raise SelectionError(f"video not found: {video_path}")
    ffmpeg = require_ffmpeg()

    indices = selected_indices(report)
    fps = float((report.get("metadata") or {}).get("fps") or 0.0)
    source, analysis, scale = _analysis_scale(report)
    destination_dir = Path(output_dir).expanduser()
    started = time.monotonic()
    skipped = _prepare_output(destination_dir, dry_run)

    entries = [
        _extract_position(ffmpeg, video_path, position, index, fps, destination_dir,
                          image_format, jpeg_quality, dry_run)
        for position, index in enumerate(indices)
    ]

    if not dry_run:
        _write_manifest(destination_dir, entries)

    return ExtractionReport(
        video=str(video_path),
        output_dir=str(output_dir),
        frames_written=0 if dry_run else len(entries),
        frames_expected=len(indices),
        source_frame_indices=indices,
        source_resolution=source,
        analysis_resolution=analysis,
        analysis_scale=scale,
        image_format=image_format,
        jpeg_quality=jpeg_quality,
        invocations=0 if dry_run else len(indices),
        seconds=time.monotonic() - started,
        skipped=skipped,
    )


def _prepare_output(destination_dir: Path, dry_run: bool) -> tuple[str, ...]:
    """Create the output directory and drop a previous extraction's frames."""
    if dry_run:
        return ("dry run: nothing written and no previous frames removed",)
    destination_dir.mkdir(parents=True, exist_ok=True)
    removed = _clear_previous(destination_dir)
    return (f"removed {removed} stale frame(s) from a previous extraction",) if removed else ()


def _extract_position(
    ffmpeg: str,
    video: Path,
    position: int,
    index: int,
    fps: float,
    destination_dir: Path,
    image_format: str,
    jpeg_quality: int,
    dry_run: bool,
) -> dict:
    """Write one selected frame and return its manifest entry."""
    name = f"{FRAME_TEMPLATE % (position + 1)}.{image_format}"
    if not dry_run:
        _extract_one(ffmpeg, video, index, fps, destination_dir / name, jpeg_quality)
    return {
        "file": name,
        "source_frame_index": index,
        "source_timestamp_seconds": round(frame_timestamp(index, fps), 4),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sample_frames.py",
        description="Extract the frames a capture_gate.py report selected.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", help="path to the capture video")
    parser.add_argument("report", help="JSON report from capture_gate.py --json")
    parser.add_argument("--out", dest="out", help="output directory (default: <video dir>/images)")
    parser.add_argument("--image-format", choices=("jpg", "png"), default="jpg")
    parser.add_argument("--jpeg-quality", type=int, default=2, help="JPEG quality, default 2")
    parser.add_argument("--dry-run", action="store_true", help="report the work without writing")
    return parser.parse_args(argv)


def render_report(extract: ExtractionReport) -> str:
    lines = [
        "=== EXTRACTION ===",
        f"video:    {extract.video}",
        f"output:   {extract.output_dir}",
        f"frames:   {extract.frames_written} of {extract.frames_expected} selected, written as "
        f"{FRAME_TEMPLATE.replace('%04d', 'NNNN')}.{extract.image_format}",
        f"resolution: {extract.source_resolution} (source, preserved) -- measurements were made on "
        f"{extract.analysis_resolution} analysis frames at {extract.analysis_scale:g}x",
        f"work:     {extract.invocations} ffmpeg invocation(s), one seek per kept frame, "
        f"{extract.seconds:.1f}s; no other frame of the clip was decoded",
        f"source frame indices: {_summarise(extract.source_frame_indices)}",
        f"manifest: {MANIFEST_NAME} maps each written file back to its source frame index",
    ]
    for note in extract.skipped:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def _summarise(indices: tuple[int, ...]) -> str:
    """Compact rendering of many indices: a range when they are contiguous."""
    if not indices:
        return "none"
    contiguous = indices[-1] - indices[0] + 1 == len(indices)
    if contiguous:
        return f"{indices[0]}..{indices[-1]} (contiguous)"
    return f"{indices[0]}..{indices[-1]} (first 12: {', '.join(str(i) for i in indices[:12])})"


def load_report(report_path: Path) -> dict:
    """Read a gate report, or exit with the reason it could not be read."""
    if not report_path.is_file():
        sys.stderr.write(f"FAIL: report not found: {report_path}\n")
        raise SystemExit(EXIT_USAGE)
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"FAIL: report is not valid JSON: {exc}\n")
        raise SystemExit(EXIT_USAGE) from exc


#: Exception type -> exit code. Ordered most specific first, because
#: ExtractionFailed subclasses SelectionError.
_EXIT_FOR_ERROR = (
    (FrameReadError, EXIT_MISSING_TOOL),
    (ExtractionFailed, EXIT_EXTRACT_FAILED),
    (SelectionError, EXIT_USAGE),
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    video = Path(args.video).expanduser()
    report = load_report(Path(args.report).expanduser())
    output_dir = Path(args.out).expanduser() if args.out else video.parent / "images"
    try:
        extract = extract_selection(
            report,
            video,
            output_dir,
            image_format=args.image_format,
            jpeg_quality=args.jpeg_quality,
            dry_run=args.dry_run,
        )
    except _EXIT_FOR_ERROR as error:
        sys.stderr.write(f"FAIL: {error}\n")
        return next(code for kind, code in _EXIT_FOR_ERROR if isinstance(error, kind))
    print(render_report(extract))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
