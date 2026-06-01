# splat_pipeline — Front-end pipeline for Video → Gaussian Splat

The offline pipeline that turns a video capture of a real place into two co-registered
assets: a Gaussian splat (visual) and a collision mesh (physics). Runs once per scene
on the GPU workstation.

## Quick start

```bash
# 1. Place your conforming video in a scene directory
mkdir -p scenes/my_room
cp /path/to/capture.mp4 scenes/my_room/video.mp4

# 2. Validate the input
python3 scripts/splat_pipeline/validate_input.py scenes/my_room/video.mp4

# 3. Run the pipeline (skeleton — stages land via subissues #107–#111)
bash scripts/splat_pipeline/run_pipeline.sh scenes/my_room
```

## Per-scene layout

```
<scene_dir>/
  video.mp4              # Input capture (conforming format, see below)
  images/                # Stage A output — sharp frames (JPEG)
  database.db            # Stage B — COLMAP feature database
  sparse/0/              # Stage B output — COLMAP-format poses
    cameras.bin            # Camera intrinsics
    images.bin             # Camera extrinsics
    points3D.bin           # Sparse point cloud
  scene.ply              # Stage C output — VISUAL asset (Gaussian splat)
  collision.glb          # Stage D output — PHYSICS asset (collision mesh)
  alignment.toml         # Filled during Back-end Step 4 alignment ritual
```

Final assets are copied to `splat_walk/assets/splats/<scene_name>/` at integration
(subissue #111).

## Conforming video requirements

The reconstruction quality is dominated by the input. These are **hard requirements**
for v1:

| Requirement | Check | Rationale |
|------------|-------|-----------|
| Static scene | Manual checklist | Moving content corrupts geometry |
| Real parallax | Motion proxy (soft) | Pure pan = zero parallax = nothing to reconstruct |
| Even lighting | Manual checklist | Auto-exposure swings confuse feature matching |
| Low motion blur | Blur proxy (soft) | Blur destroys features needed for pose estimation |
| Resolution ≥ 1080p | ffprobe (hard) | Minimum detail for reliable reconstruction |
| Coverage: 2–3 angles per surface | Manual checklist | Surfaces seen from one angle cannot be triangulated |

**Design rule:** The splat looks correct ONLY from viewpoints near where the real
camera went. Confine the player to roughly the captured camera path volume. Straying
far from the camera path produces smearing and visual artifacts — this is a
fundamental limitation of Gaussian splatting from posed video, not a bug.

## Pipeline stages

| Stage | Script (when implemented) | Subissue | Input | Output |
|-------|--------------------------|----------|-------|--------|
| Validate | `validate_input.py` | #106 | `video.mp4` | PASS / FAIL |
| A — Frames | `run_pipeline.sh Stage A` + `cull_blurry.py` | #107 | `video.mp4` | `images/*.jpg` |
| B — Pose | `pose_colmap.sh` / `pose_vggt.sh` | #108 | `images/` | `sparse/0/*.bin` |
| C — Splat | `train_brush.sh` | #109 | `images/` + `sparse/` | `scene.ply` |
| D — Mesh | `extract_mesh.sh` + `decimate_to_glb.py` | #110 | `scene.ply` checkpoint | `collision.glb` |
| Integration | Asset copy + alignment | #111 | all above | `splat_walk/assets/splats/` |

### Stage details

**Validate (this issue, #106):** Runs hard checks (resolution, frame rate, codec probe
via ffprobe) that exit non-zero on failure. Runs soft checks (blur proxy, motion proxy
via OpenCV optical flow) that warn but do not block. Always prints a manual
static-scene checklist that the operator must verify.

**Stage A (#107):** Extract frames at 3 fps (configurable via `SPLAT_EXTRACT_FPS`
env var) with ffmpeg, then cull the blurriest ~18% by variance-of-Laplacian using
`cull_blurry.py`. Output: `images/` containing only sharp frames.
- **Usage**: `scripts/splat_pipeline/cull_blurry.py <scene_dir> [--percentile 18] [--dry-run]`
- **Exit codes**: 0 = ok, 1 = usage error, 2 = missing opencv/numpy, 3 = no readable frames
- **Idempotent**: re-running on an already-culled directory does not crash
- **Escalation — dark/low-contrast video**: if most frames score low and culling removes
  too many, apply a brightening pre-pass before Stage A:
  `ffmpeg -i video.mp4 -vf "eq=gamma=3.0:contrast=1.5:brightness=0.2" -c:v libx264 bright_video.mp4`
  then use the brightened video as input. Also consider lowering `--percentile` or raising
  `SPLAT_EXTRACT_FPS` to retain more frames for pose estimation.

**Stage B (#108):** COLMAP feature extraction + exhaustive/sequential matching, then
GLOMAP global mapping. Default path. On failure (few images registered), auto-fallback
to VGGT (Path 2). Output: `sparse/0/` in COLMAP binary format.

### Stage B — Usage

```bash
# Default: COLMAP exhaustive matching + GLOMAP mapper
scripts/splat_pipeline/pose_colmap.sh <scene_dir>

# Sequential matcher for long walk-through videos (much faster)
scripts/splat_pipeline/pose_colmap.sh <scene_dir> --sequential

# Keep database.db after run (default: cleaned up)
scripts/splat_pipeline/pose_colmap.sh <scene_dir> --no-cleanup
```

**Prerequisites:**

| Tool | Version | Note |
|------|---------|------|
| COLMAP | 3.10 | **3.13 breaks downstream tools** (dot-vs-colon CLI syntax change). Standardize on 3.10. |
| GLOMAP | latest | Drop-in global mapper, faster than vanilla COLMAP at comparable quality. |

**Success / failure semantics:**

| Exit code | Meaning | Pipeline action |
|-----------|---------|-----------------|
| 0 | `POSE_OK` — model complete, sufficient registered images | Proceed to Stage C |
| 1 | Usage error | Fix arguments |
| 2 | Missing `colmap` or `glomap` on PATH | Install dependencies |
| 3 | No `images/` directory or no frames | Run Stage A first |
| 4 | COLMAP step failed (features or matching) | Check video quality |
| 5 | GLOMAP failed (no model produced) | Try VGGT fallback |
| 6 | `POSE_FAILED` — model exists but too few images registered | Auto-routed to VGGT fallback (Path 2) |

On exit code 6, the script writes a `POSE_FAILED` marker file to `<scene_dir>/POSE_FAILED`
with a human+ machine-readable reason. `run_pipeline.sh` detects this and automatically
routes to `pose_vggt.sh` (Path 2).

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSE_MATCHER_MODE` | `exhaustive` | `sequential` or `exhaustive` |
| `POSE_MIN_REGISTERED` | `0.5` | Fraction of input images that must register (0.0–1.0) |

**Output:** `<scene_dir>/sparse/0/{cameras.bin, images.bin, points3D.bin}` in COLMAP binary format. Consumed by Stage C (Brush).

### Stage B — VGGT fallback (Path 2)

When COLMAP fails or produces too few registered images, `run_pipeline.sh` automatically
routes to `pose_vggt.sh` (Path 2). VGGT is a feed-forward transformer that predicts
poses + 3D in a single pass, tolerating low parallax, motion blur, and textureless
surfaces. It exports directly to COLMAP binary format — a drop-in replacement for
Path 1's output.

**Usage:**

```bash
# Default: VGGT without bundle adjustment (lower VRAM, faster)
scripts/splat_pipeline/pose_vggt.sh <scene_dir>

# With bundle adjustment: set VGGT_USE_BA=1 (more robust, higher VRAM)
VGGT_USE_BA=1 scripts/splat_pipeline/pose_vggt.sh <scene_dir>
```

**Prerequisites:**

| Tool | Version | Note |
|------|---------|------|
| Python | 3.10+ | Must have pip; CUDA toolkit for GPU inference |
| git | any | For cloning VGGT repo |

VGGT is cloned automatically on first run into `$VGGT_ROOT` (default `$HOME/vggt`).
Dependencies are installed via pip into the active Python environment and guarded
by a `.vggt_deps_ok` marker file to avoid re-installing on every run.

**Success / failure semantics:**

| Exit code | Meaning | Pipeline action |
|-----------|---------|-----------------|
| 0 | `POSE_OK` — sparse model produced | Proceed to Stage C |
| 1 | Usage error | Fix arguments |
| 2 | Missing `python3` or `git` | Install dependencies |
| 3 | No `images/` directory or no frames | Run Stage A first |
| 4 | VGGT clone or pip install failed | Check network, git, pip |
| 5 | VGGT ran but produced no output | Re-capture (violates requirements) |

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `VGGT_ROOT` | `$HOME/vggt` | Path to clone/use the VGGT repo |
| `VGGT_REPO_URL` | `https://github.com/facebookresearch/vggt` | Repo URL for cloning |
| `VGGT_USE_BA` | (empty — disabled) | Set to `1` or `true` to enable bundle adjustment |
| `VGGT_PYTHON` | `python3` | Python interpreter to use |

**Escalation notes:**

| Symptom | Cause | Action |
|---------|-------|--------|
| VGGT OOMs | 12 GB VRAM exceeded with `--use_ba` | Drop `VGGT_USE_BA` (faster, slightly less robust) or reduce frame count / resolution |
| VGGT produces garbage | Video violates static-scene or parallax requirements | Re-capture is the only fix — do not attempt to salvage dynamic-scene video |
| VGGT not found | `VGGT_ROOT` points to an empty or wrong directory | Set `VGGT_ROOT` to an empty path and re-run to trigger auto-clone |

**Trade-off:** VGGT poses are less metrically precise than a clean COLMAP run but
vastly more robust. Less metric precision means a fiddlier alignment ritual
(Back-end Step 4) and possibly a non-trivial scale factor.

**Output:** `<scene_dir>/sparse/0/{cameras.bin, images.bin, points3D.bin}` in COLMAP
binary format — identical contract to Path 1. Consumed by Stage C (Brush).

**Stage C (#109):** Train the Gaussian splat with Brush (`ArthurBrussee/brush`), a
Rust+wgpu trainer. Monitor in Brush viewer; stop when quality plateaus. Output:
`scene.ply`.

### Stage C — Usage

```bash
# Basic: 30k steps, no splat cap
scripts/splat_pipeline/train_brush.sh <scene_dir>

# Custom step count
scripts/splat_pipeline/train_brush.sh <scene_dir> --total-steps 20000

# Cap splats for VRAM-limited targets (e.g., 12 GB RTX 4070 Ti)
scripts/splat_pipeline/train_brush.sh <scene_dir> --max-splats 3000000
```

| Option | Default | Purpose |
|--------|---------|---------|
| `--total-steps N` | 30000 | Number of training iterations. 7k–30k typical. |
| `--max-splats N` | unlimited | Cap the number of Gaussians at export time. |

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `BRUSH_BIN` | `brush` | Path to the Brush binary. |
| `BRUSH_TOTAL_STEPS` | 30000 | Default total steps (overridable by `--total-steps`). |
| `BRUSH_MAX_SPLATS` | (none) | Default max splats (overridable by `--max-splats`). |

**Prerequisites:** Brush (ArthurBrussee/brush), a Rust+wgpu+Burn trainer.
Install from: https://github.com/ArthurBrussee/brush/releases

**Output:** `<scene_dir>/scene.ply` — the VISUAL Gaussian splat asset. The script reads
the PLY header and reports the splat count, with VRAM advisory at 5M and 10M thresholds.

**VRAM / splat budget for 12 GB RTX 4070 Ti:**

| Splats | Status | Action |
|--------|--------|--------|
| 1–3M | Comfortable | Proceed. |
| 3–5M | Acceptable | Monitor Bevy runtime framerate. |
| 5–10M | Warning | Re-train with `--max-splats` if framerate drops. |
| 10M+ | Critical | Re-train with `--max-splats`; Bevy renderer will strain. |

**Exit codes:**

| Exit code | Meaning | Pipeline action |
|-----------|---------|-----------------|
| 0 | Success — scene.ply produced and non-empty | Proceed to Stage D |
| 1 | Usage error | Fix arguments |
| 2 | Missing `brush` on PATH | Install Brush |
| 3 | Missing `images/` or `sparse/0/` | Run Stages A + B first |
| 4 | Brush training failed | Check Brush logs, GPU drivers, VRAM |

**Escalation guidance:**

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| Smearing everywhere, quality never plateaus | Upstream pose problem | Revisit Stage B (try the other path) |
| Smearing only far from camera path | Expected limitation | Enforce player confinement downstream |
| VRAM blowout during training | Too many Gaussians | Cap with `--max-splats`, lower resolution |
| Brush fails to find COLMAP data | Sparse dir structure wrong | Verify `sparse/0/{cameras,images,points3D}.bin` exist |

**Stage D (#110):** Extract a surface-aligned mesh from the trained splat using SuGaR
or 2DGS — co-registered with the splat automatically. Decimate to <200k tris via
Blender headless. Output: `collision.glb`.

**Integration (#111):** Copy `scene.ply` + `collision.glb` to
`splat_walk/assets/splats/<scene_name>/`. Run the alignment ritual (Back-end Step 4)
to populate `alignment.toml`. Walk end-to-end in Bevy.

### Dependency graph

```
#106 (validate scaffold)
  ├── #107 (Stage A)  ← Frame extraction + blur culling implemented
  ├── #108 (Stage B)  ← depends on #107
  ├── #109 (Stage C)  ← depends on #108
  ├── #110 (Stage D)  ← depends on #109
  └── #111 (Integration) ← depends on #107-#110 + back-end steps
```

## Validator output reference

`validate_input.py <video.mp4>` prints:

```
File:     /path/to/video.mp4
Codec:    h264
Res:      3840x2160
FPS:      30.0
Duration: 12.5s
Frames:   375
Pix fmt:  yuv420p

Blur proxy (mean Laplacian variance): 342.1
Motion proxy (mean optical-flow magnitude): 1.23

+-------------------------------------------------------------+
|  MANUAL CHECKLIST — verify BEFORE running the pipeline:     |
|  ...                                                        |
+-------------------------------------------------------------+

Hard checks passed.
```

Exit codes:
- `0` — all hard checks passed
- `1` — usage error or file not found
- `2` — ffprobe not installed
- `3` — hard failure (sub-1080p, non-video, probe failure)

## GPU workstation environment

- GPU: NVIDIA RTX 4070 Ti (12 GB VRAM)
- 12 GB VRAM is the binding constraint — watch splat count and mesh density
- Stage C: 1–3M splats comfortable; 10M+ strains Bevy at runtime
- Stage D: skip texture baking; use `--low_poly` to avoid OOM

## Related docs

| Doc | Content |
|-----|---------|
| `PLAN.md` | Milestone overview and build order |
| `splat-handoff/PLAN_video_to_splat.md` | Detailed front-end implementation plan |
| `splat-handoff/handoff_contract.md` | Front ↔ back interface contract |
| `splat-handoff/fe_stageA_frames.md` | Stage A scaffold |
| `splat-handoff/fe_stageB_colmap.md` | Stage B COLMAP path |
| `splat-handoff/fe_stageB_vggt.md` | Stage B VGGT fallback |
| `splat-handoff/fe_stageC_brush.md` | Stage C splat training |
| `splat-handoff/fe_stageD_mesh.md` | Stage D collision mesh |
