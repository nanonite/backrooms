#!/usr/bin/env python3
"""Tests for staging a COLMAP capture into nerfstudio's expected layout.

The bugs guarded here are the ones that cost a whole pipeline run each: a model
at the wrong path, an interactive prompt eating EOF, and a staging step that
quietly writes into the capture it was supposed to leave alone.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_colmap_dataset.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from colmap_dataset import (
    MAX_AUTO_RESOLUTION,
    DatasetError,
    resolve_downscale_factor,
    stage_dataset,
)


def make_capture(root: Path, frames: int = 3, width: int = 1920, height: int = 1080) -> Path:
    """Create a minimal COLMAP capture tree with real (tiny) JPEGs."""
    images = root / "images"
    images.mkdir(parents=True)
    for index in range(frames):
        _write_jpeg(images / f"frame_{index:04d}.jpg", width, height)
    sparse = root / "sparse" / "0"
    sparse.mkdir(parents=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse / name).write_bytes(b"\x00" * 8)
    return root


def _write_jpeg(path: Path, width: int, height: int) -> None:
    """Write a JPEG of the requested size using ffmpeg."""
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=red:s={width}x{height}",
         "-frames:v", "1", str(path)],
        capture_output=True,
        check=True,
    )


# ---------------------------------------------------------------------------
# Downscale factor arithmetic
# ---------------------------------------------------------------------------


def test_1920_input_is_halved_because_1920_exceeds_the_auto_resolution_cap():
    assert resolve_downscale_factor(1920, 1080) == 2


def test_an_input_already_under_the_cap_is_not_downscaled():
    assert resolve_downscale_factor(1280, 720) == 1


def test_a_4k_input_is_halved_twice():
    assert resolve_downscale_factor(3840, 2160) == 4


def test_the_cap_is_the_value_nerfstudio_uses():
    assert MAX_AUTO_RESOLUTION == 1600


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------


def test_staging_links_the_capture_and_never_writes_into_it(tmp_path):
    capture = make_capture(tmp_path / "capture")
    before = sorted(path.name for path in (capture / "images").iterdir())

    staged = stage_dataset(capture, tmp_path / "staging")

    assert sorted(path.name for path in (capture / "images").iterdir()) == before
    assert (tmp_path / "staging" / "images").is_symlink()
    assert staged.frame_count == 3


def test_staging_renders_the_downscaled_frames_nerfstudio_would_have_asked_for(tmp_path):
    staged = stage_dataset(make_capture(tmp_path / "capture"), tmp_path / "staging")

    rendered = sorted((tmp_path / "staging" / "images_2").glob("*.jpg"))
    assert len(rendered) == 3
    assert staged.downscaled_size == (960, 540)
    assert staged.image_size == (1920, 1080)


def test_the_model_is_reachable_at_the_path_nerfstudio_is_told_to_use(tmp_path):
    stage_dataset(make_capture(tmp_path / "capture"), tmp_path / "staging")

    assert (tmp_path / "staging" / "sparse" / "0" / "points3D.bin").exists()


def test_restaging_reuses_rendered_frames_rather_than_redoing_them(tmp_path):
    capture = make_capture(tmp_path / "capture")
    staging = tmp_path / "staging"
    stage_dataset(capture, staging)
    marker = staging / "images_2" / "frame_0000.jpg"
    marker.write_bytes(marker.read_bytes() + b"marker")

    staged = stage_dataset(capture, staging)

    assert (staging / "images_2" / "frame_0000.jpg").read_bytes().endswith(b"marker")
    assert staged.frame_count == 3


def test_skipping_downscaling_leaves_the_input_resolution_alone(tmp_path):
    staged = stage_dataset(make_capture(tmp_path / "capture"), tmp_path / "staging", skip_downscaling=True)

    assert staged.downscaled_size == staged.image_size
    assert not (tmp_path / "staging" / "images_2").exists()


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_capture_without_images_is_refused(tmp_path):
    capture = tmp_path / "capture"
    (capture / "sparse" / "0").mkdir(parents=True)

    with pytest.raises(DatasetError, match="images/"):
        stage_dataset(capture, tmp_path / "staging")


def test_a_capture_without_a_colmap_model_is_refused(tmp_path):
    capture = tmp_path / "capture"
    (capture / "images").mkdir(parents=True)

    with pytest.raises(DatasetError, match="COLMAP model"):
        stage_dataset(capture, tmp_path / "staging")


def test_a_missing_capture_directory_is_refused(tmp_path):
    with pytest.raises(DatasetError, match="not found"):
        stage_dataset(tmp_path / "absent", tmp_path / "staging")


def test_staging_into_the_capture_itself_is_refused(tmp_path):
    capture = make_capture(tmp_path / "capture")

    with pytest.raises(DatasetError, match="must differ"):
        stage_dataset(capture, capture)