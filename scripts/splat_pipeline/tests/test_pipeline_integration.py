"""
Integration test for run_pipeline.sh — end-to-end execution from the repository root.

This test verifies that the pipeline can actually execute (not just string-match
its source) by running it against a real scene directory with stubbed externals.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_pipeline_integration.py -v
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PIPELINE_SCRIPT = REPO_ROOT / "scripts" / "splat_pipeline" / "run_pipeline.sh"


def _make_executable(path: Path) -> None:
    st = path.stat()
    path.chmod(st.st_mode | 0o755)


def _write_stub(bin_dir: Path, name: str, content: str) -> Path:
    path = bin_dir / name
    path.write_text(content)
    _make_executable(path)
    return path


def _make_stub_env(tmp_path: Path) -> tuple[dict, Path]:
    """Create stub executables in a temp bin dir and return (env, stub_script_dir).

    The stub_script_dir contains copies of all pipeline scripts with stubbed
    externals, so run_pipeline.sh can be invoked with SCRIPT_DIR pointing at it.
    """
    bin_dir = tmp_path / "stub_bin"
    bin_dir.mkdir()

    # Stub validate_input.py — simulate a passing validation
    _write_stub(bin_dir, "validate_input.py", """#!/usr/bin/env python3
import sys
print("File:     test.mp4")
print("Codec:    h264")
print("Res:      1920x1080")
print("FPS:      30.0")
print("Duration: 10.0s")
print("Frames:   300")
print()
print("Hard checks passed.")
sys.exit(0)
""")

    # Stub capture_gate.py — write a minimal gate report
    _write_stub(bin_dir, "capture_gate.py", """#!/usr/bin/env python3
import json, sys, os
report = {
    "metadata": {"path": "test.mp4", "width": 1920, "height": 1080, "fps": 30.0, "duration_seconds": 10.0, "frame_count": 300},
    "selection": {"selected": list(range(1, 16)), "selected_count": 15, "eligible": 20, "excluded_by_reason": {}},
    "verdict": {"status": "accepted", "findings": [], "limits": [], "notes": []},
    "scan": {"analysis_size": {"width": 640, "height": 360, "scale": 0.33}, "decode": {"probe": {"retained": 10, "visited": 10, "seconds": 1.0, "reason": "ok"}, "candidates": {"retained": 20, "clip_frames": 100, "retained_fraction": 0.2, "visited": 50, "seconds": 2.0}, "burst_frames_decoded": 5}, "bursts": {"median_residual_fraction": 0.01, "p90_hot_block_fraction": 0.02}, "parallax_gap": 5, "motion_px_per_frame": 10.0, "stride": 5, "seconds": 3.0},
    "coverage": {"path_length_widths": 5.0, "retained_path_length_widths": 4.0, "viewpoint_bins": 10, "selected_count": 15, "distinct_directions": 3, "selected_span_seconds": 5.0, "clip_span_seconds": 10.0, "span_fraction": 0.5},
    "consistency": {"classification": "consistent", "evidence": "no cuts"},
    "matching": {"strategy": "sequential", "pairs": 15, "exhaustive_pairs": 105, "reduction_factor": 7.0, "reason": "test", "unmatched_notes": []},
    "resource_estimate": {"frames": 15, "source_resolution": "1920x1080", "frame_files_bytes": 1000000, "database_bytes": 500000, "sparse_model_bytes": 200000, "total_disk_bytes": 1700000, "matching_pairs": 15, "matching_seconds": 60.0, "sampling_seconds": 3.0},
    "resource_verdict": {"fits": True, "free_disk_bytes": 1000000000, "free_ram_bytes": 1000000000, "blockers": [], "actions": []},
    "budget": {"target_frames": 150, "max_candidates": 240, "analysis_max_pixels": 230400, "max_sample_seconds": 120, "min_shift_fraction": 0.05, "cut_distance_limit": 0.3, "sequential_window": 5, "retrieval_keyframes": 10},
    "stage": "scanned",
    "seconds": 3.0
}
json.dump(report, open(sys.argv[sys.argv.index('--json') + 1], 'w'))
sys.exit(0)
""")

    # Stub sample_frames.py — write a few fake frames
    _write_stub(bin_dir, "sample_frames.py", """#!/usr/bin/env python3
import sys, os
out_dir = sys.argv[sys.argv.index('--out') + 1]
os.makedirs(out_dir, exist_ok=True)
for i in range(1, 16):
    with open(os.path.join(out_dir, f'frame_{i:04d}.jpg'), 'w') as f:
        f.write(f'fake_image_{i}')
sys.exit(0)
""")

    # Stub pose_colmap.sh — create sparse/0/ with dummy files
    _write_stub(bin_dir, "pose_colmap.sh", """#!/usr/bin/env bash
set -euo pipefail
SCENE_DIR="$1"
mkdir -p "$SCENE_DIR/sparse/0"
echo "dummy" > "$SCENE_DIR/sparse/0/cameras.bin"
echo "dummy" > "$SCENE_DIR/sparse/0/images.bin"
echo "dummy" > "$SCENE_DIR/sparse/0/points3D.bin"
exit 0
""")

    # Stub train_splatfacto.sh — create a minimal scene.ply
    _write_stub(bin_dir, "train_splatfacto.sh", """#!/usr/bin/env bash
set -euo pipefail
SCENE_DIR="$1"
cat > "$SCENE_DIR/scene.ply" << 'PLYEOF'
ply
format binary_little_endian 1.0
element vertex 100
property float x
property float y
property float z
end_header
PLYEOF
mkdir -p "$SCENE_DIR/splatfacto_output"
echo '{"transform": [[1,0,0,0],[0,1,0,0],[0,0,1,0]]}' > "$SCENE_DIR/splatfacto_output/dataparser_transforms.json"
exit 0
""")

    # Stub measure_splat_frame.py — create a minimal alignment manifest
    _write_stub(bin_dir, "measure_splat_frame.py", """#!/usr/bin/env python3
import json, sys
out = sys.argv[sys.argv.index('--out') + 1]
manifest = {
    "schema_version": 2,
    "scene_id": "test_scene",
    "ply_to_world": {
        "basis_columns": [[1,0,0],[0,1,0],[0,0,1]],
        "metres_per_unit": 1.0,
        "origin_ply_units": [0,0,0],
        "frame_name": "test",
        "up_axis": "y",
        "up_sign": 1,
        "handedness": "right"
    },
    "scale_reference": {"kind": "chosen", "quantity": "test", "raw_units": 1.0, "raw_units_spread": 0.01, "target_metres": 2.4, "reason": "test"},
    "automatic_transforms": [],
    "landmarks": {"floor": [0,0,0], "ceiling": [0,2.4,0], "room_centre": [0,1.2,0]},
    "collider": {"min_corner": [-5,0,-5], "max_corner": [5,2.4,5], "floor_height": 0.0, "ceiling_height": 2.4, "derivation": "test"},
    "splat_bounds": {"observed_min": [-5,0,-5], "observed_max": [5,2.4,5], "core_min": [-5,0,-5], "core_max": [5,2.4,5], "full_min": [-5,0,-5], "full_max": [5,2.4,5], "splat_count": 100},
    "cameras": {"count": 10, "world_min": [-1,1,0], "world_max": [1,1,3], "height_min_m": 1.0, "height_mean_m": 1.5, "height_max_m": 2.0, "source": "test"},
    "spawn": [0, 0.5, 0],
    "spawn_clearance_m": 0.5,
    "asset": {"resource_path": "res://assets/test/scene.ply", "source_path": "test.ply", "md5": "abc123", "splat_count": 100, "ply_header": {"generated": "test", "vertical": "Axis: y"}, "builder_centroid_ply": [0,0,0], "up_axis_evidence": {"colmap_up": [0,1,0], "ply_frame_up": [0,1,0], "principal_axis": "y", "principal_share": 1.0, "registered_images": 10, "method": "test"}},
    "capture": {"footage_kind": "synthetic", "video": "test.mp4", "colmap_model": "test", "nerfstudio_dataparser_transforms": "test", "core_window_splats": 50, "core_bounds_ply_units": [[-1,-1,-1],[1,1,1]], "walls_measured": False, "width_note": "test"},
    "rejected_scales": [],
    "notes": "test"
}
json.dump(manifest, open(out, 'w'))
sys.exit(0)
""")

    # Stub generate_collision.py — create a minimal collision.glb
    _write_stub(bin_dir, "generate_collision.py", """#!/usr/bin/env python3
import sys, os, json
out_dir = sys.argv[sys.argv.index('--out') + 1]
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, 'collision.glb'), 'wb') as f:
    f.write(b'glTF\\x02\\x00\\x00\\x00' + b'\\x00' * 100)
json.dump({"header": {"version": 1, "generator": "test", "resolution": 0.05, "grid_min": [0,0,0], "grid_max": [1,1,1], "grid_shape": [20,20,20], "tree_depth": 1, "node_count": 1, "num_mixed_leaves": 0}}, open(os.path.join(out_dir, 'voxel.json'), 'w'))
sys.exit(0)
""")

    # Stub traversal_plan.py — create a minimal traversal manifest
    _write_stub(bin_dir, "traversal_plan.py", """#!/usr/bin/env python3
import json, sys
out = sys.argv[sys.argv.index('--out') + 1]
plan = {"route": [], "probes": [], "spawn": [0, 0.5, 0], "tolerances": {}}
json.dump(plan, open(out, 'w'))
sys.exit(0)
""")

    # Stub stage_godot.sh — create the staged assets
    _write_stub(bin_dir, "stage_godot.sh", """#!/usr/bin/env bash
set -euo pipefail
SCENE_DIR="$1"
SCENE_NAME="$(basename "$SCENE_DIR")"
DEST_DIR="$SCENE_DIR/../godot_assets/$SCENE_NAME"
mkdir -p "$DEST_DIR/collision"
cp "$SCENE_DIR/scene.ply" "$DEST_DIR/scene.ply"
cp "$SCENE_DIR/collision/collision.glb" "$DEST_DIR/collision/$SCENE_NAME.collision.glb"
cp "$SCENE_DIR/alignment_manifest.json" "$DEST_DIR/alignment_manifest.json"
echo "$SCENE_NAME" > "$SCENE_DIR/../godot_assets/current_scene.txt"
exit 0
""")

    # Stub model_coverage.py — just exit 0
    _write_stub(bin_dir, "model_coverage.py", "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n")

    # Stub cull_blurry.py — just exit 0
    _write_stub(bin_dir, "cull_blurry.py", "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n")

    # Copy run_pipeline.sh to the stub dir and modify it to use the stub scripts
    # This is needed because run_pipeline.sh calls scripts directly from $SCRIPT_DIR
    stub_pipeline = bin_dir / "run_pipeline.sh"
    shutil.copy2(PIPELINE_SCRIPT, stub_pipeline)
    _make_executable(stub_pipeline)

    # Modify the stub pipeline to use the stub scripts
    # Replace SCRIPT_DIR with the stub bin dir
    content = stub_pipeline.read_text()
    content = content.replace(
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        f'SCRIPT_DIR="{bin_dir}"'
    )
    # Replace GODOT_ASSETS_ROOT with a temp path
    godot_assets = tmp_path / "godot_assets"
    content = content.replace(
        'GODOT_ASSETS_ROOT="${GODOT_ASSETS_ROOT:-$(cd "$SCRIPT_DIR/../../godot_walk/assets" && pwd)}"',
        f'GODOT_ASSETS_ROOT="{godot_assets}"'
    )
    stub_pipeline.write_text(content)

    # Also need to copy pipeline_state.py to the stub dir
    # because run_pipeline.sh imports it
    shutil.copy2(REPO_ROOT / "scripts" / "splat_pipeline" / "pipeline_state.py", bin_dir / "pipeline_state.py")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    return env, bin_dir


def test_pipeline_executes_end_to_end(tmp_path):
    """Run run_pipeline.sh from the repository root with stubbed externals."""
    scene_dir = tmp_path / "test_scene"
    scene_dir.mkdir()
    (scene_dir / "video.mp4").write_text("fake video content")

    env, stub_dir = _make_stub_env(tmp_path)

    # Run the stub pipeline (which uses stub scripts) from the repository root
    stub_pipeline = stub_dir / "run_pipeline.sh"
    result = subprocess.run(
        ["bash", str(stub_pipeline), str(scene_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, (
        f"Pipeline failed with exit code {result.returncode}.\n"
        f"stdout: {result.stdout[-2000:]}\n"
        f"stderr: {result.stderr[-2000:]}"
    )

    # Verify that the expected outputs were produced
    assert (scene_dir / "images").is_dir(), "Stage A should create images/"
    assert (scene_dir / "sparse" / "0" / "cameras.bin").exists(), "Stage B should create sparse model"
    assert (scene_dir / "sparse" / "0" / "images.bin").exists(), "Stage B should create sparse model"
    assert (scene_dir / "sparse" / "0" / "points3D.bin").exists(), "Stage B should create sparse model"
    assert (scene_dir / "scene.ply").exists(), "Stage C should create scene.ply"
    assert (scene_dir / "collision" / "collision.glb").exists(), "Stage D should create collision.glb"
    assert (scene_dir / "alignment_manifest.json").exists(), "Stage E should create alignment_manifest.json"
    assert (scene_dir / "traversal_manifest.json").exists(), "Stage E should create traversal_manifest.json"

    # Verify that pipeline_state.json was created with all stages
    state = json.loads((scene_dir / "pipeline_state.json").read_text())
    for stage in ["stage_a", "stage_b", "stage_c", "stage_d", "stage_e", "stage_f"]:
        assert stage in state, f"pipeline_state.json should record {stage}"
        assert state[stage]["status"] == "success", f"{stage} should be recorded as success"

    # Verify that per-stage logs were created
    for stage in ["stage_a", "stage_b", "stage_c", "stage_d", "stage_e", "stage_f"]:
        log_file = scene_dir / "logs" / f"{stage}.log"
        assert log_file.exists(), f"Per-stage log should exist: {log_file}"


def test_pipeline_resumability(tmp_path):
    """Run the pipeline twice and verify that the second run skips all stages."""
    scene_dir = tmp_path / "test_scene"
    scene_dir.mkdir()
    (scene_dir / "video.mp4").write_text("fake video content")

    env, stub_dir = _make_stub_env(tmp_path)

    # First run — should execute all stages
    stub_pipeline = stub_dir / "run_pipeline.sh"
    result1 = subprocess.run(
        ["bash", str(stub_pipeline), str(scene_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result1.returncode == 0, f"First run failed: {result1.stderr[-1000:]}"

    # Second run — should skip all stages
    result2 = subprocess.run(
        ["bash", str(stub_pipeline), str(scene_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result2.returncode == 0, f"Second run failed: {result2.stderr[-1000:]}"
    assert "skipped" in result2.stdout.lower(), "Second run should skip unchanged stages"


def test_pipeline_dry_run_does_not_mutate(tmp_path):
    """Verify that --dry-run does not create directories or copy files."""
    scene_dir = tmp_path / "test_scene"
    scene_dir.mkdir()
    (scene_dir / "video.mp4").write_text("fake video content")

    env, stub_dir = _make_stub_env(tmp_path)

    # Run with --dry-run
    stub_pipeline = stub_dir / "run_pipeline.sh"
    result = subprocess.run(
        ["bash", str(stub_pipeline), str(scene_dir), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, f"Dry run failed: {result.stderr[-1000:]}"
    assert not (scene_dir / "images").exists(), "Dry run should not create images/"
    assert not (scene_dir / "logs").exists(), "Dry run should not create logs/"
    assert not (scene_dir / "pipeline_state.json").exists(), "Dry run should not create pipeline_state.json"
