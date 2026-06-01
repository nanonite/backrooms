#!/usr/bin/env bash
# run_pipeline.sh — End-to-end splat-pipeline driver.
#
# Validates input, creates per-scene directory layout, and sequences
# Stages A → D. Each stage script is invoked here as it lands via its
# own subissue. Currently ALL stage calls are PLACEHOLDERS.
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

EXTRACT_FPS="${SPLAT_EXTRACT_FPS:-3}"

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
  Stage A    Frame extraction at ${EXTRACT_FPS} fps + blur culling  [subissue #107]
              (Override fps: SPLAT_EXTRACT_FPS=2 run_pipeline.sh ...)
  Stage B    Pose estimation (COLMAP → VGGT fallback) [subissue #108]
  Stage C    Splat training (Brush)                [subissue #109]
  Stage D    Collision mesh (SuGaR → decimate)     [subissue #110]
  Stage INT  Asset copy + alignment ritual          [subissue #111]

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
# Stage A — Frame extraction + blur culling
# ---------------------------------------------------------------------------

echo
echo "--- Stage A: Frame extraction ---"

ffmpeg_bin="$(command -v ffmpeg || true)"
if [[ -z "$ffmpeg_bin" ]]; then
    echo "FAIL: ffmpeg not found in PATH. Install ffmpeg and re-run." >&2
    exit 2
fi

echo "Extracting frames at ${EXTRACT_FPS} fps from $VIDEO_PATH ..."

# Clear stale frames from previous extractions so downstream stages only
# see frames from the current video/settings.
find "$SCENE_DIR/images" -maxdepth 1 -type f \( -iname 'frame_*.jpg' -o -iname 'frame_*.jpeg' -o -iname 'frame_*.png' \) -delete

"$ffmpeg_bin" -y \
    -i "$VIDEO_PATH" \
    -vf "fps=${EXTRACT_FPS}" \
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

# ---------------------------------------------------------------------------
# Stage B — Pose estimation (COLMAP default, VGGT fallback)
# ---------------------------------------------------------------------------

echo "--- Stage B: Pose estimation (subissue #108) ---"
echo "NOT YET IMPLEMENTED. Will call: pose_colmap.sh $SCENE_DIR"
echo "Expected: $SCENE_DIR/sparse/0/{cameras,images,points3D}.bin"
echo "Fallback script: pose_vggt.sh for low-parallax videos."
echo "Install: COLMAP 3.10, GLOMAP (default); VGGT (fallback)."
echo "See: splat-handoff/fe_stageB_colmap.md, fe_stageB_vggt.md"
echo

# ---------------------------------------------------------------------------
# Stage C — Splat training (Brush)
# ---------------------------------------------------------------------------

echo "--- Stage C: Splat training (subissue #109) ---"
echo "NOT YET IMPLEMENTED. Will call: train_brush.sh $SCENE_DIR"
echo "Expected: $SCENE_DIR/scene.ply (VISUAL asset)."
echo "Install: Brush (ArthurBrussee/brush)."
echo "VRAM note: 12GB VRAM on RTX 4070 Ti; cap with --max-splats if needed."
echo "See: splat-handoff/fe_stageC_brush.md"
echo

# ---------------------------------------------------------------------------
# Stage D — Collision mesh (SuGaR → decimate → glb)
# ---------------------------------------------------------------------------

echo "--- Stage D: Collision mesh (subissue #110) ---"
echo "NOT YET IMPLEMENTED. Will call: extract_mesh.sh $SCENE_DIR && decimate_to_glb.py $SCENE_DIR"
echo "Expected: $SCENE_DIR/collision.glb (PHYSICS asset, invisible, <200k tris)."
echo "Install: SuGaR / 2DGS, Blender (headless)."
echo "CRITICAL: mesh must be co-registered with scene.ply (same reconstruction frame)."
echo "See: splat-handoff/fe_stageD_mesh.md"
echo

# ---------------------------------------------------------------------------
# Integration — Asset copy + alignment
# ---------------------------------------------------------------------------

echo "--- Integration (subissue #111) ---"
echo "NOT YET IMPLEMENTED."
echo "After all stages complete, copy assets to:"
echo "  splat_walk/assets/splats/$SCENE_NAME/"
echo "Expected files: scene.ply, collision.glb, alignment.toml"
echo "See: splat-handoff/handoff_contract.md, splat-handoff/integ5_full.md"
echo

echo "=== Pipeline scaffold complete ==="
echo "Stages A–D are placeholders. Implement each via its subissue to run the full pipeline."
