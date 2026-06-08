"""
Tests for stage_assets.sh — argument parsing, asset copying, alignment idempotency.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "stage_assets.sh"


def _make_env():
    """Return a copy of os.environ — required to avoid mutating the parent process."""
    return dict(os.environ)


def _run_stage(scene_dir: Path, splats_root: Path):
    """Run stage_assets.sh with SPLAT_SPLATS_ROOT pointed at a test tree."""
    env = _make_env()
    env["SPLAT_SPLATS_ROOT"] = str(splats_root)
    result = subprocess.run(
        ["bash", str(SCRIPT), str(scene_dir)],
        capture_output=True,
        text=True,
        env=env,
    )
    return result


# ---------------------------------------------------------------------------
# Argument / help
# ---------------------------------------------------------------------------


def test_help_shows_usage():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout


def test_missing_scene_dir_fails():
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "scene_dir" in result.stderr.lower()


def test_scene_dir_not_found_fails():
    result = subprocess.run(
        ["bash", str(SCRIPT), "/nonexistent/scene_dir_12345"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Asset copying
# ---------------------------------------------------------------------------


def test_copies_scene_ply_and_collision_glb(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 1.0\n")

    scene_dir = tmp_path / "scene_work"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("fake ply content")
    (scene_dir / "collision.glb").write_text("fake glb content")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode == 0
    dest = splats_root / "scene_work"
    assert dest.is_dir()
    assert (dest / "scene.ply").read_text() == "fake ply content"
    assert (dest / "collision.mesh.glb").read_text() == "fake glb content"


# ---------------------------------------------------------------------------
# alignment.toml idempotency
# ---------------------------------------------------------------------------


def test_creates_alignment_toml_from_template_when_missing(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 2.5\n[rotation]\nx = 0.5\n")

    scene_dir = tmp_path / "my_scene"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("ply")
    (scene_dir / "collision.glb").write_text("glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode == 0
    dest = splats_root / "my_scene"
    assert dest.is_dir()
    alignment = (dest / "alignment.toml").read_text()
    assert "scale = 2.5" in alignment
    assert "0.5" in alignment


def test_preserves_existing_alignment_toml_on_rerun(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 1.0\n")

    # Pre-populate a hand-tuned alignment.toml under the SAME scene name
    # that will be derived from scene_dir's basename.
    dest = splats_root / "my_scene"
    dest.mkdir(parents=True)
    (dest / "alignment.toml").write_text("scale = 3.14  # tuned by hand\n")

    scene_dir = tmp_path / "my_scene"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("ply")
    (scene_dir / "collision.glb").write_text("glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode == 0
    alignment = (dest / "alignment.toml").read_text()
    assert "scale = 3.14" in alignment
    assert "tuned by hand" in alignment
    assert "preserving" in result.stdout.lower()


def test_rerun_overwrites_scene_ply_and_collision_glb(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 1.0\n")

    dest = splats_root / "my_scene"
    dest.mkdir(parents=True)
    (dest / "scene.ply").write_text("old ply")
    (dest / "collision.mesh.glb").write_text("old glb")
    (dest / "alignment.toml").write_text("scale = 9.9\n")

    scene_dir = tmp_path / "my_scene"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("new ply")
    (scene_dir / "collision.glb").write_text("new glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode == 0
    assert (dest / "scene.ply").read_text() == "new ply"
    assert (dest / "collision.mesh.glb").read_text() == "new glb"
    assert (dest / "alignment.toml").read_text() == "scale = 9.9\n"


# ---------------------------------------------------------------------------
# current_scene.txt
# ---------------------------------------------------------------------------


def test_updates_current_scene_txt(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 1.0\n")

    scene_dir = tmp_path / "kitchen"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("ply")
    (scene_dir / "collision.glb").write_text("glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode == 0
    current = (splats_root / "current_scene.txt").read_text().strip()
    assert current == "kitchen"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_fails_when_scene_ply_missing(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 1.0\n")

    scene_dir = tmp_path / "scene_work"
    scene_dir.mkdir()
    # scene.ply missing
    (scene_dir / "collision.glb").write_text("glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode != 0
    assert "scene.ply" in result.stderr


def test_fails_when_collision_glb_missing(tmp_path):
    splats_root = tmp_path / "splats"
    (splats_root / "_template").mkdir(parents=True)
    (splats_root / "_template/alignment.toml").write_text("scale = 1.0\n")

    scene_dir = tmp_path / "scene_work"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("ply")
    # collision.glb missing

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode != 0
    assert "collision.glb" in result.stderr


def test_fails_when_template_missing(tmp_path):
    splats_root = tmp_path / "splats"
    # No _template directory at all

    scene_dir = tmp_path / "scene_work"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("ply")
    (scene_dir / "collision.glb").write_text("glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode != 0
    assert "template" in result.stderr.lower()


def test_current_scene_txt_not_updated_on_failure(tmp_path):
    """If staging fails partway, current_scene.txt must not be written."""
    splats_root = tmp_path / "splats"
    # No _template — will fail before current_scene.txt write

    scene_dir = tmp_path / "scene_work"
    scene_dir.mkdir()
    (scene_dir / "scene.ply").write_text("ply")
    (scene_dir / "collision.glb").write_text("glb")

    result = _run_stage(scene_dir, splats_root)

    assert result.returncode != 0
    assert not (splats_root / "current_scene.txt").exists()
