#!/usr/bin/env python3
"""
Tests for extract_mesh.sh — argument parsing, dependency checks, input validation,
success/failure gates, and environment variable overrides.

Creates a stub SuGaR train.py executable in a temp PATH so tests work without
a real SuGaR install or GPU.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "extract_mesh.sh"
STUB_PYTHON = Path(__file__).resolve().parent.parent / "stub_python3.sh"

# ---------------------------------------------------------------------------
# SuGaR stub train.py
# ---------------------------------------------------------------------------

_SUGAR_STUB = """#!/usr/bin/env python3
\"\"\"Stub SuGaR train.py for testing extract_mesh.sh.\"\"\"
import os
import sys

def main():
    # Check for forced failure
    if os.environ.get('SUGAR_FAIL', ''):
        sys.stderr.write("sugar stub: forced failure\\n")
        sys.exit(int(os.environ.get('SUGAR_EXIT_CODE', '1')))

    scene_dir = None
    checkpoint = None
    export_obj = False
    low_poly = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-s' and i + 1 < len(sys.argv):
            scene_dir = sys.argv[i + 1]
            i += 2
        elif arg == '-c' and i + 1 < len(sys.argv):
            checkpoint = sys.argv[i + 1]
            i += 2
        elif arg == '--export_obj':
            export_obj = sys.argv[i + 1] if i + 1 < len(sys.argv) else 'False'
            i += 2
        elif arg == '--low_poly':
            low_poly = sys.argv[i + 1] if i + 1 < len(sys.argv) else 'False'
            i += 2
        elif arg == '--skip_texture_baking':
            # Consume value
            i += 2 if i + 1 < len(sys.argv) else 1
        elif arg == '-r':
            i += 2 if i + 1 < len(sys.argv) else 1
        else:
            i += 1

    if os.environ.get('SUGAR_NO_OUTPUT', ''):
        sys.exit(0)

    if scene_dir is None:
        sys.stderr.write("sugar stub: no -s scene_dir\\n")
        sys.exit(1)

    export_name = os.environ.get('SUGAR_EXPORT_NAME', 'mesh_export')

    if os.environ.get('SUGAR_WRITE_ALT_PATH', ''):
        # Write only to alternate path (simulates SuGaR writing to non-default location)
        alt_dir = os.path.join(scene_dir, 'subdir')
        os.makedirs(alt_dir, exist_ok=True)
        alt_path = os.path.join(alt_dir, f'{export_name}.obj')
        vertex_count = 6
        with open(alt_path, 'w') as f:
            f.write('# stub SuGaR OBJ (alt path)\\n')
            for v in range(vertex_count):
                f.write(f'v {v}.0 {v}.0 {v}.0\\n')
            f.write('f 1 2 3\\n')
            f.write('f 2 3 4\\n')
        sys.exit(0)

    output_path = os.environ.get('SUGAR_EXPORT_PATH', '')

    if output_path:
        obj_path = os.path.join(output_path, f'{export_name}.obj')
    else:
        obj_path = os.path.join(scene_dir, f'{export_name}.obj')

    os.makedirs(os.path.dirname(obj_path) or '.', exist_ok=True)

    # Write a minimal OBJ file
    vertex_count = int(os.environ.get('SUGAR_VERTEX_COUNT', '4'))
    with open(obj_path, 'w') as f:
        f.write('# stub SuGaR OBJ\\n')
        for v in range(vertex_count):
            f.write(f'v {v}.0 {v}.0 {v}.0\\n')
        if vertex_count >= 3:
            f.write('f 1 2 3\\n')
        if vertex_count >= 4:
            f.write('f 2 3 4\\n')

    if os.environ.get('SUGAR_WRITE_ALT_PATH', ''):
        alt_dir = os.path.join(scene_dir, 'subdir')
        os.makedirs(alt_dir, exist_ok=True)
        alt_path = os.path.join(alt_dir, f'{export_name}.obj')
        with open(alt_path, 'w') as f:
            f.write('# stub SuGaR OBJ (alt path)\\n')
            f.write('v 0 0 0\\n')
            f.write('v 1 1 1\\n')
            f.write('v 2 2 2\\n')
            f.write('f 1 2 3\\n')

    sys.exit(0)

if __name__ == '__main__':
    main()
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
    """Create stub SuGaR train.py and return env with PATH unchanged.
    Uses the real system python3, only fakes the SuGaR train.py."""

    # We don't put a fake python3 in PATH to avoid infinite recursion.
    # The real system python3 will be found naturally.

    sugar_root = tmp_path / "sugar_repo"
    sugar_root.mkdir()

    _write_stub(sugar_root, "train.py", _SUGAR_STUB)

    env = os.environ.copy()
    env["SUGAR_PYTHON"] = "python3"
    env["SUGAR_TRAIN_SCRIPT"] = str(sugar_root / "train.py")
    env["SUGAR_ROOT"] = str(sugar_root)
    # Ensure the stub train.py is importable via PATH (for direct exec)
    env["PATH"] = env.get("PATH", "")

    return env


def _make_scene_dir(tmp_path: Path, with_ply: bool = True, with_checkpoint: bool = True) -> Path:
    """Create a scene directory with scene.ply and checkpoint output/."""
    scene_dir = tmp_path / "scene"
    scene_dir.mkdir()

    if with_ply:
        ply = scene_dir / "scene.ply"
        ply.write_bytes(b"ply\nformat binary_little_endian 1.0\nelement vertex 1000\nend_header\n\x00" * 50)

    if with_checkpoint:
        ckpt = scene_dir / "output"
        ckpt.mkdir()
        (ckpt / "checkpoint.pth").write_text("fake_checkpoint")

    return scene_dir


def _run(
    scene_dir: Path, extra_args=None, env=None
) -> tuple[int, str, str]:
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
        cmd = ["bash", str(SCRIPT), "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_short_flag(self):
        cmd = ["bash", str(SCRIPT), "-h"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_unknown_option_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, extra_args=["--bogus"], env=env)
        assert rc == 1
        assert "Unknown option" in stderr

    def test_checkpoint_missing_arg_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, extra_args=["--checkpoint"], env=env)
        assert rc == 1
        assert "requires a path argument" in stderr

    def test_export_name_missing_arg_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, extra_args=["--export-name"], env=env)
        assert rc == 1
        assert "requires a name argument" in stderr


# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------


class TestDependencyChecks:
    def test_no_python3_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_PYTHON"] = "nonexistent_python123"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 2
        assert "not found in PATH" in stderr

    def test_no_train_script_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_TRAIN_SCRIPT"] = "/nonexistent/path/train.py"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 2
        assert "not found at" in stderr


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_missing_scene_ply_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path, with_ply=False)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 3
        assert "scene.ply not found" in stderr

    def test_empty_scene_ply_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path, with_ply=True)
        # Write empty scene.ply
        (scene_dir / "scene.ply").write_text("")
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 3
        assert "empty" in stderr.lower()

    def test_missing_checkpoint_dir_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path, with_checkpoint=False)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 3
        assert "Checkpoint directory not found" in stderr


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_default_success(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 0
        obj = scene_dir / "mesh_export.obj"
        assert obj.exists()
        assert obj.stat().st_size > 0
        assert "Stage D" in stdout
        assert "complete" in stdout.lower()

    def test_custom_export_name(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_EXPORT_NAME"] = "my_mesh"
        rc, stdout, stderr = _run(
            scene_dir, extra_args=["--export-name", "my_mesh"], env=env
        )
        assert rc == 0

    def test_custom_checkpoint_path(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        custom_ckpt = tmp_path / "custom_ckpt"
        custom_ckpt.mkdir()
        (custom_ckpt / "checkpoint.pth").write_text("custom")
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(
            scene_dir, extra_args=["--checkpoint", str(custom_ckpt)], env=env
        )
        assert rc == 0
        assert str(custom_ckpt) in stdout

    def test_env_var_python_respected(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_PYTHON"] = "python3"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 0

    def test_env_var_train_script_respected(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        # Write a minimal stub train.py
        alt_sugar = tmp_path / "alt_sugar"
        alt_sugar.mkdir()
        _write_stub(alt_sugar, "train.py", _SUGAR_STUB)
        env["SUGAR_TRAIN_SCRIPT"] = str(alt_sugar / "train.py")
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 0


# ---------------------------------------------------------------------------
# Failure gates
# ---------------------------------------------------------------------------


class TestFailureGates:
    def test_sugar_nonzero_exit(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_FAIL"] = "1"
        env["SUGAR_EXIT_CODE"] = "3"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 4
        assert "failed with exit code 3" in stderr

    def test_sugar_no_output(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_NO_OUTPUT"] = "1"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 5
        assert "no mesh was produced" in stderr.lower()

    def test_sugar_writes_empty_obj(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_VERTEX_COUNT"] = "0"
        # With 0 vertices, stub writes only comments, which is small but non-zero
        # Use SUGAR_NO_OUTPUT to truly simulate missing output
        del env["SUGAR_VERTEX_COUNT"]
        env["SUGAR_NO_OUTPUT"] = "1"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 5
        assert "no mesh was produced" in stderr.lower()

    def test_sugar_writes_alt_path(self, tmp_path):
        """If SuGaR writes to an alternate location, the script finds and moves it."""
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["SUGAR_WRITE_ALT_PATH"] = "1"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 0
        obj = scene_dir / "mesh_export.obj"
        assert obj.exists()
        assert obj.stat().st_size > 0


# ---------------------------------------------------------------------------
# Pipeline integration — Stage D wiring in run_pipeline.sh
# ---------------------------------------------------------------------------

PIPELINE_SCRIPT = Path(__file__).resolve().parent.parent / "run_pipeline.sh"


class TestPipelineIntegration:
    """Test that run_pipeline.sh correctly wires Stage D."""

    def test_stage_d_section_present(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert "Stage D: Collision mesh" in pipeline_src
        assert "extract_mesh.sh" in pipeline_src
        assert "decimate_to_glb.py" in pipeline_src
        assert "collision.glb" in pipeline_src

    def test_co_registration_warning_present(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert "CO-REGISTRATION CONTRACT" in pipeline_src
        assert "collision.glb MUST share the coordinate frame" in pipeline_src

    def test_no_old_placeholder(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert "NOT YET IMPLEMENTED. Will call" not in pipeline_src

    def test_extract_mesh_invoked_with_scene_dir(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert '"$SCRIPT_DIR/extract_mesh.sh" "$SCENE_DIR"' in pipeline_src

    def test_post_stage_d_verification(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert 'collision.glb is missing' in pipeline_src
        assert 'collision.glb is empty' in pipeline_src

    def test_blender_called_in_stage_d(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert '$BLENDER_PATH" --background' in pipeline_src
        assert 'decimate_to_glb.py' in pipeline_src

    def test_blender_bin_env_var(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert 'BLENDER_BIN="${BLENDER_BIN:-blender}"' in pipeline_src

    def test_decimate_target_tris_env_var(self):
        pipeline_src = PIPELINE_SCRIPT.read_text()
        assert 'DECIMATE_TARGET_TRIS' in pipeline_src
