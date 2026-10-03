#!/usr/bin/env python3
"""Report which frames a sparse model actually registered, and what it missed.

A COLMAP run on a good capture registers nearly every frame you gave it, and on
a marginal one it registers a *subset* that looks like a complete room. The
subset is the dangerous case: COLMAP will happily report success, and a stage
downstream will train a splat over the room it reconstructed and nothing else.
The parts of the capture that never registered have no geometry at all, so the
playable volume is silently smaller than the capture walked.

This module reads the model COLMAP wrote and reports four things:

* **Which model was chosen.** COLMAP writes ``sparse/0``, ``sparse/1``... and a
  disconnected reconstruction lands in several. ``colmap_model.find_sparse_model``
  picks the one with the most registered images, which is the right default and a
  silent one -- so this module names every model it found, its size, and which
  one was used. A reader can disagree with the choice having seen it.
* **Registered versus excluded frames**, by name, so the two sets can be diffed
  against the frames that were extracted.
* **Coverage of the extracted set**, as a fraction, because "registered 41 of 150
  frames" and "registered 149 of 150" must not look the same in a log.
* **Unsupported coverage**, named as the frames it excludes. The gate measures
  what the *camera* covered; this measures what the *model* covers, and the gap
  between the two is the part of the walk with no geometry.

Intrinsics and poses are read as written and passed through unchanged. This
module reports on the model; it never rewrites, repairs or re-registers it.

Usage:
    python3 scripts/splat_pipeline/model_coverage.py <scene_dir> [options]

Options:
    --frames-dir PATH    extracted frames (default: <scene_dir>/images)
    --model PATH         a specific sparse model to report on
    --min-coverage F      coverage below this is a block (default: 0.8)
    --json PATH          write the full report as JSON
    -h, --help           show this message

Exit codes:
    0  the model covers the extracted frames well enough to proceed
    1  usage error, or no sparse model could be read
    2  coverage is below --min-coverage: parts of the walk have no geometry
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from colmap_model import camera_centers, find_sparse_model, read_cameras, read_images

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_LOW_COVERAGE = 2

#: Below this fraction of extracted frames registered, the model does not
#: describe the capture that was walked, and downstream stages would train on a
#: room smaller than the one the capture covered.
DEFAULT_MIN_COVERAGE = 0.8

#: Frame extensions ``sample_frames.py`` and ``run_pipeline.sh`` write.
FRAME_PATTERNS = ("*.jpg", "*.jpeg", "*.png")


class ModelCoverageError(RuntimeError):
    """The model or the frame set could not be read."""


@dataclass(frozen=True)
class ModelChoice:
    """Every sparse model found, and which one this report describes."""

    chosen: str
    chosen_images: int
    all_models: tuple[tuple[str, int], ...]

    def others(self) -> tuple[tuple[str, int], ...]:
        """Models present but not used."""
        return tuple(entry for entry in self.all_models if entry[0] != self.chosen)

    def to_dict(self) -> dict:
        return {
            "chosen": self.chosen,
            "chosen_registered_images": self.chosen_images,
            "models_found": [{"path": path, "registered_images": count} for path, count in self.all_models],
            "models_not_used": [{"path": path, "registered_images": count} for path, count in self.others()],
        }


@dataclass(frozen=True)
class Intrinsics:
    """The camera intrinsics the model was solved with, read as written."""

    camera_count: int
    models: tuple[str, ...]
    resolutions: tuple[str, ...]
    principal_points: tuple[tuple[float, float], ...]

    def to_dict(self) -> dict:
        return {
            "camera_count": self.camera_count,
            "models": list(self.models),
            "resolutions": list(self.resolutions),
            "principal_points": [[round(x, 2), round(y, 2)] for x, y in self.principal_points],
        }


@dataclass(frozen=True)
class RegistrationCoverage:
    """Which frames registered, and the coverage fraction they represent."""

    extracted: int
    registered: int
    excluded: int
    registered_names: tuple[str, ...]
    excluded_names: tuple[str, ...]

    @property
    def coverage(self) -> float:
        """Registered frames as a fraction of the frames extracted."""
        return self.registered / self.extracted if self.extracted else 0.0

    def to_dict(self) -> dict:
        return {
            "extracted_frames": self.extracted,
            "registered": self.registered,
            "excluded": self.excluded,
            "coverage": round(self.coverage, 4),
            "registered_names": list(self.registered_names),
            "excluded_names": list(self.excluded_names),
        }


@dataclass(frozen=True)
class CoverageReport:
    """Everything a reader needs to know about what the model does and does not cover."""

    scene_dir: str
    choice: ModelChoice
    intrinsics: Intrinsics
    registration: RegistrationCoverage
    min_coverage: float
    pose_extent: tuple[float, float, float]
    warnings: tuple[str, ...]

    @property
    def covers_enough(self) -> bool:
        """True when the model registers enough of the extracted frames."""
        return self.registration.coverage >= self.min_coverage

    @property
    def unsupported_frames(self) -> tuple[str, ...]:
        """Frames the capture walked that the model gives no geometry for."""
        return self.registration.excluded_names

    def to_dict(self) -> dict:
        return {
            "scene_dir": self.scene_dir,
            "min_coverage": self.min_coverage,
            "covers_enough": self.covers_enough,
            "model": self.choice.to_dict(),
            "intrinsics": self.intrinsics.to_dict(),
            "registration": self.registration.to_dict(),
            "pose_extent": {
                "x": round(self.pose_extent[0], 4),
                "y": round(self.pose_extent[1], 4),
                "z": round(self.pose_extent[2], 4),
                "units": "COLMAP world units, arbitrary scale (a sparse model carries no metric scale)",
            },
            "unsupported_coverage": {
                "frames": list(self.unsupported_frames),
                "count": len(self.unsupported_frames),
                "note": (
                    "these frames were captured and matched against but never registered; the walkable "
                    "volume is limited to the registered subset, so a walk through them will fall "
                    "outside the reconstruction"
                ),
            },
            "warnings": list(self.warnings),
        }


def _model_directories(scene_dir: Path) -> list[Path]:
    """Sparse model directories under ``scene_dir``, shallowest first."""
    return sorted(
        path.parent
        for path in (scene_dir / "sparse").rglob("images.bin")
        if (path.parent / "cameras.bin").is_file()
    )


def choose_model(scene_dir: str | Path, model_path: str | Path | None = None) -> ModelChoice:
    """Pick the model to report on, and record every model that was found.

    Raises :class:`ModelCoverageError` when no model is readable, so a missing
    Stage B output is reported as a missing model rather than as a coverage of
    zero.
    """
    scene = Path(scene_dir).expanduser()
    if model_path is not None:
        chosen = Path(model_path).expanduser()
        images = read_images(chosen)
        return ModelChoice(str(chosen), len(images), ((str(chosen), len(images)),))

    found = _model_directories(scene)
    if not found:
        found = [find_sparse_model(scene)]
    counted = tuple((str(path), len(read_images(path))) for path in found)
    chosen_path = max(counted, key=lambda entry: entry[1])[0]
    return ModelChoice(chosen_path, max(entry[1] for entry in counted), counted)


def _principal_point(camera) -> tuple[float, float]:
    """Principal point of a camera record, or NaN for a model that has none.

    SIMPLE_* models store ``(f, cx, cy)``; the PINHOLE family stores
    ``(fx, fy, cx, cy, ...)``. The arity alone cannot tell them apart -- SIMPLE
    PINHOLE has four params too -- so the model name decides, and a report that
    cannot resolve one says NaN rather than printing a focal length as if it were
    an optical centre.
    """
    if camera.model.startswith("SIMPLE") and len(camera.params) >= 3:
        return camera.params[1], camera.params[2]
    if not camera.model.startswith("SIMPLE") and len(camera.params) >= 4:
        return camera.params[2], camera.params[3]
    return float("nan"), float("nan")


def read_intrinsics(model_dir: str | Path) -> Intrinsics:
    """Read the camera intrinsics of a model, unchanged and in model order."""
    cameras = read_cameras(model_dir)
    if not cameras:
        raise ModelCoverageError(f"model at {model_dir} contains no camera record")
    ordered = [cameras[key] for key in sorted(cameras)]
    return Intrinsics(
        camera_count=len(ordered),
        models=tuple(dict.fromkeys(camera.model for camera in ordered)),
        resolutions=tuple(dict.fromkeys(f"{camera.width}x{camera.height}" for camera in ordered)),
        principal_points=tuple(_principal_point(camera) for camera in ordered),
    )


def extracted_frames(frames_dir: str | Path) -> list[str]:
    """Frame file names in a directory, in extraction order."""
    directory = Path(frames_dir).expanduser()
    names: list[str] = []
    for pattern in FRAME_PATTERNS:
        names.extend(path.name for path in directory.glob(pattern))
    return sorted(names)


def compare_registration(model_dir: str | Path, frame_names: list[str]) -> RegistrationCoverage:
    """Split the extracted frames into the ones COLMAP registered and the ones it did not.

    Comparison is by file name, because that is the only identifier the two
    sides share: the model records the image name COLMAP was given and the frame
    directory holds the files.
    """
    registered = sorted(image.name for image in read_images(model_dir))
    extracted = list(frame_names)
    if not extracted:
        raise ModelCoverageError(
            "no frames found to compare against; pass --frames-dir pointing at the extracted frames"
        )
    registered_set = set(registered)
    matched = tuple(name for name in extracted if name in registered_set)
    excluded = tuple(name for name in extracted if name not in registered_set)
    return RegistrationCoverage(
        extracted=len(extracted),
        registered=len(matched),
        excluded=len(excluded),
        registered_names=matched,
        excluded_names=excluded,
    )


def pose_extent(model_dir: str | Path) -> tuple[float, float, float]:
    """Per-axis span of the registered camera centres, in COLMAP world units."""
    images = read_images(model_dir)
    if not images:
        raise ModelCoverageError(f"model at {model_dir} has no registered images")
    centres = camera_centers(images)
    return tuple(float(value) for value in (centres.max(axis=0) - centres.min(axis=0)))


def _warnings(choice: ModelChoice, registration: RegistrationCoverage) -> list[str]:
    """Facts a reader needs before trusting the model as the whole capture."""
    notes = []
    for path, count in choice.others():
        notes.append(
            f"a second model at {path} holds {count} registered image(s) and was not used; "
            "those frames are not in the reported coverage"
        )
    if registration.coverage < DEFAULT_MIN_COVERAGE:
        notes.append(
            f"only {registration.coverage:.0%} of the extracted frames registered, below the "
            f"{DEFAULT_MIN_COVERAGE:.0%} default; treat the reconstruction as partial"
        )
    return notes


def build_report(
    scene_dir: str | Path,
    frames_dir: str | Path | None = None,
    model_path: str | Path | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> CoverageReport:
    """Read the model and report what it covers and what it does not."""
    scene = Path(scene_dir).expanduser()
    choice = choose_model(scene, model_path)
    model_dir = Path(choice.chosen)
    registration = compare_registration(model_dir, extracted_frames(frames_dir or scene / "images"))
    return CoverageReport(
        scene_dir=str(scene),
        choice=choice,
        intrinsics=read_intrinsics(model_dir),
        registration=registration,
        min_coverage=min_coverage,
        pose_extent=pose_extent(model_dir),
        warnings=tuple(_warnings(choice, registration)),
    )


#: Unsupported frames listed before the summary is collapsed with a count.
UNSUPPORTED_SAMPLE_LINES = 10


def render_report(report: CoverageReport) -> str:
    """Render the coverage report as text."""
    sections = (_render_model(report), _render_registration(report), _render_limits(report))
    return "\n".join(line for section in sections for line in section)


def _render_model(report: CoverageReport) -> list[str]:
    lines = [
        "=== SPARSE MODEL ===",
        f"model used: {report.choice.chosen} ({report.choice.chosen_images} registered images)",
    ]
    lines += [
        f"  other model: {path} ({count} registered images) -- NOT used"
        for path, count in report.choice.others()
    ]
    lines += [
        f"cameras: {report.intrinsics.camera_count}, model {', '.join(report.intrinsics.models)}, "
        f"resolution {', '.join(report.intrinsics.resolutions)}",
        f"pose extent: {report.pose_extent[0]:.3f} x {report.pose_extent[1]:.3f} x "
        f"{report.pose_extent[2]:.3f} COLMAP units (arbitrary scale)",
        "",
    ]
    return lines


def _render_registration(report: CoverageReport) -> list[str]:
    registration = report.registration
    lines = [
        "=== REGISTRATION ===",
        f"extracted {registration.extracted} frames, registered {registration.registered}, "
        f"excluded {registration.excluded} ({registration.coverage:.1%} coverage)",
    ]
    lines += [f"  no geometry: {name}" for name in report.unsupported_frames[:UNSUPPORTED_SAMPLE_LINES]]
    remaining = len(report.unsupported_frames) - UNSUPPORTED_SAMPLE_LINES
    if remaining > 0:
        lines.append(f"  ... and {remaining} more")
    lines.append(
        f"coverage floor {report.min_coverage:.0%}: "
        + ("met" if report.covers_enough else "NOT MET")
    )
    return lines


def _render_limits(report: CoverageReport) -> list[str]:
    lines = [f"warn: {warning}" for warning in report.warnings]
    if report.unsupported_frames:
        lines.append(
            "note: the walkable volume is limited to the registered frames; a walk through the "
            "excluded ones leaves the reconstruction"
        )
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="model_coverage.py",
        description="Report registered vs excluded frames in a COLMAP sparse model.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("scene_dir", help="scene directory containing sparse/ and images/")
    parser.add_argument("--frames-dir", help="extracted frames (default: <scene_dir>/images)")
    parser.add_argument("--model", help="report on this sparse model instead of choosing one")
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    parser.add_argument("--json", dest="json_path", help="write the full report as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not 0 < args.min_coverage <= 1:
        sys.stderr.write("FAIL: --min-coverage must be in (0, 1]\n")
        return EXIT_USAGE
    try:
        report = build_report(args.scene_dir, args.frames_dir, args.model, args.min_coverage)
    except (ModelCoverageError, FileNotFoundError, ValueError, struct.error, OSError) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return EXIT_USAGE
    print(render_report(report))
    if args.json_path:
        Path(args.json_path).expanduser().write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return EXIT_OK if report.covers_enough else EXIT_LOW_COVERAGE


if __name__ == "__main__":
    sys.exit(main())
