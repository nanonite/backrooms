#!/usr/bin/env python3
"""
Tests for train_brush.sh — argument parsing, dependency checks, input validation,
success/failure gates, splat-count extraction, and --max-splats flag passing.

Creates a stub brush executable in a temp PATH so tests work without a real
Brush binary or GPU.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "train_brush.sh"

# ---------------------------------------------------------------------------
# PLY builder helper — produces a minimal valid PLY with element vertex header
# ---------------------------------------------------------------------------


def _ply_bytes(vertex_count: int) -> bytes:
    """Return bytes of a minimal valid PLY file with the given vertex count."""
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {vertex_count}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    )
    # Append dummy vertex data (3 floats * vertex_count * 4 bytes)
    import struct

    body = b""
    for _ in range(vertex_count):
        body += struct.pack("<fff", 0.0, 0.0, 0.0)
    return header.encode("ascii") + body


# ---------------------------------------------------------------------------
# Stub brush executable
# ---------------------------------------------------------------------------

_BRUSH_STUB = """#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BRUSH_FAIL:-}" ]]; then
    echo "brush stub: forced failure" >&2
    exit 1
fi

# Extract args
SCENE_DIR=""
TOTAL_STEPS=""
MAX_SPLATS=""
EXPORT_PATH=""
EXPORT_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --total-steps) TOTAL_STEPS="$2"; shift 2 ;;
        --max-splats) MAX_SPLATS="$2"; shift 2 ;;
        --export-path) EXPORT_PATH="$2"; shift 2 ;;
        --export-name) EXPORT_NAME="$2"; shift 2 ;;
        *)
            if [[ -z "$SCENE_DIR" ]]; then
                SCENE_DIR="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$EXPORT_PATH" ]]; then
    echo "brush stub: --export-path required" >&2
    exit 1
fi
if [[ -z "$EXPORT_NAME" ]]; then
    echo "brush stub: --export-name required" >&2
    exit 1
fi

# Decide vertex count: use requested cap if set, else env var, else 1500000
REQUESTED_CAP="${MAX_SPLATS:-}"
ENV_COUNT="${BRUSH_SPLAT_COUNT:-1500000}"

if [[ -n "$REQUESTED_CAP" ]] && [[ "$REQUESTED_CAP" -lt "$ENV_COUNT" ]]; then
    VERTEX_COUNT="$REQUESTED_CAP"
else
    VERTEX_COUNT="$ENV_COUNT"
fi

# Ensure export directory exists (Brush creates it if needed, stub mimics this)
mkdir -p "$EXPORT_PATH"

# Write the PLY file to export_path/export_name
python3 - "$EXPORT_PATH/$EXPORT_NAME" "$VERTEX_COUNT" << '_PYEOF'
import struct, sys
export_path = sys.argv[1]
vertex_count = int(sys.argv[2])
header = (
    "ply\\n"
    "format binary_little_endian 1.0\\n"
    f"element vertex {vertex_count}\\n"
    "property float x\\n"
    "property float y\\n"
    "property float z\\n"
    "end_header\\n"
)
# Pre-allocate with repeated bytes, not a loop (avoids O(n^2) string concat).
vertex_bytes = struct.pack("<fff", 0.0, 0.0, 0.0) * vertex_count
with open(export_path, "wb") as f:
    f.write(header.encode("ascii") + vertex_bytes)
_PYEOF

# Echo args for test assertions
echo "brush stub: scene=$SCENE_DIR total_steps=$TOTAL_STEPS max_splats=${MAX_SPLATS:-none} export=$EXPORT_PATH export_name=$EXPORT_NAME"
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executable(path: Path) -> None:
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write_stub(bin_dir: Path, name: str, content: str) -> Path:
    path = bin_dir / name
    path.write_text(content)
    _make_executable(path)
    return path


def _make_stub_env(tmp_path: Path) -> dict:
    """Create stub brush in a temp bin dir and return env with PATH set."""
    bin_dir = tmp_path / "stub_bin"
    bin_dir.mkdir()
    _write_stub(bin_dir, "brush", _BRUSH_STUB)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def _make_real_jpegs(images_dir: Path, count: int) -> None:
    """Create N minimal but valid JPEG files readable by OpenCV."""
    import numpy as np

    try:
        import cv2
    except ImportError:
        pytest.skip("opencv-python not available")

    # 16x16 grayscale image with some gradient (non-zero Laplacian variance)
    arr = np.zeros((16, 16), dtype=np.uint8)
    for x in range(16):
        for y in range(16):
            arr[y, x] = (x * 16 + y) % 256

    for i in range(count):
        path = images_dir / f"frame_{i:04d}.jpg"
        cv2.imwrite(str(path), arr)


def _make_images(scene_dir: Path, count: int) -> Path:
    """Create N placeholder frames in scene_dir/images/."""
    images_dir = scene_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (images_dir / f"frame_{i:04d}.jpg").write_text(f"fake_image_{i}")
    return images_dir


def _make_sparse(scene_dir: Path) -> Path:
    """Create sparse/0/ with cameras.bin, images.bin, points3D.bin."""
    sparse_dir = scene_dir / "sparse" / "0"
    sparse_dir.mkdir(parents=True, exist_ok=True)
    for name in ("cameras.bin", "images.bin", "points3D.bin"):
        (sparse_dir / name).write_text(f"fake_{name}")
    return sparse_dir


def _run(scene_dir: Path, extra_args=None, env=None) -> tuple[int, str, str]:
    """Run train_brush.sh and return (returncode, stdout, stderr)."""
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
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--bogus"], env=env)
        assert rc == 1
        assert "Unknown option" in stderr

    def test_total_steps_non_integer_fails(self, tmp_path):
        _make_images(tmp_path, 3)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--total-steps", "abc"], env=env)
        assert rc == 1
        assert "positive integer" in stderr

    def test_total_steps_missing_value_fails(self, tmp_path):
        _make_images(tmp_path, 3)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--total-steps"], env=env)
        assert rc == 1
        assert "positive integer" in stderr

    def test_max_splats_non_integer_fails(self, tmp_path):
        _make_images(tmp_path, 3)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--max-splats", "xyz"], env=env)
        assert rc == 1
        assert "positive integer" in stderr

    def test_max_splats_zero_fails(self, tmp_path):
        _make_images(tmp_path, 3)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--max-splats", "0"], env=env)
        assert rc == 1
        assert "greater than 0" in stderr


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------


class TestDependencyChecks:
    def test_no_brush_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        stub_dir = tmp_path / "empty_bin"
        stub_dir.mkdir()
        env = os.environ.copy()
        env["PATH"] = f"{stub_dir}:{os.defpath}"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 2
        assert "not found in PATH" in stderr

    def test_brush_bin_env_override(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_BIN"] = "nonexistent_brush_binary"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 2
        assert "not found in PATH" in stderr


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
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "No images found" in stderr

    def test_missing_sparse_dir_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "sparse/0 directory not found" in stderr

    def test_missing_cameras_bin_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        sparse_dir = tmp_path / "sparse" / "0"
        sparse_dir.mkdir(parents=True)
        (sparse_dir / "images.bin").write_text("fake")
        (sparse_dir / "points3D.bin").write_text("fake")
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "cameras.bin" in stderr

    def test_missing_images_bin_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        sparse_dir = tmp_path / "sparse" / "0"
        sparse_dir.mkdir(parents=True)
        (sparse_dir / "cameras.bin").write_text("fake")
        (sparse_dir / "points3D.bin").write_text("fake")
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "images.bin" in stderr

    def test_missing_points3d_bin_fails(self, tmp_path):
        _make_images(tmp_path, 5)
        sparse_dir = tmp_path / "sparse" / "0"
        sparse_dir.mkdir(parents=True)
        (sparse_dir / "cameras.bin").write_text("fake")
        (sparse_dir / "images.bin").write_text("fake")
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 3
        assert "points3D.bin" in stderr


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_default_success(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        ply = tmp_path / "scene.ply"
        assert ply.exists()
        assert ply.stat().st_size > 0
        assert "Stage C" in stdout
        assert "complete" in stdout.lower()

    def test_splat_count_extracted(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "Splat count:" in stdout

    def test_total_steps_flag_passed(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--total-steps", "5000"], env=env)
        assert rc == 0
        assert "total_steps=5000" in stdout

    def test_total_steps_env_var(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_TOTAL_STEPS"] = "7000"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "total_steps=7000" in stdout

    def test_max_splats_flag_passed(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--max-splats", "500000"], env=env)
        assert rc == 0
        assert "max_splats=500000" in stdout

    def test_max_splats_env_var(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_MAX_SPLATS"] = "800000"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "max_splats=800000" in stdout

    def test_max_splats_cli_overrides_env(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_MAX_SPLATS"] = "800000"
        rc, stdout, stderr = _run(
            tmp_path, extra_args=["--max-splats", "600000"], env=env
        )
        assert rc == 0
        assert "max_splats=600000" in stdout

    def test_max_splats_shown_in_header(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(tmp_path, extra_args=["--max-splats", "999"], env=env)
        assert rc == 0
        assert "Max splats:   999" in stdout


# ---------------------------------------------------------------------------
# Failure gates
# ---------------------------------------------------------------------------


class TestFailureGates:
    def test_brush_nonzero_exit(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_FAIL"] = "1"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 4
        assert "failed with exit code" in stderr

    def test_brush_writes_empty_ply(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        bin_dir = tmp_path / "stub_bin"
        bin_dir.mkdir()

        # Stub that writes an empty file to export-path/export-name
        stub = """#!/usr/bin/env bash
set -euo pipefail
EXPORT_DIR=""
EXPORT_NAME=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --export-path) EXPORT_DIR="$2"; shift 2 ;;
        --export-name) EXPORT_NAME="$2"; shift 2 ;;
        *) shift ;;
    esac
done
if [[ -z "$EXPORT_DIR" ]]; then
    echo "brush: --export-path required" >&2; exit 1
fi
if [[ -z "$EXPORT_NAME" ]]; then
    echo "brush: --export-name required" >&2; exit 1
fi
mkdir -p "$EXPORT_DIR"
touch "$EXPORT_DIR/$EXPORT_NAME"
"""
        brush_path = _write_stub(bin_dir, "brush", stub)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 4
        assert "empty" in stderr.lower()

    def test_brush_writes_no_file(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        bin_dir = tmp_path / "stub_bin"
        bin_dir.mkdir()

        # Stub that exits 0 but doesn't write scene.ply
        stub = """#!/usr/bin/env bash
set -euo pipefail
echo "brush: ran successfully but forgot export" >&2
exit 0
"""
        brush_path = _write_stub(bin_dir, "brush", stub)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 4
        assert "not created" in stderr.lower()


# ---------------------------------------------------------------------------
# Splat-count threshold warnings
# ---------------------------------------------------------------------------


class TestSplatThresholdWarnings:
    def test_critical_count_warns(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_SPLAT_COUNT"] = "12000000"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "will strain Bevy" in stderr

    def test_warning_count_warns(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_SPLAT_COUNT"] = "6000000"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "watch VRAM" in stderr

    def test_comfortable_count_no_warn(self, tmp_path):
        _make_images(tmp_path, 5)
        _make_sparse(tmp_path)
        env = _make_stub_env(tmp_path)
        env["BRUSH_SPLAT_COUNT"] = "1500000"
        rc, stdout, stderr = _run(tmp_path, env=env)
        assert rc == 0
        assert "will strain Bevy" not in stderr
        assert "watch VRAM" not in stderr


# ---------------------------------------------------------------------------
# PLY vertex counting
# ---------------------------------------------------------------------------


class TestPlyVertexCounting:
    def test_count_vertices_from_ply(self, tmp_path):
        """Verify the PLY header parse logic reliably counts vertices."""
        ply_path = tmp_path / "test.ply"
        ply_path.write_bytes(_ply_bytes(42))

        # Simulate what the count_ply_vertices function does in train_brush.sh
        with open(ply_path, 'rb') as f:
            chunk = f.read(4096)
        header_end = chunk.find(b'end_header')
        assert header_end != -1
        header = chunk[:header_end].decode('ascii', errors='replace')
        count = None
        for line in header.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == 'element' and parts[1] == 'vertex':
                count = int(parts[2])
                break
        assert count == 42

    def test_count_zero_vertices(self, tmp_path):
        ply_path = tmp_path / "zero.ply"
        ply_path.write_bytes(_ply_bytes(0))

        with open(ply_path, 'rb') as f:
            chunk = f.read(4096)
        header_end = chunk.find(b'end_header')
        header = chunk[:header_end].decode('ascii', errors='replace')
        count = None
        for line in header.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == 'element' and parts[1] == 'vertex':
                count = int(parts[2])
                break
        assert count == 0


# ---------------------------------------------------------------------------
# run_pipeline.sh integration — Stage C wiring
# ---------------------------------------------------------------------------

PIPELINE_SCRIPT = Path(__file__).resolve().parent.parent / "run_pipeline.sh"


class TestPipelineIntegration:
    """Test that run_pipeline.sh correctly wires Stage C training."""

    def test_stage_c_section_present(self):
        """run_pipeline.sh Stage C section is implemented, not a placeholder."""
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert "Stage C: Splat training" in pipeline_src
        assert "train_splatfacto.sh" in pipeline_src
        assert "train_brush.sh" in pipeline_src
        assert "scene.ply" in pipeline_src
        # Verify the old Stage C placeholder is gone (other stages may still have it)
        assert "--- Stage C: Splat training (subissue #109) ---" not in pipeline_src

    def test_error_when_train_brush_missing(self):
        """Pipeline source references the correct error message for missing script."""
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert 'train_brush.sh not found or not executable' in pipeline_src

    def test_post_stage_c_verification_in_pipeline(self):
        """Pipeline verifies scene.ply exists and is non-empty after Stage C."""
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert 'scene.ply is missing' in pipeline_src
        assert 'scene.ply is empty' in pipeline_src

    def test_train_brush_invoked_with_scene_dir(self):
        """Pipeline passes scene_dir to train_brush.sh as fallback."""
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert '"$SCRIPT_DIR/train_brush.sh" "$SCENE_DIR"' in pipeline_src

    def test_stage_c_invocation(self, tmp_path):
        """train_brush.sh is a valid executable script that produces scene.ply."""
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        _make_images(scene_dir, 3)
        _make_sparse(scene_dir)

        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 0
        ply = scene_dir / "scene.ply"
        assert ply.exists()
        assert ply.stat().st_size > 0
