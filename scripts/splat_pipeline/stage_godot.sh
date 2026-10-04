#!/usr/bin/env bash
# stage_godot.sh — Copy pipeline outputs into the Godot project assets tree.
#
# Copies scene.ply + collision.glb + alignment_manifest.json from a completed
# scene_dir into godot_walk/assets/<scene_name>/, generates the .tscn scene
# file from a template, writes a scene manifest with provenance hashes, and
# updates godot_walk/current_scene.txt so the runtime picks up the new scene.
#
# Usage:
#   scripts/splat_pipeline/stage_godot.sh <scene_dir>
#
#   scene_dir    Path to the per-scene working directory (same as run_pipeline.sh).
#                Must contain scene.ply, collision.glb, and alignment_manifest.json.
#
# Environment:
#   GODOT_ASSETS_ROOT    Destination root (default: ../../godot_walk/assets).
#   GODOT_SCENE_TEMPLATE  Path to the .tscn template (default: scene_template.tscn
#                        in the same directory as this script).
#
# The scene manifest (scene_manifest.json) records:
#   - scene name, source video path, video MD5
#   - splat MD5, collision MD5, manifest MD5
#   - tool versions (splat-transform, COLMAP, nerfstudio)
#   - stage timestamps from pipeline_state.json
#
# Idempotent: rerun replaces assets but preserves nothing by default —
# a re-staged scene is a new scene, not a patch on the old one.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Allow override for testing (defaults to resolution relative to script location).
GODOT_ASSETS_ROOT="${GODOT_ASSETS_ROOT:-$(cd "$SCRIPT_DIR/../../godot_walk/assets" && pwd)}"
GODOT_SCENE_TEMPLATE="${GODOT_SCENE_TEMPLATE:-$SCRIPT_DIR/scene_template.tscn}"

usage() {
    cat <<'EOF'
Usage: stage_godot.sh <scene_dir>

  scene_dir    Path to the per-scene working directory.
               Must contain scene.ply, collision.glb, and alignment_manifest.json.

Copies final assets into godot_walk/assets/<scene_name>/, generates the .tscn
scene file, writes scene_manifest.json, and updates current_scene.txt.
EOF
    exit 0
}

if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    usage
fi

if [[ $# -lt 1 ]]; then
    echo "ERROR: scene_dir argument required." >&2
    echo "Use --help for usage." >&2
    exit 1
fi

SCENE_DIR="$(realpath "$1")"
SCENE_NAME="$(basename "$SCENE_DIR")"

DEST_DIR="$GODOT_ASSETS_ROOT/$SCENE_NAME"
COLLISION_DIR="$DEST_DIR/collision"
CURRENT_SCENE="$GODOT_ASSETS_ROOT/current_scene.txt"

echo "=== Stage Godot ==="
echo "Scene:     $SCENE_NAME"
echo "Scene dir: $SCENE_DIR"
echo "Dest:      $DEST_DIR"
echo

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------

if [[ ! -f "$SCENE_DIR/scene.ply" ]]; then
    echo "FAIL: scene.ply not found at '$SCENE_DIR/scene.ply'." >&2
    echo "Run Stages A–C first (run_pipeline.sh)." >&2
    exit 1
fi

if [[ ! -f "$SCENE_DIR/collision.collision.glb" ]]; then
    echo "FAIL: collision.glb not found at '$SCENE_DIR/collision.collision.glb'." >&2
    echo "Run Stage D first (run_pipeline.sh)." >&2
    exit 1
fi

if [[ ! -f "$SCENE_DIR/alignment_manifest.json" ]]; then
    echo "FAIL: alignment_manifest.json not found at '$SCENE_DIR/alignment_manifest.json'." >&2
    echo "Run Stage E first (run_pipeline.sh)." >&2
    exit 1
fi

if [[ ! -f "$GODOT_SCENE_TEMPLATE" ]]; then
    echo "FAIL: scene template not found at '$GODOT_SCENE_TEMPLATE'." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Copy assets
# ---------------------------------------------------------------------------

mkdir -p "$COLLISION_DIR"

cp "$SCENE_DIR/scene.ply" "$DEST_DIR/scene.ply"
echo "Copied scene.ply -> $DEST_DIR/scene.ply"

cp "$SCENE_DIR/collision.collision.glb" "$COLLISION_DIR/$SCENE_NAME.collision.glb"
echo "Copied collision.glb -> $COLLISION_DIR/$SCENE_NAME.collision.glb"

cp "$SCENE_DIR/alignment_manifest.json" "$DEST_DIR/alignment_manifest.json"
echo "Copied alignment_manifest.json -> $DEST_DIR/alignment_manifest.json"

# ---------------------------------------------------------------------------
# Generate scene file from template
# ---------------------------------------------------------------------------

# Read the contract values from the manifest using Python (the manifest is JSON,
# and the values we need are nested — doing this in bash would be fragile).
read -r SPLAT_TRANSFORM COLLISION_TRANSFORM SAFETY_NET_TRANSFORM PLAYER_SPAWN_TRANSFORM PLAYER_TRANSFORM PLY_PATH COLLISION_GLB_PATH < <(python3 - "$SCENE_DIR/alignment_manifest.json" "$SCENE_NAME" <<'PYEOF'
import json
import sys

manifest_path, scene_name = sys.argv[1], sys.argv[2]
with open(manifest_path) as f:
    m = json.load(f)

# Splat node transform: rotation × uniform scale, zero translation.
# From emit_scene_contract.py: the contract's node_transform_matrix() rows.
import numpy as np

basis = m["ply_to_world"]["basis_columns"]
mpu = m["ply_to_world"]["metres_per_unit"]
# Transform3D(row0, row1, row2, translation) — row-major 3x3 + translation.
# The basis_columns are the columns of the rotation matrix.
# Transform3D takes rows, so we transpose.
rot = np.array(basis).T  # now rot[i][j] = basis[j][i] = row i, col j
values = []
for row in range(3):
    for col in range(3):
        values.append(float(rot[row][col]) * mpu)
values.extend([0.0, 0.0, 0.0])  # translation
splat_tf = "Transform3D(%s)" % ", ".join("%.7g" % v for v in values)

# Collision node transform: from collision_params.collision_node_transform.
# basis = contract.rotation @ ENGINE_FRAME_ROTATION.T
# translation = -(contract.rotation @ origin_ply_units) * metres_per_unit
engine_rot = np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]])
rot_full = np.array(basis)  # columns
collision_basis = rot_full @ engine_rot.T
origin = m["ply_to_world"]["origin_ply_units"]
translation = -(rot_full @ np.array(origin)) * mpu
values = []
for row in range(3):
    for col in range(3):
        values.append(float(collision_basis[row][col]))
values.extend([float(translation[0]), float(translation[1]), float(translation[2])])
collision_tf = "Transform3D(%s)" % ", ".join("%.7g" % v for v in values)

# Safety net: 1.3 m below the lowest surface, 3.0 m margin.
floor_y = m["collider"]["floor_height"]
net_y = floor_y - 1.3
room = m["collider"]
size_x = room["max_corner"][0] - room["min_corner"][0] + 6.0
size_z = room["max_corner"][2] - room["min_corner"][2] + 6.0
centre_x = (room["max_corner"][0] + room["min_corner"][0]) / 2.0
centre_z = (room["max_corner"][2] + room["min_corner"][2]) / 2.0
safety_tf = "Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.7g, %.7g, %.7g)" % (centre_x, net_y, centre_z)

# Player spawn: the contract's spawn marker.
spawn = m["spawn"]
spawn_tf = "Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.7g, %.7g, %.7g)" % (spawn[0], spawn[1], spawn[2])

# Player: on the generated collision's floor surface under the marker.
# The floor surface is the contract's floor_height; the capsule is 1.2 m tall,
# so the centre is floor_height + 0.6.
player_y = floor_y + 0.6
player_tf = "Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.7g, %.7g, %.7g)" % (spawn[0], player_y, spawn[2])

ply_path = "res://assets/%s/scene.ply" % scene_name
collision_glb_path = "res://assets/%s/collision/%s.collision.glb" % (scene_name, scene_name)

print(splat_tf)
print(collision_tf)
print(safety_tf)
print(spawn_tf)
print(player_tf)
print(ply_path)
print(collision_glb_path)
PYEOF
)

# Generate the .tscn from the template.
SCENE_FILE="$DEST_DIR/$SCENE_NAME.tscn"
python3 - "$GODOT_SCENE_TEMPLATE" "$SCENE_FILE" "$SPLAT_TRANSFORM" "$COLLISION_TRANSFORM" "$SAFETY_NET_TRANSFORM" "$PLAYER_SPAWN_TRANSFORM" "$PLAYER_TRANSFORM" "$PLY_PATH" "$COLLISION_GLB_PATH" "$SCENE_NAME" <<'PYEOF'
import sys

template_path, out_path = sys.argv[1], sys.argv[2]
splat_tf, collision_tf, safety_tf, spawn_tf, player_tf, ply_path, collision_glb_path, scene_name = sys.argv[3:]

with open(template_path) as f:
    content = f.read()

replacements = {
    "@SCENE_NAME@": scene_name,
    "@SPLAT_TRANSFORM@": splat_tf,
    "@COLLISION_TRANSFORM@": collision_tf,
    "@SAFETY_NET_TRANSFORM@": safety_tf,
    "@PLAYER_SPAWN_TRANSFORM@": spawn_tf,
    "@PLAYER_TRANSFORM@": player_tf,
    "@PLY_PATH@": ply_path,
    "@COLLISION_GLB_PATH@": collision_glb_path,
}
for key, value in replacements.items():
    content = content.replace(key, value)

with open(out_path, "w") as f:
    f.write(content)
PYEOF

echo "Generated $SCENE_FILE"

# ---------------------------------------------------------------------------
# Write scene manifest
# ---------------------------------------------------------------------------

python3 - "$SCENE_DIR" "$DEST_DIR" "$SCENE_NAME" <<'PYEOF'
import hashlib
import json
import sys
from pathlib import Path

scene_dir = Path(sys.argv[1])
dest_dir = Path(sys.argv[2])
scene_name = sys.argv[3]


def md5(path):
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Load pipeline state for stage timestamps.
state_path = scene_dir / "pipeline_state.json"
state = {}
if state_path.is_file():
    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        pass

# Load alignment manifest for tool versions.
manifest_path = dest_dir / "alignment_manifest.json"
manifest = {}
if manifest_path.is_file():
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        pass

scene_manifest = {
    "scene_name": scene_name,
    "source_video": str(scene_dir / "video.mp4"),
    "source_video_md5": md5(scene_dir / "video.mp4"),
    "assets": {
        "splat": {
            "path": "res://assets/%s/scene.ply" % scene_name,
            "md5": md5(dest_dir / "scene.ply"),
            "splat_count": manifest.get("asset", {}).get("splat_count", 0),
        },
        "collision": {
            "path": "res://assets/%s/collision/%s.collision.glb" % (scene_name, scene_name),
            "md5": md5(dest_dir / "collision" / ("%s.collision.glb" % scene_name)),
        },
        "alignment_manifest": {
            "path": "res://assets/%s/alignment_manifest.json" % scene_name,
            "md5": md5(dest_dir / "alignment_manifest.json"),
        },
    },
    "tools": {
        "splat_transform": manifest.get("tool", {}).get("pinned_version", "unknown"),
        "colmap": "3.10",
        "nerfstudio": "1.1.5",
        "gsplat": "1.5.1",
    },
    "stages": {
        name: {
            "status": record.get("status", "unknown"),
            "timestamp": record.get("timestamp", ""),
            "input_hash": record.get("input_hash", ""),
            "output_hash": record.get("output_hash", ""),
        }
        for name, record in state.items()
    },
    "scene_id": manifest.get("scene_id", scene_name),
    "footage_kind": manifest.get("capture", {}).get("footage_kind", "unknown"),
    "walls_measured": manifest.get("capture", {}).get("walls_measured", False),
}

out_path = dest_dir / "scene_manifest.json"
out_path.write_text(json.dumps(scene_manifest, indent=2) + "\n")
print("Wrote %s" % out_path)
PYEOF

# ---------------------------------------------------------------------------
# Update current_scene.txt
# ---------------------------------------------------------------------------

echo "$SCENE_NAME" > "$CURRENT_SCENE"
echo "Updated current_scene.txt -> '$SCENE_NAME'"

echo
echo "=== Godot staging complete ==="
echo "Assets staged at: $DEST_DIR"
echo "Next: cd godot_walk && godot4 --headless --script res://scripts/verify_scene.gd"
