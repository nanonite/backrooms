"""
Tests for convert_video.sh — argument parsing, validation, scene name safety.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v

The full pipeline (run_pipeline.sh) is NOT exercised — tests provide
CONVERT_SCENES_ROOT to isolate scene-directory setup from the real repo,
and accept that exec into the pipeline will fail in test environments
(no COLMAP, Brush, SuGaR, or Blender).
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "convert_video.sh"


def _make_env():
    """Return a copy of os.environ — required to avoid mutating the parent process."""
    return dict(os.environ)


def _run_convert(video_path: str, scene_name=None, *, extra_env=None):
    """Run convert_video.sh. Returns subprocess.CompletedProcess."""
    env = _make_env()
    if extra_env:
        env.update(extra_env)
    args = ["bash", str(SCRIPT), str(video_path)]
    if scene_name is not None:
        args.append(scene_name)
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_help_shows_usage():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout


def test_help_flag_h():
    result = subprocess.run(
        ["bash", str(SCRIPT), "-h"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_missing_video_path_fails():
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "video_path" in result.stderr.lower()


def test_nonexistent_video_fails(tmp_path):
    bogus = str(tmp_path / "does_not_exist.mp4")
    result = _run_convert(bogus)
    assert result.returncode != 0
    assert "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Scene name safety — f-style check before realpath
# ---------------------------------------------------------------------------


def test_rejects_dot_scene_name(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("dummy")
    result = _run_convert(str(video), ".")
    assert result.returncode != 0
    assert "safe" in result.stderr.lower()


def test_rejects_dotdot_scene_name(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("dummy")
    result = _run_convert(str(video), "..")
    assert result.returncode != 0
    assert "safe" in result.stderr.lower()


def test_rejects_slash_in_scene_name(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("dummy")
    result = _run_convert(str(video), "evil/name")
    assert result.returncode != 0
    assert "safe" in result.stderr.lower()


def test_rejects_absolute_traversal_scene_name(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("dummy")
    result = _run_convert(str(video), "/etc/passwd")
    assert result.returncode != 0
    assert "safe" in result.stderr.lower()


def test_rejects_relative_traversal_scene_name(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("dummy")
    result = _run_convert(str(video), "../../outside")
    assert result.returncode != 0
    assert "safe" in result.stderr.lower()


def test_rejects_colon_in_scene_name(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("dummy")
    result = _run_convert(str(video), "name:bad")
    assert result.returncode != 0
    assert "safe" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Scene directory setup (before exec into pipeline)
# ---------------------------------------------------------------------------


def test_creates_scene_dir_and_copies_video(tmp_path):
    """Scene dir + video.mp4 created before pipeline exec (which may fail).

    Uses CONVERT_SCENES_ROOT to isolate setup from the real scripts directory.
    """
    scenes_root = tmp_path / "scenes"
    video = tmp_path / "capture.mp4"
    video.write_text("fake mp4")

    result = _run_convert(
        str(video),
        extra_env={"CONVERT_SCENES_ROOT": str(scenes_root)},
    )

    # Pipeline exec will likely fail (fake video, no COLMAP etc.), but setup
    # happens before exec. The scene dir and video.mp4 must exist.
    scene_dir = scenes_root / "capture"
    assert scene_dir.is_dir(), (
        f"Scene dir not created at {scene_dir}. "
        f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
    )
    assert (scene_dir / "video.mp4").exists()
    assert (scene_dir / "video.mp4").read_text() == "fake mp4"


def test_creates_scene_dir_with_custom_name(tmp_path):
    scenes_root = tmp_path / "scenes"
    video = tmp_path / "input.mov"
    video.write_text("fake mov")

    result = _run_convert(
        str(video),
        "my_explicit_scene",
        extra_env={"CONVERT_SCENES_ROOT": str(scenes_root)},
    )

    scene_dir = scenes_root / "my_explicit_scene"
    assert scene_dir.is_dir()
    assert (scene_dir / "video.mp4").exists()
    assert (scene_dir / "video.mp4").read_text() == "fake mov"


def test_derives_scene_name_from_video_filename(tmp_path):
    """When no scene_name is given, the name comes from the video filename (no ext)."""
    scenes_root = tmp_path / "scenes"
    video = tmp_path / "walkthrough_2024.mp4"
    video.write_text("dummy")

    result = _run_convert(
        str(video),
        extra_env={"CONVERT_SCENES_ROOT": str(scenes_root)},
    )

    scene_dir = scenes_root / "walkthrough_2024"
    assert scene_dir.is_dir()
    assert (scene_dir / "video.mp4").exists()
