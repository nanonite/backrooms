#!/usr/bin/env python3
"""
Tests for pose_colmap.sh — argument parsing, dependency checks, success/failure gates.

Creates stub colmap/glomap executables in a temp PATH so tests work without
real COLMAP/GLOMAP binaries.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import os
import stat
import struct
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "pose_colmap.sh"


# ---------------------------------------------------------------------------
# Stub executables
# ---------------------------------------------------------------------------

_COLMAP_STUB = """#!/bin/bash
set -euo pipefail
if [[ -n "${COLMAP_FAIL:-}" ]]; then
    echo "colmap stub: forced failure" >&2
    exit 1
fi
case "$1" in
    feature_extractor|exhaustive_matcher|sequential_matcher) exit 0 ;;
    *) echo "colmap stub: unknown command $1" >&2; exit 1 ;;
esac
"""

_GLOMAP_STUB = """#!/bin/bash
set -euo pipefail
if [[ -n "${GLOMAP_FAIL:-}" ]]; then
    echo "glomap stub: forced failure" >&2
    exit 1
fi
if [[ "$1" != "mapper" ]]; then
    echo "glomap stub: unknown command $1" >&2; exit 1
fi
shift
OUTPUT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output_path) OUTPUT="$2"; shift 2 ;;
        *) shift ;;
    esac
done
if [[ -z "$OUTPUT" ]]; then
    echo "glomap stub: no --output_path" >&2; exit 1
fi
MODEL_DIR="${OUTPUT}/0"
mkdir -p "$MODEL_DIR"

COUNT="${GLOMAP_REGISTERED_COUNT:-10}"
SKIP="${GLOMAP_SKIP_BIN:-}"

python3 - "$MODEL_DIR" "$COUNT" "$SKIP" << '_PYEOF'
import struct, os, sys
model_dir = sys.argv[1]
count = int(sys.argv[2])
skip = sys.argv[3]

if skip != "cameras.bin":
    with open(os.path.join(model_dir, "cameras.bin"), "wb") as f:
        f.write(struct.pack("<Q", 1))

if skip != "images.bin":
    with open(os.path.join(model_dir, "images.bin"), "wb") as f:
        f.write(struct.pack("<Q", count))

if skip != "points3D.bin":
    with open(os.path.join(model_dir, "points3D.bin"), "wb") as f:
        f.write(struct.pack("<Q", 100))
_PYEOF
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executable(path: Path) -> None:
    """Set executable bits on a file."""
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write_stub(bin_dir: Path, name: str, content: str) -> Path:
    path = bin_dir / name
    path.write_text(content)
    _make_executable(path)
    return path


def _make_stub_env(tmp_path: Path) -> dict:
    """Create stub colmap/glomap in a temp bin dir and return env with PATH set."""
    bin_dir = tmp_path / "stub_bin"
    bin_dir.mkdir()
    _write_stub(bin_dir, "colmap", _COLMAP_STUB)
    _write_stub(bin_dir, "glomap", _GLOMAP_STUB)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def _make_images(scene_dir: Path, count: int) -> Path:
    """Create N placeholder frames in scene_dir/images/."""
    images_dir = scene_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (images_dir / f"frame_{i:04d}.jpg").write_text(f"fake_image_{i}")
    return images_dir


def _run(scene_dir: Path, extra_args=None, env=None) -> tuple[int, str, str]:
    """Run pose_colmap.sh and return (returncode, stdout, stderr)."""
    cmd = ["bash", str(SCRIPT), str(scene_dir)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


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
        rc, stdout, stderr = _run(Path("--help"))
        assert rc == 0
        assert "Usage:" in stdout

    def test_help_short_flag(self):
        rc, stdout, stderr = _run(Path("-h"))
        assert rc == 0
        assert "Usage:" in stdout

    def test_unknown_option_fails(self, tmp_path):
        _make_images(tmp_path, 3)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--bogus"], env=env)
        assert rc == 1
        assert "Unknown option" in stderr


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------


class TestDependencyChecks:
    def test_no_colmap_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        glomap = bin_dir / "glomap"
        glomap.write_text("#!/bin/bash\nexit 0\n")
        _make_executable(glomap)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 2
        assert "colmap not found" in stderr

    def test_no_glomap_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        colmap = bin_dir / "colmap"
        colmap.write_text("#!/bin/bash\nexit 0\n")
        _make_executable(colmap)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 2
        assert "glomap not found" in stderr

    def test_both_missing_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        stub_dir = tmp_path / "stubs"
        stub_dir.mkdir()
        env = os.environ.copy()
        # Prepend empty stub dir so colmap/glomap are not found, but keep
        # standard paths (defpath) so bash itself can be located.
        env["PATH"] = f"{stub_dir}:{os.defpath}"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 2


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_missing_images_dir_fails(self, tmp_path):
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "images directory not found" in stderr

    def test_empty_images_dir_fails(self, tmp_path):
        (tmp_path / "images").mkdir()
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "No images found" in stderr


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_exhaustive_default(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert (tmp_path / "sparse/0/cameras.bin").exists()
        assert (tmp_path / "sparse/0/images.bin").exists()
        assert (tmp_path / "sparse/0/points3D.bin").exists()
        assert "POSE_OK" in stdout

    def test_sequential_flag(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(
            tmp_path, extra_args=["--sequential"], env=env
        )
        assert rc == 0
        assert "POSE_OK" in stdout

    def test_sequential_env_var(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        env["POSE_MATCHER_MODE"] = "sequential"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "POSE_OK" in stdout

    def test_no_cleanup_keeps_db(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(
            tmp_path, extra_args=["--no-cleanup"], env=env
        )
        assert rc == 0
        assert "POSE_OK" in stdout


# ---------------------------------------------------------------------------
# Failure gates
# ---------------------------------------------------------------------------


class TestFailureGates:
    def test_missing_cameras_bin(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_SKIP_BIN"] = "cameras.bin"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        marker = tmp_path / "POSE_FAILED"
        assert marker.exists()
        assert "cameras.bin" in marker.read_text()

    def test_missing_images_bin(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_SKIP_BIN"] = "images.bin"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        assert (tmp_path / "POSE_FAILED").exists()

    def test_missing_points3d_bin(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_SKIP_BIN"] = "points3D.bin"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5
        assert (tmp_path / "POSE_FAILED").exists()

    def test_pose_failed_too_few_registered(self, tmp_path):
        _make_images(tmp_path, 10)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "2"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 6
        marker = tmp_path / "POSE_FAILED"
        assert marker.exists()
        assert "POSE_FAILED:" in marker.read_text()

    def test_min_registered_env_override_lowers_threshold(self, tmp_path):
        _make_images(tmp_path, 10)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "2"
        env["POSE_MIN_REGISTERED"] = "0.1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "POSE_OK" in stdout

    def test_glomap_failure_exits_5(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_FAIL"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 5

    def test_colmap_failure_exits_4(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        env["COLMAP_FAIL"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 4


# ---------------------------------------------------------------------------
# Threshold edge cases — ceiling rounding and minimum registered gate
# ---------------------------------------------------------------------------


class TestThresholdEdgeCases:
    def test_one_image_zero_registered_fails(self, tmp_path):
        _make_images(tmp_path, 1)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "0"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 6  # ceil(1*0.5)=1 > 0

    def test_one_image_one_registered_passes(self, tmp_path):
        _make_images(tmp_path, 1)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0  # ceil(1*0.5)=1, 1>=1

    def test_three_images_one_registered_fails(self, tmp_path):
        _make_images(tmp_path, 3)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 6  # ceil(3*0.5)=2, 1<2

    def test_three_images_two_registered_passes(self, tmp_path):
        _make_images(tmp_path, 3)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "2"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0  # ceil(3*0.5)=2, 2>=2

    def test_two_images_one_registered_passes(self, tmp_path):
        _make_images(tmp_path, 2)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0  # ceil(2*0.5)=1, 1>=1


# ---------------------------------------------------------------------------
# Machine-readable signaling
# ---------------------------------------------------------------------------


class TestMachineReadableSignal:
    def test_pose_ok_on_success(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "POSE_OK:" in stdout
        assert not (tmp_path / "POSE_FAILED").exists()

    def test_pose_failed_marker_content(self, tmp_path):
        _make_images(tmp_path, 10)
        env = _make_stub_env(tmp_path)
        env["GLOMAP_REGISTERED_COUNT"] = "3"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 6
        marker = tmp_path / "POSE_FAILED"
        content = marker.read_text()
        assert "POSE_FAILED:" in content
        assert "registered" in content.lower()

    def test_stale_marker_cleared_on_success(self, tmp_path):
        _make_images(tmp_path, 5)
        (tmp_path / "POSE_FAILED").write_text("previous failure")
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert not (tmp_path / "POSE_FAILED").exists()


# ---------------------------------------------------------------------------
# Matcher mode output
# ---------------------------------------------------------------------------


class TestMatchingMode:
    def test_exhaustive_mode_in_output(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "exhaustive" in stdout.lower()

    def test_sequential_mode_in_output(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(
            tmp_path, extra_args=["--sequential"], env=env
        )
        assert rc == 0
        # sequential appears in the Matcher: line of the script header
        assert "sequential" in stdout.lower()
