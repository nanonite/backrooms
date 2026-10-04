#!/usr/bin/env bash
# convert_video.sh — One-shot entrypoint: video file → staged Godot scene.
#
# Takes any video file path, derives a safe scene name, creates the per-scene
# working directory under scenes/<scene_name>/, copies the video as video.mp4,
# and drives the full pipeline (Stages A → F + Godot staging).
#
# Usage:
#   scripts/splat_pipeline/convert_video.sh <video_path> [scene_name] [--dry-run] [--force]
#
#   video_path   Path to the input video file (any format ffmpeg can read).
#   scene_name   Optional. Derived from the video filename if omitted.
#                Must be a safe identifier — no slashes, dots, or traversal.
#   --dry-run    Print the pipeline plan and exit without executing.
#   --force      Re-run all stages, ignoring previous successful results.
#
# After the pipeline completes, the scene is staged under
# godot_walk/assets/<scene_name>/ and current_scene.txt is updated.
# The operator can then: cd godot_walk && godot4 --headless --script res://scripts/verify_scene.gd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Allow override for testing (defaults to resolution relative to script location).
SCENES_ROOT="${CONVERT_SCENES_ROOT:-$SCRIPT_DIR/scenes}"

usage() {
    cat <<'EOF'
Usage: convert_video.sh <video_path> [scene_name] [--dry-run] [--force]

  video_path   Path to the input video file (e.g. ~/Videos/capture.mp4).
  scene_name   Optional name for the scene. Derived from the video filename
               if omitted. Must be a safe identifier — no slashes, dots,
               or path traversal.
  --dry-run    Print the pipeline plan and exit without executing.
  --force      Re-run all stages, ignoring previous successful results.

Pipeline:
  1. Validate the input video exists.
  2. Derive a safe scene name.
  3. Create scenes/<scene_name>/ and copy video.mp4.
  4. Run run_pipeline.sh (Stages A–F + Godot staging).
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
shift

# Parse optional scene_name and flags.
SCENE_NAME=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|--force)
            EXTRA_ARGS+=("$1")
            shift
            ;;
        -*)
            echo "ERROR: Unknown option: $1" >&2
            echo "Use --help for usage." >&2
            exit 1
            ;;
        *)
            if [[ -z "$SCENE_NAME" ]]; then
                SCENE_NAME="$1"
            else
                echo "ERROR: Unexpected argument: $1" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate the file exists BEFORE realpath, so error messages reflect the
# user's original argument rather than an empty or mangled path.
if [[ ! -f "$VIDEO_PATH" ]]; then
    echo "FAIL: video file not found at '$VIDEO_PATH'." >&2
    exit 1
fi

VIDEO_PATH="$(realpath "$VIDEO_PATH")"

# Derive scene name from optional argument or video filename (strip extension).
if [[ -z "$SCENE_NAME" ]]; then
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

# Dry-run: print the plan without creating directories or copying the video.
# run_pipeline.sh tolerates a missing video.mp4 under --dry-run.
if [[ " ${EXTRA_ARGS[*]} " == *" --dry-run "* ]]; then
    echo "=== Convert video (dry run) ==="
    echo "Video:     $VIDEO_PATH"
    echo "Scene:     $SCENE_NAME"
    echo "Scene dir: $SCENE_DIR (not created)"
    echo
    exec "$SCRIPT_DIR/run_pipeline.sh" "$SCENE_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
fi

# Guard: warn when an existing scene's video.mp4 would be overwritten.
# If the existing file is byte-identical to the input, proceed silently.
# --force explicitly overwrites a different file.
if [[ -f "$SCENE_DIR/video.mp4" ]]; then
    if cmp -s "$SCENE_DIR/video.mp4" "$VIDEO_PATH"; then
        echo "Note: $SCENE_DIR/video.mp4 is identical to the input; keeping it."
    elif [[ " ${EXTRA_ARGS[*]} " == *" --force "* ]]; then
        echo "Note: --force set; overwriting $SCENE_DIR/video.mp4."
    else
        echo "FAIL: $SCENE_DIR/video.mp4 already exists and differs from the input." >&2
        echo "This scene name is already in use. Choose a different name, use" >&2
        echo "--force to overwrite, or remove the existing scene directory first." >&2
        exit 1
    fi
fi

mkdir -p "$SCENE_DIR"
cp "$VIDEO_PATH" "$SCENE_DIR/video.mp4"

echo "=== Convert video ==="
echo "Video:     $VIDEO_PATH"
echo "Scene:     $SCENE_NAME"
echo "Scene dir: $SCENE_DIR"
echo

exec "$SCRIPT_DIR/run_pipeline.sh" "$SCENE_DIR" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
