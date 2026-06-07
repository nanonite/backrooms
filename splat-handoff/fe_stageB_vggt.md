## Goal (Front-end Stage B, Path 2 — VGGT pose estimation) [FALLBACK PATH]
Feed-forward pose + dense geometry for video that makes COLMAP fail. VGGT
(facebookresearch/vggt, CVPR 2025) predicts intrinsics/extrinsics + a dense point
cloud in a single transformer pass, in seconds, and tolerates low parallax, motion
blur, flat textureless walls, and inconsistent frames. Exports DIRECTLY to COLMAP
format, so it is a DROP-IN replacement for Path 1's output.

## Implementation
`scripts/splat_pipeline/pose_vggt.sh` — the wrapper is already written and working.
This doc is the context for maintaining it, not for creating it from scratch.

## Prereqs / Blockers
- Depends on Stage A (frames). Triggered when the COLMAP stage reports exit code 5
  or 6 (or a `POSE_FAILED` marker file exists). The pipeline driver
  (`run_pipeline.sh`) handles this routing automatically.
- Requires VGGT cloned to `$VGGT_ROOT` (script auto-clones if missing).
- Requires Python 3.10+ and `git` on PATH.
- GPU with enough VRAM (RTX 4070 Ti 12GB is the target).

### Environment defaults (set in flake.nix + honored by scripts)
| Variable | Default (in script) | Override in flake.nix shellHook |
|---|---|---|
| `VGGT_ROOT` | `$HOME/vggt` | `/home/user/backrooms-workspace/build/vggt` |
| `SUGAR_ROOT` | `$HOME/SuGaR` | `/home/user/backrooms-workspace/build/SuGaR` |
| `VGGT_REPO_URL` | `https://github.com/facebookresearch/vggt` | (not overridden) |
| `VGGT_USE_BA` | empty (disabled) | (not overridden) |
| `VGGT_PYTHON` | `python3` | (not overridden) |

**These were moved from `$HOME` paths to workspace-local `build/` paths in 76e794d.**
The script default is still `$HOME/vggt`, but the Nix dev shell (`flake.nix:80-81`)
exports the workspace-local path as the default. When NOT running inside the Nix shell,
set `VGGT_ROOT` before invoking the script.

**SuGaR presence check** (flake.nix:100) uses `extract_mesh.py` (not `train.py`):
`[[ -f "$SUGAR_ROOT/extract_mesh.py" ]]` — this was fixed in a07eef2 because earlier
SuGaR distributions named the entry point differently. The Stage D wrapper
(`extract_mesh.sh`) also validates the presence of the SuGaR train script at
`$SUGAR_ROOT/train.py`, but the flake.nix welcome-banner check uses `extract_mesh.py`
to confirm SuGaR was installed successfully.

**GLOMAP build deps** (also applies when running VGGT as fallback, because GLOMAP
must still be compiled even if it's not invoked): `cgal` and `openimageio` are
required in the Nix dev shell packages (`flake.nix:46-47`, added in 05e2885).
These are C++ link-time dependencies for building GLOMAP from source.

## Commands (wrapper invocation)
```bash
# Basic invocation (BA disabled by default — lower VRAM, faster):
scripts/splat_pipeline/pose_vggt.sh <scene_dir>

# With bundle adjustment (more robust poses, more VRAM):
VGGT_USE_BA=1 scripts/splat_pipeline/pose_vggt.sh <scene_dir>

# Custom VGGT_ROOT (outside Nix shell):
VGGT_ROOT=/path/to/vggt scripts/splat_pipeline/pose_vggt.sh <scene_dir>
```

The wrapper handles:
1. **Guarded clone** — clones VGGT only if `$VGGT_ROOT/demo_colmap.py` is missing.
   If the directory exists but the script is absent, exits with code 4.
2. **Guarded pip install** — installs `$VGGT_ROOT/requirements.txt` only once,
   tracked by a `.vggt_deps_ok` sentinel file in `$VGGT_ROOT`.
3. **Output normalization** — VGGT's `demo_colmap.py` writes `cameras.bin`/`images.bin`/
   `points3D.bin` flat into `$SCENE_DIR/sparse/` (no `sparse/0/` subdirectory).
   The wrapper MOVES them into `sparse/0/` to match the COLMAP convention expected by
   Stage C (`train_brush.sh` validates `sparse/0/cameras.bin` explicitly).
4. **Exit code contract** — see below.

### Exit codes
| Code | Meaning |
|---|---|
| 0 | `POSE_OK` — `sparse/0/{cameras,images,points3D}.bin` produced. |
| 1 | Usage error (missing `scene_dir`, bad args). |
| 2 | Missing dependencies (`python3`, `git` not in PATH). |
| 3 | Input validation failed (no `images/` directory or empty). |
| 4 | VGGT clone or dependency install failed. |
| 5 | VGGT model run failed or produced no output. |

### Raw VGGT command (what the wrapper runs under the hood)
```bash
# BA disabled by default (wrapper default). Enable with VGGT_USE_BA=1.
python3 "$VGGT_ROOT/demo_colmap.py" --scene_dir="$SCENE_DIR"

# With bundle adjustment (set VGGT_USE_BA=1 or VGGT_USE_BA=true):
python3 "$VGGT_ROOT/demo_colmap.py" --scene_dir="$SCENE_DIR" --use_ba
```

## STAGE_B_STATUS masking gotcha (fixed — DO NOT REINTRODUCE)
When the pipeline driver (`run_pipeline.sh`) falls back from COLMAP to VGGT, it MUST
reset `STAGE_B_STATUS=0` before invoking `pose_vggt.sh` (fixed in a00079b). Without
this reset, the `|| STAGE_B_STATUS=$?` pattern only captures non-zero exits, leaving
a stale COLMAP failure code (5 or 6) in the variable even after VGGT succeeds. This
falsely reports pipeline failure. See `run_pipeline.sh:171` for the current fix.

## Acceptance criteria
- `scene_dir/sparse/0/{cameras,images,points3D}.bin` produced in COLMAP format,
  consumable by Stage C exactly like Path 1 output (via `train_brush.sh`).
- `run_pipeline.sh` can route Stage A → (COLMAP, on fail → VGGT) → Stage C without
  manual file shuffling.

## Trade-off to record
VGGT poses are LESS metrically precise than a clean COLMAP run but VASTLY more robust.
For "the video isn't great but I need SOMETHING," VGGT wins. For a careful capture,
COLMAP wins on fidelity. Less metric precision = expect a fiddlier alignment ritual
(Back-end Step 4) and possibly a non-trivial scale factor.

## Escalation conditions
- VGGT OOMs with `VGGT_USE_BA=1` on 12GB → drop BA (default; use without `VGGT_USE_BA`).
  BA is DISABLED by default in the wrapper, not enabled as earlier docs suggested.
  Only enable it when COLMAP-quality poses are needed and VRAM permits.
- VGGT clone fails → check network, verify `VGGT_REPO_URL` is accessible.
- Even VGGT produces garbage → the capture violates the static-scene or parallax hard
  requirements; re-capture is the only fix. Do not try to salvage dynamic-scene video.
- VGGT output NOT in `sparse/0/` — check the normalization step in `pose_vggt.sh:220-240`.
  If `demo_colmap.py` upstream changes its output layout, update the normalization logic.

## Output
`scene_dir/sparse/0/` in COLMAP binary format (normalized from VGGT's flat `sparse/`
layout). Consumed by Stage C (Brush).
