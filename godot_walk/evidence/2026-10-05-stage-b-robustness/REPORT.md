# Stage B robustness (#99) — report

**Task:** #99 Fix local pose reconstruction fallback and environment setup
**Date:** 2026-10-05 · **Worker:** Chainlink agent, workflow `chainlink_01nn3`, attempt 1/8
**Verdict:** **COMPLETE.** GLOMAP builds and installs; VGGT metadata filtering,
frame cap, OOM backoff, and bounded refusal all verified on real fixtures.

## Summary

| Question | Answer |
|---|---|
| GLOMAP builds and installs? | **Yes** — built against conda COLMAP 3.10, installed to `~/.local/bin/glomap`. `glomap --help` verified. |
| VGGT ignores non-image metadata? | **Yes** — staging symlink dir excludes frames.json; verified by tests. |
| VGGT OOM is controlled? | **Yes** — deterministic frame cap (12), OOM backoff (halving), bounded refusal (exit 7). |
| Fixture reaches usable pose stage? | **Yes** — corridor_x_e2e (31 frames) and room_large_e2e (50 frames) both succeed at 12 frames after OOM backoff from 24. |
| Bounded refusal verified? | **Yes** — VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=24 triggers POSE_REFUSED + exit 7. |
| Tests pass? | **Yes** — 95/95 in the three touched test files; full suite 700 passed, 6 failed (all pre-existing unrelated: cull_blurry cv2, train_brush.sh). |

## GLOMAP build

**Problem:** nixpkgs COLMAP 4.0.4 is incompatible with GLOMAP 1.2.0
(`Rigid3d::translation` changed from field to method in COLMAP 4.0).
The FETCH_COLMAP=ON path (GLOMAP fetches its own COLMAP) hits a glog
version conflict: nixpkgs glog 0.7.1 requires `GLOG_USE_GLOG_EXPORT` but
the system glog 0.6 in `/usr/include` shadows it.

**Fix:** Build GLOMAP against the conda env's COLMAP 3.10 (the pipeline's
standard version). The conda env has all deps (FreeImage, FLANN, LZ4, Qt5,
glog 0.7.x, Ceres, CGAL, boost, eigen). The setup-pipeline-tools.sh script
now passes `-DCOLMAP_DIR` and `-DCMAKE_PREFIX_PATH` pointing at the conda env.

**Result:** `glomap` installed to `~/.local/bin/glomap` (8.5 MB). Verified
with `glomap --help`.

## VGGT metadata filtering

**Problem:** `sample_frames.py` writes `images/frames.json`. VGGT's
`demo_colmap.py` globs every file in `images/` and calls `PIL.Image.open` on
each, crashing on `frames.json`.

**Fix:** `pose_vggt.sh` stages a symlink dir (`.vggt_staging/images/`)
containing only image files (extension filter: .jpg/.jpeg/.png). VGGT's
`demo_colmap.py` is called with `--scene_dir` pointing at the staging dir.
The manifest stays in `images/` (accepted #88 semantics preserved).

**Verification:** 65/65 tests pass in `test_vggt_budget.py` and
`test_pose_vggt.py`. The staging dir excludes non-image files.

## VGGT OOM policy

**Problem:** VGGT-1B aggregator global attention OOMs at 31 frames (11805 MiB
peak) on the 12 GB RTX 4070 Ti.

**Fix:** Deterministic frame cap + OOM backoff + bounded refusal:
- `VGGT_MAX_FRAMES` (default 24): caps the frame count, subsampled evenly.
- OOM backoff: on OOM, retry with half the frames, down to `VGGT_MIN_FRAMES` (default 4).
- Bounded refusal: if all attempts OOM, write `POSE_REFUSED` (naming budget +
  suggested settings) and exit 7.

**Verification:**
- corridor_x_e2e (31 frames): 24 OOMs → 12 succeeds. Peak GPU 11643 MiB.
- room_large_e2e (50 frames): 24 OOMs → 12 succeeds.
- Bounded refusal: VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=24 → POSE_REFUSED + exit 7.

## Files changed

| File | Change |
|---|---|
| `flake.nix` | Added poselib, faiss, glew, metis, onnxruntime, curl to dev shell |
| `environment/setup-pipeline-tools.sh` | GLOMAP builds against conda COLMAP 3.10; full cmake log capture + actionable diagnostics |
| `scripts/splat_pipeline/pose_vggt.sh` | Staging symlink dir (metadata filter), frame cap, OOM backoff, bounded refusal (exit 7) |
| `scripts/splat_pipeline/pose_colmap.sh` | Improved glomap-missing diagnostic |
| `scripts/splat_pipeline/run_pipeline.sh` | Handle exit 7 (bounded refusal) with actionable message; persist 'refused' status |
| `scripts/splat_pipeline/vggt_budget.py` | New: pure policy functions (filter, cap, backoff, classify, refuse) |
| `scripts/splat_pipeline/pipeline_state.py` | New: record_refusal() to persist 'refused' status |
| `scripts/splat_pipeline/tests/test_vggt_budget.py` | New: 32 tests for the policy module |
| `scripts/splat_pipeline/tests/test_pose_vggt.py` | Extended: 11 new integration tests |
| `scripts/splat_pipeline/README.md` | Documented exit 7, POSE_REFUSED, VGGT_MAX_FRAMES, VGGT_MIN_FRAMES |
| `godot_walk/evidence/2026-10-05-stage-b-robustness/` | New: evidence record |

## Honest limitations

- The GLOMAP build uses the conda env's COLMAP 3.10, not the nixpkgs COLMAP.
  This is intentional: the pipeline standardizes on COLMAP 3.10, and the
  nixpkgs COLMAP 4.0.4 is incompatible with GLOMAP 1.2.0. The conda env is
  self-consistent (all deps present).
- The VGGT frame cap (24) is derived from the #91 measurements (31 frames OOMs
  at 11805 MiB). The measured peak at 12 frames is 11643 MiB, confirming that
  12 frames is near the limit. The cap could be tuned further with more
  measurements.
- The bounded refusal path was tested with VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=24
  (single attempt). The full backoff path (24→12→6→4) was not tested to
  exhaustion because 12 frames succeeds.
