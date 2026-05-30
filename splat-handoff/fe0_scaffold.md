## Goal (Front-end Step 0 — pipeline scaffold + intake validator)
Stand up the offline pipeline skeleton and a conforming-video intake check. The
front-end runs once per scene on the GPU workstation and emits the per-scene assets.
This issue creates the directory layout, a driver script, and a validator that
REJECTS/FLAGS non-conforming video up front (cheaper than discovering failure after
hours of pose estimation).

## Environment
- GPU workstation: NVIDIA RTX 4070 Ti (12GB VRAM). VRAM is the binding constraint
  for both Brush training and SuGaR mesh extraction — keep it in mind throughout.
- Reuse the conda env strategy already in this repo where possible, but the splat
  toolchain (Brush, VGGT, SuGaR) is NEW — see the per-stage subissues for installs.

## Files to create
- `scripts/splat_pipeline/` — new directory, all front-end scripts live here.
- `scripts/splat_pipeline/run_pipeline.sh` — end-to-end driver (calls Stages A→D).
- `scripts/splat_pipeline/validate_input.py` — conforming-video intake check.
- `scripts/splat_pipeline/README.md` — documents the per-scene `scene_dir/` layout.

### Per-scene working layout (document in README)
```
scene_dir/
  video.mp4              # input
  images/                # Stage A output (sharp frames)
  database.db            # COLMAP db (Stage B)
  sparse/0/              # COLMAP-format poses: cameras.bin images.bin points3D.bin
  scene.ply              # Stage C output — VISUAL asset
  collision.glb          # Stage D output — PHYSICS asset
  alignment.toml         # filled during Back-end Step 4 ritual
```
Final assets are copied to `splat_walk/assets/splats/<scene_name>/`.

## Conforming-video HARD requirements (validator should check what it can, flag the rest)
- STATIC scene: no people/cars/wind/water motion. (Dynamic = corrupt geometry; out of scope.)
- REAL PARALLAX: camera must TRANSLATE through space (orbit/strafe/walk-through).
  Pure pan/rotate-in-place = zero parallax = reconstructs to NOTHING.
- Even, consistent lighting; no auto-exposure swings or flashing.
- Low motion blur; slow smooth movement.
- Resolution ≥ 1080p (4K ideal).
- Coverage: every surface the player will see observed from ≥2–3 distinct angles.

Design rule (enforce downstream): the splat looks correct ONLY near where the real
camera went. Confine the player to roughly the captured volume.

### `validate_input.py` — what it can actually check automatically
```python
# - probe resolution (>=1080p) via ffprobe
# - probe duration / estimated frame count at fps=3
# - sample N frames, compute mean variance-of-Laplacian (blur proxy); warn if low
# - sample N frames, estimate inter-frame motion (optical flow magnitude); warn if
#   motion is dominated by pure rotation / near-zero translation (low-parallax proxy)
# - cannot verify "static scene" automatically -> print a manual-checklist reminder
# Exit non-zero on hard failures (resolution), warn-and-continue on soft ones.
```

## Acceptance criteria
- `scripts/splat_pipeline/` exists with the four files above.
- `validate_input.py <video.mp4>` runs, reports resolution/blur/parallax proxies,
  exits non-zero on sub-1080p input, prints the manual static-scene checklist.
- `run_pipeline.sh` is a documented skeleton that sequences Stages A→D (stages may be
  stubs that call the per-stage scripts; wire them as those subissues land).

## Escalation conditions
- If the only available capture is generated/low-parallax/uncooperative video, note
  that Stage B Path 1 (COLMAP) will likely fail and the VGGT fallback (Path 2) is the
  expected route — do not treat COLMAP failure as a blocker.
