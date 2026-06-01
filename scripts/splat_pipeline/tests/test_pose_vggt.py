#!/usr/bin/env python3
"""
Tests for pose_vggt.sh — argument parsing, dependency checks, success/failure gates.

Creates a stub VGGT demo_colmap.py in a temp VGGT_ROOT so tests work without
real VGGT, git clone, or GPU.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_pose_vggt.py -v
"""

import os
import stat
import struct
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "pose_vggt.sh"


def _make_executable(path: Path) -> None:
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_images(scene_dir: Path, count: int) -> Path:
    images_dir = scene_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (images_dir / f"frame_{i:04d}.jpg").write_text(f"fake_image_{i}")
    return images_dir


def _make_vggt_stub(vggt_root: Path) -> Path:
    """Create stub VGGT repo with demo_colmap.py and .vggt_deps_ok marker."""
    vggt_root.mkdir(parents=True, exist_ok=True)

    demo_colmap = vggt_root / "demo_colmap.py"
    demo_colmap.write_text(
        """#!/usr/bin/env python3
import argparse, os, struct, sys

parser = argparse.ArgumentParser()
parser.add_argument("--scene_dir", required=True)
parser.add_argument("--use_ba", action="store_true")
args = parser.parse_args()

if os.environ.get("VGGT_STUB_FAIL"):
    print("VGGT stub: forced failure", file=sys.stderr)
    sys.exit(1)

# Real VGGT demo_colmap.py writes to sparse/ directly (not sparse/0/).
# pose_vggt.sh normalizes to sparse/0/ after the run.
sparse_dir = os.path.join(args.scene_dir, "sparse")
os.makedirs(sparse_dir, exist_ok=True)

count = int(os.environ.get("VGGT_STUB_REGISTERED", "10"))
skip = os.environ.get("VGGT_STUB_SKIP", "")

for fname, val in [("cameras.bin", 1), ("images.bin", count), ("points3D.bin", 100)]:
    if fname == skip:
        continue
    with open(os.path.join(sparse_dir, fname), "wb") as f:
        f.write(struct.pack("<Q", val))

print(f"VGGT stub: wrote sparse model to {sparse_dir}")
if args.use_ba:
    print("Bundle adjustment: active")
"""
    )
    _make_executable(demo_colmap)

    (vggt_root / ".vggt_deps_ok").touch()

    return demo_colmap


def _make_env(tmp_path: Path, vggt_root: Path) -> dict:
    """Return environment dict with VGGT_ROOT and PATH set."""
    env = os.environ.copy()
    env["VGGT_ROOT"] = str(vggt_root)
    # Ensure git is on PATH (real git, not a stub — we test missing-git separately)
    return env


def _run(scene_dir: Path, extra_args=None, env=None) -> tuple[int, str, str]:
    cmd = ["bash", str(SCRIPT), str(scene_dir)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Script existence and executable bit
# ---------------------------------------------------------------------------


class TestScriptExists:
    def test_script_exists(self):
        assert SCRIPT.exists(), "pose_vggt.sh must exist"

    def test_script_executable(self):
        assert os.access(SCRIPT, os.X_OK), "pose_vggt.sh must be executable"


# ---------------------------------------------------------------------------
# Usage / argument parsing
# ---------------------------------------------------------------------------


class TestUsage:
    def test_no_args_fails(self):
        cmd = ["bash", str(SCRIPT)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 1
        assert "argument required" in result.stderr

    def test_help_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_short_flag(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "-h"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------


class TestDependencyChecks:
    def test_missing_python_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        env = os.environ.copy()
        env["VGGT_ROOT"] = str(tmp_path / "vggt")
        env["VGGT_PYTHON"] = "nonexistent_python_binary_xyz"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 2
        assert "Python not found" in stderr


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_missing_images_dir_fails(self, tmp_path):
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "images directory not found" in stderr

    def test_empty_images_dir_fails(self, tmp_path):
        (tmp_path / "images").mkdir()
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "No images found" in stderr

    def test_vggt_root_missing_demo_colmap(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        vggt_root.mkdir()
        # VGGT_ROOT exists but no demo_colmap.py — should fail with code 4
        (vggt_root / ".vggt_deps_ok").touch()
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 4
        assert "demo_colmap.py not found" in stderr


# ---------------------------------------------------------------------------
# Success path — VGGT stub produces expected output
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_vggt_produces_sparse_output(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert (tmp_path / "sparse/0/cameras.bin").exists()
        assert (tmp_path / "sparse/0/images.bin").exists()
        assert (tmp_path / "sparse/0/points3D.bin").exists()
        assert "POSE_OK" in stdout

    def test_with_bundle_adjustment(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_USE_BA"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "ENABLED" in stdout

    def test_use_ba_with_true_string(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_USE_BA"] = "true"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "ENABLED" in stdout

    def test_use_ba_disabled_by_default(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "DISABLED" in stdout

    def test_custom_python(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_PYTHON"] = "python3"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "POSE_OK" in stdout


# ---------------------------------------------------------------------------
# Failure gates
# ---------------------------------------------------------------------------


class TestFailureGates:
    def test_missing_cameras_bin(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_STUB_SKIP"] = "cameras.bin"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        assert "cameras.bin" in stderr

    def test_missing_images_bin(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_STUB_SKIP"] = "images.bin"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        assert "images.bin" in stderr

    def test_missing_points3d_bin(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_STUB_SKIP"] = "points3D.bin"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        assert "points3D.bin" in stderr

    def test_vggt_model_run_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        env["VGGT_STUB_FAIL"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        assert "demo_colmap.py failed" in stderr

    def test_stale_output_cleared(self, tmp_path):
        _make_images(tmp_path, 5)
        # Pre-create a stale sparse dir from a previous run
        stale_dir = tmp_path / "sparse" / "0"
        stale_dir.mkdir(parents=True)
        (stale_dir / "old_junk.txt").write_text("stale")
        (stale_dir / "cameras.bin").write_bytes(struct.pack("<Q", 5))
        (stale_dir / "images.bin").write_bytes(struct.pack("<Q", 5))
        (stale_dir / "points3D.bin").write_bytes(struct.pack("<Q", 5))

        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        # Stale junk should be gone
        assert not (stale_dir / "old_junk.txt").exists()
        # Fresh output should exist
        assert (stale_dir / "cameras.bin").exists()


# ---------------------------------------------------------------------------
# Env var configuration
# ---------------------------------------------------------------------------


class TestEnvVarConfig:
    def test_vggt_root_env(self, tmp_path):
        _make_images(tmp_path, 5)
        custom_root = tmp_path / "custom_vggt"
        _make_vggt_stub(custom_root)
        env = os.environ.copy()
        env["VGGT_ROOT"] = str(custom_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "POSE_OK" in stdout

    def test_pose_ok_in_output(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "POSE_OK" in stdout

    def test_fallback_label_in_output(self, tmp_path):
        _make_images(tmp_path, 5)
        vggt_root = tmp_path / "vggt_stub"
        _make_vggt_stub(vggt_root)
        env = _make_env(tmp_path, vggt_root)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "FALLBACK" in stdout
