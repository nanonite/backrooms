#!/usr/bin/env bash
# convert_video.sh — One-shot entrypoint: video file → staged splat scene.
#
# Takes any video file path, derives a safe scene name, creates the per-scene
# working directory under scenes/<scene_name>/, copies the video as video.mp4,
# and drives the full pipeline (Stages A → D + staging).
#
# Usage:
#   scripts/splat_pipeline/convert_video.sh <video_path> [scene_name]
#
#   video_path   Path to the input video file (any format ffmpeg can read).
#   scene_name   Optional. Derived from the video filename if omitted.
#                Must be a safe identifier — no slashes, dots, or traversal.
#
# After the pipeline completes, the scene is staged under
# splat_walk/assets/splats/<scene_name>/ and current_scene.txt is updated.
# The operator can then: cd splat_walk && cargo run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Allow override for testing (defaults to resolution relative to script location).
SCENES_ROOT="${CONVERT_SCENES_ROOT:-$SCRIPT_DIR/scenes}"

usage() {
    cat <<'EOF'
Usage: convert_video.sh <video_path> [scene_name]

  video_path   Path to the input video file (e.g. ~/Videos/capture.mp4).
  scene_name   Optional name for the scene. Derived from the video filename
               if omitted. Must be a safe identifier — no slashes, dots,
               or path traversal.

Pipeline:
  1. Validate the input video exists.
  2. Derive a safe scene name.
  3. Create scenes/<scene_name>/ and copy video.mp4.
  4. Run run_pipeline.sh (Stages A–D + staging).
EOF
    exit 0
}

if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    usage
fi

if [[ $# -lt 1 ]]; then
    echo "ERROR: video_path argument required." >&2
    echo "Use --help for usage." >&2
    exit 1
fi

VIDEO_PATH="$1"

# Validate the file exists BEFORE realpath, so error messages reflect the
# user's original argument rather than an empty or mangled path.
if [[ ! -f "$VIDEO_PATH" ]]; then
    echo "FAIL: video file not found at '$VIDEO_PATH'." >&2
    exit 1
fi

VIDEO_PATH="$(realpath "$VIDEO_PATH")"

# Derive scene name from optional argument or video filename (strip extension).
if [[ -n "${2:-}" ]]; then
    SCENE_NAME="$2"
else
    SCENE_NAME="$(basename "$VIDEO_PATH" | sed 's/\.[^.]*$//')"
fi

# Reject unsafe scene names: empty, single dot, double dot, containing any
# slash, or containing ".." as a component (path-traversal attempts).
if [[ -z "$SCENE_NAME" ]] || \
   [[ "$SCENE_NAME" == "." ]] || \
   [[ "$SCENE_NAME" == ".." ]] || \
   [[ "$SCENE_NAME" =~ / ]] || \
   [[ "$SCENE_NAME" =~ (^|/)\.\.(/|$) ]] || \
   [[ "$SCENE_NAME" =~ : ]]; then
    echo "FAIL: scene_name '$SCENE_NAME' is not a safe identifier." >&2
    echo "Use only alphanumerics, hyphens, and underscores." >&2
    exit 1
fi

SCENE_DIR="$SCENES_ROOT/$SCENE_NAME"

mkdir -p "$SCENE_DIR"
cp "$VIDEO_PATH" "$SCENE_DIR/video.mp4"

echo "=== Convert video ==="
echo "Video:     $VIDEO_PATH"
echo "Scene:     $SCENE_NAME"
echo "Scene dir: $SCENE_DIR"
echo

exec "$SCRIPT_DIR/run_pipeline.sh" "$SCENE_DIR"
