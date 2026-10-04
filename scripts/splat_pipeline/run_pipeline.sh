#!/usr/bin/env bash
# run_pipeline.sh — End-to-end splat-pipeline driver.
#
# Validates input, creates per-scene directory layout, and sequences
# Stages A → F. Supports resumability (skip unchanged stages), dry-run
# (print plan without executing), and per-stage logging.
#
# Usage:
#   scripts/splat_pipeline/run_pipeline.sh <scene_dir> [--dry-run] [--force]
#
#   scene_dir    Path to the per-scene working directory.
#                Must contain video.mp4 (the conforming input capture).
#   --dry-run    Print the plan and exit without executing any stage.
#   --force      Re-run all stages, ignoring previous successful results.
#
# Requirements:
#   - Python 3.10+ with validate_input.py in the same directory
#   - ffmpeg/ffprobe on PATH (for validate + Stage A)
#   - COLMAP 3.10 + GLOMAP (Stage B, default path)
#   - Nerfstudio Splatfacto (Stage C, default) or Brush (fallback)
#   - @playcanvas/splat-transform@3.9.0 (Stage D)
#   - Godot 4.x (Stage F, for scene verification)
#
# Per-scene layout produced (see README.md for full details):
#   scene_dir/
#     video.mp4              # input
#     images/                # Stage A output
#     database.db            # Stage B (COLMAP)
#     sparse/0/              # Stage B output (COLMAP format)
#     scene.ply              # Stage C output (VISUAL)
#     collision.glb          # Stage D output (PHYSICS)
#     alignment_manifest.json # Stage E output (CALIBRATION)
#     traversal_manifest.json # Stage E output (TRAVERSAL)
#     pipeline_state.json    # Resumability state
#     logs/                  # Per-stage logs

set -euo pipefail

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------

# Fixed-fps extraction rate for the legacy path (SPLAT_EXTRACT_FPS=0). Set to 0
# to take that path instead of the capture gate.
EXTRACT_FPS="${SPLAT_EXTRACT_FPS:-3}"

# Frames to select for reconstruction. 150 sits inside the 100-200 small-room
# hypothesis -- a starting point, not a guarantee; the gate reports which side of
# it a capture lands on rather than clamping the number.
TARGET_FRAMES="${SPLAT_TARGET_FRAMES:-150}"

# Training backend: "splatfacto" (default) or "brush" (fallback).
TRAIN_BACKEND="${TRAIN_BACKEND:-splatfacto}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Godot assets root (where stage_godot.sh copies assets).
GODOT_ASSETS_ROOT="${GODOT_ASSETS_ROOT:-$(cd "$SCRIPT_DIR/../../godot_walk/assets" && pwd)}"

usage() {
    cat <<'EOF'
Usage: run_pipeline.sh <scene_dir> [--dry-run] [--force]

  scene_dir    Path to the per-scene working directory.
               Must contain video.mp4 (conforming input capture).

Options:
  --dry-run    Print the plan and exit without executing any stage.
  --force      Re-run all stages, ignoring previous successful results.

Stages:
  validate   Intake check (resolution, blur, parallax proxies)
  Stage A    Bounded sampling: capture_gate.py judges the capture and selects the
              frames worth reconstructing, then sample_frames.py writes only those
              at source resolution. Frames target ${TARGET_FRAMES} (small-room
              hypothesis 100-200).
  Stage B    Pose estimation (COLMAP → VGGT fallback)
  Stage C    Splat training (Nerfstudio Splatfacto, Brush fallback)
  Stage D    Collision mesh (generate_collision.py via @playcanvas/splat-transform)
  Stage E    Alignment contract + traversal plan (measure_splat_frame.py, traversal_plan.py)
  Stage F    Godot staging (stage_godot.sh)

Design rule: the splat is reliable ONLY near the captured camera path.
Confine the player to roughly the captured volume.
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
shift

DRY_RUN=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --force) FORCE=true ;;
        --help|-h) usage ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Use --help for usage." >&2
            exit 1
            ;;
    esac
    shift
done

SCENE_NAME="$(basename "$SCENE_DIR")"
VIDEO_PATH="$SCENE_DIR/video.mp4"

echo "=== Splat pipeline ==="
echo "Scene:    $SCENE_NAME"
echo "Dir:      $SCENE_DIR"
echo "Dry-run:  $DRY_RUN"
echo "Force:    $FORCE"
echo

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

if [[ ! -f "$VIDEO_PATH" ]] && [[ "$DRY_RUN" != true ]]; then
    echo "FAIL: video.mp4 not found at '$VIDEO_PATH'." >&2
    echo "Place a conforming capture video at that path and re-run." >&2
    exit 1
fi

# Create expected subdirectories (not in dry-run mode)
if [[ "$DRY_RUN" != true ]]; then
    mkdir -p "$SCENE_DIR/images"
    mkdir -p "$SCENE_DIR/logs"
fi

# ---------------------------------------------------------------------------
# Resumability helper
# ---------------------------------------------------------------------------

# Check if a stage should be skipped. Returns 0 if the stage can be skipped.
# Uses pipeline_state.py to check for a previous successful run with matching
# input hash.
should_skip_stage() {
    local stage_name="$1"
    local input_hash="$2"

    if [[ "$FORCE" == true ]]; then
        return 1
    fi

    PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys
from pathlib import Path
import pipeline_state

scene_dir = Path(sys.argv[1])
stage_name = sys.argv[2]
input_hash = sys.argv[3]

record = pipeline_state.should_skip(scene_dir, stage_name, input_hash)
if record is not None:
    print('SKIP: %s (previous successful run at %s)' % (stage_name, record.timestamp))
    sys.exit(0)
else:
    sys.exit(1)
" "$SCENE_DIR" "$stage_name" "$input_hash"
}

# Record a stage result.
record_stage() {
    local stage_name="$1"
    local input_hash="$2"
    local output_hash="$3"
    local status="$4"
    local detail="${5:-}"

    PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys
from pathlib import Path
import pipeline_state

scene_dir = Path(sys.argv[1])
stage_name = sys.argv[2]
input_hash = sys.argv[3]
output_hash = sys.argv[4]
status = sys.argv[5]
detail = sys.argv[6]

if status == 'success':
    pipeline_state.record_success(scene_dir, stage_name, input_hash, output_hash, detail=detail)
else:
    pipeline_state.record_failure(scene_dir, stage_name, input_hash, detail=detail)
" "$SCENE_DIR" "$stage_name" "$input_hash" "$output_hash" "$status" "$detail"
}

# Compute the hash of a file.
file_hash() {
    PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys
from pathlib import Path
import pipeline_state
print(pipeline_state.file_hash(Path(sys.argv[1])))
" "$1"
}

# Compute a hash from settings strings.
settings_hash() {
    PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys
import pipeline_state
print(pipeline_state.compute_hash(*sys.argv[1:]))
" "$@"
}

# ---------------------------------------------------------------------------
# Dry-run: print the plan and exit
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" == true ]]; then
    echo "=== DRY RUN — plan only ==="
    echo
    echo "Stage 1: Validate input"
    echo "  python3 $SCRIPT_DIR/validate_input.py $VIDEO_PATH"
    echo
    echo "Stage A: Bounded sampling"
    echo "  python3 $SCRIPT_DIR/capture_gate.py $VIDEO_PATH --target-frames $TARGET_FRAMES --staging-dir $SCENE_DIR --json $SCENE_DIR/capture_gate.json"
    echo "  python3 $SCRIPT_DIR/sample_frames.py $VIDEO_PATH $SCENE_DIR/capture_gate.json --out $SCENE_DIR/images"
    echo
    echo "Stage B: Pose estimation (COLMAP → VGGT fallback)"
    echo "  $SCRIPT_DIR/pose_colmap.sh $SCENE_DIR"
    echo
    echo "Stage C: Splat training ($TRAIN_BACKEND)"
    if [[ "$TRAIN_BACKEND" == "splatfacto" ]]; then
        echo "  $SCRIPT_DIR/train_splatfacto.sh $SCENE_DIR"
    else
        echo "  $SCRIPT_DIR/train_brush.sh $SCENE_DIR"
    fi
    echo
    echo "Stage D: Collision mesh"
    echo "  python3 $SCRIPT_DIR/generate_collision.py --manifest $SCENE_DIR/alignment_manifest.json --ply $SCENE_DIR/scene.ply --out $SCENE_DIR/collision --report $SCENE_DIR/collision_benchmark.json"
    echo
    echo "Stage E: Alignment contract + traversal plan"
    echo "  python3 $SCRIPT_DIR/measure_splat_frame.py --ply $SCENE_DIR/scene.ply --colmap-model $SCENE_DIR/sparse/0 --dataparser-transforms $SCENE_DIR/splatfacto_output/dataparser_transforms.json --scene-id $SCENE_NAME --out $SCENE_DIR/alignment_manifest.json"
    echo "  python3 $SCRIPT_DIR/traversal_plan.py --manifest $SCENE_DIR/alignment_manifest.json --report $SCENE_DIR/collision_benchmark.json --glb $SCENE_DIR/collision.collision.glb --out $SCENE_DIR/traversal_manifest.json"
    echo
    echo "Stage F: Godot staging"
    echo "  $SCRIPT_DIR/stage_godot.sh $SCENE_DIR"
    echo
    echo "=== End of dry run ==="
    exit 0
fi

# ---------------------------------------------------------------------------
# Validate input
# ---------------------------------------------------------------------------

echo "--- Validate ---"
python3 "$SCRIPT_DIR/validate_input.py" "$VIDEO_PATH" || {
    echo "FAIL: input validation failed (see above). Aborting." >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Stage A — Bounded capture gate + selective frame extraction
# ---------------------------------------------------------------------------

STAGE_A_LOG="$SCENE_DIR/logs/stage_a.log"

echo
echo "--- Stage A: Bounded sampling and frame extraction ---" | tee "$STAGE_A_LOG"

STAGE_A_INPUT_HASH="$(file_hash "$VIDEO_PATH")"
STAGE_A_INPUT_HASH="$(settings_hash "$STAGE_A_INPUT_HASH" "$TARGET_FRAMES" "$EXTRACT_FPS")"

if should_skip_stage "stage_a" "$STAGE_A_INPUT_HASH"; then
    echo "Stage A skipped (unchanged)." | tee -a "$STAGE_A_LOG"
else
    ffmpeg_bin="$(command -v ffmpeg || true)"
    if [[ -z "$ffmpeg_bin" ]]; then
        echo "FAIL: ffmpeg not found in PATH. Install ffmpeg and re-run." >&2 | tee -a "$STAGE_A_LOG"
        record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "ffmpeg not found"
        exit 2
    fi

    # Initialize GATE_REPORT for the legacy path (SPLAT_EXTRACT_FPS=0).
    GATE_REPORT=""

    if [[ "${EXTRACT_FPS}" == "0" ]]; then
        echo "SPLAT_EXTRACT_FPS=0: skipping the capture gate, extracting every 3rd frame." | tee -a "$STAGE_A_LOG"
        find "$SCENE_DIR/images" -maxdepth 1 -type f \( -iname 'frame_*.jpg' -o -iname 'frame_*.jpeg' -o -iname 'frame_*.png' \) -delete

        "$ffmpeg_bin" -y \
            -i "$VIDEO_PATH" \
            -vf "fps=3" \
            -q:v 2 \
            "$SCENE_DIR/images/frame_%04d.jpg"

        extracted_count=$(find "$SCENE_DIR/images" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | wc -l)
        if [[ "$extracted_count" -eq 0 ]]; then
            echo "FAIL: ffmpeg extracted zero frames. Check the video file." >&2 | tee -a "$STAGE_A_LOG"
            record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "zero frames extracted"
            exit 3
        fi
        echo "Extracted $extracted_count frames." | tee -a "$STAGE_A_LOG"

        echo
        echo "Culling blurry frames ..." | tee -a "$STAGE_A_LOG"
        python3 "$SCRIPT_DIR/cull_blurry.py" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_A_LOG" || {
            echo "FAIL: blur culling failed (see above). Aborting." >&2 | tee -a "$STAGE_A_LOG"
            record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "blur culling failed"
            exit 1
        }
        echo
    else
        GATE_REPORT="$SCENE_DIR/capture_gate.json"

        set +e
        python3 "$SCRIPT_DIR/capture_gate.py" "$VIDEO_PATH" \
            --target-frames "$TARGET_FRAMES" \
            --staging-dir "$SCENE_DIR" \
            --json "$GATE_REPORT" 2>&1 | tee -a "$STAGE_A_LOG"
        gate_status=${PIPESTATUS[0]}
        set -e

        # Exit 3 is a rejection, which is a different outcome from a crash: the gate
        # ran, measured the capture, and printed what to change about it.
        if [[ "$gate_status" -eq 3 ]]; then
            echo >&2 | tee -a "$STAGE_A_LOG"
            echo "FAIL: this capture cannot support a coherent walkable scene." >&2 | tee -a "$STAGE_A_LOG"
            echo "The findings above name both the measurement and the capture change" >&2 | tee -a "$STAGE_A_LOG"
            echo "that would fix it. Nothing downstream can recover geometry the" >&2 | tee -a "$STAGE_A_LOG"
            echo "capture does not contain; re-shoot and re-run." >&2 | tee -a "$STAGE_A_LOG"
            record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "capture rejected"
            exit 3
        fi
        if [[ "$gate_status" -ne 0 ]]; then
            echo "FAIL: the capture gate could not evaluate the video (exit $gate_status)." >&2 | tee -a "$STAGE_A_LOG"
            record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "gate exit $gate_status"
            exit "$gate_status"
        fi

        echo
        echo "Extracting the selected frames at source resolution ..." | tee -a "$STAGE_A_LOG"
        python3 "$SCRIPT_DIR/sample_frames.py" "$VIDEO_PATH" "$GATE_REPORT" \
            --out "$SCENE_DIR/images" 2>&1 | tee -a "$STAGE_A_LOG" || {
            echo "FAIL: frame extraction failed (see above). Aborting." >&2 | tee -a "$STAGE_A_LOG"
            record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "frame extraction failed"
            exit 1
        }

        extracted_count=$(find "$SCENE_DIR/images" -maxdepth 1 -type f -iname 'frame_*' | wc -l)
        if [[ "$extracted_count" -eq 0 ]]; then
            echo "FAIL: extraction produced zero frames. Check the video file." >&2 | tee -a "$STAGE_A_LOG"
            record_stage "stage_a" "$STAGE_A_INPUT_HASH" "" "failed" "zero frames after extraction"
            exit 3
        fi
        echo "Extracted $extracted_count selected frames into $SCENE_DIR/images." | tee -a "$STAGE_A_LOG"
        echo
    fi

    STAGE_A_OUTPUT_HASH="$(file_hash "$GATE_REPORT" 2>/dev/null || echo "")"
    STAGE_A_OUTPUT_HASH="$(settings_hash "$STAGE_A_OUTPUT_HASH" "$extracted_count")"
    record_stage "stage_a" "$STAGE_A_INPUT_HASH" "$STAGE_A_OUTPUT_HASH" "success" "extracted $extracted_count frames"
fi

# ---------------------------------------------------------------------------
# Stage B — Pose estimation (COLMAP default, VGGT fallback)
# ---------------------------------------------------------------------------

STAGE_B_LOG="$SCENE_DIR/logs/stage_b.log"

echo
echo "--- Stage B: Pose estimation ---" | tee "$STAGE_B_LOG"

# Compute input hash from the images directory and matcher mode.
STAGE_B_INPUT_HASH="$(PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys, hashlib
from pathlib import Path
import pipeline_state

images_dir = Path(sys.argv[1])
h = hashlib.sha256()
for f in sorted(images_dir.glob('frame_*')):
    h.update(pipeline_state.file_hash(f).encode())
    h.update(b'\x00')
print(h.hexdigest())
" "$SCENE_DIR/images")"
STAGE_B_INPUT_HASH="$(settings_hash "$STAGE_B_INPUT_HASH" "${POSE_MATCHER_MODE:-exhaustive}")"

if should_skip_stage "stage_b" "$STAGE_B_INPUT_HASH"; then
    echo "Stage B skipped (unchanged)." | tee -a "$STAGE_B_LOG"
else
    STAGE_B_STATUS=0

    if [[ -x "$SCRIPT_DIR/pose_colmap.sh" ]]; then
        echo "Path 1 (default): COLMAP/GLOMAP" | tee -a "$STAGE_B_LOG"
        "$SCRIPT_DIR/pose_colmap.sh" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_B_LOG" || STAGE_B_STATUS=${PIPESTATUS[0]}

        if [[ "$STAGE_B_STATUS" -eq 0 ]]; then
            echo "Stage B (COLMAP) succeeded." | tee -a "$STAGE_B_LOG"
        elif [[ "$STAGE_B_STATUS" -eq 2 ]] || [[ "$STAGE_B_STATUS" -eq 5 ]] || [[ "$STAGE_B_STATUS" -eq 6 ]] || [[ -f "$SCENE_DIR/POSE_FAILED" ]]; then
            echo "COLMAP/GLOMAP unavailable or POSE_FAILED (exit $STAGE_B_STATUS)." | tee -a "$STAGE_B_LOG"
            echo "Trying VGGT fallback (Path 2) ..." | tee -a "$STAGE_B_LOG"

            if [[ -x "$SCRIPT_DIR/pose_vggt.sh" ]]; then
                STAGE_B_STATUS=0
                "$SCRIPT_DIR/pose_vggt.sh" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_B_LOG" || STAGE_B_STATUS=${PIPESTATUS[0]}
            else
                echo "FAIL: POSE_FAILED but pose_vggt.sh not found/executable." >&2 | tee -a "$STAGE_B_LOG"
                echo "Install VGGT or re-capture with better parallax." >&2 | tee -a "$STAGE_B_LOG"
                record_stage "stage_b" "$STAGE_B_INPUT_HASH" "" "failed" "pose_vggt.sh not found"
                exit 1
            fi

            if [[ "$STAGE_B_STATUS" -eq 0 ]]; then
                echo "Stage B (VGGT fallback) succeeded." | tee -a "$STAGE_B_LOG"
            else
                echo "FAIL: both COLMAP and VGGT failed. Pipeline cannot continue." >&2 | tee -a "$STAGE_B_LOG"
                record_stage "stage_b" "$STAGE_B_INPUT_HASH" "" "failed" "both pose methods failed"
                exit 1
            fi
        elif [[ -f "$SCENE_DIR/sparse/0/images.bin" ]]; then
            echo "Stage B produced a sparse model (non-zero exit $STAGE_B_STATUS)." | tee -a "$STAGE_B_LOG"
            echo "Continuing with available model — inspect registration count." | tee -a "$STAGE_B_LOG"
            STAGE_B_STATUS=0
        else
            echo "FAIL: Stage B failed with exit code $STAGE_B_STATUS." >&2 | tee -a "$STAGE_B_LOG"
            echo "No sparse model was produced." >&2 | tee -a "$STAGE_B_LOG"
            record_stage "stage_b" "$STAGE_B_INPUT_HASH" "" "failed" "no sparse model"
            exit 1
        fi
    else
        echo "WARN: pose_colmap.sh not found or not executable. Skipping Stage B." >&2 | tee -a "$STAGE_B_LOG"
        echo "Expected: $SCENE_DIR/sparse/0/{cameras,images,points3D}.bin" >&2 | tee -a "$STAGE_B_LOG"
    fi

    # The capture gate measures what the *camera* covered; this measures what the
    # *model* covers. The gap between them is the part of the walk with no geometry,
    # and it is invisible from COLMAP's exit code: a disconnected or under-registered
    # reconstruction still reports success. A floor below 1.0 does not fail the run --
    # a partial reconstruction is usable, but its limits have to be stated before
    # Stage C trains on it.
    if [[ -d "$SCENE_DIR/sparse" ]]; then
        echo
        echo "--- Registration coverage ---" | tee -a "$STAGE_B_LOG"
        coverage_status=0
        python3 "$SCRIPT_DIR/model_coverage.py" "$SCENE_DIR" \
            --frames-dir "$SCENE_DIR/images" 2>&1 | tee -a "$STAGE_B_LOG" || coverage_status=${PIPESTATUS[0]}
        if [[ "$coverage_status" -eq 2 ]]; then
            echo "WARN: registration coverage is below the floor (see above)." >&2 | tee -a "$STAGE_B_LOG"
            echo "The walkable volume is limited to the registered frames; a walk" >&2 | tee -a "$STAGE_B_LOG"
            echo "through the excluded ones leaves the reconstruction." >&2 | tee -a "$STAGE_B_LOG"
        fi
    fi

    echo

    STAGE_B_OUTPUT_HASH="$(PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys, hashlib
from pathlib import Path
import pipeline_state

sparse_dir = Path(sys.argv[1])
h = hashlib.sha256()
for name in ['cameras.bin', 'images.bin', 'points3D.bin']:
    f = sparse_dir / name
    h.update(pipeline_state.file_hash(f).encode())
    h.update(b'\x00')
print(h.hexdigest())
" "$SCENE_DIR/sparse/0")"
    record_stage "stage_b" "$STAGE_B_INPUT_HASH" "$STAGE_B_OUTPUT_HASH" "success" "COLMAP model produced"
fi

echo

# ---------------------------------------------------------------------------
# Stage C — Splat training (Splatfacto default, Brush fallback)
# ---------------------------------------------------------------------------

STAGE_C_LOG="$SCENE_DIR/logs/stage_c.log"

echo
echo "--- Stage C: Splat training ---" | tee "$STAGE_C_LOG"

STAGE_C_INPUT_HASH="$(PYTHONPATH="$SCRIPT_DIR" python3 -c "
import sys, hashlib
from pathlib import Path
import pipeline_state

sparse_dir = Path(sys.argv[1])
h = hashlib.sha256()
for name in ['cameras.bin', 'images.bin', 'points3D.bin']:
    f = sparse_dir / name
    h.update(pipeline_state.file_hash(f).encode())
    h.update(b'\x00')
print(h.hexdigest())
" "$SCENE_DIR/sparse/0")"
STAGE_C_INPUT_HASH="$(settings_hash "$STAGE_C_INPUT_HASH" "$TRAIN_BACKEND" "${NS_MAX_STEPS:-30000}")"

if should_skip_stage "stage_c" "$STAGE_C_INPUT_HASH"; then
    echo "Stage C skipped (unchanged)." | tee -a "$STAGE_C_LOG"
else
    if [[ "$TRAIN_BACKEND" == "splatfacto" ]]; then
        if [[ -x "$SCRIPT_DIR/train_splatfacto.sh" ]]; then
            "$SCRIPT_DIR/train_splatfacto.sh" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_C_LOG" || {
                echo "FAIL: Stage C (Splatfacto training) failed (see above)." >&2 | tee -a "$STAGE_C_LOG"
                echo "Falling back to Brush..." >&2 | tee -a "$STAGE_C_LOG"
                if [[ -x "$SCRIPT_DIR/train_brush.sh" ]]; then
                    "$SCRIPT_DIR/train_brush.sh" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_C_LOG" || {
                        echo "FAIL: Brush fallback also failed." >&2 | tee -a "$STAGE_C_LOG"
                        record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "both training backends failed"
                        exit 1
                    }
                else
                    echo "FAIL: train_brush.sh not found." >&2 | tee -a "$STAGE_C_LOG"
                    record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "train_brush.sh not found"
                    exit 1
                fi
            }
        else
            echo "FAIL: train_splatfacto.sh not found or not executable." >&2 | tee -a "$STAGE_C_LOG"
            echo "Expected: $SCRIPT_DIR/train_splatfacto.sh" >&2 | tee -a "$STAGE_C_LOG"
            record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "train_splatfacto.sh not executable"
            exit 1
        fi
    else
        if [[ -x "$SCRIPT_DIR/train_brush.sh" ]]; then
            "$SCRIPT_DIR/train_brush.sh" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_C_LOG" || {
                echo "FAIL: Stage C (Brush training) failed (see above)." >&2 | tee -a "$STAGE_C_LOG"
                record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "Brush training failed"
                exit 1
            }
        else
            echo "FAIL: train_brush.sh not found or not executable." >&2 | tee -a "$STAGE_C_LOG"
            echo "Expected: $SCRIPT_DIR/train_brush.sh" >&2 | tee -a "$STAGE_C_LOG"
            record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "train_brush.sh not executable"
            exit 1
        fi
    fi

    if [[ ! -f "$SCENE_DIR/scene.ply" ]]; then
        echo "FAIL: training exited 0 but scene.ply is missing at '$SCENE_DIR/scene.ply'." >&2 | tee -a "$STAGE_C_LOG"
        record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "scene.ply missing"
        exit 1
    fi

    PLY_SIZE=$(stat -c%s "$SCENE_DIR/scene.ply" 2>/dev/null || echo "0")
    if [[ "$PLY_SIZE" -eq 0 ]]; then
        echo "FAIL: scene.ply is empty (0 bytes)." >&2 | tee -a "$STAGE_C_LOG"
        record_stage "stage_c" "$STAGE_C_INPUT_HASH" "" "failed" "scene.ply empty"
        exit 1
    fi
    echo "Stage C complete — scene.ply ($PLY_SIZE bytes)." | tee -a "$STAGE_C_LOG"

    STAGE_C_OUTPUT_HASH="$(file_hash "$SCENE_DIR/scene.ply")"
    record_stage "stage_c" "$STAGE_C_INPUT_HASH" "$STAGE_C_OUTPUT_HASH" "success" "scene.ply produced"
fi

echo

# ---------------------------------------------------------------------------
# Stage D — Collision mesh (generate_collision.py)
# ---------------------------------------------------------------------------

STAGE_D_LOG="$SCENE_DIR/logs/stage_d.log"

echo
echo "--- Stage D: Collision mesh ---" | tee "$STAGE_D_LOG"

STAGE_D_INPUT_HASH="$(file_hash "$SCENE_DIR/scene.ply")"
STAGE_D_INPUT_HASH="$(settings_hash "$STAGE_D_INPUT_HASH" "${VOXEL_SIZE_M:-0.05}" "${EXTERIOR_FILL_M:-1.2}" "${CLUSTER_RESOLUTION_M:-0.25}")"
# Include alignment_manifest.json: generate_collision.py consumes it and validates
# its metres_per_unit/scale reference.
STAGE_D_INPUT_HASH="$(settings_hash "$STAGE_D_INPUT_HASH" "$(file_hash "$SCENE_DIR/alignment_manifest.json")")"

if should_skip_stage "stage_d" "$STAGE_D_INPUT_HASH"; then
    echo "Stage D skipped (unchanged)." | tee -a "$STAGE_D_LOG"
else
    # Check that the alignment manifest exists (needed by generate_collision.py).
    if [[ ! -f "$SCENE_DIR/alignment_manifest.json" ]]; then
        echo "WARN: alignment_manifest.json not found. Running Stage E first..." >&2 | tee -a "$STAGE_D_LOG"
        # Stage E will be run below; we'll come back to Stage D after.
        :
    else
        echo "Generating collision mesh via @playcanvas/splat-transform..." | tee -a "$STAGE_D_LOG"

        # generate_collision.py --out is a STEM, not a directory.
        # It writes <stem>.collision.glb, <stem>.voxel.json, <stem>.voxel.bin.
        COLLISION_STEM="$SCENE_DIR/collision"
        COLLISION_GLB="$COLLISION_STEM.collision.glb"
        COLLISION_REPORT="$SCENE_DIR/collision_benchmark.json"

        python3 "$SCRIPT_DIR/generate_collision.py" \
            --manifest "$SCENE_DIR/alignment_manifest.json" \
            --ply "$SCENE_DIR/scene.ply" \
            --out "$COLLISION_STEM" \
            --report "$COLLISION_REPORT" 2>&1 | tee -a "$STAGE_D_LOG" || {
            echo "FAIL: collision generation failed (see above)." >&2 | tee -a "$STAGE_D_LOG"
            record_stage "stage_d" "$STAGE_D_INPUT_HASH" "" "failed" "collision generation failed"
            exit 1
        }

        if [[ ! -f "$COLLISION_GLB" ]]; then
            echo "FAIL: generate_collision.py exited 0 but collision.glb is missing at $COLLISION_GLB." >&2 | tee -a "$STAGE_D_LOG"
            record_stage "stage_d" "$STAGE_D_INPUT_HASH" "" "failed" "collision.glb missing"
            exit 1
        fi

        GLB_SIZE=$(stat -c%s "$COLLISION_GLB" 2>/dev/null || echo "0")
        if [[ "$GLB_SIZE" -eq 0 ]]; then
            echo "FAIL: collision.glb is empty (0 bytes)." >&2 | tee -a "$STAGE_D_LOG"
            record_stage "stage_d" "$STAGE_D_INPUT_HASH" "" "failed" "collision.glb empty"
            exit 1
        fi

        echo "Stage D complete — collision.glb ($GLB_SIZE bytes)." | tee -a "$STAGE_D_LOG"

        STAGE_D_OUTPUT_HASH="$(file_hash "$COLLISION_GLB")"
        record_stage "stage_d" "$STAGE_D_INPUT_HASH" "$STAGE_D_OUTPUT_HASH" "success" "collision.glb produced"
    fi
fi

echo

# ---------------------------------------------------------------------------
# Stage E — Alignment contract + traversal plan
# ---------------------------------------------------------------------------

STAGE_E_LOG="$SCENE_DIR/logs/stage_e.log"

echo
echo "--- Stage E: Alignment contract + traversal plan ---" | tee "$STAGE_E_LOG"

# Find the dataparser transforms JSON (produced by Stage C).
DATAPARSER_TRANSFORMS=""
for candidate in \
    "$SCENE_DIR/splatfacto_output/dataparser_transforms.json" \
    "$SCENE_DIR"/splatfacto_output/*/dataparser_transforms.json; do
    if [[ -f "$candidate" ]]; then
        DATAPARSER_TRANSFORMS="$candidate"
        break
    fi
done

if [[ -z "$DATAPARSER_TRANSFORMS" ]]; then
    echo "WARN: dataparser_transforms.json not found. Stage E may fail." >&2 | tee -a "$STAGE_E_LOG"
    echo "Expected: $SCENE_DIR/splatfacto_output/dataparser_transforms.json" >&2 | tee -a "$STAGE_E_LOG"
fi

STAGE_E_INPUT_HASH="$(file_hash "$SCENE_DIR/scene.ply")"
STAGE_E_INPUT_HASH="$(settings_hash "$STAGE_E_INPUT_HASH" "$SCENE_NAME" "${TARGET_CLEAR_HEIGHT:-2.4}" "${FOOTAGE_KIND:-synthetic}")"
# Include collision.glb and Stage D settings so a collision change invalidates the traversal plan.
STAGE_E_INPUT_HASH="$(settings_hash "$STAGE_E_INPUT_HASH" "$(file_hash "$SCENE_DIR/collision.collision.glb")" "${VOXEL_SIZE_M:-0.05}" "${EXTERIOR_FILL_M:-1.2}" "${CLUSTER_RESOLUTION_M:-0.25}")"
# Include the COLMAP sparse model and dataparser_transforms.json that measure_splat_frame.py consumes.
STAGE_E_INPUT_HASH="$(settings_hash "$STAGE_E_INPUT_HASH" "$(file_hash "$SCENE_DIR/sparse/0/cameras.bin")" "$(file_hash "$SCENE_DIR/sparse/0/images.bin")" "$(file_hash "$SCENE_DIR/sparse/0/points3D.bin")" "$(file_hash "$DATAPARSER_TRANSFORMS")")"

if should_skip_stage "stage_e" "$STAGE_E_INPUT_HASH"; then
    echo "Stage E skipped (unchanged)." | tee -a "$STAGE_E_LOG"
else
    echo "Measuring alignment contract..." | tee -a "$STAGE_E_LOG"

    python3 "$SCRIPT_DIR/measure_splat_frame.py" \
        --ply "$SCENE_DIR/scene.ply" \
        --colmap-model "$SCENE_DIR/sparse/0" \
        --dataparser-transforms "$DATAPARSER_TRANSFORMS" \
        --scene-id "$SCENE_NAME" \
        --asset-path "res://assets/$SCENE_NAME/scene.ply" \
        --source-path "$SCENE_DIR/scene.ply" \
        --video "$VIDEO_PATH" \
        --footage-kind "${FOOTAGE_KIND:-synthetic}" \
        --target-clear-height "${TARGET_CLEAR_HEIGHT:-2.4}" \
        --out "$SCENE_DIR/alignment_manifest.json" 2>&1 | tee -a "$STAGE_E_LOG" || {
        echo "FAIL: alignment contract measurement failed (see above)." >&2 | tee -a "$STAGE_E_LOG"
        record_stage "stage_e" "$STAGE_E_INPUT_HASH" "" "failed" "alignment measurement failed"
        exit 1
    }

    if [[ ! -f "$SCENE_DIR/alignment_manifest.json" ]]; then
        echo "FAIL: measure_splat_frame.py exited 0 but alignment_manifest.json is missing." >&2 | tee -a "$STAGE_E_LOG"
        record_stage "stage_e" "$STAGE_E_INPUT_HASH" "" "failed" "alignment_manifest.json missing"
        exit 1
    fi

    echo "Alignment contract written to $SCENE_DIR/alignment_manifest.json" | tee -a "$STAGE_E_LOG"

    # Now that the alignment manifest exists, run Stage D if it was skipped.
    COLLISION_GLB="$SCENE_DIR/collision.collision.glb"
    if [[ ! -f "$COLLISION_GLB" ]]; then
        echo
        echo "Running Stage D (collision generation) now that the alignment manifest exists..." | tee -a "$STAGE_E_LOG"

        COLLISION_STEM="$SCENE_DIR/collision"
        COLLISION_REPORT="$SCENE_DIR/collision_benchmark.json"

        python3 "$SCRIPT_DIR/generate_collision.py" \
            --manifest "$SCENE_DIR/alignment_manifest.json" \
            --ply "$SCENE_DIR/scene.ply" \
            --out "$COLLISION_STEM" \
            --report "$COLLISION_REPORT" 2>&1 | tee -a "$STAGE_E_LOG" || {
            echo "FAIL: collision generation failed (see above)." >&2 | tee -a "$STAGE_E_LOG"
            record_stage "stage_d" "$STAGE_D_INPUT_HASH" "" "failed" "collision generation failed (in Stage E)"
            exit 1
        }

        if [[ ! -f "$COLLISION_GLB" ]]; then
            echo "FAIL: generate_collision.py exited 0 but collision.glb is missing at $COLLISION_GLB." >&2 | tee -a "$STAGE_E_LOG"
            record_stage "stage_d" "$STAGE_D_INPUT_HASH" "" "failed" "collision.glb missing (in Stage E)"
            exit 1
        fi

        GLB_SIZE=$(stat -c%s "$COLLISION_GLB" 2>/dev/null || echo "0")
        if [[ "$GLB_SIZE" -eq 0 ]]; then
            echo "FAIL: collision.glb is empty (0 bytes)." >&2 | tee -a "$STAGE_E_LOG"
            record_stage "stage_d" "$STAGE_D_INPUT_HASH" "" "failed" "collision.glb empty (in Stage E)"
            exit 1
        fi

        echo "Stage D complete — collision.glb ($GLB_SIZE bytes)." | tee -a "$STAGE_E_LOG"

        STAGE_D_OUTPUT_HASH="$(file_hash "$COLLISION_GLB")"
        record_stage "stage_d" "$STAGE_D_INPUT_HASH" "$STAGE_D_OUTPUT_HASH" "success" "collision.glb produced"
    fi

    # Derive the traversal plan.
    echo
    echo "Deriving traversal plan..." | tee -a "$STAGE_E_LOG"

    python3 "$SCRIPT_DIR/traversal_plan.py" \
        --manifest "$SCENE_DIR/alignment_manifest.json" \
        --report "$SCENE_DIR/collision_benchmark.json" \
        --glb "$COLLISION_GLB" \
        --out "$SCENE_DIR/traversal_manifest.json" 2>&1 | tee -a "$STAGE_E_LOG" || {
        echo "FAIL: traversal plan derivation failed (see above)." >&2 | tee -a "$STAGE_E_LOG"
        record_stage "stage_e" "$STAGE_E_INPUT_HASH" "" "failed" "traversal plan failed"
        exit 1
    }

    if [[ ! -f "$SCENE_DIR/traversal_manifest.json" ]]; then
        echo "FAIL: traversal_plan.py exited 0 but traversal_manifest.json is missing." >&2 | tee -a "$STAGE_E_LOG"
        record_stage "stage_e" "$STAGE_E_INPUT_HASH" "" "failed" "traversal_manifest.json missing"
        exit 1
    fi

    echo "Traversal plan written to $SCENE_DIR/traversal_manifest.json" | tee -a "$STAGE_E_LOG"

    STAGE_E_OUTPUT_HASH="$(file_hash "$SCENE_DIR/alignment_manifest.json")"
    STAGE_E_OUTPUT_HASH="$(settings_hash "$STAGE_E_OUTPUT_HASH" "$(file_hash "$SCENE_DIR/traversal_manifest.json")")"
    record_stage "stage_e" "$STAGE_E_INPUT_HASH" "$STAGE_E_OUTPUT_HASH" "success" "alignment + traversal manifests produced"
fi

echo

# ---------------------------------------------------------------------------
# Stage F — Godot staging
# ---------------------------------------------------------------------------

STAGE_F_LOG="$SCENE_DIR/logs/stage_f.log"

echo
echo "--- Stage F: Godot staging ---" | tee "$STAGE_F_LOG"

STAGE_F_INPUT_HASH="$(file_hash "$SCENE_DIR/scene.ply")"
STAGE_F_INPUT_HASH="$(settings_hash "$STAGE_F_INPUT_HASH" "$(file_hash "$SCENE_DIR/collision.collision.glb")" "$(file_hash "$SCENE_DIR/alignment_manifest.json")" "$(file_hash "$SCENE_DIR/traversal_manifest.json")")"

if should_skip_stage "stage_f" "$STAGE_F_INPUT_HASH"; then
    echo "Stage F skipped (unchanged)." | tee -a "$STAGE_F_LOG"
else
    if [[ -x "$SCRIPT_DIR/stage_godot.sh" ]]; then
        "$SCRIPT_DIR/stage_godot.sh" "$SCENE_DIR" 2>&1 | tee -a "$STAGE_F_LOG" || {
            echo "FAIL: Godot staging failed (see above)." >&2 | tee -a "$STAGE_F_LOG"
            record_stage "stage_f" "$STAGE_F_INPUT_HASH" "" "failed" "Godot staging failed"
            exit 1
        }
    else
        echo "FAIL: stage_godot.sh not found or not executable." >&2 | tee -a "$STAGE_F_LOG"
        echo "Expected: $SCRIPT_DIR/stage_godot.sh" >&2 | tee -a "$STAGE_F_LOG"
        record_stage "stage_f" "$STAGE_F_INPUT_HASH" "" "failed" "stage_godot.sh not executable"
        exit 1
    fi

    STAGE_F_OUTPUT_HASH="$(file_hash "$GODOT_ASSETS_ROOT/$SCENE_NAME/scene.ply" 2>/dev/null || echo "")"
    record_stage "stage_f" "$STAGE_F_INPUT_HASH" "$STAGE_F_OUTPUT_HASH" "success" "Godot scene staged"
fi

echo
echo "=== Pipeline complete ==="
echo "All stages finished. Assets staged in godot_walk/assets/$SCENE_NAME/"
echo "Next: cd godot_walk && godot4 --headless --script res://scripts/verify_scene.gd"
