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
#   VGGT_MAX_FRAMES  Frame cap for one attempt (default: 24). The aggregator's
#                 global attention is quadratic in the frame count; 31 frames
#                 at 1080p OOMs on the 12 GB target GPU. A larger selection is
#                 subsampled evenly, never truncated to its opening.
#   VGGT_MIN_FRAMES  Floor for the OOM backoff (default: 4). Below this the
#                 run is refused rather than attempted again.
#
# Exit codes:
#   0  POSE_OK — sparse/0/{cameras,images,points3D}.bin produced.
#   1  Usage error.
#   2  Missing dependencies (python3, git).
#   3  Input validation failed (no images/ directory or empty).
#   4  VGGT clone or dependency install failed.
#   5  VGGT model run failed or produced no output.
#   6  (reserved — was never emitted; kept so scripts parsing 1-5 are stable)
#   7  POSE_REFUSED — bounded resource refusal. Every attempt OOM'd down to
#      VGGT_MIN_FRAMES; POSE_REFUSED names the budget and the setting that
#      would change it. This is a controlled outcome, not a crash.
#
# Requirements:
#   - Python 3.10+
#   - git
#   - GPU with sufficient VRAM (target: RTX 4070 Ti, 12 GB)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VGGT_REPO_URL_DEFAULT="https://github.com/facebookresearch/vggt"
VGGT_READY_FILE=".vggt_deps_ok"
STAGING_DIR_NAME=".vggt_staging"

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
  VGGT_MAX_FRAMES  Frame cap for one attempt (default: 24).
  VGGT_MIN_FRAMES  Floor for the OOM backoff (default: 4).
  VGGT_PYTHON   Python interpreter (default: python3).

Exit codes:
  0  Success — sparse model produced.
  1  Usage error.
  2  Missing dependencies.
  3  Input validation failed.
  4  VGGT clone/install failed.
  5  VGGT model run failed.
  7  POSE_REFUSED — bounded resource refusal (see POSE_REFUSED file).
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
STAGING_DIR="$SCENE_DIR/$STAGING_DIR_NAME"

VGGT_ROOT="${VGGT_ROOT:-$HOME/vggt}"
VGGT_REPO_URL="${VGGT_REPO_URL:-$VGGT_REPO_URL_DEFAULT}"
VGGT_PYTHON="${VGGT_PYTHON:-python3}"
VGGT_USE_BA="${VGGT_USE_BA:-}"
VGGT_MAX_FRAMES="${VGGT_MAX_FRAMES:-24}"
VGGT_MIN_FRAMES="${VGGT_MIN_FRAMES:-4}"
VGGT_DEMO="$VGGT_ROOT/demo_colmap.py"
VGGT_READY_PATH="$VGGT_ROOT/$VGGT_READY_FILE"

echo "=== VGGT pose estimation (Path 2 — FALLBACK) ==="
echo "Scene:       $SCENE_DIR"
echo "VGGT root:   $VGGT_ROOT"
echo "Use BA:      ${VGGT_USE_BA:-false}"
echo "Python:      $VGGT_PYTHON"
echo "Frame cap:   $VGGT_MAX_FRAMES (min $VGGT_MIN_FRAMES)"
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

# The image count comes from the policy module, which filters to image
# extensions — the same filter the staging step applies, so the count and
# the staged set can never disagree.
INPUT_IMAGE_COUNT=$(PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -c "
import sys
from pathlib import Path
import vggt_budget
images = vggt_budget.select_image_files(Path(sys.argv[1]).iterdir())
print(len(images))
" "$IMAGES_DIR")

if [[ "$INPUT_IMAGE_COUNT" -eq 0 ]]; then
    die 3 "No images found in '$IMAGES_DIR'. Run Stage A (frame extraction) first."
fi

echo "Input images: $INPUT_IMAGE_COUNT"
echo

# ---------------------------------------------------------------------------
# Clean stale outputs from previous runs
# ---------------------------------------------------------------------------

rm -rf "$SPARSE_DIR"
rm -rf "$STAGING_DIR"
rm -f "$SCENE_DIR/POSE_REFUSED"
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
# Stage B.2b — Run VGGT pose estimation (frame cap + OOM backoff)
# ---------------------------------------------------------------------------

echo "--- VGGT pose estimation ---"

VGGT_ARGS=("--scene_dir=$STAGING_DIR")
if [[ "${VGGT_USE_BA:-}" == "1" ]] || [[ "${VGGT_USE_BA:-}" == "true" ]]; then
    VGGT_ARGS+=("--use_ba")
    echo "Bundle adjustment: ENABLED (uses more VRAM, more robust)."
else
    echo "Bundle adjustment: DISABLED. Set VGGT_USE_BA=1 to enable."
fi

echo "This requires a GPU with sufficient VRAM (target: RTX 4070 Ti, 12 GB)."
echo

# The attempt schedule: capped selection first, halving on each OOM, down to
# VGGT_MIN_FRAMES. Computed once so every attempt is deterministic.
ATTEMPT_SCHEDULE=$(PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -c "
import sys
from pathlib import Path
import vggt_budget
images = vggt_budget.select_image_files(Path(sys.argv[1]).iterdir())
for count in vggt_budget.plan_attempts(len(images), int(sys.argv[2]), int(sys.argv[3])):
    print(count)
" "$IMAGES_DIR" "$VGGT_MAX_FRAMES" "$VGGT_MIN_FRAMES") \
    || die 1 "Invalid VGGT frame budget: VGGT_MIN_FRAMES ($VGGT_MIN_FRAMES) must be <= VGGT_MAX_FRAMES ($VGGT_MAX_FRAMES)."

ATTEMPT_COUNT=0
LAST_RUN_LOG=""
REFUSAL_REASON=""

while IFS= read -r FRAMES_THIS_ATTEMPT; do
    [[ -z "$FRAMES_THIS_ATTEMPT" ]] && continue
    ATTEMPT_COUNT=$((ATTEMPT_COUNT + 1))

    echo "--- Attempt $ATTEMPT_COUNT: $FRAMES_THIS_ATTEMPT frame(s) ---"

    # Stage a symlink dir holding ONLY image files. VGGT's demo_colmap.py
    # globs every file under <scene>/images/ and calls PIL.Image.open on
    # each, so the pipeline's own metadata (frames.json) must never be
    # visible to it — a non-image file there crashes the loader.
    rm -rf "$STAGING_DIR"
    mkdir -p "$STAGING_DIR/images"
    PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -c "
import sys
from pathlib import Path
import vggt_budget
images = vggt_budget.select_image_files(Path(sys.argv[1]).iterdir())
staging = Path(sys.argv[2]) / 'images'
for index in vggt_budget.evenly_spaced_indices(len(images), int(sys.argv[3])):
    target = staging / images[index].name
    target.symlink_to(images[index])
" "$IMAGES_DIR" "$STAGING_DIR" "$FRAMES_THIS_ATTEMPT"

    STAGED_IMAGES=$(find "$STAGING_DIR/images" -maxdepth 1 -type l | wc -l)
    echo "Staged $STAGED_IMAGES image(s) in $STAGING_DIR/images (metadata excluded)."

    RUN_LOG="$STAGING_DIR/vggt_attempt_${ATTEMPT_COUNT}.log"
    set +e
    "$PYTHON_BIN" "$VGGT_DEMO" "${VGGT_ARGS[@]}" > "$RUN_LOG" 2>&1
    RUN_STATUS=$?
    set -e
    LAST_RUN_LOG="$RUN_LOG"

    if [[ "$RUN_STATUS" -eq 0 ]]; then
        echo "VGGT attempt $ATTEMPT_COUNT succeeded."
        break
    fi

    FAILURE_KIND=$(PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -c "
import sys
from pathlib import Path
import vggt_budget
print(vggt_budget.classify_failure(Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')))
" "$RUN_LOG")

    if [[ "$FAILURE_KIND" == "oom" ]]; then
        REFUSAL_REASON="CUDA out of memory at $FRAMES_THIS_ATTEMPT frame(s)"
        echo "WARN: VGGT OOM at $FRAMES_THIS_ATTEMPT frame(s). See $RUN_LOG." >&2
        if [[ "$FRAMES_THIS_ATTEMPT" -gt "$VGGT_MIN_FRAMES" ]]; then
            echo "Retrying with fewer frames (OOM backoff)."
        fi
    elif [[ "$FAILURE_KIND" == "env" ]]; then
        die 5 "VGGT environment failure (see $RUN_LOG)." \
              "The Python interpreter or its dependencies are broken — this is not a capture problem." \
              "Set VGGT_PYTHON to the conda env's Python (e.g. \$HOME/anaconda3/envs/nerfstudio/bin/python3) and re-run."
    else
        die 5 "VGGT demo_colmap.py failed (non-OOM, see $RUN_LOG)." \
              "Capture may violate static-scene or parallax requirements; re-capture is the only fix."
    fi
done <<< "$ATTEMPT_SCHEDULE"

if [[ "$ATTEMPT_COUNT" -eq 0 ]]; then
    die 5 "VGGT attempt schedule was empty. Check VGGT_MAX_FRAMES/VGGT_MIN_FRAMES."
fi

# Every attempt OOM'd: issue the bounded refusal instead of crashing.
if [[ "$RUN_STATUS" -ne 0 ]]; then
    BUDGET="RTX 4070 Ti 12 GiB (target); $INPUT_IMAGE_COUNT input images; attempts: $ATTEMPT_SCHEDULE"
    SUGGESTED="lower VGGT_MAX_FRAMES (currently $VGGT_MAX_FRAMES) or VGGT_MIN_FRAMES (currently $VGGT_MIN_FRAMES), or free VRAM and re-run"
    PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -c "
import sys
from pathlib import Path
import vggt_budget
vggt_budget.write_refusal(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4])
" "$SCENE_DIR" "$REFUSAL_REASON" "$BUDGET" "$SUGGESTED"
    echo "ERROR: every VGGT attempt OOM'd down to $VGGT_MIN_FRAMES frames." >&2
    echo "Bounded refusal written to $SCENE_DIR/POSE_REFUSED." >&2
    exit 7
fi

echo "VGGT pose estimation complete."
echo

# ---------------------------------------------------------------------------
# Normalize VGGT output to sparse/0/ (pipeline contract)
# ---------------------------------------------------------------------------
# VGGT demo_colmap.py writes to <staging>/sparse/ directly, but the pipeline
# expects <scene>/sparse/0/ (COLMAP convention inherited from Path 1).

echo "--- Normalize output ---"

VGGT_FLAT_CAMERAS="$STAGING_DIR/sparse/cameras.bin"
VGGT_FLAT_IMAGES="$STAGING_DIR/sparse/images.bin"
VGGT_FLAT_POINTS="$STAGING_DIR/sparse/points3D.bin"

if [[ -f "$VGGT_FLAT_CAMERAS" ]] || [[ -f "$VGGT_FLAT_IMAGES" ]] || [[ -f "$VGGT_FLAT_POINTS" ]]; then
    echo "VGGT wrote output to $STAGING_DIR/sparse directly. Normalizing to $SPARSE_MODEL_DIR ..."
    mkdir -p "$SPARSE_MODEL_DIR"
    for f in "$VGGT_FLAT_CAMERAS" "$VGGT_FLAT_IMAGES" "$VGGT_FLAT_POINTS"; do
        if [[ -f "$f" ]]; then
            mv "$f" "$SPARSE_MODEL_DIR/"
        fi
    done
    echo "Output normalized to $SPARSE_MODEL_DIR."
else
    echo "VGGT output not found in flat $STAGING_DIR/sparse layout."
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
