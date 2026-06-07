## Goal (Front-end Stage B, Path 1 — COLMAP/GLOMAP pose estimation) [DEFAULT PATH]
Recover camera intrinsics/extrinsics + a sparse point cloud in COLMAP binary format.
This is where the WHOLE pipeline succeeds or fails. Default to this path; use the
VGGT fallback (Path 2) ONLY when this fails.

## Implementation
`scripts/splat_pipeline/pose_colmap.sh` — the wrapper is already written and working.
This doc is the context for maintaining it, not for creating it from scratch.

## Prereqs / Blockers
- Depends on Stage A (sharp frames in `scene_dir/images/`).
- Requires COLMAP and GLOMAP. KNOWN REPO GOTCHA: COLMAP 3.13 breaks downstream tools
  here; the workspace standardized on COLMAP 3.10 (dot-vs-colon CLI syntax change).
  GLOMAP is a drop-in global mapper, much faster than vanilla COLMAP at comparable
  quality — PREFER it for the mapping step.
- **nix dev-shell deps for GLOMAP build**: `cgal` and `openimageio` must be in
  `flake.nix` packages (added in 05e2885). If building GLOMAP from source without
  the Nix shell, install CGAL + OpenImageIO packages from your system package manager
  first. These are C++ link-time deps for libcolmap, not Python packages.

## Commands (wrapper invocation)
```bash
# Default: exhaustive matching
scripts/splat_pipeline/pose_colmap.sh <scene_dir>

# Faster for long walk-through videos:
scripts/splat_pipeline/pose_colmap.sh <scene_dir> --sequential

# Keep database.db after run (for debugging):
scripts/splat_pipeline/pose_colmap.sh <scene_dir> --no-cleanup
```

### Environment variables (all have defaults)
| Variable | Default | Description |
|---|---|---|
| `POSE_MATCHER_MODE` | `exhaustive` | `sequential` or `exhaustive`. Overridden by `--sequential` CLI flag. |
| `POSE_MIN_REGISTERED` | `0.5` | Fraction of input images (0.0–1.0) that must register. If fewer register, script emits `POSE_FAILED` marker (exit 6), triggering VGGT fallback. |

### Exit codes (contract with run_pipeline.sh)
| Code | Meaning | Does it trigger VGGT fallback? |
|---|---|---|
| 0 | Success — `sparse/0/{cameras,images,points3D}.bin` exist, enough registered. | No |
| 1 | Usage error (missing `scene_dir`, bad args). | No |
| 2 | Missing dependencies (`colmap` or `glomap` not in PATH). | No — fix env |
| 3 | Input validation failed (no `images/` dir or empty). | No |
| 4 | COLMAP step failed (feature extraction or matching). | **No** — infra/quality issue, not a pose-ambiguity failure |
| 5 | GLOMAP failed (mapper produced no model, or output files missing). | **Yes** |
| 6 | `POSE_FAILED` — model exists but too few images registered. | **Yes** |

### What the wrapper does internally (for debugging/modification)
```bash
# Feature extraction + matching (COLMAP), then global mapping (GLOMAP)
colmap feature_extractor \
    --database_path "$DATABASE_PATH" \
    --image_path "$IMAGES_DIR" \
    --ImageReader.single_camera 1

# Default: colmap exhaustive_matcher --database_path "$DATABASE_PATH"
# With --sequential: colmap sequential_matcher --database_path "$DATABASE_PATH"

glomap mapper \
    --database_path "$DATABASE_PATH" \
    --image_path "$IMAGES_DIR" \
    --output_path "$SPARSE_DIR"
```

## Fallback contract with run_pipeline.sh (STAGE_B_STATUS masking gotcha — FIXED)
The pipeline driver (`run_pipeline.sh`) auto-switches to VGGT when COLMAP reports
failure. This depends on exit codes AND the `POSE_FAILED` marker file.

**CRITICAL GOTCHA (fixed in a00079b — DO NOT REINTRODUCE):** `run_pipeline.sh` MUST
reset `STAGE_B_STATUS=0` before launching VGGT:
```bash
# CORRECT (current code in run_pipeline.sh):
if [[ -x "$SCRIPT_DIR/pose_vggt.sh" ]]; then
    STAGE_B_STATUS=0    # <-- REQUIRED RESET
    "$SCRIPT_DIR/pose_vggt.sh" "$SCENE_DIR" || STAGE_B_STATUS=$?
fi
```
Without this reset, a successful VGGT run leaves `STAGE_B_STATUS` holding COLMAP's
stale failure code (5 or 6), because `|| STAGE_B_STATUS=$?` only fires on non-zero
exit. The pipeline then falsely reports failure even after valid `sparse/0/` output
was produced.

The full fallback logic in `run_pipeline.sh:164-193`:
1. Run `pose_colmap.sh`; capture exit code in `STAGE_B_STATUS`
2. If `STAGE_B_STATUS == 0` → COLMAP succeeded, continue to Stage C
3. If `STAGE_B_STATUS == 5 || 6` OR `POSE_FAILED` marker file exists → try VGGT fallback
4. If non-zero exit BUT `sparse/0/images.bin` exists → continue with available model
   (edge case: partial COLMAP success)
5. If exit code 4 or any other non-zero without sparse output → abort pipeline

## Success check (gate to Path 2)
`scene_dir/sparse/0/` contains `cameras.bin`, `images.bin`, `points3D.bin`, AND
at least `POSE_MIN_REGISTERED` fraction of input images registered (default: 0.5).
If insufficient images register, the wrapper writes a `POSE_FAILED` marker file
and exits 6, which triggers the VGGT fallback in `run_pipeline.sh`.

## Acceptance criteria
- On a cooperative capture, `scene_dir/sparse/0/{cameras,images,points3D}.bin` exist
  with the bulk of frames registered.
- The wrapper emits clear machine-readable exit codes (0=success, 5=GLOMAP fail,
  6=POSE_FAILED) that `run_pipeline.sh` uses for fallback routing.

## Escalation conditions
- Few/no images register (low parallax, blur, textureless walls) → VGGT fallback (Path 2).
- Dark video → apply the brightening pre-pass from Stage A and use exhaustive matching.
- OOM / very slow on large frame sets → switch to `sequential_matcher`, lower frame count.
- COLMAP/GLOMAP not in PATH → COLMAP 3.10 is provided by the `nerfstudio` conda env;
  GLOMAP must be built from source (cmake build with cgal + openimageio deps) and
  installed to `$HOME/.local/bin/`. In the Nix dev shell, the conda env `bin/` is
  prepended to PATH automatically, and all GLOMAP build deps are available.
- GLOMAP build failure → verify `cgal` and `openimageio` are present in the Nix dev
  shell packages (`flake.nix:46-47`). These are C++ link-time dependencies.

## Output
`scene_dir/sparse/` in COLMAP binary format. Consumed by Stage C (Brush).
Trade-off note: clean COLMAP wins on FIDELITY vs VGGT; VGGT wins on ROBUSTNESS.
