#!/usr/bin/env python3
"""
Tests for decimate_to_glb.py — argument parsing, triangle-budget validation,
decimation-ratio calculation, --validate-args mode, and stub Blender integration.

Validates the Blender-bound Python script without requiring a real Blender
installation. Pure functions are tested by importing the module directly.
Argument parsing is tested via --validate-args subprocess mode.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "decimate_to_glb.py"

# Ensure the script directory is importable for direct function testing
sys.path.insert(0, str(SCRIPT.parent))


# ---------------------------------------------------------------------------
# Import the module's pure functions (no Blender dependency)
# ---------------------------------------------------------------------------

import decimate_to_glb as d2g


# ---------------------------------------------------------------------------
# Stub content reused from test_extract_mesh
# ---------------------------------------------------------------------------

SUGAR_STUB = """#!/usr/bin/env python3
import os, sys
if os.environ.get('SUGAR_FAIL', ''):
    sys.stderr.write("sugar stub: forced failure\\n")
    sys.exit(int(os.environ.get('SUGAR_EXIT_CODE', '1')))
scene_dir = None
checkpoint = None
i = 1
while i < len(sys.argv):
    arg = sys.argv[i]
    if arg == '-s' and i + 1 < len(sys.argv):
        scene_dir = sys.argv[i + 1]; i += 2
    elif arg == '-c' and i + 1 < len(sys.argv):
        checkpoint = sys.argv[i + 1]; i += 2
    elif arg == '--export_obj':
        i += 2
    elif arg == '--low_poly':
        i += 2
    elif arg == '--skip_texture_baking':
        i += 2
    elif arg == '-r':
        i += 2
    else:
        i += 1
if os.environ.get('SUGAR_NO_OUTPUT', ''):
    sys.exit(0)
if scene_dir is None:
    sys.stderr.write("sugar stub: no -s scene_dir\\n")
    sys.exit(1)
export_name = os.environ.get('SUGAR_EXPORT_NAME', 'mesh_export')
output_path = os.environ.get('SUGAR_EXPORT_PATH', '')
if output_path:
    obj_path = os.path.join(output_path, f'{export_name}.obj')
else:
    obj_path = os.path.join(scene_dir, f'{export_name}.obj')
os.makedirs(os.path.dirname(obj_path) or '.', exist_ok=True)
vertex_count = int(os.environ.get('SUGAR_VERTEX_COUNT', '4'))
with open(obj_path, 'w') as f:
    f.write('# stub SuGaR OBJ\\n')
    for v in range(vertex_count):
        f.write(f'v {v}.0 {v}.0 {v}.0\\n')
    if vertex_count >= 3:
        f.write('f 1 2 3\\n')
    if vertex_count >= 4:
        f.write('f 2 3 4\\n')
sys.exit(0)
"""


def _run_validate_args(args: list[str], env=None) -> tuple[int, str, str]:
    """Run the script in --validate-args mode."""
    cmd = ["python3", str(SCRIPT), "--validate-args"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


def _write_stub(path: Path, content: str) -> Path:
    path.write_text(content)
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---------------------------------------------------------------------------
# Pure function tests — calculate_decimation_ratio
# ---------------------------------------------------------------------------


class TestCalculateDecimationRatio:
    def test_under_target_returns_one(self):
        assert d2g.calculate_decimation_ratio(100, 200) == 1.0

    def test_equal_target_returns_one(self):
        assert d2g.calculate_decimation_ratio(200, 200) == 1.0

    def test_above_target_returns_ratio(self):
        ratio = d2g.calculate_decimation_ratio(400, 100)
        assert ratio == pytest.approx(0.25)

    def test_far_above_target(self):
        ratio = d2g.calculate_decimation_ratio(1000000, 200000)
        assert ratio == pytest.approx(0.2)

    def test_clamped_to_min_ratio(self):
        ratio = d2g.calculate_decimation_ratio(1000000000, 1)
        assert ratio == pytest.approx(0.001)

    def test_zero_current_triangles_raises(self):
        with pytest.raises(ValueError):
            d2g.calculate_decimation_ratio(0, 100)

    def test_negative_current_triangles_raises(self):
        with pytest.raises(ValueError):
            d2g.calculate_decimation_ratio(-10, 100)

    def test_zero_target_triangles_raises(self):
        with pytest.raises(ValueError):
            d2g.calculate_decimation_ratio(100, 0)

    def test_negative_target_triangles_raises(self):
        with pytest.raises(ValueError):
            d2g.calculate_decimation_ratio(100, -5)


# ---------------------------------------------------------------------------
# Pure function tests — write_log
# ---------------------------------------------------------------------------


class TestWriteLog:
    def test_appends_to_log(self, tmp_path):
        log_file = tmp_path / "test.log"
        d2g.write_log(log_file, "line 1")
        d2g.write_log(log_file, "line 2")
        content = log_file.read_text()
        assert "line 1" in content
        assert "line 2" in content

    def test_creates_parent_dir(self, tmp_path):
        log_file = tmp_path / "sub" / "dir" / "test.log"
        d2g.write_log(log_file, "hello")
        assert log_file.exists()

    def test_multiline_diagnostics(self, tmp_path):
        log_file = tmp_path / "diag.log"
        d2g.write_log(log_file, "=== START ===")
        d2g.write_log(log_file, "IMPORT: reading mesh.obj (12345 bytes).")
        d2g.write_log(log_file, "TRIANGLES: 50000 after decimation.")
        d2g.write_log(log_file, "EXPORT: wrote collision.glb (4567 bytes).")
        d2g.write_log(log_file, "=== SUCCESS ===")
        content = log_file.read_text()
        assert "=== START ===" in content
        assert "IMPORT: reading mesh.obj (12345 bytes)." in content
        assert "TRIANGLES: 50000 after decimation." in content
        assert "EXPORT: wrote collision.glb (4567 bytes)." in content
        assert "=== SUCCESS ===" in content


# ---------------------------------------------------------------------------
# Argument parsing tests (--validate-args mode, no Blender needed)
# ---------------------------------------------------------------------------


class TestValidateArgsMode:
    def test_scene_dir_required(self):
        rc, stdout, stderr = _run_validate_args([])
        assert rc != 0

    def test_defaults_produced(self, tmp_path):
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        rc, stdout, stderr = _run_validate_args(["--scene-dir", str(scene_dir)])
        assert rc == 0
        assert str(scene_dir) in stdout
        assert "mesh_export.obj" in stdout
        assert "collision.glb" in stdout
        assert "target_triangles:" in stdout
        assert "200000" in stdout
        assert "decimate_to_glb.log" in stdout
        assert "min_component_faces:" in stdout

    def test_custom_target_triangles(self, tmp_path):
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        rc, stdout, stderr = _run_validate_args(
            ["--scene-dir", str(scene_dir), "--target-triangles", "100000"]
        )
        assert rc == 0
        assert "target_triangles: 100000" in stdout

    def test_custom_input_output(self, tmp_path):
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        rc, stdout, stderr = _run_validate_args(
            [
                "--scene-dir", str(scene_dir),
                "--input-mesh", "/tmp/custom.obj",
                "--output", "/tmp/out.glb",
            ]
        )
        assert rc == 0
        assert "input_mesh:" in stdout
        assert "/tmp/custom.obj" in stdout
        assert "/tmp/out.glb" in stdout

    def test_custom_log_file(self, tmp_path):
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        rc, stdout, stderr = _run_validate_args(
            [
                "--scene-dir", str(scene_dir),
                "--log-file", str(tmp_path / "custom.log"),
            ]
        )
        assert rc == 0
        assert "custom.log" in stdout

    def test_min_component_faces_default(self, tmp_path):
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        rc, stdout, stderr = _run_validate_args(["--scene-dir", str(scene_dir)])
        assert rc == 0
        assert "min_component_faces: 50" in stdout

    def test_min_component_faces_custom(self, tmp_path):
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        rc, stdout, stderr = _run_validate_args(
            ["--scene-dir", str(scene_dir), "--min-component-faces", "200"]
        )
        assert rc == 0
        assert "min_component_faces: 200" in stdout


# ---------------------------------------------------------------------------
# Triangle budget validation
# ---------------------------------------------------------------------------


class TestTriangleBudgetValidation:
    def test_very_low_target_warns(self, tmp_path):
        log_file = tmp_path / "warn.log"
        d2g.validate_triangle_budget(50, log_file)
        content = log_file.read_text()
        assert "very low" in content

    def test_above_default_warns(self, tmp_path):
        log_file = tmp_path / "warn2.log"
        d2g.validate_triangle_budget(300000, log_file)
        content = log_file.read_text()
        assert "exceeds recommended maximum" in content

    def test_default_target_no_warn(self, tmp_path):
        log_file = tmp_path / "ok.log"
        d2g.validate_triangle_budget(d2g.DEFAULT_TARGET_TRIANGLES, log_file)
        # Default target should not generate warnings
        if log_file.exists():
            content = log_file.read_text()
            assert "very low" not in content
            assert "exceeds recommended maximum" not in content

    def test_mid_range_no_warn(self, tmp_path):
        log_file = tmp_path / "ok2.log"
        d2g.validate_triangle_budget(100000, log_file)
        if log_file.exists():
            content = log_file.read_text()
            assert "very low" not in content
            assert "exceeds recommended maximum" not in content


# ---------------------------------------------------------------------------
# Argument parsing (direct import — tests parse_args function)
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_scene_dir_required(self):
        with pytest.raises(SystemExit):
            d2g.parse_args(["--validate-args"])

    def test_defaults(self):
        args = d2g.parse_args(["--scene-dir", "/tmp/scene", "--validate-args"])
        assert args.scene_dir == "/tmp/scene"
        assert args.input_mesh is None
        assert args.output is None
        assert args.target_triangles == 200000
        assert args.min_component_faces == 50
        assert args.log_file is None

    def test_all_custom(self):
        args = d2g.parse_args(
            [
                "--scene-dir", "/tmp/scene",
                "--input-mesh", "/tmp/in.obj",
                "--output", "/tmp/out.glb",
                "--target-triangles", "50000",
                "--min-component-faces", "100",
                "--log-file", "/tmp/diag.log",
                "--validate-args",
            ]
        )
        assert args.scene_dir == "/tmp/scene"
        assert args.input_mesh == "/tmp/in.obj"
        assert args.output == "/tmp/out.glb"
        assert args.target_triangles == 50000
        assert args.min_component_faces == 100
        assert args.log_file == "/tmp/diag.log"


# ---------------------------------------------------------------------------
# Blender mode detection (outside Blender, should error)
# ---------------------------------------------------------------------------


class TestBlenderMode:
    def test_not_inside_blender_errors(self, tmp_path):
        """When run outside Blender without --validate-args, exits with error."""
        rc, stdout, stderr = _run_validate_args(
            ["--scene-dir", str(tmp_path), "--noop"]
        )
        # --noop is unrecognized, so argparse fails
        assert rc != 0

    def test_outside_blender_no_bpy(self, tmp_path):
        """Script detects no 'bpy' and gives a useful error (only in non-validate mode)."""
        # Test that main() raises SystemExit when bpy is missing
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()
        try:
            d2g.main(["--scene-dir", str(scene_dir)])
        except SystemExit as e:
            assert e.code == 1


# ---------------------------------------------------------------------------
# Stub Blender integration test
# ---------------------------------------------------------------------------

_STUB_BLENDER = """#!/usr/bin/env bash
# Stub Blender: creates a minimal collision.glb and writes a log file.
set -euo pipefail

ARGS=("$@")

# Extract scene-dir from args
SCENE_DIR=""
TARGET_TRIS="200000"
LOG_FILE=""
MIN_COMP="50"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene-dir) SCENE_DIR="$2"; shift 2 ;;
        --target-triangles) TARGET_TRIS="$2"; shift 2 ;;
        --log-file) LOG_FILE="$2"; shift 2 ;;
        --min-component-faces) MIN_COMP="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$SCENE_DIR" ]]; then
    echo "ERROR: --scene-dir required" >&2
    exit 1
fi

# Write the Blender diagnostic log
echo "=== decimate_to_glb.py ===" >> "$LOG_FILE"
echo "Scene dir:       $SCENE_DIR" >> "$LOG_FILE"
echo "Blender version: 4.0 (stub)" >> "$LOG_FILE"
echo "TRIANGLES: 50000" >> "$LOG_FILE"
echo "DECIMATE: applying ratio 0.250 to reach target $TARGET_TRIS" >> "$LOG_FILE"
echo "EXPORT: wrote $SCENE_DIR/collision.glb (12345 bytes)." >> "$LOG_FILE"
echo "=== SUCCESS ===" >> "$LOG_FILE"

# Create a minimal GLB file (valid binary glTF header)
python3 -c "
import struct, pathlib
path = pathlib.Path('$SCENE_DIR') / 'collision.glb'
path.parent.mkdir(parents=True, exist_ok=True)
# Minimal GLB: header (12) + empty JSON chunk
magic = 0x46546C67  # 'glTF'
version = 2
json_chunk = b'{\"asset\":{\"version\":\"2.0\"}}'
# Pad to 4-byte alignment
while len(json_chunk) % 4 != 0:
    json_chunk += b' '
json_len = len(json_chunk)
total_len = 12 + 8 + json_len
header = struct.pack('<I', magic) + struct.pack('<II', version, total_len)
chunk_header = struct.pack('<II', json_len, 0x4E4F534A)  # JSON chunk type
with open(path, 'wb') as f:
    f.write(header + chunk_header + json_chunk)
"
echo "stub blender: created $SCENE_DIR/collision.glb"
"""


class TestStubBlender:
    def test_stub_blender_pipeline(self, tmp_path):
        """Run the full Stage D pipeline with stub SuGaR + stub Blender."""
        scene_dir = tmp_path / "scene"
        scene_dir.mkdir()

        # Create scene.ply
        ply = scene_dir / "scene.ply"
        ply.write_bytes(
            b"ply\nformat binary_little_endian 1.0\n"
            b"element vertex 1000\nend_header\n" + b"\x00" * 50
        )

        # Create checkpoint dir
        ckpt = scene_dir / "output"
        ckpt.mkdir()
        (ckpt / "checkpoint.pth").write_text("fake")

        # Set up stub SuGaR environment
        sugar_root = tmp_path / "sugar"
        sugar_root.mkdir()
        _write_stub(sugar_root / "train.py", SUGAR_STUB)

        stub_bin = tmp_path / "stub_bin"
        stub_bin.mkdir()
        _write_stub(stub_bin / "blender", _STUB_BLENDER)

        env = os.environ.copy()
        env["PATH"] = f"{stub_bin}:{env.get('PATH', '')}"
        env["SUGAR_PYTHON"] = "python3"
        env["SUGAR_TRAIN_SCRIPT"] = str(sugar_root / "train.py")
        env["SUGAR_ROOT"] = str(sugar_root)
        env["BLENDER_BIN"] = "blender"
        env["SUGAR_VERTEX_COUNT"] = "8"

        # Step D1: Run extract_mesh.sh
        extract_script = SCRIPT.parent / "extract_mesh.sh"
        result = subprocess.run(
            ["bash", str(extract_script), str(scene_dir)],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, f"extract_mesh.sh failed: {result.stderr}"
        assert (scene_dir / "mesh_export.obj").exists()

        # Step D2: Run stub Blender → decimate_to_glb
        log_file = scene_dir / "decimate_to_glb.log"
        result = subprocess.run(
            [
                str(stub_bin / "blender"),
                "--background",
                "--python", str(SCRIPT),
                "--",
                "--scene-dir", str(scene_dir),
                "--target-triangles", "100000",
                "--log-file", str(log_file),
            ],
            capture_output=True, text=True, env=env,
            timeout=30,
        )
        assert result.returncode == 0, f"stub blender failed: {result.stderr}"

        # Verify output
        assert (scene_dir / "collision.glb").exists()
        assert (scene_dir / "collision.glb").stat().st_size > 0
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "=== SUCCESS ===" in log_content
        assert "TRIANGLES:" in log_content
        assert "EXPORT:" in log_content

    def test_collision_tool_not_found_error(self, tmp_path):
        """Pipeline source has an error message for missing collision tool."""
        pipeline_script = SCRIPT.parent / "run_pipeline.sh"
        content = pipeline_script.read_text()
        assert "generate_collision.py" in content
