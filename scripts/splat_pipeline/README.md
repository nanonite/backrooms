# splat_pipeline — Front-end pipeline for Video → Gaussian Splat

The offline pipeline that turns a video capture of a real place into two co-registered
assets: a Gaussian splat (visual) and a collision mesh (physics). Runs once per scene
on the GPU workstation.

## Quick start

```bash
# One command: video → walkable Godot scene
scripts/splat_pipeline/convert_video.sh /path/to/capture.mp4

# Or with an explicit scene name
scripts/splat_pipeline/convert_video.sh /path/to/capture.mp4 my_room

# Dry-run: print the plan without executing
scripts/splat_pipeline/convert_video.sh /path/to/capture.mp4 --dry-run

# Force re-run of all stages (ignore previous results)
scripts/splat_pipeline/convert_video.sh /path/to/capture.mp4 --force
```

The pipeline is **resumable**: after an interruption, re-run the same command
and unchanged stages are skipped. Changing the video or any setting changes
the stage's input hash, so that stage (and everything downstream) re-runs.

## Resumability and dry-run

Each stage records its input hash, output hash, and status in
`<scene_dir>/pipeline_state.json`. Before running a stage, the pipeline checks
whether a previous successful record exists with a matching input hash:

- **Match** — the stage is skipped (resumability after interruption).
- **Mismatch** — the stage re-runs (invalidation on input/settings change).
- **Failed** — the stage re-runs (a failure never causes a skip).

Stages run in dependency order, so each stage's declared inputs already exist
when its input hash is computed: **D — alignment contract** runs before
**E — collision + traversal**, because `generate_collision.py` consumes
`alignment_manifest.json`. This is what lets a resumed run skip every unchanged
stage instead of re-running the pair.

`--dry-run` prints the plan and exits without executing. `--force` re-runs all
stages, ignoring previous results.

Before any stage, a preflight report lists which external tools are on PATH
(`ffmpeg`, `colmap`, `glomap`, `ns-train`, `node`, `godot4`, ...). It is
informational; the per-stage dependency checks remain authoritative.

Per-stage logs are written to `<scene_dir>/logs/<stage_name>.log`.

## Nondeterminism tolerances

The pipeline is **deterministic** for stages that depend only on their inputs:

- **Stage A** (frame selection): deterministic — the capture gate selects the same
  frames for the same video and settings.
- **Stage B** (pose estimation): deterministic — COLMAP/GLOMAP produce the same
  sparse model for the same images. The sub-model with the most registered cameras
  is selected explicitly and recorded in `sparse_model.json`.
- **Stage C** (Splatfacto training): **nondeterministic** — GPU floating-point
  nondeterminism means two runs with the same seed produce slightly different
  splats. The tolerance is: splat count within 5%, camera positions within 0.01 m.
  The trained config and dataparser transform are hashed into `tool_versions.json`.
- **Stage D** (alignment contract): deterministic — derived from the splat, the
  selected COLMAP model, and the dataparser transform.
- **Stage E** (collision + traversal): deterministic — `splat-transform` has no
  seedable sampling, so identical settings give byte-identical output.
- **Stage F** (Godot staging): deterministic — copies assets and generates the
  scene file.

A fresh run and a resumed run produce **equivalent** validated assets within these
tolerances. This is verified by `test_pipeline_resumability`, which runs the
pipeline twice, asserts the second run reports every stage as skipped, and compares
the SHA-256 of `scene.ply`, `alignment_manifest.json`, `collision.collision.glb`,
`collision_benchmark.json`, and `traversal_manifest.json` between the two runs.
Because the test's training backend is deterministic, those bytes must match
exactly; on a GPU host only the Stage C outputs differ, and the Stage C tolerance
above applies. `test_pipeline_invalidates_on_input_change` additionally checks that
changing the video re-runs Stage A.

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
  sparse_model.json      # Stage B output — selected COLMAP model + candidates
  scene.ply              # Stage C output — VISUAL asset (Gaussian splat)
  tool_versions.json     # Stage C output — tool/model/checkpoint identity
  alignment_manifest.json # Stage D output — calibration contract
  collision.collision.glb # Stage E output — PHYSICS asset (collision mesh)
  collision_benchmark.json # Stage E output — collision verdict/provenance
  traversal_manifest.json # Stage E output — traversal plan
  pipeline_state.json    # Resumability state (input/output hashes per stage)
  logs/                  # Per-stage logs
```

Final assets are copied to `godot_walk/assets/<scene_name>/` at Stage F.

## Conforming video requirements

The reconstruction quality is dominated by the input. These are what the gate
checks, and how it treats each:

| Requirement | Check | Rationale |
|------------|-------|-----------|
| Static scene | Burst probe (hard) | Moving content corrupts geometry |
| Real parallax | Measured translation (hard) | Pure pan = zero baseline = nothing to reconstruct |
| One continuous take | Cut detection (hard) | Frames across a cut share no geometry |
| Even lighting | Manual checklist | Auto-exposure swings confuse feature matching |
| Low motion blur | Sharpness (warn) | Blur destroys features needed for pose estimation |
| Resolution ≥ 320×240 | ffprobe (hard) | Below this a frame cannot carry matchable texture |
| Resolution ≥ 1080p | ffprobe (**advisory**) | Costs detail at distance; does not prevent registration |
| Coverage: 2–3 angles per surface | Coverage report (warn) | Surfaces seen from one angle cannot be triangulated |

**720p is accepted.** It is enough to match features reliably; it costs detail on
distant surfaces, which shows up as a softer reconstruction rather than as a
failure to register. `validate_input.py` used to reject anything under 1080p,
which discarded usable captures. Resolution is now reported with its cost, never
used as a refusal.

**Design rule:** The splat looks correct ONLY from viewpoints near where the real
camera went. Confine the player to roughly the captured camera path volume. Straying
far from the camera path produces smearing and visual artifacts — this is a
fundamental limitation of Gaussian splatting from posed video, not a bug.

## Pipeline stages

| Stage | Script | Input | Output |
|-------|--------|-------|--------|
| Validate | `validate_input.py` | `video.mp4` | PASS / FAIL |
| A — Sample + extract | `capture_gate.py` + `sample_frames.py` | `video.mp4` | `capture_gate.json` + `images/*.jpg` |
| A′ — Blur cull | `cull_blurry.py` (legacy fixed-fps path only) | `images/` | `images/*.jpg` |
| Registration report | `model_coverage.py` | `sparse/` + `images/` | registered vs excluded frames |
| B — Pose | `pose_colmap.sh` / `pose_vggt.sh` | `images/` | `sparse/<n>/*.bin` |
| C — Splat | `train_splatfacto.sh` (default) / `train_brush.sh` (fallback) | `images/` + selected `sparse/<n>/` | `scene.ply` |
| D — Alignment | `measure_splat_frame.py` | `scene.ply` + selected `sparse/<n>/` + dataparser | `alignment_manifest.json` |
| E — Collision + traversal | `generate_collision.py` + `traversal_plan.py` | `scene.ply` + `alignment_manifest.json` | `collision.collision.glb` + `collision_benchmark.json` + `traversal_manifest.json` |
| F — Godot staging | `stage_godot.sh` | all above | `godot_walk/assets/<scene>/` |
| M — Photogrammetry mesh | `mesh_photogrammetry.sh` | `images/` + `sparse/0/` | `mesh_raw.ply` + `scene.glb` |

### Stage details

**Validate (#106):** A fast intake check on container metadata alone — frame size,
frame rate, duration — so a non-video or an unmatchably small frame is refused
before anything decodes. Blur and parallax proxies run when OpenCV is available
and only warn. Prints a manual checklist for what cannot be measured. For the
full judgement see Stage A.

**Stage A — bounded sampling and selection (#90):** Replaces fixed-fps extraction
with a bounded sample, a selection, and a verdict.

```bash
python3 scripts/splat_pipeline/capture_gate.py scenes/my_room/video.mp4 \
    --target-frames 150 --json scenes/my_room/capture_gate.json
python3 scripts/splat_pipeline/sample_frames.py \
    scenes/my_room/video.mp4 scenes/my_room/capture_gate.json \
    --out scenes/my_room/images
```

`capture_gate.py` decodes a bounded sample — never the whole clip — and measures
sharpness, inter-sample translation, scene cuts, moving content, temporal
geometry consistency and view coverage. It selects the frames worth
reconstructing, reports why every other frame was dropped, estimates the disk/RAM
cost of the selection against this host before spending any of it, and prints one
verdict. **Every rejection names the capture change that fixes it**, because
"fail" is not something an operator can act on.

`sample_frames.py` writes only the selected frames, one ffmpeg seek each, at
**source** resolution. The gate measures on downscaled analysis frames — the
right place to measure, the wrong place to reconstruct from — and the written
frames are at the resolution COLMAP extracts features from. A `frames.json`
manifest maps each written file back to its source frame index.

- **Frame budget**: configurable, default 150, inside a 100–200 *hypothesis* for a
  small room. It is a starting point, not a guarantee: a long corridor needs more
  views and a still photo needs none. A run outside the hypothesis is flagged, not
  clamped, because a target that silently resets itself teaches nothing about why
  the number was wrong.
- **Matching**: bounded retrieval matching against spread keyframes, plus a
  sequential window for the local chain. Exhaustive all-pairs is 11,175 pairs at
  150 frames; the plan reports its own pair count, the reduction, and what it
  gives up — a missed loop closure shows up as two disconnected reconstructions,
  not as a bad one.
- **Exit codes**: 0 = accepted (possibly with warnings), 1 = usage, 2 = missing
  ffmpeg/ffprobe, 3 = rejected, 4 = unreadable input.
- **Fixtures**: `fixtures/README.md` documents the accepted/rejected clip pairs,
  the measured basis for each threshold, and the recorded command outputs.

**Legacy Stage A path (#107):** `SPLAT_EXTRACT_FPS=0 run_pipeline.sh <scene_dir>`
extracts at a fixed 3 fps and culls the blurriest ~18% by variance-of-Laplacian
with `cull_blurry.py`. Useful when debugging downstream stages against a known
frame set; not the default, because it decodes and stores the whole clip.
- **Usage**: `scripts/splat_pipeline/cull_blurry.py <scene_dir> [--percentile 18] [--dry-run]`
- **Exit codes**: 0 = ok, 1 = usage error, 2 = missing opencv/numpy, 3 = no readable frames
- **Idempotent**: re-running on an already-culled directory does not crash
- **Escalation — dark/low-contrast video**: if most frames score low and culling removes
  too many, apply a brightening pre-pass before Stage A:
  `ffmpeg -i video.mp4 -vf "eq=gamma=3.0:contrast=1.5:brightness=0.2" -c:v libx264 bright_video.mp4`
  then use the brightened video as input. Also consider lowering `--percentile` or raising
  `SPLAT_EXTRACT_FPS` to retain more frames for pose estimation.

**Stage B (#108):** COLMAP feature extraction + bounded matching, then
GLOMAP global mapping. Default path. On failure (few images registered), auto-fallback
to VGGT (Path 2). Output: `sparse/0/` in COLMAP binary format.

**Registration report (#90):** After Stage B, `model_coverage.py` reads the model
COLMAP actually wrote and reports which extracted frames registered, which did
not, and by name. COLMAP exits 0 on a reconstruction that registered 41 of 150
frames, and a downstream stage will happily train a splat over the room that
reconstructed and nothing else — so the gap between what the camera covered and
what the model covers has to be stated. Where a disconnected reconstruction split
across `sparse/0` and `sparse/1`, the report names the component it used *and* the
one it left out rather than silently keeping the largest.

```bash
python3 scripts/splat_pipeline/model_coverage.py scenes/my_room
# Exit 2 = coverage below the floor (default 80%); a warning, not a failure.
```

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
| 7 | `POSE_REFUSED` — bounded resource refusal | See `POSE_REFUSED` file for budget + suggested setting |

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `VGGT_ROOT` | `$HOME/vggt` | Path to clone/use the VGGT repo |
| `VGGT_REPO_URL` | `https://github.com/facebookresearch/vggt` | Repo URL for cloning |
| `VGGT_USE_BA` | (empty — disabled) | Set to `1` or `true` to enable bundle adjustment |
| `VGGT_PYTHON` | `python3` | Python interpreter to use |
| `VGGT_MAX_FRAMES` | `12` | Frame cap for one attempt. The aggregator's global attention is quadratic in the frame count; measured on this host, 24 frames at 1080p OOMs (~11.6 GiB peak) and 12 frames is the largest selection that fits (11643 MiB peak). A larger selection is subsampled evenly, never truncated to its opening. |
| `VGGT_MIN_FRAMES` | `4` | Floor for the OOM backoff. Below this the run is refused rather than attempted again. |

**Escalation notes:**

| Symptom | Cause | Action |
|---------|-------|--------|
| VGGT OOMs | 12 GB VRAM exceeded | The script automatically retries with fewer frames (deterministic halving from `VGGT_MAX_FRAMES` down to `VGGT_MIN_FRAMES`). If every attempt OOMs, it writes `POSE_REFUSED` and exits 7. Lower `VGGT_MAX_FRAMES` to reduce peak VRAM, or raise `VGGT_MIN_FRAMES` to allow smaller attempts. |
| VGGT produces garbage | Video violates static-scene or parallax requirements | Re-capture is the only fix — do not attempt to salvage dynamic-scene video |
| VGGT not found | `VGGT_ROOT` points to an empty or wrong directory | Set `VGGT_ROOT` to an empty path and re-run to trigger auto-clone |

**Trade-off:** VGGT poses are less metrically precise than a clean COLMAP run but
vastly more robust. Less metric precision means a fiddlier alignment ritual
(Back-end Step 4) and possibly a non-trivial scale factor.

**Output:** `<scene_dir>/sparse/0/{cameras.bin, images.bin, points3D.bin}` in COLMAP
binary format — identical contract to Path 1. Consumed by Stage C (Brush).

**Stage C (#109):** Train the Gaussian splat. The default backend is Nerfstudio
Splatfacto (`train_splatfacto.sh`); Brush (`train_brush.sh`) is the fallback for
hosts where nerfstudio is unavailable. Output: `scene.ply`.

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

**Stage D (#83):** Measure the alignment contract. `measure_splat_frame.py` reads
the trained splat, the selected COLMAP model, and the nerfstudio dataparser
transform to produce `alignment_manifest.json` — the single source of truth for
the PLY→Godot-world mapping, landmarks, camera path, and player spawn. The
selected model is whichever sub-model `colmap_model.find_sparse_model` chose
(most registered cameras), recorded in `sparse_model.json`.

```bash
python3 scripts/splat_pipeline/measure_splat_frame.py \
    --ply <scene_dir>/scene.ply \
    --colmap-model <scene_dir>/sparse/<n> \
    --dataparser-transforms <scene_dir>/splatfacto_output/dataparser_transforms.json \
    --scene-id <scene_name> \
    --out <scene_dir>/alignment_manifest.json
```

**Stage E (#111 + #85):** Generate collision geometry from the trained splat using
the pinned `@playcanvas/splat-transform@3.9.0` tool (`generate_collision.py`), then
derive the traversal plan. The collision mesh is CO-REGISTERED with `scene.ply`
automatically — they come from the same Gaussian reconstruction, so the contract's
transform fixes both. `traversal_plan.py` reads the collision mesh and the contract
to produce `traversal_manifest.json` — the walk route, probes, tolerances, and the
safe spawn.

```bash
python3 scripts/splat_pipeline/generate_collision.py \
    --manifest <scene_dir>/alignment_manifest.json \
    --ply <scene_dir>/scene.ply \
    --out <scene_dir>/collision \
    --report <scene_dir>/collision_benchmark.json

python3 scripts/splat_pipeline/traversal_plan.py \
    --manifest <scene_dir>/alignment_manifest.json \
    --report <scene_dir>/collision_benchmark.json \
    --glb <scene_dir>/collision.collision.glb \
    --out <scene_dir>/traversal_manifest.json
```

**Stage F (#88):** Stage the scene for Godot. `stage_godot.sh` copies the assets
to `godot_walk/assets/<scene_name>/`, generates the `.tscn` scene file from a
template, writes `scene_manifest.json` with provenance hashes, and updates
`current_scene.txt`.

```bash
scripts/splat_pipeline/stage_godot.sh <scene_dir>
```

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

### Legacy mesh extraction (SuGaR) — retired

> The SuGaR + Blender collision path below is **not** wired into
> `run_pipeline.sh`. The pipeline generates collision with
> `generate_collision.py` (pinned `@playcanvas/splat-transform@3.9.0`) in Stage E.
> These scripts remain for reference and manual comparison only.

```bash
# Step D1: Extract mesh from splat (SuGaR)
scripts/splat_pipeline/extract_mesh.sh <scene_dir>

# With explicit checkpoint path
scripts/splat_pipeline/extract_mesh.sh <scene_dir> --checkpoint <ckpt_dir>

# Step D2: Decimate and export collision.glb (headless Blender)
blender --background --python scripts/splat_pipeline/decimate_to_glb.py -- \\
    --scene-dir <scene_dir> [--target-triangles 150000]
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

## Frame and metric-scale contract (#83)

A splat is not self-describing: it has no up axis, no units, and the renderer
adds transforms of its own. Two scenes can serialise identical transforms and
still disagree, because the *effective* mapping differs. Stage F fixes that by
producing one explicit manifest per scene, which the Godot runtime reads and
verifies.

| Script | Role |
|---|---|
| `splat_ply.py` | Read a 3DGS PLY verbatim — no axis or unit correction |
| `colmap_model.py` | Read COLMAP poses; the record of which axis points at the floor |
| `splat_geometry.py` | Measure floor/ceiling/wall planes from Gaussian covariances |
| `frame_axes.py` | Compose the frame → Godot rotation (always a proper rotation) |
| `splat_frame.py` | The `FrameContract` record and its invariants |
| `manifest_rules.py` | The hand-maintained table of automatic addon transforms |
| `measure_splat_frame.py` | CLI: measure a scene and write its manifest |
| `emit_scene_contract.py` | Print the manifest-derived Godot transforms |

Measure a scene, then check what changed:

```bash
python3 scripts/splat_pipeline/measure_splat_frame.py \
    --ply godot_walk/assets/corridor_splat/corridor.ply \
    --colmap-model data/scenes/corridor_travel/sparse/0 \
    --dataparser-transforms outputs/<run>/dataparser_transforms.json \
    --scene-id corridor_splat --target-clear-height 2.40 \
    --out godot_walk/assets/corridor_splat/alignment_manifest.json

python3 scripts/splat_pipeline/emit_scene_contract.py \
    --manifest godot_walk/assets/corridor_splat/alignment_manifest.json
```

`--target-clear-height` applies to **synthetic** footage, where no real-world
reference exists and the scale is therefore a documented *choice*. For real
footage use `--footage-kind real --measured-reference <metres>`; the manifest
then records `kind: "measured_reference"`. The two are never conflated.

Two things this deliberately refuses to invent:

- **Wall planes.** A surface is only accepted above an 8× density-contrast
  threshold. On `corridor_straight` the floor/ceiling reach 17× and 24× while the
  horizontal axes peak at 2–7× and are blobs. A capture that fails the bar records
  `walls_measured: false` and falls back to observation bounds.
- **Surface sign.** A Gaussian covariance encodes an axis, not a facing, so
  floor and ceiling are found as the two dominant mode *pairs* along the up axis.
  Splitting on sign finds the same sheet twice and reports a zero-height room.

The manifest also records **where the reconstruction cameras land**, mapped
through the same `ply_to_world` as everything else. That record matters because
it is the only one not derived from the room: the splat node, the collider and
the spawn are hand-authored in `.tscn` files, so without it the contract only ever
checks the authored things against each other. Requiring the cameras to sit inside
the room — at a plausible walking eye height — is what catches a wrong up axis or
a wrong scale independently of the room's own geometry.

Verify both halves:

```bash
python3 -m pytest scripts/splat_pipeline/tests/test_splat_frame.py -v
cd godot_walk
godot4 --headless --script res://scripts/verify_alignment.gd   # both scenes
godot4 --headless --script res://scripts/test_splat_alignment.gd  # the reader
```

The manifest also records **where the reconstruction cameras land**, mapped
through the same `ply_to_world` as everything else. That record matters because
it is the only one not derived from the room: the splat node, the collider and
the spawn are hand-authored in `.tscn` files, so without it the contract only ever
checks the authored things against each other. Requiring the cameras to sit inside
the room — at a plausible walking eye height — is what catches a wrong up axis or
a wrong scale independently of the room's own geometry. For `corridor_splat` that
is 192 cameras with a mean height 1.153 m above the floor, which is what a person
walking records.

Verify both halves:

```bash
python3 -m pytest scripts/splat_pipeline/tests/test_splat_frame.py -v
cd godot_walk
godot4 --headless --script res://scripts/verify_alignment.gd      # both scenes
godot4 --headless --script res://scripts/test_splat_alignment.gd  # the reader
```

The second script is not redundant with the first. Every check in
`verify_alignment.gd` passes on the shipped scenes, so a check that *cannot* fail
is indistinguishable from a working one — and one did: the GDGS correction
constant declared a z axis of `(1,0,0)`, giving determinant 0, which made the
"the addon did not rotate the room" assertion unsatisfiable and permanently
green. `test_splat_alignment.gd` asserts the reader's negative cases, and
re-introducing that exact bug fails 5 of its 27 checks.

See `godot_walk/assets/corridor_splat/README.md` for the worked example,
including the measured up axis, the chosen 5.128384 m/unit scale, and the
automatic GDGS transforms recorded as applied exactly once (or zero times, for
the identity-basis correction the scenes neutralise).

### Dependency graph

```
#106 (validate scaffold)
  ├── #107 (Stage A)  ← Frame extraction + blur culling implemented
  ├── #108 (Stage B)  ← COLMAP pose + VGGT fallback implemented
  ├── #109 (Stage C)  ← Splatfacto training (Brush fallback) implemented
  ├── #83 (Stage D)   ← Alignment contract implemented
  ├── #111 (Stage E)  ← Collision generation + traversal plan implemented
  └── #88 (Stage F)   ← Godot staging implemented
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
The model is passed as `--colmap-path <selected>`, because nerfstudio defaults to
`colmap/sparse/0` while this repo's COLMAP 3.10 + GLOMAP output lives under
`sparse/`. `train_splatfacto.sh` passes the sub-model selected by
`colmap_model.find_sparse_model` (most registered cameras).

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
| `scripts/splat_pipeline/COLLISION.md` | Generated collision geometry: pinned splat-transform benchmark, calibrations and measured acceptance verdicts (#84) |
| `scripts/splat_pipeline/budgets/rtx4070ti/` | Frozen measurement JSON, logs and raw pytest output behind those budgets |

## Collision geometry from splats (#84)

`generate_collision.py` runs the pinned `@playcanvas/splat-transform@3.9.0`
collision pipeline over a splat, maps the result into a #83 alignment contract's
calibrated frame, and scores it before writing anything down:

```bash
cd scripts/splat_pipeline && npm install @playcanvas/splat-transform@3.9.0
SPLAT_TRANSFORM_NODE_MODULES=$PWD/node_modules python3 generate_collision.py \
    --manifest ../../godot_walk/assets/corridor_splat/alignment_manifest.json \
    --ply ../../exports/corridor_travel_v1/splat.ply \
    --out ../../outputs/collision/corridor_splat \
    --report collision_benchmark.json
```

Two things to know before reading its output. The tool writes voxel and mesh data
in the PlayCanvas **engine frame** — the PLY frame rotated 180 degrees about z —
and one `--seed-pos` in that frame drives every navigation stage. And its collision
features are WebGPU-only, so this stage is blocked wherever
`splat-transform --list-gpus` finds no adapter.

Measured verdicts, settings sweeps and the collision transform #85 needs are in
[`COLLISION.md`](COLLISION.md); the machine-readable runs are
`collision_benchmark.json` and `collision_benchmark_gdgs_demo.json`.
