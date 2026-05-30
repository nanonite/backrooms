## Goal (Front-end Stage A — frame extraction + blur culling)
Turn `video.mp4` into a set of SHARP frames in COLMAP-ingestible layout. Motion blur
is the #1 cause of reconstruction failure, so we extract at a modest rate and then
cull the blurriest frames.

## Prereqs / Blockers
- Depends on Front-end Step 0 (scaffold + `scene_dir/` layout).
- Requires `ffmpeg` and Python with `opencv-python` + `numpy`.

## Commands
Extract 2–4 frames/sec (more is NOT better — redundant frames slow pose estimation
without adding coverage):
```bash
mkdir -p scene_dir/images
ffmpeg -i scene_dir/video.mp4 -vf "fps=3" -q:v 2 scene_dir/images/frame_%04d.jpg
```

## Files to create
- `scripts/splat_pipeline/cull_blurry.py`

### `cull_blurry.py` (variance-of-Laplacian sharpness filter; drop blurriest ~18%)
```python
import cv2, os, glob, numpy as np
frames = sorted(glob.glob("scene_dir/images/*.jpg"))
scores = {f: cv2.Laplacian(cv2.imread(f, cv2.IMREAD_GRAYSCALE), cv2.CV_64F).var() for f in frames}
thresh = np.percentile(list(scores.values()), 18)   # drop blurriest ~18%
for f, s in scores.items():
    if s < thresh:
        os.remove(f)
print(f"kept {sum(1 for s in scores.values() if s >= thresh)} / {len(frames)} frames")
```
Parameterize the `images/` path (don't hard-code `scene_dir`) so `run_pipeline.sh`
can pass the active scene directory.

## Acceptance criteria
- `scene_dir/images/` contains only the sharp frames after culling.
- Frame count is reasonable (tens to low hundreds for a short walkthrough; thousands
  means fps too high — lower it).
- Script prints kept/total and is idempotent-safe (re-running on an already-culled
  dir doesn't crash).

## Escalation conditions
- Dark/low-contrast video makes everything blurry-looking and feature-poor → brighten
  frames before downstream pose estimation. This repo already documented a fix:
  `ffmpeg -vf "eq=gamma=3.0:contrast=1.5:brightness=0.2"` and prefer exhaustive matching.
- Too few frames survive culling → lower the percentile or raise fps and re-extract.

## Output
`scene_dir/images/` — sharp frames only. Consumed by Stage B.
