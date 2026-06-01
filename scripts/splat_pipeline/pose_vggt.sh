#!/usr/bin/env bash
# pose_vggt.sh — Stage B Path 2: VGGT fallback pose estimation wrapper.
#
# Feed-forward pose + dense geometry for video that makes COLMAP fail.
# VGGT (facebookresearch/vggt, CVPR 2025) predicts intrinsics/extrinsics
# + a dense point cloud in a single transformer pass, in seconds, and
# tolerates low parallax, motion blur, flat textureless walls, and
# inconsistent frames. Exports DIRECTLY to COLMAP format — DROP-IN
# replacement for Stage B Path 1 output.
#
# Usage:
#   pose_vggt.sh <scene_dir>
#
#   scene_dir    Per-scene working directory. Must contain images/ from Stage A.
#
# Environment variables (all with reasonable defaults):
#   VGGT_ROOT     Path to clone/use the VGGT repo (default: $HOME/vggt).
#   VGGT_REPO_URL URL for cloning VGGT
#                 (default: https://github.com/facebookresearch/vggt).
#   VGGT_USE_BA   Set to "1" or "true" to enable bundle adjustment.
#                 Disabled by default (lower VRAM, faster). Enable for more
#                 robust poses — but watch for OOM on 12 GB GPUs.
#   VGGT_PYTHON   Python interpreter (default: python3).
#
# Exit codes:
#   0  POSE_OK — sparse/0/{cameras,images,points3D}.bin produced.
#   1  Usage error.
#   2  Missing dependencies (python3, git).
#   3  Input validation failed (no images/ directory or empty).
#   4  VGGT clone or dependency install failed.
#   5  VGGT model run failed or produced no output.
#
# Requirements:
#   - Python 3.10+
#   - git
#   - GPU with sufficient VRAM (target: RTX 4070 Ti, 12 GB)

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VGGT_REPO_URL_DEFAULT="https://github.com/facebookresearch/vggt"
VGGT_READY_FILE=".vggt_deps_ok"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: pose_vggt.sh <scene_dir>

  scene_dir    Per-scene directory containing images/ from Stage A.

Environment:
  VGGT_ROOT     Path to VGGT repo clone (default: $HOME/vggt).
  VGGT_REPO_URL URL for cloning VGGT (default: facebookresearch/vggt).
  VGGT_USE_BA   Set to "1" or "true" to enable bundle adjustment
                (disabled by default).
  VGGT_PYTHON   Python interpreter (default: python3).

Exit codes:
  0  Success — sparse model produced.
  1  Usage error.
  2  Missing dependencies.
  3  Input validation failed.
  4  VGGT clone/install failed.
  5  VGGT model run failed.
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
SCENE_DIR="$(realpath "$SCENE_DIR")"
IMAGES_DIR="$SCENE_DIR/images"
SPARSE_DIR="$SCENE_DIR/sparse"
SPARSE_MODEL_DIR="$SPARSE_DIR/0"

VGGT_ROOT="${VGGT_ROOT:-$HOME/vggt}"
VGGT_REPO_URL="${VGGT_REPO_URL:-$VGGT_REPO_URL_DEFAULT}"
VGGT_PYTHON="${VGGT_PYTHON:-python3}"
VGGT_USE_BA="${VGGT_USE_BA:-}"
VGGT_DEMO="$VGGT_ROOT/demo_colmap.py"
VGGT_READY_PATH="$VGGT_ROOT/$VGGT_READY_FILE"

echo "=== VGGT pose estimation (Path 2 — FALLBACK) ==="
echo "Scene:       $SCENE_DIR"
echo "VGGT root:   $VGGT_ROOT"
echo "Use BA:      ${VGGT_USE_BA:-false}"
echo "Python:      $VGGT_PYTHON"
echo

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

PYTHON_BIN="$(command -v "$VGGT_PYTHON" || true)"
if [[ -z "$PYTHON_BIN" ]]; then
    die 2 "Python not found: '$VGGT_PYTHON'. Install Python 3.10+ or set VGGT_PYTHON."
fi

GIT_BIN="$(command -v git || true)"
if [[ -z "$GIT_BIN" ]]; then
    die 2 "git not found in PATH. Install git and re-run."
fi

echo "python:   $PYTHON_BIN"
echo "git:      $GIT_BIN"
echo

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

if [[ ! -d "$IMAGES_DIR" ]]; then
    die 3 "images directory not found: '$IMAGES_DIR'. Run Stage A first."
fi

INPUT_IMAGE_COUNT=$(find "$IMAGES_DIR" -maxdepth 1 -type f \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | wc -l)

if [[ "$INPUT_IMAGE_COUNT" -eq 0 ]]; then
    die 3 "No images found in '$IMAGES_DIR'. Run Stage A (frame extraction) first."
fi

echo "Input images: $INPUT_IMAGE_COUNT"
echo

# ---------------------------------------------------------------------------
# Clean stale outputs from previous runs
# ---------------------------------------------------------------------------

rm -rf "$SPARSE_DIR"
mkdir -p "$SPARSE_DIR"

# ---------------------------------------------------------------------------
# Stage B.2a — Clone/install VGGT (guarded — only if needed)
# ---------------------------------------------------------------------------

echo "--- VGGT clone/install ---"

if [[ ! -f "$VGGT_DEMO" ]]; then
    if [[ -d "$VGGT_ROOT" ]]; then
        die 4 "VGGT_ROOT ($VGGT_ROOT) exists but demo_colmap.py not found inside." \
              "Remove the directory or set VGGT_ROOT to a new path, then re-run."
    fi
    echo "Cloning VGGT from $VGGT_REPO_URL into $VGGT_ROOT ..."
    "$GIT_BIN" clone "$VGGT_REPO_URL" "$VGGT_ROOT" \
        || die 4 "Failed to clone VGGT. Check VGGT_REPO_URL and network connectivity."
else
    echo "VGGT repo found at $VGGT_ROOT (demo_colmap.py present). Skipping clone."
fi

if [[ ! -f "$VGGT_READY_PATH" ]]; then
    echo "Installing VGGT Python dependencies ..."
    "$PYTHON_BIN" -m pip install -r "$VGGT_ROOT/requirements.txt" \
        || die 4 "Failed to install VGGT requirements. Check pip and the requirements file."
    touch "$VGGT_READY_PATH"
else
    echo "VGGT dependencies already installed ($VGGT_READY_PATH exists). Skipping install."
fi

echo

# ---------------------------------------------------------------------------
# Stage B.2b — Run VGGT pose estimation
# ---------------------------------------------------------------------------

echo "--- VGGT pose estimation ---"

VGGT_ARGS=("--scene_dir=$SCENE_DIR")
if [[ "${VGGT_USE_BA:-}" == "1" ]] || [[ "${VGGT_USE_BA:-}" == "true" ]]; then
    VGGT_ARGS+=("--use_ba")
    echo "Bundle adjustment: ENABLED (uses more VRAM, more robust)."
else
    echo "Bundle adjustment: DISABLED. Set VGGT_USE_BA=1 to enable."
fi

echo "Running VGGT demo_colmap.py ..."
echo "This requires a GPU with sufficient VRAM (target: RTX 4070 Ti, 12 GB)."
echo

"$PYTHON_BIN" "$VGGT_DEMO" "${VGGT_ARGS[@]}" || die 5 "VGGT demo_colmap.py failed."

echo "VGGT pose estimation complete."
echo

# ---------------------------------------------------------------------------
# Normalize VGGT output to sparse/0/ (pipeline contract)
# ---------------------------------------------------------------------------
# VGGT demo_colmap.py writes to sparse/ directly, but the pipeline expects
# sparse/0/ (COLMAP convention inherited from Path 1). Normalize the layout.

echo "--- Normalize output ---"

VGGT_FLAT_CAMERAS="$SPARSE_DIR/cameras.bin"
VGGT_FLAT_IMAGES="$SPARSE_DIR/images.bin"
VGGT_FLAT_POINTS="$SPARSE_DIR/points3D.bin"

if [[ -f "$VGGT_FLAT_CAMERAS" ]] || [[ -f "$VGGT_FLAT_IMAGES" ]] || [[ -f "$VGGT_FLAT_POINTS" ]]; then
    echo "VGGT wrote output to $SPARSE_DIR directly. Normalizing to $SPARSE_MODEL_DIR ..."
    mkdir -p "$SPARSE_MODEL_DIR"
    for f in "$VGGT_FLAT_CAMERAS" "$VGGT_FLAT_IMAGES" "$VGGT_FLAT_POINTS"; do
        if [[ -f "$f" ]]; then
            mv "$f" "$SPARSE_MODEL_DIR/"
        fi
    done
    echo "Output normalized to $SPARSE_MODEL_DIR."
else
    echo "VGGT output not found in flat $SPARSE_DIR layout."
    if [[ -f "$SPARSE_MODEL_DIR/cameras.bin" ]]; then
        echo "Output already in $SPARSE_MODEL_DIR. Skipping normalization."
    fi
fi

echo

# ---------------------------------------------------------------------------
# Success gate — verify output files
# ---------------------------------------------------------------------------

echo "--- Success gate ---"

CAMERAS_BIN="$SPARSE_MODEL_DIR/cameras.bin"
IMAGES_BIN="$SPARSE_MODEL_DIR/images.bin"
POINTS_BIN="$SPARSE_MODEL_DIR/points3D.bin"

missing_vggt=()
for f in "$CAMERAS_BIN" "$IMAGES_BIN" "$POINTS_BIN"; do
    if [[ ! -f "$f" ]]; then
        missing_vggt+=("$(basename "$f")")
    fi
done

if [[ ${#missing_vggt[@]} -gt 0 ]]; then
    die 5 "VGGT ran but did not produce expected output: ${missing_vggt[*]}." \
          "Capture may violate static-scene or parallax requirements; re-capture is the only fix."
fi

echo "POSE_OK: $SPARSE_MODEL_DIR/{cameras,images,points3D}.bin produced."
echo

echo "=== Stage B (VGGT fallback) complete ==="
echo "Model: $SPARSE_MODEL_DIR"
exit 0
