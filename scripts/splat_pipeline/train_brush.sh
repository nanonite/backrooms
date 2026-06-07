#!/usr/bin/env bash
# train_brush.sh — Stage C: Gaussian-splat training with Brush (ArthurBrussee/brush).
#
# Trains a Gaussian splat from the COLMAP-format dataset produced by Stage B
# (images/ + sparse/0/). Outputs scene_dir/scene.ply — the VISUAL asset.
#
# Usage:
#   train_brush.sh <scene_dir> [--total-steps N] [--max-splats N]
#
#   scene_dir      Per-scene working directory containing images/ and sparse/0/.
#   --total-steps  Number of training iterations (default: 30000).
#   --max-splats   Cap the number of Gaussians (optional, for VRAM-limited targets).
#
# Environment:
#   BRUSH_BIN          Path to the Brush binary (default: brush).
#   BRUSH_TOTAL_STEPS  Default --total-steps (overridable by CLI; default: 30000).
#   BRUSH_MAX_SPLATS   Default --max-splats (overridable by CLI; optional).
#
# Exit codes:
#   0  Success — scene.ply produced and non-empty.
#   1  Usage error (missing scene_dir, bad args).
#   2  Missing dependencies (brush not found or not executable).
#   3  Input validation failed (no images/ dir, no sparse/0/, insufficient files).
#   4  Brush training failed (non-zero exit from brush, or no output produced).
#
# VRAM budget (12 GB RTX 4070 Ti):
#   1–3M splats → comfortable at runtime in Bevy.
#   5M+ splats → watch VRAM; consider --max-splats.
#   10M+ splats → will strain Bevy renderer; re-train with --max-splats.
#
# Requirements:
#   - Brush (ArthurBrussee/brush): Rust + wgpu trainer, ingests COLMAP format.
#     Install from: https://github.com/ArthurBrussee/brush/releases
#   - GPU with wgpu-compatible backend (Vulkan, Metal, DX12).

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TOTAL_STEPS=30000
SPLINE_SCENE_PLY="scene.ply"

# Splat-count thresholds for VRAM advisory (12 GB RTX 4070 Ti)
SPLAT_COMFORTABLE=3000000
SPLAT_WARNING=5000000
SPLAT_CRITICAL=10000000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: train_brush.sh <scene_dir> [--total-steps N] [--max-splats N]

  scene_dir      Per-scene working directory containing images/ and sparse/0/.

Options:
  --total-steps N   Number of training iterations (default: 30000).
  --max-splats N    Cap the number of Gaussians (optional, for VRAM-limited targets).

Environment:
  BRUSH_BIN          Path to the Brush binary (default: brush).
  BRUSH_TOTAL_STEPS  Default total steps (overridable by --total-steps).
  BRUSH_MAX_SPLATS   Default max splats (overridable by --max-splats).

Exit codes:
  0  Success — scene.ply produced.
  1  Usage error.
  2  Missing dependencies.
  3  Input validation failed.
  4  Brush training failed.
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

# Count "element vertex" entries from a PLY file header reliably.
# PLY headers are ASCII lines ending with "end_header". We just grep.
# Returns 0 and prints the count, or returns 1 on failure.
count_ply_vertices() {
    local ply_path="$1"
    if [[ ! -f "$ply_path" ]] || [[ ! -r "$ply_path" ]]; then
        return 1
    fi
    # PLY header: "element vertex <N>" before "end_header"
    python3 -c "
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
" "$ply_path" 2>/dev/null
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

BRUSH_TOTAL_STEPS_VAL="${BRUSH_TOTAL_STEPS:-$DEFAULT_TOTAL_STEPS}"
BRUSH_MAX_SPLATS_VAL="${BRUSH_MAX_SPLATS:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --total-steps)
            if [[ $# -lt 2 ]] || [[ ! "$2" =~ ^[0-9]+$ ]]; then
                die 1 "--total-steps requires a positive integer argument."
            fi
            BRUSH_TOTAL_STEPS_VAL="$2"
            shift 2
            ;;
        --max-splats)
            if [[ $# -lt 2 ]] || [[ ! "$2" =~ ^[0-9]+$ ]]; then
                die 1 "--max-splats requires a positive integer argument."
            fi
            if [[ "$2" -eq 0 ]]; then
                die 1 "--max-splats must be greater than 0."
            fi
            BRUSH_MAX_SPLATS_VAL="$2"
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
PLY_OUT="$SCENE_DIR/$SPLINE_SCENE_PLY"

echo "=== Brush splat training (Stage C) ==="
echo "Scene:        $SCENE_DIR"
echo "Total steps:  $BRUSH_TOTAL_STEPS_VAL"
if [[ -n "$BRUSH_MAX_SPLATS_VAL" ]]; then
    echo "Max splats:   $BRUSH_MAX_SPLATS_VAL"
else
    echo "Max splats:   unlimited"
fi
echo

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

BRUSH_BIN="${BRUSH_BIN:-brush}"
BRUSH_PATH="$(command -v "$BRUSH_BIN" || true)"

if [[ -z "$BRUSH_PATH" ]]; then
    die 2 "Brush binary '$BRUSH_BIN' not found in PATH."
fi
if [[ ! -x "$BRUSH_PATH" ]]; then
    die 2 "Brush binary '$BRUSH_PATH' is not executable."
fi

echo "Brush: $BRUSH_PATH"
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
# Stage C — Brush training
# ---------------------------------------------------------------------------

echo "--- Stage C: Brush training ---"

BRUSH_ARGS=(
    "$SCENE_DIR"
    "--total-train-iters" "$BRUSH_TOTAL_STEPS_VAL"
    "--export-path" "./{dataset}/"
    "--export-name" "$SPLINE_SCENE_PLY"
)

if [[ -n "$BRUSH_MAX_SPLATS_VAL" ]]; then
    BRUSH_ARGS+=("--max-splats" "$BRUSH_MAX_SPLATS_VAL")
fi

echo "Command: $BRUSH_PATH ${BRUSH_ARGS[*]}"
echo

# Run Brush. Do NOT use set -e inside the command group — we want to capture
# the exit code and produce a clear message.
BRUSH_EXIT=0
"$BRUSH_PATH" "${BRUSH_ARGS[@]}" || BRUSH_EXIT=$?

if [[ "$BRUSH_EXIT" -ne 0 ]]; then
    die 4 "Brush training failed with exit code $BRUSH_EXIT."
fi

# ---------------------------------------------------------------------------
# Success gate — verify output
# ---------------------------------------------------------------------------

echo
echo "--- Success gate ---"

if [[ ! -f "$PLY_OUT" ]]; then
    die 4 "Brush exited 0 but scene.ply was not created at '$PLY_OUT'."
fi

PLY_SIZE=$(stat -c%s "$PLY_OUT" 2>/dev/null || echo "0")
if [[ "$PLY_SIZE" -eq 0 ]]; then
    die 4 "Brush produced an empty scene.ply at '$PLY_OUT'."
fi

echo "Output: $PLY_OUT ($PLY_SIZE bytes)"

# Count splats from the PLY header
SPLAT_COUNT=$(count_ply_vertices "$PLY_OUT" || true)
if [[ -n "$SPLAT_COUNT" ]] && [[ "$SPLAT_COUNT" -gt 0 ]]; then
    echo "Splat count: $SPLAT_COUNT"

    if [[ "$SPLAT_COUNT" -ge "$SPLAT_CRITICAL" ]]; then
        warn "Splat count ($SPLAT_COUNT) >= $SPLAT_CRITICAL — will strain Bevy renderer."
        warn "Re-train with --max-splats to cap:"
        warn "  train_brush.sh $SCENE_DIR --max-splats $SPLAT_WARNING"
    elif [[ "$SPLAT_COUNT" -ge "$SPLAT_WARNING" ]]; then
        warn "Splat count ($SPLAT_COUNT) >= $SPLAT_WARNING — watch VRAM at runtime."
        warn "If runtime performance is poor, re-train with a lower --max-splats."
    fi
else
    echo "Splat count: could not determine (PLY header parse failed)."
    echo "To check manually, open scene.ply in Brush's viewer."
fi

echo
echo "=== Stage C (Brush) complete ==="
echo "Visual asset: $PLY_OUT"
echo
echo "Next: Stage D — extract collision mesh (SuGaR → decimate → collision.glb)."
echo "See: splat-handoff/fe_stageD_mesh.md"

exit 0
