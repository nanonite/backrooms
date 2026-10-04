#!/usr/bin/env bash
# train_splatfacto.sh — Stage C: Gaussian-splat training with Nerfstudio Splatfacto.
#
# Trains a Gaussian splat from the COLMAP-format dataset produced by Stage B
# (images/ + sparse/0/). Outputs scene_dir/scene.ply — the VISUAL asset.
#
# This is the DEFAULT training path. Brush (train_brush.sh) is the fallback
# for hosts where nerfstudio is unavailable.
#
# Usage:
#   train_splatfacto.sh <scene_dir> [--max-steps N] [--eval-mode MODE]
#
#   scene_dir      Per-scene working directory containing images/ and sparse/0/.
#   --max-steps    Maximum training iterations (default: 30000).
#   --eval-mode    Evaluation mode: all | few | none (default: all).
#
# Environment:
#   NS_BIN             Path to the ns-train binary (default: ns-train).
#   NS_MAX_STEPS       Default --max-steps (overridable by CLI; default: 30000).
#   NS_EVAL_MODE       Default --eval-mode (overridable by CLI; default: all).
#   NS_OUTPUT_DIR      Output directory (default: <scene_dir>/splatfacto_output).
#
# Exit codes:
#   0  Success — scene.ply produced and non-empty.
#   1  Usage error (missing scene_dir, bad args).
#   2  Missing dependencies (ns-train not found).
#   3  Input validation failed (no images/ dir, no sparse/0/, insufficient files).
#   4  Training failed (non-zero exit from ns-train, or no output produced).
#
# Requirements:
#   - Nerfstudio (ns-train) with Splatfacto model support.
#   - GPU with CUDA (Splatfacto uses gsplat, which requires CUDA).
#
# The output PLY is written to <scene_dir>/scene.ply. The nerfstudio output
# directory contains the dataparser_transforms.json needed by Stage E.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_STEPS=30000
DEFAULT_EVAL_MODE="all"
SCENE_PLY="scene.ply"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: train_splatfacto.sh <scene_dir> [--max-steps N] [--eval-mode MODE]

  scene_dir      Per-scene working directory containing images/ and sparse/0/.

Options:
  --max-steps N    Maximum training iterations (default: 30000).
  --eval-mode MODE Evaluation mode: all | few | none (default: all).

Environment:
  NS_BIN             Path to the ns-train binary (default: ns-train).
  NS_MAX_STEPS       Default max steps (overridable by --max-steps).
  NS_EVAL_MODE       Default eval mode (overridable by --eval-mode).
  NS_OUTPUT_DIR      Output directory (default: <scene_dir>/splatfacto_output).

Exit codes:
  0  Success — scene.ply produced.
  1  Usage error.
  2  Missing dependencies.
  3  Input validation failed.
  4  Training failed.
EOF
    exit 0
}

die() {
    local code="$1"
    shift
    echo "ERROR: $*" >&2
    exit "$code"
}

warn() {
    echo "WARN: $*" >&2
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    usage
fi

if [[ $# -lt 1 ]]; then
    die 1 "scene_dir argument required. Use --help for usage."
fi

SCENE_DIR="$1"
shift

NS_MAX_STEPS_VAL="${NS_MAX_STEPS:-$DEFAULT_MAX_STEPS}"
NS_EVAL_MODE_VAL="${NS_EVAL_MODE:-$DEFAULT_EVAL_MODE}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-steps)
            if [[ $# -lt 2 ]] || [[ ! "$2" =~ ^[0-9]+$ ]]; then
                die 1 "--max-steps requires a positive integer argument."
            fi
            NS_MAX_STEPS_VAL="$2"
            shift 2
            ;;
        --eval-mode)
            if [[ $# -lt 2 ]]; then
                die 1 "--eval-mode requires an argument."
            fi
            NS_EVAL_MODE_VAL="$2"
            shift 2
            ;;
        --help|-h) usage ;;
        *)
            die 1 "Unknown option: $1. Use --help for usage."
            ;;
    esac
done

SCENE_DIR="$(realpath "$SCENE_DIR")"
IMAGES_DIR="$SCENE_DIR/images"
SPARSE_MODEL_DIR="$SCENE_DIR/sparse/0"
PLY_OUT="$SCENE_DIR/$SCENE_PLY"
OUTPUT_DIR="${NS_OUTPUT_DIR:-$SCENE_DIR/splatfacto_output}"

echo "=== Nerfstudio Splatfacto training (Stage C) ==="
echo "Scene:      $SCENE_DIR"
echo "Max steps:  $NS_MAX_STEPS_VAL"
echo "Eval mode:  $NS_EVAL_MODE_VAL"
echo "Output dir: $OUTPUT_DIR"
echo

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

NS_BIN="${NS_BIN:-ns-train}"
NS_PATH="$(command -v "$NS_BIN" || true)"

if [[ -z "$NS_PATH" ]]; then
    die 2 "ns-train binary '$NS_BIN' not found in PATH."
fi
if [[ ! -x "$NS_PATH" ]]; then
    die 2 "ns-train binary '$NS_PATH' is not executable."
fi

echo "ns-train: $NS_PATH"
echo

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

if [[ ! -d "$IMAGES_DIR" ]]; then
    die 3 "images directory not found: '$IMAGES_DIR'. Run Stage A first."
fi

IMAGE_COUNT=$(find "$IMAGES_DIR" -maxdepth 1 -type f \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | wc -l)

if [[ "$IMAGE_COUNT" -eq 0 ]]; then
    die 3 "No images found in '$IMAGES_DIR'. Run Stage A (frame extraction) first."
fi

echo "Input images: $IMAGE_COUNT"

if [[ ! -d "$SPARSE_MODEL_DIR" ]]; then
    die 3 "sparse/0 directory not found: '$SPARSE_MODEL_DIR'. Run Stage B first."
fi

CAMERAS_BIN="$SPARSE_MODEL_DIR/cameras.bin"
IMAGES_BIN="$SPARSE_MODEL_DIR/images.bin"
POINTS_BIN="$SPARSE_MODEL_DIR/points3D.bin"

if [[ ! -f "$CAMERAS_BIN" ]]; then
    die 3 "cameras.bin not found: '$CAMERAS_BIN'. Stage B output incomplete."
fi
if [[ ! -f "$IMAGES_BIN" ]]; then
    die 3 "images.bin not found: '$IMAGES_BIN'. Stage B output incomplete."
fi
if [[ ! -f "$POINTS_BIN" ]]; then
    die 3 "points3D.bin not found: '$POINTS_BIN'. Stage B output incomplete."
fi

echo "COLMAP model: $SPARSE_MODEL_DIR"
echo

# ---------------------------------------------------------------------------
# Clean stale output from previous run
# ---------------------------------------------------------------------------

rm -f "$PLY_OUT"

# ---------------------------------------------------------------------------
# Stage C — Splatfacto training
# ---------------------------------------------------------------------------

echo "--- Stage C: Nerfstudio Splatfacto training ---"

# nerfstudio's ns-train command. The --data flag points at the scene directory
# (which contains images/ and sparse/0/). The --output-dir flag controls where
# the training outputs (including dataparser_transforms.json) are written.
#
# The --pipeline.model.eval-mode flag controls how many evaluation images
# are rendered during training. "all" renders every image, "few" renders a
# subset, "none" renders none.
#
# The --max-num-iterations flag controls the training duration.

NS_TRAIN_ARGS=(
    "splatfacto"
    "--data" "$SCENE_DIR"
    "--output-dir" "$OUTPUT_DIR"
    "--pipeline.model.eval-mode" "$NS_EVAL_MODE_VAL"
    "--max-num-iterations" "$NS_MAX_STEPS_VAL"
)

echo "Command: $NS_PATH ${NS_TRAIN_ARGS[*]}"
echo

# Run ns-train. Do NOT use set -e inside the command group — we want to capture
# the exit code and produce a clear message.
NS_EXIT=0
"$NS_PATH" "${NS_TRAIN_ARGS[@]}" || NS_EXIT=$?

if [[ "$NS_EXIT" -ne 0 ]]; then
    die 4 "ns-train failed with exit code $NS_EXIT."
fi

# ---------------------------------------------------------------------------
# Export PLY
# ---------------------------------------------------------------------------

echo
echo "--- Exporting PLY ---"

# nerfstudio exports the trained splat as a PLY file. The exact path depends
# on the nerfstudio version and configuration. We look for the most common
# locations.
#
# The export command is:
#   ns-export gaussian-splat --load-config <config> --output-dir <dir>
#
# But newer versions of nerfstudio export automatically during training. We
# check for the PLY in the output directory first.

EXPORTED_PLY=""

# Check for auto-exported PLY in the output directory.
for candidate in \
    "$OUTPUT_DIR"/*.ply \
    "$OUTPUT_DIR"/nerfstudio_models/*.ply \
    "$OUTPUT_DIR"/export/*.ply; do
    if [[ -f "$candidate" ]]; then
        EXPORTED_PLY="$candidate"
        break
    fi
done

# If no auto-exported PLY was found, try to export manually.
if [[ -z "$EXPORTED_PLY" ]]; then
    # Find the config YAML in the output directory.
    CONFIG_YAML=""
    for candidate in "$OUTPUT_DIR"/config.yml "$OUTPUT_DIR"/*/config.yml; do
        if [[ -f "$candidate" ]]; then
            CONFIG_YAML="$candidate"
            break
        fi
    done

    if [[ -n "$CONFIG_YAML" ]]; then
        echo "No auto-exported PLY found. Exporting from config: $CONFIG_YAML"
        ns-export gaussian-splat \
            --load-config "$CONFIG_YAML" \
            --output-dir "$OUTPUT_DIR" || {
            warn "ns-export failed. The PLY may need to be exported manually."
        }

        # Check again for the exported PLY.
        for candidate in \
            "$OUTPUT_DIR"/*.ply \
            "$OUTPUT_DIR"/nerfstudio_models/*.ply \
            "$OUTPUT_DIR"/export/*.ply; do
            if [[ -f "$candidate" ]]; then
                EXPORTED_PLY="$candidate"
                break
            fi
        done
    fi
fi

if [[ -z "$EXPORTED_PLY" ]]; then
    die 4 "ns-train exited 0 but no PLY was produced. Check the output directory: $OUTPUT_DIR"
fi

cp "$EXPORTED_PLY" "$PLY_OUT"
echo "Copied $EXPORTED_PLY -> $PLY_OUT"

# ---------------------------------------------------------------------------
# Success gate — verify output
# ---------------------------------------------------------------------------

echo
echo "--- Success gate ---"

if [[ ! -f "$PLY_OUT" ]]; then
    die 4 "Export exited 0 but scene.ply was not created at '$PLY_OUT'."
fi

PLY_SIZE=$(stat -c%s "$PLY_OUT" 2>/dev/null || echo "0")
if [[ "$PLY_SIZE" -eq 0 ]]; then
    die 4 "Export produced an empty scene.ply at '$PLY_OUT'."
fi

echo "Output: $PLY_OUT ($PLY_SIZE bytes)"

# Count splats from the PLY header
SPLAT_COUNT=$(python3 -c "
import sys
try:
    with open(sys.argv[1], 'rb') as f:
        chunk = f.read(4096)
    header_end = chunk.find(b'end_header')
    if header_end == -1:
        sys.exit(1)
    header = chunk[:header_end].decode('ascii', errors='replace')
    for line in header.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0] == 'element' and parts[1] == 'vertex':
            print(parts[2])
            sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
" "$PLY_OUT" 2>/dev/null || true)

if [[ -n "$SPLAT_COUNT" ]] && [[ "$SPLAT_COUNT" -gt 0 ]]; then
    echo "Splat count: $SPLAT_COUNT"
else
    echo "Splat count: could not determine (PLY header parse failed)."
fi

echo
echo "=== Stage C (Splatfacto) complete ==="
echo "Visual asset: $PLY_OUT"
echo
echo "Next: Stage D — generate collision mesh (generate_collision.py)."

exit 0
