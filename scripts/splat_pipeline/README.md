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

# 3. Run the pipeline (Stages A–D implemented; integration pending #113/#114)
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
(subissue #113/#114).

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
| D — Mesh | `extract_mesh.sh` + `decimate_to_glb.py` | #111 | `scene.ply` checkpoint | `collision.glb` |
| M — Photogrammetry mesh | `mesh_photogrammetry.sh` | #68/#70 | `images/` + `sparse/0/` | `mesh_raw.ply` + `scene.glb` |
| Integration | Asset copy + alignment | #113/#114 | all above | `splat_walk/assets/splats/` |

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

**Stage M (#68/#70):** Optional photogrammetry mesh path for workstation validation.
Default COLMAP path runs dense MVS and uses `delaunay_mesher` because it is
free-space aware and avoids ballooning interiors. Stage M also defaults to tighter
`stereo_fusion` filters (min pixels 3, reprojection error 2, depth error 0.01,
check images 3) to drop floaters before meshing. If the floor develops holes,
relax `FUSION_MIN_PIXELS` toward 2 or tune the other `FUSION_*` overrides for
the workstation sweep. `--mesher poisson` keeps the previous Poisson path
available for comparison. If the local COLMAP build lacks `delaunay_mesher`,
route validation to #71 (Meshroom/AliceVision fallback) instead of attempting
#70 on that build.


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

**Stage D (#111):** Extract a surface-aligned collision mesh from the trained splat
using SuGaR or 2DGS. The mesh is CO-REGISTERED with `scene.ply` automatically —
they come from the same Gaussian reconstruction, so one transform fixes both
at Back-end Step 4. Decimate to <200k tris via Blender headless. Output: `collision.glb`.

### Stage M — Photogrammetry mesh usage

```bash
# Default: COLMAP dense MVS + Delaunay meshing
scripts/splat_pipeline/mesh_photogrammetry.sh <scene_dir>

# Keep dense workspace for workstation debugging
scripts/splat_pipeline/mesh_photogrammetry.sh <scene_dir> --keep-dense

# Comparison path: previous Poisson mesher
scripts/splat_pipeline/mesh_photogrammetry.sh <scene_dir> --mesher poisson

# Fallback path when COLMAP dense remains blobby or lacks Delaunay
scripts/splat_pipeline/mesh_photogrammetry.sh <scene_dir> --fallback meshroom
```

**Stereo fusion overrides:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `FUSION_MIN_PIXELS` | `3` | Minimum support pixels; lower toward `2` if floors get holes |
| `FUSION_MAX_REPROJ_ERROR` | `2` | Maximum reprojection error before dropping noisy points |
| `FUSION_MAX_DEPTH_ERROR` | `0.01` | Maximum relative depth disagreement |
| `FUSION_CHECK_NUM_IMAGES` | `3` | Minimum agreeing source images |

**COLMAP mesher selection:**

| Option | Input | Output | Use when |
|--------|-------|--------|----------|
| `--mesher delaunay` | Dense COLMAP workspace | `mesh_raw.ply` | Default for interiors; free-space aware |
| `--mesher poisson` | `dense/fused.ply` | `mesh_raw.ply` | Comparison with the previous reconstruction path |

#70 must run on a GPU/display workstation because it re-runs or reuses COLMAP MVS
and validates screenshots. If `colmap -h` does not list `delaunay_mesher`, skip
#70 for that build and use #71 (Meshroom/AliceVision fallback).

### Stage D — Usage

```bash
# Step D1: Extract mesh from splat (SuGaR)
scripts/splat_pipeline/extract_mesh.sh <scene_dir>

# With explicit checkpoint path
scripts/splat_pipeline/extract_mesh.sh <scene_dir> --checkpoint <ckpt_dir>

# Step D2: Decimate and export collision.glb (headless Blender)
blender --background --python scripts/splat_pipeline/decimate_to_glb.py -- \\
    --scene-dir <scene_dir> [--target-triangles 150000]

# Both steps are run automatically by run_pipeline.sh in sequence.
```

**Prerequisites:**

| Tool | Version | Note |
|------|---------|------|
| SuGaR / 2DGS | latest | Install from https://github.com/Anttwo/SuGaR (or equivalent) |
| Blender | 3.x+ | Headless mode (`--background`) required for automation |
| Python | 3.10+ | Must have SuGaR dependencies installed |

**Success / failure semantics:**

| Exit code (extract_mesh.sh) | Meaning | Pipeline action |
|------------------------------|---------|-----------------|
| 0 | Mesh exported — `mesh_export.obj` produced | Proceed to Step D2 |
| 1 | Usage error | Fix arguments |
| 2 | Missing dependencies (python3, SuGaR train.py) | Install SuGaR |
| 3 | Input validation failed (no scene.ply, no checkpoint) | Run Stages A–C first |
| 4 | SuGaR export failed (non-zero exit from train.py) | Check GPU drivers, VRAM |
| 5 | Output mesh missing or empty | Check SuGaR model config |

**Blender decimation (decimate_to_glb.py):**

The headless Blender script performs three operations:
1. **Import** — reads `mesh_export.obj` (or any format SuGaR produces)
2. **Clean** — deletes disconnected components with <50 faces (floating junk)
3. **Decimate** — applies collapse decimation to reach the target triangle budget
4. **Export** — writes `collision.glb` (GLB format, no materials)

All diagnostics are written to `<scene_dir>/decimate_to_glb.log` because
snap/flatpak Blender may suppress stdout/stderr.

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUGAR_ROOT` | `$HOME/SuGaR` | Path to SuGaR/2DGS repo |
| `SUGAR_PYTHON` | `python3` | Python interpreter for SuGaR |
| `SUGAR_TRAIN_SCRIPT` | `$SUGAR_ROOT/train.py` | Path to SuGaR's train.py |
| `SUGAR_LOW_POLY` | `True` | Low-poly export flag |
| `SUGAR_SKIP_TEXTURE` | `True` | Skip texture baking (not needed for collision) |
| `BLENDER_BIN` | `blender` | Path to Blender binary |
| `DECIMATE_TARGET_TRIS` | 200000 | Max triangle count after decimation |

**Asset contract:**

`collision.glb` is a **PHYSICS-ONLY** asset:
- Never rendered — no textures, no materials, no normals needed
- Loaded in Bevy as a `Mesh` for the `avian3d` trimesh collider
- CO-REGISTERED with `scene.ply` — they share the same coordinate frame
- One transform in `alignment.toml` (Back-end Step 4) fixes both
- Ugly is fine — floors/walls clean up well; vegetation/thin rails come out blobby but collision just feels slightly lumpy there

**Failure modes:**

| Symptom | Cause | Action |
|---------|-------|--------|
| SuGaR OOMs on 12 GB VRAM | Texture baking enabled or Poisson too expensive | Ensure `SUGAR_SKIP_TEXTURE=True`, `SUGAR_LOW_POLY=True` |
| Floor has holes | Mesh extraction produced non-continuous floor | Hand-patch in Blender; continuous floor is the one hard requirement |
| Co-registration looks off | Mesh extracted from wrong reconstruction frame | Re-extract WITH SAME checkpoint SuGaR uses (not an independent mesher) |
| collision.glb > 200k tris | Decimation ratio was insufficient | Lower `DECIMATE_TARGET_TRIS` and re-run Step D2 |
| Blender log file is empty | Snap Blender sandboxing suppresses file writes | Use system-installed Blender or adjust snap permissions |

**Post-Stage D quality verification (requires human):**
- Open `collision.glb` in Blender — verify continuous floor, no large gaps
- At Back-end Step 4: verify ONE transform aligns both mesh + splat
- In Bevy runtime: walk the mesh, confirm no fall-throughs

**Escalation guidance:**

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| SuGaR train.py not found | `SUGAR_ROOT` or `SUGAR_TRAIN_SCRIPT` misconfigured | Set the correct path or clone the repo |
| export_obj flag not recognized | Different SuGaR fork with different interface | Set `SUGAR_TRAIN_SCRIPT` to the correct script and adjust flags in `extract_mesh.sh` |
| Blender hangs on large OBJ | Import too slow for headless | Decimate in SuGaR first with more aggressive `--low_poly` settings |
| Decimated mesh loses critical geometry | Target triangle count too low | Raise `DECIMATE_TARGET_TRIS` (but keep under 200k for runtime performance) |

**Integration (#113/#114):** Copy `scene.ply` + `collision.glb` to
`splat_walk/assets/splats/<scene_name>/`. Run the alignment ritual (Back-end Step 4)
to populate `alignment.toml`. Walk end-to-end in Bevy.

### Dependency graph

```
#106 (validate scaffold)
  ├── #107 (Stage A)  ← Frame extraction + blur culling implemented
  ├── #108 (Stage B)  ← COLMAP pose + VGGT fallback implemented
  ├── #109 (Stage C)  ← Brush splat training implemented
  ├── #111 (Stage D)  ← SuGaR mesh extraction + decimation implemented
  └── #113/#114 (Integration) ← depends on #107-#111 + back-end steps
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

## Hardware preflight and resource budgets (#89)

Run this **before** any GPU stage. It measures the machine rather than trusting
the notes about it, probes each compute API the pipeline needs independently, and
publishes a budget from whatever has actually been measured.

**Measured results, pinned versions and the two stages that cannot run on this
workstation are in [`HARDWARE_BUDGET.md`](HARDWARE_BUDGET.md).**

```bash
python3 scripts/splat_pipeline/preflight_hardware.py \
    --scene <scene_name> --measurements splat_logs/measurements.json \
    --json splat_logs/preflight.json
```

| Exit | Meaning |
|------|---------|
| `0` | every required capability passed and the measured default budget fits |
| `1` | usage error |
| `2` | CUDA training unusable — reconstruction cannot run here at all |
| `3` | Vulkan unusable — nothing can be rendered or walked |
| `4` | WebGPU unavailable — reconstruction is fine, collision is not |
| `5` | the measured default budget exceeds the headroom-adjusted VRAM |

A non-zero exit is a refusal with a stated cause and a specific next action, not
a crash. Every failure line names the fix rather than restating the symptom.

### What it measures

| Property | Source |
|---|---|
| GPU, driver, **usable** VRAM, VRAM held by other jobs | `nvidia-smi` (`--query-gpu`, `--query-compute-apps`) |
| RAM total / available | `/proc/meminfo` |
| Disk free on each output filesystem | `statvfs` |
| Pinned tool versions | the exact query per tool, recorded alongside the version |
| CUDA training | one real forward/backward/SGD step in the pinned interpreter |
| Vulkan rendering | boots the shipped renderer against a throwaway project, reads its device banner |
| WebGPU collision | probes `wgpu`, Node and Deno in turn |

**Usable VRAM, never total.** The budget is `min(card free, torch free)` minus
20% headroom. A display server and any other job already hold part of the card —
during one sampling window this machine was at 96% load with 10.4 GiB held, which
would block a stage that the 12 GiB total happily admits.

**A missing compute API blocks its stage regardless of free memory.** Collision is
blocked on this host despite 9.2 GiB free, because without a WebGPU adapter it
would not run slowly — it would not run.

**A stage that was attempted here and failed is not reported as runnable.** The
resource verdict answers "is there space"; only a measured attempt answers "does
it work". A recorded failure in `splat_logs/measurements.json` re-issues that
stage's verdict as BLOCKED, carrying the log line that explains it.

### Benchmarking a stage

Every stage is priced by the same sampler, so the numbers are comparable.

```bash
# Default Splatfacto through the pinned interpreter
python3 scripts/splat_pipeline/benchmark_reconstruction.py splatfacto \
    --data <scene_dir> --staging-dir outputs/<scene>_ns \
    --output-dir outputs/<scene>/splatfacto --log splat_logs/splatfacto.log

# Runtime render: VRAM, wall time and fps at a stated resolution
python3 scripts/splat_pipeline/benchmark_reconstruction.py render \
    --project godot_walk --scene res://scenes/corridor_splat.tscn \
    --resolution 1280x720 --frames 300 --warmup 60 --orbit-radius 1.0 \
    --splat godot_walk/assets/corridor_splat/corridor.ply

# Anything else (collision, import, ...)
python3 scripts/splat_pipeline/benchmark_reconstruction.py command \
    --label collision --input-dir <in> --output-dir <out> -- <command...>
```

Each record keeps the exact argv, the interpreter, the exit code, peak VRAM and
RAM, elapsed time, disk written, splat count and — for render — fps. **Failed
stages are recorded too**, with the tail of their log: a stage that was attempted
and could not run is a different fact from one nobody tried, and the error line is
what the next attempt has to address.

`--orbit-radius` moves the viewpoint during a render probe. Measuring one fixed
camera measures one lucky culling result; a walkthrough always changes what the
splat is asked to draw.

### Bounded inputs

nerfstudio 1.1.5's Splatfacto has **no hard cap on Gaussian count** — there is no
`--cap-max-num-splats`. The levers that exist are `--pipeline.model.stop-split-at`
(default `15000`, freeze densification earlier) and the dataparser's
`--downscale-factor`. Any bound must be stated as a *measured* splat count from a
run that used the lever, never as a configured cap.

`colmap_dataset.py` stages a capture for an unattended run: symlinked read-only
inputs so the capture is never modified, and pre-rendered `images_2` so nerfstudio
does not prompt for downscaling (an automated run otherwise dies on `EOFError`).
The model is passed as `--colmap-path sparse/0`, because nerfstudio defaults to
`colmap/sparse/0` and this repo's COLMAP 3.10 + GLOMAP output is at `sparse/0`.

## GPU workstation environment

Measured on this workstation — see [`HARDWARE_BUDGET.md`](HARDWARE_BUDGET.md) for
the full table and for what could not be measured:

- GPU: NVIDIA RTX 4070 Ti, 11.99 GiB VRAM total, **9.2 GiB usable** at last check
- Host RAM: 62.5 GiB total, 45.5 GiB available
- Vulkan: **1.4.329**, Forward+, working (probed by booting Godot 4.6.3)
- CUDA training: **working** (RTX 4070 Ti cc 8.9, torch 2.3.1+cu121)
- WebGPU / wgpu: **no adapter on this host** — blocks the collision stage, and
  blocks Brush (a wgpu trainer) entirely
- `colmap` and `glomap` are **not installed**, so the pose stages cannot run here
- Runtime: 182,569 splats hold 60.12 fps at 1280x720 for 0.29 GiB of VRAM — but
  that is the display's refresh rate, so it shows the renderer keeps up, not how
  much headroom is left

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
| `scripts/splat_pipeline/HARDWARE_BUDGET.md` | Measured hardware, pinned versions and published budgets (#89) |
| `scripts/splat_pipeline/budgets/rtx4070ti/` | Frozen measurement JSON and logs behind those budgets |
