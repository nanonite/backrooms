#!/usr/bin/env bash
# colmap_and_gate.sh — frames -> COLMAP sparse model -> parallax gate.
#
# One-shot verification for a freshly generated clip. Uses plain COLMAP (the path
# that built the proven squeeze96 model); GLOMAP is NOT required. Runs the
# preflight parallax gate at the end and exits non-zero if the capture is too
# straight to reconstruct (so you never waste a ~12 min splatfacto run).
#
# Usage:
#   conda activate nerfstudio
#   scripts/splat_pipeline/colmap_and_gate.sh [video.mp4] [scene_dir]
#
# Defaults:
#   video.mp4  -> data/scenes/corridor_straight/video.mp4
#   scene_dir  -> data/scenes/corridor_walk_v2
#
# Output: <scene_dir>/images/, <scene_dir>/sparse/0/{cameras,images,points3D}.bin
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VIDEO="${1:-$ROOT/data/scenes/corridor_straight/video.mp4}"
SCENE="${2:-$ROOT/data/scenes/corridor_walk_v2}"
IMAGES="$SCENE/images"
DB="$SCENE/database.db"
SPARSE="$SCENE/sparse"

command -v ffmpeg >/dev/null || { echo "ERROR: ffmpeg not found (conda activate nerfstudio)"; exit 2; }
command -v colmap >/dev/null || { echo "ERROR: colmap not found (conda activate nerfstudio)"; exit 2; }
[[ -f "$VIDEO" ]] || { echo "ERROR: video not found: $VIDEO"; exit 1; }

echo "=== Stage A: extract frames ==="
rm -rf "$IMAGES" "$SPARSE" "$DB"
mkdir -p "$IMAGES"
# extract every frame as high-quality jpg (4s clip -> ~96-120 frames)
ffmpeg -hide_banner -loglevel error -i "$VIDEO" -qscale:v 2 "$IMAGES/frame_%04d.jpg"
N=$(find "$IMAGES" -maxdepth 1 -type f -iname '*.jpg' | wc -l)
echo "extracted $N frames -> $IMAGES"
[[ "$N" -ge 2 ]] || { echo "ERROR: too few frames extracted"; exit 3; }

echo "=== Stage B.1: COLMAP feature_extractor ==="
# use_gpu 0: GPU SIFT hits CuTexImage texture-memory errors on 192x1080p frames
colmap feature_extractor \
  --database_path "$DB" \
  --image_path "$IMAGES" \
  --ImageReader.single_camera 1 \
  --SiftExtraction.use_gpu 0

echo "=== Stage B.2: COLMAP exhaustive_matcher ==="
colmap exhaustive_matcher --database_path "$DB" --SiftMatching.use_gpu 0

echo "=== Stage B.3: COLMAP mapper ==="
mkdir -p "$SPARSE"
# Relaxed init thresholds: AI-video corridor clips have low-baseline initial pairs,
# so COLMAP's defaults (init_min_num_inliers=100) reject every pair with
# "No good initial image pair found" and register only 2 cameras. These thresholds
# let the mapper bootstrap from the weaker pairs typical of a forward walk-through.
# (Proven on clip 2: defaults -> 2 cams; relaxed -> 96 cams.)
colmap mapper --database_path "$DB" --image_path "$IMAGES" --output_path "$SPARSE" \
  --Mapper.init_min_num_inliers 30 \
  --Mapper.abs_pose_min_num_inliers 15 \
  --Mapper.init_max_error 6 \
  --Mapper.min_num_matches 15

[[ -f "$SPARSE/0/images.bin" ]] || { echo "ERROR: mapper produced no model (sparse/0 missing)"; exit 5; }

# COLMAP may emit several disjoint sub-models (sparse/0, sparse/1, ...). Pick the
# one with the most registered cameras so the gate scores the best reconstruction.
BEST="$SPARSE/0"
BEST_N=0
for d in "$SPARSE"/*/; do
  [[ -f "$d/images.bin" ]] || continue
  n=$(python3 -c "import struct,sys; print(struct.unpack('<Q', open(sys.argv[1],'rb').read(8))[0])" "$d/images.bin" 2>/dev/null || echo 0)
  if [[ "$n" -gt "$BEST_N" ]]; then BEST_N="$n"; BEST="${d%/}"; fi
done
echo "model -> $BEST ($BEST_N cameras registered)"

echo
echo "=== Gate: preflight_parallax ==="
python3 "$ROOT/scripts/splat_pipeline/preflight_parallax.py" "$BEST"
RC=$?
echo
if [[ $RC -eq 0 ]]; then
  echo "READY: parallax passed. Train with:"
  echo "  ns-train splatfacto --data $SCENE --output-dir outputs \\"
  echo "    --experiment-name corridor_walk_v2 --max-num-iterations 30000 \\"
  echo "    --vis tensorboard --viewer.quit-on-train-completion True \\"
  echo "    colmap --colmap-path ${BEST#$SCENE/} --images-path images --downscale-factor 1"
else
  echo "STOP: parallax too low — recapture per VIDEO_CAPTURE_SPEC.md before training."
fi
exit $RC
