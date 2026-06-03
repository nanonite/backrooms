#!/usr/bin/env bash
# stage_assets.sh — Copy pipeline outputs into the Bevy app assets tree.
#
# Copies scene.ply + collision.glb from a completed scene_dir into
# splat_walk/assets/splats/<scene_name>/, creates alignment.toml from the
# _template only if missing (preserving any hand-tuned values), and updates
# splat_walk/assets/splats/current_scene.txt so the runtime picks up the new scene.
#
# Usage:
#   scripts/splat_pipeline/stage_assets.sh <scene_dir>
#
# Idempotent: rerun replaces scene.ply and collision.glb but keeps a tuned
# alignment.toml. When run from run_pipeline.sh, scene_dir is the argument
# passed to the pipeline driver.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Allow override for testing (defaults to resolution relative to script location).
SPLATS_ROOT="${SPLAT_SPLATS_ROOT:-$(cd "$SCRIPT_DIR/../../splat_walk/assets/splats" && pwd)}"

usage() {
    cat <<'EOF'
Usage: stage_assets.sh <scene_dir>

  scene_dir    Path to the per-scene working directory (same as run_pipeline.sh).
               Must contain scene.ply and collision.glb.

Copies final assets into splat_walk/assets/splats/<scene_name>/ and updates
current_scene.txt so the Bevy runtime loads the scene on next startup.
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

DEST_DIR="$SPLATS_ROOT/$SCENE_NAME"
TEMPLATE="$SPLATS_ROOT/_template/alignment.toml"
CURRENT_SCENE="$SPLATS_ROOT/current_scene.txt"

echo "=== Stage assets ==="
echo "Scene:     $SCENE_NAME"
echo "Scene dir: $SCENE_DIR"
echo "Dest:      $DEST_DIR"
echo

if [[ ! -f "$SCENE_DIR/scene.ply" ]]; then
    echo "FAIL: scene.ply not found at '$SCENE_DIR/scene.ply'." >&2
    echo "Run Stages A–C first (run_pipeline.sh)." >&2
    exit 1
fi

if [[ ! -f "$SCENE_DIR/collision.glb" ]]; then
    echo "FAIL: collision.glb not found at '$SCENE_DIR/collision.glb'." >&2
    echo "Run Stage D first (run_pipeline.sh)." >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

cp "$SCENE_DIR/scene.ply" "$DEST_DIR/scene.ply"
echo "Copied scene.ply -> $DEST_DIR/scene.ply"

cp "$SCENE_DIR/collision.glb" "$DEST_DIR/collision.glb"
echo "Copied collision.glb -> $DEST_DIR/collision.glb"

if [[ ! -f "$DEST_DIR/alignment.toml" ]]; then
    if [[ ! -f "$TEMPLATE" ]]; then
        echo "FAIL: alignment template not found at '$TEMPLATE'." >&2
        exit 1
    fi
    cp "$TEMPLATE" "$DEST_DIR/alignment.toml"
    echo "Created alignment.toml from template."
else
    echo "alignment.toml already exists — preserving tuned values."
fi

echo "$SCENE_NAME" > "$CURRENT_SCENE"
echo "Updated current_scene.txt -> '$SCENE_NAME'"

echo
echo "=== Staging complete ==="
echo "Assets staged at: $DEST_DIR"
echo "Next: cd splat_walk && cargo run"
