#!/usr/bin/env python3
"""Stage a COLMAP capture into the layout nerfstudio will actually read.

Nerfstudio's colmap dataparser expects the model at ``<data>/colmap/sparse/0``
(this repo's COLMAP 3.10 + GLOMAP output is at ``<data>/sparse/0``), and when it
resolves its default downscale factor it *asks* whether to generate the
downscaled images. Two consequences for an unattended run:

* the model directory must be passed explicitly, or the run dies before touching
  the GPU;
* the prompt reads stdin, so an automated run gets ``EOFError`` instead of
  training.

This module removes both problems without mutating the capture: symlinks for the
read-only inputs, and pre-rendered ``images_2`` so nerfstudio finds what it
wanted to ask for. The staging directory is disposable and is measured
separately from the capture.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

FFMPEG = "ffmpeg"

#: Nerfstudio's ``MAX_AUTO_RESOLUTION``. Above this it halves the images.
MAX_AUTO_RESOLUTION = 1600

#: Default rounding mode in nerfstudio's colmap dataparser.
DEFAULT_ROUNDING = "floor"


class DatasetError(RuntimeError):
    """Raised when a capture cannot be staged for nerfstudio."""


@dataclass(frozen=True)
class StagedDataset:
    """A prepared dataset and the settings that produced it."""

    staging_dir: Path
    source_dir: Path
    downscale_factor: int
    frame_count: int
    image_size: tuple[int, int]
    downscaled_size: tuple[int, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "staging_dir": str(self.staging_dir),
            "source_dir": str(self.source_dir),
            "downscale_factor": self.downscale_factor,
            "frame_count": self.frame_count,
            "input_resolution": f"{self.image_size[0]}x{self.image_size[1]}",
            "training_resolution": f"{self.downscaled_size[0]}x{self.downscaled_size[1]}",
        }


def resolve_downscale_factor(width: int, height: int) -> int:
    """Return the factor nerfstudio's own default resolves to for this input."""
    longest = max(width, height)
    factor = 1
    while longest // factor > MAX_AUTO_RESOLUTION:
        factor *= 2
    return factor


def _scale(size: tuple[int, int], factor: int, rounding: str) -> tuple[int, int]:
    """Scale a size the way nerfstudio's dataparser does, including rounding mode."""
    import math

    rules = {
        "floor": math.floor,
        "round": round,
        "ceil": math.ceil,
    }
    if rounding not in rules:
        raise DatasetError(f"unknown rounding mode {rounding!r}")
    rule = rules[rounding]
    return rule(size[0] / factor), rule(size[1] / factor)


def _link(source: Path, destination: Path) -> None:
    """Symlink ``source`` at ``destination``, replacing anything already there."""
    if destination.is_symlink() or destination.exists():
        destination.unlink()
    destination.symlink_to(source.resolve())


def _image_size(image_path: Path) -> tuple[int, int]:
    """Return an image's pixel size using ffprobe, so no image library is needed."""
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(image_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width, height = completed.stdout.strip().split("x")
    return int(width), int(height)


def _downscale_one(source: Path, destination: Path, size: tuple[int, int]) -> None:
    """Render one frame at ``size`` with ffmpeg, matching nerfstudio's own command."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-noautorotate",
            "-i",
            str(source),
            "-q:v",
            "2",
            "-vf",
            f"scale={size[0]}:{size[1]}",
            str(destination),
        ],
        capture_output=True,
        check=True,
    )


def _staging_images(source_dir: Path, staging_dir: Path) -> Path:
    """Return the staging ``images`` directory, linked to the capture's frames."""
    images = source_dir / "images"
    if not images.is_dir():
        raise DatasetError(f"no images/ directory in {source_dir}")
    _link(images, staging_dir / "images")
    return images


def _stage_sparse(source_dir: Path, staging_dir: Path) -> None:
    """Link the COLMAP model into the ``sparse/0`` layout nerfstudio reads."""
    sparse = source_dir / "sparse"
    if not (sparse / "0" / "points3D.bin").exists():
        raise DatasetError(f"no COLMAP model at {sparse / '0'}")
    _link(sparse, staging_dir / "sparse")


def _render_downscaled(
    images: Path, staging_dir: Path, factor: int, size: tuple[int, int]
) -> tuple[int, int]:
    """Pre-render ``images_<factor>`` so nerfstudio never has to prompt.

    Idempotent: a frame that already exists is left alone, so re-staging a scene
    for a second benchmark does not charge 96 ffmpeg invocations to the run
    being measured.
    """
    frames = sorted(images.glob("*.jpg")) + sorted(images.glob("*.png"))
    target = staging_dir / f"images_{factor}"
    rendered = reused = 0
    for frame in frames:
        destination = target / frame.name
        if destination.exists():
            reused += 1
            continue
        _downscale_one(frame, destination, size)
        rendered += 1
    return len(frames), rendered + reused


def _existing_resolution(directory: Path) -> tuple[int, int] | None:
    """Return the pixel size of an already-rendered frame directory, if any."""
    frames = sorted(directory.glob("*.jpg")) or sorted(directory.glob("*.png"))
    return _image_size(frames[0]) if frames else None


def stage_dataset(
    source_dir: str | Path,
    staging_dir: str | Path,
    rounding: str = DEFAULT_ROUNDING,
    skip_downscaling: bool = False,
) -> StagedDataset:
    """Prepare ``source_dir`` under ``staging_dir`` for an unattended nerfstudio run.

    Safe to re-run: the read-only inputs are re-linked, already-rendered frames
    are reused, and nothing under ``source_dir`` is written.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise DatasetError(f"capture directory not found: {source}")
    staging = Path(staging_dir)
    if staging.resolve() == source.resolve():
        raise DatasetError("staging directory must differ from the capture directory")
    staging.mkdir(parents=True, exist_ok=True)

    images = _staging_images(source, staging)
    _stage_sparse(source, staging)
    frames = sorted(images.glob("*.jpg")) + sorted(images.glob("*.png"))
    if not frames:
        raise DatasetError(f"no frames found in {images}")
    source_size = _image_size(frames[0])
    factor = 1 if skip_downscaling else resolve_downscale_factor(*source_size)
    target_size = _scale(source_size, factor, rounding)
    staged_size = _existing_resolution(staging / f"images_{factor}") or target_size
    count = len(frames)
    if factor > 1:
        count, _rendered = _render_downscaled(images, staging, factor, staged_size)
    return StagedDataset(staging, source, factor, count, source_size, staged_size)


def main(argv: list[str]) -> int:
    """Stage a dataset from the command line; used by tests and manual setup."""
    if len(argv) != 2:
        print(f"usage: {sys.argv[0]} <capture_dir> <staging_dir>", file=sys.stderr)
        return 1
    if shutil.which(FFMPEG) is None:
        print(f"ERROR: {FFMPEG} is required to stage a dataset", file=sys.stderr)
        return 2
    staged = stage_dataset(argv[0], argv[1])
    print(f"staged {staged.frame_count} frames at {staged.downscaled_size} in {staged.staging_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))