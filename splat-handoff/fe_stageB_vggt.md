## Goal (Front-end Stage B, Path 2 — VGGT pose estimation) [FALLBACK PATH]
Feed-forward pose + dense geometry for video that makes COLMAP fail. VGGT
(facebookresearch/vggt, CVPR 2025) predicts intrinsics/extrinsics + a dense point
cloud in a single transformer pass, in seconds, and tolerates low parallax, motion
blur, flat textureless walls, and inconsistent frames. It exports DIRECTLY to COLMAP
format, so it is a DROP-IN replacement for Path 1's output.

## Prereqs / Blockers
- Depends on Stage A (frames). Triggered when the COLMAP subissue reports POSE_FAILED.
- Requires cloning + installing VGGT; GPU with enough VRAM (RTX 4070 Ti 12GB is the
  target — `--use_ba` is heavier, watch memory).

## Commands
```bash
git clone https://github.com/facebookresearch/vggt
cd vggt && pip install -r requirements.txt

# Emit COLMAP-format poses + sparse points into scene_dir/sparse/.
# --use_ba adds bundle adjustment (slower, more robust).
python demo_colmap.py --scene_dir=/abs/path/to/scene_dir --use_ba
# writes scene_dir/sparse/{cameras.bin, images.bin, points3D.bin}
```

## Files to create
- `scripts/splat_pipeline/pose_vggt.sh` — wraps the clone/install (guarded so it
  only installs once) + the `demo_colmap.py` call, parameterized on `scene_dir`.

## Acceptance criteria
- `scene_dir/sparse/{cameras,images,points3D}.bin` produced in COLMAP format,
  consumable by Stage C exactly like Path 1 output.
- `run_pipeline.sh` can route Stage A → (COLMAP, on fail → VGGT) → Stage C without
  manual file shuffling.

## Trade-off to record
VGGT poses are LESS metrically precise than a clean COLMAP run but VASTLY more robust.
For "the video isn't great but I need SOMETHING," VGGT wins. For a careful capture,
COLMAP wins on fidelity. Less metric precision = expect a fiddlier alignment ritual
(Back-end Step 4) and possibly a non-trivial scale factor.

## Escalation conditions
- VGGT OOMs with `--use_ba` on 12GB → drop `--use_ba` (faster, slightly less robust)
  or reduce frame count / resolution.
- Even VGGT produces garbage → the capture violates the static-scene or parallax hard
  requirements; re-capture is the only fix. Do not try to salvage dynamic-scene video.

## Output
`scene_dir/sparse/` in COLMAP binary format. Consumed by Stage C (Brush).
