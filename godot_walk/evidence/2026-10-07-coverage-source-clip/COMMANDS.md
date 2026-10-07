# Exact commands — #107 coverage-complete source clip

All commands run from `/workspace/backrooms-workspace` unless stated.

## 1. Inspect existing candidates (no GPU)

```bash
for f in room_large corridor_x dead_end; do
  python3 scripts/splat_pipeline/capture_gate.py "data/videos/$f.mp4" \
    --target-frames 150 \
    --staging-dir godot_walk/evidence/2026-10-07-coverage-source-clip/existing \
    --json "godot_walk/evidence/2026-10-07-coverage-source-clip/existing/gate_$f.json"
done
```

## 2. Generate the clip (network; needs OPENROUTER_API_KEY)

```bash
python3 scripts/generate_coverage_clip.py            # first candidate
python3 scripts/generate_coverage_clip.py --force    # candidate B (rejected); see REPORT §8
```

## 3. Validate, gate and sample the delivered clip (no GPU)

```bash
python3 scripts/splat_pipeline/validate_input.py data/scenes/backrooms_coverage_v1/video.mp4
python3 scripts/splat_pipeline/capture_gate.py data/scenes/backrooms_coverage_v1/video.mp4 \
    --target-frames 150 --staging-dir data/scenes/backrooms_coverage_v1 \
    --json data/scenes/backrooms_coverage_v1/capture_gate.json \
    > godot_walk/evidence/2026-10-07-coverage-source-clip/gate_stdout.txt
python3 scripts/splat_pipeline/sample_frames.py data/scenes/backrooms_coverage_v1/video.mp4 \
    data/scenes/backrooms_coverage_v1/capture_gate.json \
    --out data/scenes/backrooms_coverage_v1/frames \
    > godot_walk/evidence/2026-10-07-coverage-source-clip/sample_stdout.txt
```

## 4. Pose evidence — COLMAP on the 111 selected frames

```bash
COLMAP=~/anaconda3/envs/nerfstudio/bin/colmap
SCENE=data/scenes/backrooms_coverage_v1
rm -f "$SCENE/database.db"; rm -rf "$SCENE/sparse"; mkdir -p "$SCENE/sparse"

$COLMAP feature_extractor --database_path "$SCENE/database.db" \
    --image_path "$SCENE/frames" --ImageReader.single_camera 1 --SiftExtraction.use_gpu 0
$COLMAP sequential_matcher --database_path "$SCENE/database.db" \
    --SiftMatching.use_gpu 0 --SequentialMatching.overlap 20
$COLMAP mapper --database_path "$SCENE/database.db" --image_path "$SCENE/frames" \
    --output_path "$SCENE/sparse" \
    --Mapper.init_min_num_inliers 30 --Mapper.abs_pose_min_num_inliers 15 \
    --Mapper.init_max_error 6 --Mapper.min_num_matches 15

$COLMAP model_analyzer --path "$SCENE/sparse/1" \
    > godot_walk/evidence/2026-10-07-coverage-source-clip/colmap_model_analyzer.txt
python3 scripts/splat_pipeline/preflight_parallax.py "$SCENE/sparse/1" \
    > godot_walk/evidence/2026-10-07-coverage-source-clip/preflight_parallax.txt
```

The delivered run above is the one preserved as `sparse_seq/`; the mapper
consistently produces `86 + 45 + 5` overlapping components (see REPORT §5).

### 4b. Denser run (all 192 frames) and the GLOMAP attempt

```bash
ffmpeg -hide_banner -loglevel error -i "$SCENE/video.mp4" -qscale:v 2 "$SCENE/frames_all/frame_%04d.jpg"
$COLMAP feature_extractor --database_path "$SCENE/database_all.db" \
    --image_path "$SCENE/frames_all" --ImageReader.single_camera 1 --SiftExtraction.use_gpu 0
$COLMAP sequential_matcher --database_path "$SCENE/database_all.db" \
    --SiftMatching.use_gpu 0 --SequentialMatching.overlap 30
$COLMAP mapper --database_path "$SCENE/database_all.db" --image_path "$SCENE/frames_all" \
    --output_path "$SCENE/sparse_all" \
    --Mapper.init_min_num_inliers 30 --Mapper.abs_pose_min_num_inliers 15 \
    --Mapper.init_max_error 6 --Mapper.min_num_matches 15
python3 scripts/splat_pipeline/preflight_parallax.py "$SCENE/sparse_all/0"   # 5.01 deg

# supported global-SfM path — aborts on this database
~/.local/bin/glomap mapper --database_path "$SCENE/database.db" --output_path "$SCENE/glomap"
```

## 5. Tests

```bash
cd scripts/splat_pipeline
python3 -m pytest tests/test_coverage_clip.py -q
python3 -m pytest tests/ -q
```

## 6. Contact sheet

```bash
python3 - <<'PY'
from PIL import Image
import glob
frames = sorted(glob.glob("data/scenes/backrooms_coverage_v1/frames/frame_*.jpg"))
n = len(frames); cols, rows = 6, 4; cw, ch = 260, 146
sheet = Image.new("RGB", (cols * cw, rows * ch), (0, 0, 0))
idxs = [round(i * (n - 1) / (cols * rows - 1)) for i in range(cols * rows)]
for k, i in enumerate(idxs):
    sheet.paste(Image.open(frames[i]).convert("RGB").resize((cw, ch)),
                ((k % cols) * cw, (k // cols) * ch))
sheet.save("godot_walk/evidence/2026-10-07-coverage-source-clip/contact_sheet.jpg", quality=82)
PY
```
