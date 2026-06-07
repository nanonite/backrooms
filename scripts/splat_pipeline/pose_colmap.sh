#!/usr/bin/env bash
# pose_colmap.sh — Stage B Path 1: COLMAP/GLOMAP pose estimation wrapper.
#
# Recovers camera intrinsics/extrinsics + a sparse point cloud from sharp
# frames produced by Stage A. Uses COLMAP (3.10) for feature extraction and
# matching, then GLOMAP for global mapping. This is the DEFAULT pose path;
# on failure the pipeline tries the VGGT fallback (pose_vggt.sh, Path 2).
#
# Usage:
#   pose_colmap.sh <scene_dir> [--sequential] [--no-cleanup]
#
#   scene_dir    Per-scene working directory. Must contain images/ from Stage A.
#   --sequential Use sequential_matcher instead of exhaustive (faster for long
#                walk-through videos).
#   --no-cleanup Keep the COLMAP database.db after the run (default: delete).
#
# Environment:
#   POSE_MATCHER_MODE    "sequential" or "exhaustive" (default: exhaustive).
#                        Overridden by --sequential.
#   POSE_MIN_REGISTERED  Minimum fraction of images that must register (0.0–1.0).
#                        Default: 0.5. If fewer register, emits POSE_FAILED.
#
# Exit codes:
#   0  Success — sparse/0/{cameras,images,points3D}.bin exist, enough registered.
#   1  Usage error (missing scene_dir, bad args).
#   2  Missing dependencies (colmap or glomap not in PATH).
#   3  Input validation failed (no images/ dir or empty).
#   4  COLMAP step failed (feature extraction or matching).
#   5  GLOMAP failed (mapper produced no model).
#   6  POSE_FAILED — model exists but too few images registered.
#
# Requirements:
#   - COLMAP 3.10 (KNOWN GOTCHA: 3.13 breaks downstream tools with dot-vs-colon
#     CLI syntax change; the workspace standardizes on 3.10).
#   - GLOMAP (drop-in global mapper, faster than vanilla COLMAP at comparable quality).

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POSE_FAILED_FILE="POSE_FAILED"
MIN_REGISTERED_FRACTION_DEFAULT="0.5"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: pose_colmap.sh <scene_dir> [--sequential] [--no-cleanup]

  scene_dir      Per-scene directory containing images/ from Stage A.

Options:
  --sequential   Use sequential_matcher (faster for long walk-through videos).
  --no-cleanup   Keep database.db after the run.

Environment:
  POSE_MATCHER_MODE      "sequential" or "exhaustive" (default: exhaustive).
  POSE_MIN_REGISTERED    Minimum fraction of input images to register (0.0–1.0,
                         default: 0.5).

Exit codes:
  0  Success — model produced with sufficient registered images.
  1  Usage error.
  2  Missing dependencies.
  3  Input validation failed.
  4  COLMAP step failed.
  5  GLOMAP failed.
  6  POSE_FAILED — too few images registered.
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

# Count registered images by reading the uint64 header from the COLMAP binary.
# Returns 0 and prints the count, or returns 1 on failure.
count_registered_images() {
    local images_bin="$1"
    if [[ ! -f "$images_bin" ]]; then
        return 1
    fi
    python3 -c "
import struct, sys
try:
    with open(sys.argv[1], 'rb') as f:
        header = f.read(8)
        if len(header) < 8:
            sys.exit(1)
        count = struct.unpack('<Q', header)[0]
        print(count)
except Exception:
    sys.exit(1)
" "$images_bin" 2>/dev/null
}

# Mark the scene_dir as POSE_FAILED with a reason file.
mark_pose_failed() {
    local scene_dir="$1"
    local reason="$2"
    local marker="$scene_dir/$POSE_FAILED_FILE"
    echo "POSE_FAILED: $reason" > "$marker"
    echo "POSE_FAILED: $reason (marker written to $marker)"
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

MATCHER_MODE="${POSE_MATCHER_MODE:-exhaustive}"
DO_CLEANUP=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sequential) MATCHER_MODE="sequential" ;;
        --no-cleanup) DO_CLEANUP=false ;;
        --help|-h) usage ;;
        *)
            die 1 "Unknown option: $1. Use --help for usage."
            ;;
    esac
    shift
done

SCENE_DIR="$(realpath "$SCENE_DIR")"
IMAGES_DIR="$SCENE_DIR/images"
DATABASE_PATH="$SCENE_DIR/database.db"
SPARSE_DIR="$SCENE_DIR/sparse"
SPARSE_MODEL_DIR="$SPARSE_DIR/0"
MIN_REGISTERED_FRACTION="${POSE_MIN_REGISTERED:-$MIN_REGISTERED_FRACTION_DEFAULT}"

echo "=== COLMAP/GLOMAP pose estimation (Path 1) ==="
echo "Scene:    $SCENE_DIR"
echo "Matcher:  $MATCHER_MODE"
echo "Cleanup:  $DO_CLEANUP"
echo "Min reg:  ${MIN_REGISTERED_FRACTION} (fraction of input images)"
echo

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

COLMAP_BIN="$(command -v colmap || true)"
GLOMAP_BIN="$(command -v glomap || true)"

if [[ -z "$COLMAP_BIN" ]]; then
    die 2 "colmap not found in PATH. Install COLMAP 3.10 and re-run."
fi
if [[ -z "$GLOMAP_BIN" ]]; then
    die 2 "glomap not found in PATH. Install GLOMAP and re-run."
fi

echo "colmap:   $COLMAP_BIN"
echo "glomap:   $GLOMAP_BIN"
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

if "$DO_CLEANUP"; then
    rm -f "$DATABASE_PATH"
fi
rm -rf "$SPARSE_DIR"
rm -f "$SCENE_DIR/$POSE_FAILED_FILE"

mkdir -p "$SPARSE_DIR"

# ---------------------------------------------------------------------------
# Stage B.1 — COLMAP feature extraction
# ---------------------------------------------------------------------------

echo "--- Stage B.1: COLMAP feature extraction ---"

"$COLMAP_BIN" feature_extractor \
    --database_path "$DATABASE_PATH" \
    --image_path "$IMAGES_DIR" \
    --ImageReader.single_camera 1 \
    || die 4 "COLMAP feature extraction failed."

echo "Feature extraction complete."
echo

# ---------------------------------------------------------------------------
# Stage B.2 — COLMAP matching
# ---------------------------------------------------------------------------

echo "--- Stage B.2: COLMAP matching ($MATCHER_MODE) ---"

if [[ "$MATCHER_MODE" == "sequential" ]]; then
    "$COLMAP_BIN" sequential_matcher --database_path "$DATABASE_PATH" \
        || die 4 "COLMAP sequential matching failed."
else
    "$COLMAP_BIN" exhaustive_matcher --database_path "$DATABASE_PATH" \
        || die 4 "COLMAP exhaustive matching failed."
fi

echo "Matching complete."
echo

# ---------------------------------------------------------------------------
# Stage B.3 — GLOMAP global mapping
# ---------------------------------------------------------------------------

echo "--- Stage B.3: GLOMAP global mapping ---"

"$GLOMAP_BIN" mapper \
    --database_path "$DATABASE_PATH" \
    --image_path "$IMAGES_DIR" \
    --output_path "$SPARSE_DIR" \
    || die 5 "GLOMAP mapper failed."

echo "GLOMAP mapping complete."
echo

# ---------------------------------------------------------------------------
# Success gate — verify output and count registered images
# ---------------------------------------------------------------------------

echo "--- Success gate ---"

CAMERAS_BIN="$SPARSE_MODEL_DIR/cameras.bin"
IMAGES_BIN="$SPARSE_MODEL_DIR/images.bin"
POINTS_BIN="$SPARSE_MODEL_DIR/points3D.bin"

if [[ ! -f "$CAMERAS_BIN" ]]; then
    mark_pose_failed "$SCENE_DIR" "cameras.bin not found in $SPARSE_MODEL_DIR"
    die 5 "GLOMAP produced no model — cameras.bin missing."
fi
if [[ ! -f "$IMAGES_BIN" ]]; then
    mark_pose_failed "$SCENE_DIR" "images.bin not found in $SPARSE_MODEL_DIR"
    die 5 "GLOMAP produced no model — images.bin missing."
fi
if [[ ! -f "$POINTS_BIN" ]]; then
    mark_pose_failed "$SCENE_DIR" "points3D.bin not found in $SPARSE_MODEL_DIR"
    die 5 "GLOMAP produced no model — points3D.bin missing."
fi

REGISTERED_COUNT=$(count_registered_images "$IMAGES_BIN" || true)
if [[ -z "$REGISTERED_COUNT" ]]; then
    warn "Could not read registered image count from images.bin."
    REGISTERED_COUNT=0
fi

MIN_REQUIRED=$(python3 -c "
import math, sys
count = int(sys.argv[1])
fraction = float(sys.argv[2])
if count > 0:
    threshold = max(1, int(math.ceil(count * fraction)))
else:
    threshold = 0
print(threshold)
" "$INPUT_IMAGE_COUNT" "$MIN_REGISTERED_FRACTION" 2>/dev/null || echo "0")

echo "Registered images: $REGISTERED_COUNT / $INPUT_IMAGE_COUNT (minimum required: $MIN_REQUIRED)"

if [[ "$REGISTERED_COUNT" -lt "$MIN_REQUIRED" ]]; then
    mark_pose_failed "$SCENE_DIR" \
        "Only $REGISTERED_COUNT/$INPUT_IMAGE_COUNT images registered (threshold: ${MIN_REGISTERED_FRACTION}). Low parallax, blur, or textureless scene — try VGGT fallback (Path 2)."
    die 6 "POSE_FAILED: insufficient registered images ($REGISTERED_COUNT < $MIN_REQUIRED)."
fi

echo "POSE_OK: $REGISTERED_COUNT images registered."
echo

# ---------------------------------------------------------------------------
# Cleanup (unless --no-cleanup)
# ---------------------------------------------------------------------------

if "$DO_CLEANUP"; then
    rm -f "$DATABASE_PATH"
    echo "Cleaned up database.db."
fi

echo "=== Stage B (COLMAP/GLOMAP) complete ==="
echo "Model: $SPARSE_MODEL_DIR"
exit 0
