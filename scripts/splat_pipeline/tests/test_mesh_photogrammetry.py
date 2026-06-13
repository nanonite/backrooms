#!/usr/bin/env python3
"""Tests for mesh_photogrammetry.sh mesher selection."""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "mesh_photogrammetry.sh"

_COLMAP_STUB = r"""#!/bin/bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    cat <<'EOF'
image_undistorter
patch_match_stereo
stereo_fusion
poisson_mesher
EOF
    if [[ -z "${COLMAP_NO_DELAUNAY:-}" ]]; then
        echo "delaunay_mesher"
    fi
    exit 0
fi

echo "$*" >> "${COLMAP_LOG:?}"

value_after() {
    local key="$1"
    shift
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == "$key" ]]; then
            echo "${2:-}"
            return 0
        fi
        shift
    done
    return 1
}

case "$1" in
    feature_extractor)
        db_path="$(value_after --database_path "$@")"
        python3 - "$db_path" <<'PYEOF'
import sqlite3
import sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("CREATE TABLE IF NOT EXISTS images (image_id INTEGER PRIMARY KEY, name TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS two_view_geometries (pair_id INTEGER, rows INTEGER)")
conn.commit()
conn.close()
PYEOF
        ;;
    exhaustive_matcher)
        ;;
    image_undistorter)
        dense_dir="$(value_after --output_path "$@")"
        mkdir -p "$dense_dir/stereo"
        ;;
    patch_match_stereo)
        ;;
    stereo_fusion)
        output_path="$(value_after --output_path "$@")"
        python3 - "$output_path" <<'PYEOF'
import struct
import sys
with open(sys.argv[1], "wb") as handle:
    handle.write(b"ply\n")
    handle.write(b"format binary_little_endian 1.0\n")
    handle.write(b"element vertex 1\n")
    handle.write(b"property float x\nproperty float y\nproperty float z\n")
    handle.write(b"property float nx\nproperty float ny\nproperty float nz\n")
    handle.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\n")
    handle.write(b"end_header\n")
    handle.write(struct.pack("<ffffffBBB", 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 255, 255, 255))
PYEOF
        ;;
    delaunay_mesher|poisson_mesher)
        output_path="$(value_after --output_path "$@")"
        printf 'ply\n' > "$output_path"
        ;;
    *)
        echo "colmap stub: unknown command $1" >&2
        exit 1
        ;;
esac
"""

_BLENDER_STUB = r"""#!/bin/bash
set -euo pipefail
scene_dir=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene-dir)
            scene_dir="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done
if [[ -z "$scene_dir" ]]; then
    echo "blender stub: missing --scene-dir" >&2
    exit 1
fi
printf 'glb' > "$scene_dir/scene.glb"
printf 'identity\n' > "$scene_dir/scene_transform.txt"
"""


def _make_executable(path: Path) -> None:
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write_stub(bin_dir: Path, name: str, content: str) -> Path:
    path = bin_dir / name
    path.write_text(content)
    _make_executable(path)
    return path


def _make_stub_env(tmp_path: Path) -> dict:
    bin_dir = tmp_path / "stub_bin"
    bin_dir.mkdir()
    _write_stub(bin_dir, "colmap", _COLMAP_STUB)
    blender_bin = _write_stub(bin_dir, "blender", _BLENDER_STUB)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["BLENDER_BIN"] = str(blender_bin)
    env["COLMAP_LOG"] = str(tmp_path / "colmap.log")
    return env


def _make_scene_dir(tmp_path: Path) -> Path:
    scene_dir = tmp_path / "scene"
    (scene_dir / "images").mkdir(parents=True)
    (scene_dir / "images/frame_0001.jpg").write_text("fake image")
    sparse_dir = scene_dir / "sparse/0"
    sparse_dir.mkdir(parents=True)
    (sparse_dir / "cameras.bin").write_bytes(b"fake cameras")
    return scene_dir


def _run(scene_dir: Path, extra_args=None, env=None) -> tuple[int, str, str]:
    cmd = ["bash", str(SCRIPT), str(scene_dir)]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


def _colmap_log(env: dict) -> str:
    return Path(env["COLMAP_LOG"]).read_text()


class TestUsage:
    def test_help_lists_mesher_option(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "--mesher delaunay" in result.stdout
        assert "--mesher poisson" in result.stdout

    def test_invalid_mesher_fails(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, extra_args=["--mesher", "bad"], env=env)
        assert rc == 1
        assert "--mesher expects" in stderr


class TestColmapMesherSelection:
    def test_default_uses_delaunay_mesher(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 0, stderr
        log = _colmap_log(env)
        assert "delaunay_mesher" in log
        assert "poisson_mesher" not in log
        assert "Mesher:   delaunay" in stdout

    def test_poisson_flag_keeps_previous_mesher(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        rc, stdout, stderr = _run(scene_dir, extra_args=["--mesher", "poisson"], env=env)
        assert rc == 0, stderr
        log = _colmap_log(env)
        assert "poisson_mesher" in log
        assert "delaunay_mesher" not in log
        assert "Mesher:   poisson" in stdout

    def test_missing_delaunay_routes_to_meshroom_escalation(self, tmp_path):
        scene_dir = _make_scene_dir(tmp_path)
        env = _make_stub_env(tmp_path)
        env["COLMAP_NO_DELAUNAY"] = "1"
        rc, stdout, stderr = _run(scene_dir, env=env)
        assert rc == 2
        assert "delaunay_mesher" in stderr
        assert "#71 Meshroom" in stderr
