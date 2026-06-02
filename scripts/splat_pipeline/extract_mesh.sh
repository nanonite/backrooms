#!/usr/bin/env bash
# extract_mesh.sh — Stage D: Extract surface-aligned mesh from trained splat.
#
# Wraps SuGaR (Anttwo/SuGaR) or 2DGS mesh export from the same Gaussian
# reconstruction frame used by Stage C. The exported mesh is CO-REGISTERED
# with scene.ply automatically — one transform fixes both at integration.
#
# Usage:
#   extract_mesh.sh <scene_dir> [--checkpoint PATH] [--export-name NAME]
#
#   scene_dir      Per-scene working directory containing scene.ply and
#                  the Gaussian-splat checkpoint from Stage C.
#   --checkpoint   Path to the GS checkpoint directory (default: scene_dir/output).
#   --export-name  Base name for the exported mesh (default: mesh_export).
#
# Environment:
#   SUGAR_PYTHON        Python interpreter to use (default: python3).
#   SUGAR_TRAIN_SCRIPT  Path to SuGaR train.py (default: inference from $SUGAR_ROOT).
#   SUGAR_ROOT          Path to SuGaR/2DGS repo (default: $HOME/SuGaR).
#   SUGAR_LOW_POLY      Low-poly export flag (default: True).
#   SUGAR_SKIP_TEXTURE  Skip texture baking (default: True).
#
# Exit codes:
#   0  Success — mesh exported to scene_dir/<export_name>.obj.
#   1  Usage error (missing scene_dir, bad args).
#   2  Missing dependencies (python3, SuGaR train.py not found).
#   3  Input validation failed (no scene.ply, no checkpoint).
#   4  SuGaR export failed (non-zero exit from train.py).
#   5  Output mesh missing or empty after successful exit from SuGaR.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CHECKPOINT_DIR="output"
DEFAULT_EXPORT_NAME="mesh_export"

SUGAR_ROOT="${SUGAR_ROOT:-$HOME/SuGaR}"
SUGAR_PYTHON="${SUGAR_PYTHON:-python3}"
SUGAR_LOW_POLY="${SUGAR_LOW_POLY:-True}"
SUGAR_SKIP_TEXTURE="${SUGAR_SKIP_TEXTURE:-True}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: extract_mesh.sh <scene_dir> [--checkpoint PATH] [--export-name NAME]

  scene_dir      Per-scene working directory containing scene.ply + checkpoint.
  --checkpoint   Path to GS checkpoint directory (default: scene_dir/output).
  --export-name  Base name for exported mesh (default: mesh_export).

Environment:
  SUGAR_PYTHON        Python interpreter (default: python3).
  SUGAR_TRAIN_SCRIPT  Path to SuGaR train.py (default: $SUGAR_ROOT/train.py).
  SUGAR_ROOT          SuGaR/2DGS repo path (default: $HOME/SuGaR).
  SUGAR_LOW_POLY      Low-poly mode (default: True).
  SUGAR_SKIP_TEXTURE  Skip texture baking (default: True).

Exit codes: 0=success, 1=usage, 2=missing deps, 3=invalid input,
            4=export failure, 5=output missing/empty.
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

CHECKPOINT_PATH=""
EXPORT_NAME="$DEFAULT_EXPORT_NAME"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --checkpoint)
            if [[ $# -lt 2 ]]; then
                die 1 "--checkpoint requires a path argument."
            fi
            CHECKPOINT_PATH="$2"
            shift 2
            ;;
        --export-name)
            if [[ $# -lt 2 ]]; then
                die 1 "--export-name requires a name argument."
            fi
            EXPORT_NAME="$2"
            shift 2
            ;;
        --help|-h) usage ;;
        *)
            die 1 "Unknown option: $1. Use --help for usage."
            ;;
    esac
done

SCENE_DIR="$(realpath "$SCENE_DIR")"
PLY_PATH="$SCENE_DIR/scene.ply"

if [[ -z "$CHECKPOINT_PATH" ]]; then
    CHECKPOINT_PATH="$SCENE_DIR/$DEFAULT_CHECKPOINT_DIR"
fi

OUTPUT_OBJ="$SCENE_DIR/${EXPORT_NAME}.obj"

echo "=== SuGaR mesh extraction (Stage D) ==="
echo "Scene dir:    $SCENE_DIR"
echo "Checkpoint:   $CHECKPOINT_PATH"
echo "Output mesh:  $OUTPUT_OBJ"
echo

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------

PYTHON_PATH="$(command -v "$SUGAR_PYTHON" || true)"
if [[ -z "$PYTHON_PATH" ]]; then
    die 2 "Python interpreter '$SUGAR_PYTHON' not found in PATH."
fi
if [[ ! -x "$PYTHON_PATH" ]]; then
    die 2 "Python interpreter '$PYTHON_PATH' is not executable."
fi

SUGAR_TRAIN_SCRIPT="${SUGAR_TRAIN_SCRIPT:-$SUGAR_ROOT/train.py}"

if [[ ! -f "$SUGAR_TRAIN_SCRIPT" ]]; then
    die 2 "SuGaR train script not found at '$SUGAR_TRAIN_SCRIPT'."
fi

echo "Python:     $PYTHON_PATH"
echo "SuGaR:      $SUGAR_TRAIN_SCRIPT"
echo

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

if [[ ! -f "$PLY_PATH" ]]; then
    die 3 "scene.ply not found at '$PLY_PATH'. Run Stage C (train_brush.sh) first."
fi

if [[ ! -s "$PLY_PATH" ]]; then
    die 3 "scene.ply is empty at '$PLY_PATH'."
fi

if [[ ! -d "$CHECKPOINT_PATH" ]]; then
    warn "Checkpoint directory '$CHECKPOINT_PATH' does not exist."
    warn "Some SuGaR variants create the checkpoint at a different path."
    warn "Set --checkpoint or SUGAR_ROOT accordingly."
    die 3 "Checkpoint directory not found: '$CHECKPOINT_PATH'."
fi

echo "Input validation passed."
echo

# ---------------------------------------------------------------------------
# Clean stale output
# ---------------------------------------------------------------------------

rm -f "$OUTPUT_OBJ"

# ---------------------------------------------------------------------------
# Stage D — SuGaR mesh export
# ---------------------------------------------------------------------------

echo "--- Stage D: SuGaR mesh export ---"

SUGAR_ARGS=(
    -s "$SCENE_DIR"
    -c "$CHECKPOINT_PATH"
    -r density
    --export_obj True
    --low_poly "$SUGAR_LOW_POLY"
)

if [[ "$SUGAR_SKIP_TEXTURE" == "True" ]] || [[ "$SUGAR_SKIP_TEXTURE" == "true" ]] || [[ "$SUGAR_SKIP_TEXTURE" == "1" ]]; then
    SUGAR_ARGS+=(--skip_texture_baking True)
fi

echo "Command: $PYTHON_PATH $SUGAR_TRAIN_SCRIPT ${SUGAR_ARGS[*]}"
echo

SUGAR_EXIT=0
"$PYTHON_PATH" "$SUGAR_TRAIN_SCRIPT" "${SUGAR_ARGS[@]}" || SUGAR_EXIT=$?

if [[ "$SUGAR_EXIT" -ne 0 ]]; then
    die 4 "SuGaR export failed with exit code $SUGAR_EXIT."
fi

# ---------------------------------------------------------------------------
# Success gate — verify output
# ---------------------------------------------------------------------------

echo
echo "--- Success gate ---"

# SuGaR may write the mesh to a standard location; try common patterns
if [[ ! -f "$OUTPUT_OBJ" ]]; then
    # Check alternate possible output paths
    ALT_OBJ=$(find "$SCENE_DIR" -maxdepth 2 -name "${EXPORT_NAME}.obj" -print -quit 2>/dev/null || true)
    if [[ -n "$ALT_OBJ" ]] && [[ -f "$ALT_OBJ" ]]; then
        echo "Mesh found at alternate location: $ALT_OBJ"
        mv "$ALT_OBJ" "$OUTPUT_OBJ"
    fi
fi

if [[ ! -f "$OUTPUT_OBJ" ]]; then
    die 5 "SuGaR exited 0 but no mesh was produced at '$OUTPUT_OBJ'."
fi

OBJ_SIZE=$(stat -c%s "$OUTPUT_OBJ" 2>/dev/null || echo "0")
if [[ "$OBJ_SIZE" -eq 0 ]]; then
    die 5 "SuGaR produced an empty mesh at '$OUTPUT_OBJ'."
fi

echo "Output: $OUTPUT_OBJ ($OBJ_SIZE bytes)"
echo
echo "=== Stage D (SuGaR mesh export) complete ==="
echo "Mesh asset: $OUTPUT_OBJ"
echo
echo "Next: decimate_to_glb.py to produce collision.glb"
echo "See: splat-handoff/fe_stageD_mesh.md"

exit 0
