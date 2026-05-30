## Goal (Front-end Stage B, Path 1 — COLMAP/GLOMAP pose estimation) [DEFAULT PATH]
Recover camera intrinsics/extrinsics + a sparse point cloud in COLMAP binary format.
This is where the WHOLE pipeline succeeds or fails. Default to this path; use the
VGGT fallback (separate subissue) ONLY when this fails.

## Prereqs / Blockers
- Depends on Stage A (sharp frames in `scene_dir/images/`).
- Requires COLMAP and GLOMAP. KNOWN REPO GOTCHA: COLMAP 3.13 breaks downstream tools
  here; the workspace standardized on COLMAP 3.10 (dot-vs-colon CLI syntax change).
  GLOMAP is a drop-in global mapper, much faster than vanilla COLMAP at comparable
  quality — PREFER it for the mapping step.

## Commands
```bash
# Feature extraction + matching (COLMAP), then global mapping (GLOMAP)
colmap feature_extractor \
    --database_path scene_dir/database.db \
    --image_path scene_dir/images \
    --ImageReader.single_camera 1

colmap exhaustive_matcher --database_path scene_dir/database.db
# For long video walkthroughs use sequential_matcher instead — FAR faster:
# colmap sequential_matcher --database_path scene_dir/database.db

glomap mapper \
    --database_path scene_dir/database.db \
    --image_path scene_dir/images \
    --output_path scene_dir/sparse
```

## Success check (gate to Path 2)
`scene_dir/sparse/0/` contains `cameras.bin`, `images.bin`, `points3D.bin`, AND most
input images registered. If a LARGE FRACTION of images failed to register, or the
point cloud looks like noise → COLMAP has failed → go to the VGGT subissue (Path 2).

## Files to create
- `scripts/splat_pipeline/pose_colmap.sh` — wraps the three commands, parameterized
  on `scene_dir`, with the success check (count registered images, exit non-zero / emit
  a `POSE_FAILED` marker so `run_pipeline.sh` can auto-switch to Path 2).

## Acceptance criteria
- On a cooperative capture, `scene_dir/sparse/0/{cameras,images,points3D}.bin` exist
  with the bulk of frames registered.
- The wrapper emits a clear machine-readable success/fail signal for the driver.

## Escalation conditions
- Few/no images register (low parallax, blur, textureless walls) → VGGT fallback.
- Dark video → apply the brightening pre-pass from Stage A and use exhaustive matching.
- OOM / very slow on large frame sets → switch to `sequential_matcher`, lower frame count.

## Output
`scene_dir/sparse/` in COLMAP binary format. Consumed by Stage C (Brush).
Trade-off note: clean COLMAP wins on FIDELITY vs VGGT; VGGT wins on ROBUSTNESS.
