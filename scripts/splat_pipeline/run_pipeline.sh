#!/usr/bin/env bash
# run_pipeline.sh — End-to-end splat-pipeline driver.
#
# Validates input, creates per-scene directory layout, and sequences
# Stages A → D. Most stage calls are now implemented (A, B with COLMAP+VGGT
# fallback, C, D). Integration stage is a placeholder pending #113/#114.
#
# Usage:
#   scripts/splat_pipeline/run_pipeline.sh /abs/or/relative/scene_dir
#
#   The scene_dir MUST contain a video.mp4 (the conforming input capture).
#   All intermediate and final assets are written inside scene_dir/.
#   Final assets are intended for copy to:
#     splat_walk/assets/splats/<scene_name>/{scene.ply, collision.glb, alignment.toml}
#
# Requirements:
#   - Python 3.10+ with validate_input.py in the same directory
#   - ffmpeg/ffprobe on PATH (for validate + Stage A)
#   - COLMAP 3.10 + GLOMAP (Stage B, default path)
#   - Brush (Stage C)
#   - SuGaR / 2DGS + Blender (Stage D)
#
# Per-scene layout produced (see README.md for full details):
#   scene_dir/
#     video.mp4              # input
#     images/                # Stage A output
#     database.db            # Stage B (COLMAP)
#     sparse/0/              # Stage B output (COLMAP format)
#     scene.ply              # Stage C output (VISUAL)
#     collision.glb          # Stage D output (PHYSICS)
#     alignment.toml         # filled during Back-end Step 4

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
Usage: run_pipeline.sh <scene_dir>

  scene_dir    Path to the per-scene working directory.
               Must contain video.mp4 (conforming input capture).

Stages:
  validate   Intake check (resolution, blur, parallax proxies)
  Stage A    Bounded sampling: capture_gate.py judges the capture and selects the
              frames worth reconstructing, then sample_frames.py writes only those
              at source resolution. Frames target ${TARGET_FRAMES} (small-room
              hypothesis 100-200).
              (Override: SPLAT_TARGET_FRAMES=200 run_pipeline.sh ...)
              (Legacy fixed-fps path: SPLAT_EXTRACT_FPS=0 run_pipeline.sh ...)
  Stage B    Pose estimation (COLMAP → VGGT fallback) [subissue #108]
  Stage C    Splat training (Brush)                [subissue #109]
  Stage D    Collision mesh (SuGaR → decimate)     [subissue #111]
  Stage INT  Asset copy + alignment ritual          [subissue #113 / #114]

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
SCENE_NAME="$(basename "$SCENE_DIR")"
VIDEO_PATH="$SCENE_DIR/video.mp4"

echo "=== Splat pipeline ==="
echo "Scene:    $SCENE_NAME"
echo "Dir:      $SCENE_DIR"
echo

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

if [[ ! -f "$VIDEO_PATH" ]]; then
    echo "FAIL: video.mp4 not found at '$VIDEO_PATH'." >&2
    echo "Place a conforming capture video at that path and re-run." >&2
    exit 1
fi

# Create expected subdirectories
mkdir -p "$SCENE_DIR/images"

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
#
# Stage A used to extract every frame at a fixed fps and cull the blurry ones
# afterwards. That decodes and stores the whole clip, which is exactly the
# unbounded work the sampling budget exists to avoid: the gate decodes a bounded
# sample, picks the frames worth reconstructing, and extraction writes only those,
# one seek each. It also refuses a capture that cannot support a coherent
# walkable scene, naming the capture change that would fix it.
#
# Set SPLAT_EXTRACT_FPS=0 to skip the gate and keep the old fixed-fps path, which
# is useful when debugging downstream stages against a known frame set.
# ---------------------------------------------------------------------------

echo
echo "--- Stage A: Bounded sampling and frame extraction ---"

ffmpeg_bin="$(command -v ffmpeg || true)"
if [[ -z "$ffmpeg_bin" ]]; then
    echo "FAIL: ffmpeg not found in PATH. Install ffmpeg and re-run." >&2
    exit 2
fi

if [[ "${EXTRACT_FPS}" == "0" ]]; then
    echo "SPLAT_EXTRACT_FPS=0: skipping the capture gate, extracting every 3rd frame."
    find "$SCENE_DIR/images" -maxdepth 1 -type f \( -iname 'frame_*.jpg' -o -iname 'frame_*.jpeg' -o -iname 'frame_*.png' \) -delete

    "$ffmpeg_bin" -y \
        -i "$VIDEO_PATH" \
        -vf "fps=3" \
        -q:v 2 \
        "$SCENE_DIR/images/frame_%04d.jpg"

    extracted_count=$(find "$SCENE_DIR/images" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | wc -l)
    if [[ "$extracted_count" -eq 0 ]]; then
        echo "FAIL: ffmpeg extracted zero frames. Check the video file." >&2
        exit 3
    fi
    echo "Extracted $extracted_count frames."

    echo
    echo "Culling blurry frames ..."
    python3 "$SCRIPT_DIR/cull_blurry.py" "$SCENE_DIR" || {
        echo "FAIL: blur culling failed (see above). Aborting." >&2
        exit 1
    }
    echo
else
    GATE_REPORT="$SCENE_DIR/capture_gate.json"

    set +e
    python3 "$SCRIPT_DIR/capture_gate.py" "$VIDEO_PATH" \
        --target-frames "$TARGET_FRAMES" \
        --staging-dir "$SCENE_DIR" \
        --json "$GATE_REPORT"
    gate_status=$?
    set -e

    # Exit 3 is a rejection, which is a different outcome from a crash: the gate
    # ran, measured the capture, and printed what to change about it.
    if [[ "$gate_status" -eq 3 ]]; then
        echo >&2
        echo "FAIL: this capture cannot support a coherent walkable scene." >&2
        echo "The findings above name both the measurement and the capture change" >&2
        echo "that would fix it. Nothing downstream can recover geometry the" >&2
        echo "capture does not contain; re-shoot and re-run." >&2
        exit 3
    fi
    if [[ "$gate_status" -ne 0 ]]; then
        echo "FAIL: the capture gate could not evaluate the video (exit $gate_status)." >&2
        exit "$gate_status"
    fi

    echo
    echo "Extracting the selected frames at source resolution ..."
    python3 "$SCRIPT_DIR/sample_frames.py" "$VIDEO_PATH" "$GATE_REPORT" \
        --out "$SCENE_DIR/images" || {
        echo "FAIL: frame extraction failed (see above). Aborting." >&2
        exit 1
    }

    extracted_count=$(find "$SCENE_DIR/images" -maxdepth 1 -type f -iname 'frame_*' | wc -l)
    if [[ "$extracted_count" -eq 0 ]]; then
        echo "FAIL: extraction produced zero frames. Check the video file." >&2
        exit 3
    fi
    echo "Extracted $extracted_count selected frames into $SCENE_DIR/images."
    echo
fi

# ---------------------------------------------------------------------------
# Stage B — Pose estimation (COLMAP default, VGGT fallback)
# ---------------------------------------------------------------------------

echo
echo "--- Stage B: Pose estimation ---"

STAGE_B_STATUS=0

if [[ -x "$SCRIPT_DIR/pose_colmap.sh" ]]; then
    echo "Path 1 (default): COLMAP/GLOMAP"
    "$SCRIPT_DIR/pose_colmap.sh" "$SCENE_DIR" || STAGE_B_STATUS=$?

    if [[ "$STAGE_B_STATUS" -eq 0 ]]; then
        echo "Stage B (COLMAP) succeeded."
    elif [[ "$STAGE_B_STATUS" -eq 2 ]] || [[ "$STAGE_B_STATUS" -eq 5 ]] || [[ "$STAGE_B_STATUS" -eq 6 ]] || [[ -f "$SCENE_DIR/POSE_FAILED" ]]; then
        echo "COLMAP/GLOMAP unavailable or POSE_FAILED (exit $STAGE_B_STATUS)."
        echo "Trying VGGT fallback (Path 2) ..."

        if [[ -x "$SCRIPT_DIR/pose_vggt.sh" ]]; then
            STAGE_B_STATUS=0
            "$SCRIPT_DIR/pose_vggt.sh" "$SCENE_DIR" || STAGE_B_STATUS=$?
        else
            echo "FAIL: POSE_FAILED but pose_vggt.sh not found/executable." >&2
            echo "Install VGGT or re-capture with better parallax." >&2
            exit 1
        fi

        if [[ "$STAGE_B_STATUS" -eq 0 ]]; then
            echo "Stage B (VGGT fallback) succeeded."
        else
            echo "FAIL: both COLMAP and VGGT failed. Pipeline cannot continue." >&2
            exit 1
        fi
    elif [[ -f "$SCENE_DIR/sparse/0/images.bin" ]]; then
        echo "Stage B produced a sparse model (non-zero exit $STAGE_B_STATUS)."
        echo "Continuing with available model — inspect registration count."
        STAGE_B_STATUS=0
    else
        echo "FAIL: Stage B failed with exit code $STAGE_B_STATUS." >&2
        echo "No sparse model was produced." >&2
        exit 1
    fi
else
    echo "WARN: pose_colmap.sh not found or not executable. Skipping Stage B." >&2
    echo "Expected: $SCENE_DIR/sparse/0/{cameras,images,points3D}.bin" >&2
fi

# The capture gate measures what the *camera* covered; this measures what the
# *model* covers. The gap between them is the part of the walk with no geometry,
# and it is invisible from COLMAP's exit code: a disconnected or under-registered
# reconstruction still reports success. A floor below 1.0 does not fail the run --
# a partial reconstruction is usable, but its limits have to be stated before
# Stage C trains on it.
if [[ -d "$SCENE_DIR/sparse" ]]; then
    echo
    echo "--- Registration coverage ---"
    coverage_status=0
    python3 "$SCRIPT_DIR/model_coverage.py" "$SCENE_DIR" \
        --frames-dir "$SCENE_DIR/images" || coverage_status=$?
    if [[ "$coverage_status" -eq 2 ]]; then
        echo "WARN: registration coverage is below the floor (see above)." >&2
        echo "The walkable volume is limited to the registered frames; a walk" >&2
        echo "through the excluded ones leaves the reconstruction." >&2
    fi
fi

echo

# ---------------------------------------------------------------------------
# Stage C — Splat training (Brush)
# ---------------------------------------------------------------------------

echo
echo "--- Stage C: Splat training ---"

if [[ -x "$SCRIPT_DIR/train_brush.sh" ]]; then
    "$SCRIPT_DIR/train_brush.sh" "$SCENE_DIR" || {
        echo "FAIL: Stage C (Brush training) failed (see above). Aborting." >&2
        exit 1
    }

    if [[ ! -f "$SCENE_DIR/scene.ply" ]]; then
        echo "FAIL: train_brush.sh exited 0 but scene.ply is missing at '$SCENE_DIR/scene.ply'." >&2
        exit 1
    fi

    PLY_SIZE=$(stat -c%s "$SCENE_DIR/scene.ply" 2>/dev/null || echo "0")
    if [[ "$PLY_SIZE" -eq 0 ]]; then
        echo "FAIL: scene.ply is empty (0 bytes)." >&2
        exit 1
    fi
    echo "Stage C complete — scene.ply ($PLY_SIZE bytes)."
else
    echo "FAIL: train_brush.sh not found or not executable." >&2
    echo "Expected: $SCRIPT_DIR/train_brush.sh" >&2
    echo "Install Brush (ArthurBrussee/brush) and create the wrapper." >&2
    echo "See: splat-handoff/fe_stageC_brush.md" >&2
    exit 1
fi

echo

# ---------------------------------------------------------------------------
# Stage D — Collision mesh (SuGaR → decimate → glb)
# ---------------------------------------------------------------------------

echo
echo "--- Stage D: Collision mesh ---"

CO_REGISTRATION_WARNING=$(cat <<'CO_CONTRACT'
+-------------------------------------------------------------+
|  CO-REGISTRATION CONTRACT                                   |
|                                                             |
|  collision.glb MUST share the coordinate frame of scene.ply.|
|  They come from the SAME Gaussian reconstruction — one      |
|  transform fixes both at Back-end Step 4 (alignment.toml).  |
|                                                             |
|  collision.glb is PHYSICS-ONLY: invisible, never rendered.  |
|  It needs a mesh, not a material — ugly is fine.            |
+-------------------------------------------------------------+
CO_CONTRACT
)
echo "$CO_REGISTRATION_WARNING"
echo

# -- Step D1: SuGaR mesh extraction --
if [[ -x "$SCRIPT_DIR/extract_mesh.sh" ]]; then
    echo "Step D1: Extracting mesh from splat (SuGaR) ..."
    "$SCRIPT_DIR/extract_mesh.sh" "$SCENE_DIR" || {
        echo "FAIL: SuGaR mesh extraction failed (see above). Aborting." >&2
        exit 1
    }

    MESH_OBJ="$SCENE_DIR/mesh_export.obj"
    if [[ ! -f "$MESH_OBJ" ]]; then
        echo "FAIL: extract_mesh.sh exited 0 but mesh_export.obj is missing at '$MESH_OBJ'." >&2
        exit 1
    fi

    OBJ_SIZE=$(stat -c%s "$MESH_OBJ" 2>/dev/null || echo "0")
    if [[ "$OBJ_SIZE" -eq 0 ]]; then
        echo "FAIL: mesh_export.obj is empty (0 bytes)." >&2
        exit 1
    fi
    echo "Step D1 complete — mesh_export.obj ($OBJ_SIZE bytes)."
else
    echo "FAIL: extract_mesh.sh not found or not executable." >&2
    echo "Expected: $SCRIPT_DIR/extract_mesh.sh" >&2
    echo "Install: SuGaR (Anttwo/SuGaR) or 2DGS and create the wrapper." >&2
    echo "See: splat-handoff/fe_stageD_mesh.md" >&2
    exit 1
fi

echo

# -- Step D2: Decimate + export collision.glb via Blender --
BLENDER_BIN="${BLENDER_BIN:-blender}"
BLENDER_PATH="$(command -v "$BLENDER_BIN" || true)"

if [[ -z "$BLENDER_PATH" ]]; then
    echo "FAIL: Blender binary '$BLENDER_BIN' not found in PATH." >&2
    echo "Install Blender and ensure 'blender' is on PATH." >&2
    echo "Or set BLENDER_BIN=/path/to/blender." >&2
    exit 1
fi

if [[ -f "$SCRIPT_DIR/decimate_to_glb.py" ]]; then
    echo "Step D2: Decimating mesh → collision.glb (headless Blender) ..."

    DECIMATE_LOG="$SCENE_DIR/decimate_to_glb.log"

    "$BLENDER_PATH" --background \
        --python "$SCRIPT_DIR/decimate_to_glb.py" -- \
        --scene-dir "$SCENE_DIR" \
        --target-triangles "${DECIMATE_TARGET_TRIS:-200000}" \
        --log-file "$DECIMATE_LOG" || {
        echo "FAIL: Blender decimation failed (see above or $DECIMATE_LOG)." >&2
        if [[ -f "$DECIMATE_LOG" ]]; then
            echo "--- Decimation log tail ---" >&2
            tail -20 "$DECIMATE_LOG" >&2
            echo "--- end log tail ---" >&2
        fi
        exit 1
    }

    if [[ ! -f "$SCENE_DIR/collision.glb" ]]; then
        echo "FAIL: Blender exited 0 but collision.glb is missing at '$SCENE_DIR/collision.glb'." >&2
        exit 1
    fi

    GLB_SIZE=$(stat -c%s "$SCENE_DIR/collision.glb" 2>/dev/null || echo "0")
    if [[ "$GLB_SIZE" -eq 0 ]]; then
        echo "FAIL: collision.glb is empty (0 bytes)." >&2
        exit 1
    fi

    echo "Step D2 complete — collision.glb ($GLB_SIZE bytes)."
    echo "Decimation log: $DECIMATE_LOG"
else
    echo "FAIL: decimate_to_glb.py not found at '$SCRIPT_DIR/decimate_to_glb.py'." >&2
    echo "Expected: $SCRIPT_DIR/decimate_to_glb.py" >&2
    echo "See: splat-handoff/fe_stageD_mesh.md" >&2
    exit 1
fi

echo
echo "=== Stage D complete ==="
echo "Physics asset: $SCENE_DIR/collision.glb"
echo "CO-REGISTRATION: mesh shares coordinate frame with scene.ply (same reconstruction)."
echo
echo "Post-Stage D quality notes (requires human verification):"
echo "  - Floor continuity: verify no gaps that could cause fall-through."
echo "  - Floating junk: manual inspection in Blender if physics feels lumpy."
echo "  - Co-registration: verify ONE transform aligns both mesh + splat at Step 4."

# ---------------------------------------------------------------------------
# Integration — Asset copy + alignment
# ---------------------------------------------------------------------------

echo
echo "--- Integration: Stage assets ---"

if [[ -x "$SCRIPT_DIR/stage_assets.sh" ]]; then
    "$SCRIPT_DIR/stage_assets.sh" "$SCENE_DIR"
else
    echo "FAIL: stage_assets.sh not found or not executable." >&2
    echo "Expected: $SCRIPT_DIR/stage_assets.sh" >&2
    echo "(Integration stage is required to make assets available to the Bevy runtime.)" >&2
    exit 1
fi

echo
echo "=== Pipeline complete ==="
echo "All stages finished. Assets staged in splat_walk/assets/splats/$SCENE_NAME/"
echo "Next: cd splat_walk && cargo run"
