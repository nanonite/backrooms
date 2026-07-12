# Lessons Learned — Backrooms Splat Pipeline

End-to-end record of what we proved, broke, and fixed building the
AI video → COLMAP → Nerfstudio → Godot walkable Gaussian splat pipeline.

---

## 1. AI Video Generation (Veo 3.1-lite via OpenRouter)

### 1.1 Embrace the model's "desire lines"
The model has strong priors about what a backrooms scene looks like. Fighting them
(e.g. "always face straight forward down the corridor") produces weak geometry.
Embracing them (column orbit) gives better COLMAP triangulation with zero prompt fights.

**What failed:**
- Straight dolly down hallway (4s): lateral 2.2%, triangulation 5.7° — FAR-FIELD DOMINANT
- Weave + look sideways (4s): lateral 86%, triangulation 4.0° — FAR-FIELD DOMINANT
  (excellent translation, clean reprojection at 1.29px, failure is geometry not AI warping)

**What worked:**
- Column orbit (8s): lateral 45%, near-field 89%, triangulation 6.2° — PASS
  The model naturally wants to orbit a structural feature; this also gives the
  multi-angle column edges that COLMAP can triangulate across frames.

### 1.2 Literal prompt injection
"pipe junction" or "outlet plate" → the model literally renders physical pipes on the walls.
Describe geometry in spatial terms only ("wall seam", "baseboard angle", "ceiling tile join").

### 1.3 Duration
8s gives the camera room to complete an orbit. 4s is too short for column orbit.
`DURATION = 8` in `generate_corridor_travel.py`.

### 1.4 Auto-archive
Always archive the previous clip before generating a new one (rename with timestamp).
Without this, good clips are silently overwritten when tuning prompts.
The `generate_corridor_travel.py` script does this automatically.

---

## 2. COLMAP

### 2.1 GPU SIFT OOM
192 frames × 1920×1080 exhausts CUDA texture memory (`CuTexImage::BindTexture`).
Fix: `--SiftExtraction.use_gpu 0` AND `--SiftMatching.use_gpu 0`.
Both extraction AND matching must be CPU — fixing only one still OOMs.

### 2.2 COLMAP version
**COLMAP 3.13 breaks Nerfstudio 1.1.5** (CLI syntax changed from colon to dot notation).
Use COLMAP 3.10 in the `nerfstudio` conda environment.

### 2.3 Relaxed mapper thresholds
Default `init_min_num_inliers=100` rejects every pair in low-baseline AI video → 2 cams registered.
Proven working thresholds:
```
--Mapper.init_min_num_inliers 30
--Mapper.abs_pose_min_num_inliers 15
--Mapper.init_max_error 6
--Mapper.min_num_matches 15
```

### 2.4 Multi-model selection
COLMAP may emit disjoint sub-models (sparse/0, sparse/1, …).
Always pick the one with the most registered cameras for the parallax gate.
`colmap_and_gate.sh` does this automatically.

### 2.5 Cholesky failures = degenerate scene
Repeated "Matrix not positive definite" warnings in bundle adjustment mean the
scene is nearly planar/degenerate. Switching to a column orbit eliminated all
Cholesky failures and dropped runtime from ~16 min to ~52 seconds.

---

## 3. Parallax Gate (`preflight_parallax.py`)

### 3.1 The three metrics
| Metric | Minimum | Target | What it catches |
|---|---|---|---|
| Median triangulation angle | 6° | 10° | **The arbiter** — low = spiky needles |
| Lateral/forward ratio | 10% | 20% | Rotation-dominant (pivoted, didn't travel) |
| Near-field coverage | 25% | 40% | Far-field dominant (endless corridor) |

### 3.2 Triangulation angle ceiling for backrooms wallpaper
Uniform yellow-green wallpaper is too repetitive for COLMAP to match frames more
than ~1 second apart. `max_pair_angle` (best angle across ALL camera pairs per point)
tops out at ~6° regardless of how much the camera moves.
**This is content, not a bug.** Calibrate the gate to 6°, don't fight the wallpaper.

### 3.3 Failure mode naming matters
The gate names the dominant failure (ROTATION-DOMINANT vs FAR-FIELD DOMINANT)
so you know which lever to pull for recapture. Low triangulation angle alone is
not actionable — the cause determines the fix.

### 3.4 Gate calibration was conservative
Initial threshold was 8°. After proving that 6.2° triangulation produces a clean
182k-Gaussian splat, we lowered `MIN_ANG` to 6°.

---

## 4. Nerfstudio splatfacto

### 4.1 Required env var for export
```bash
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 ns-export gaussian-splat ...
```
Without this, PyTorch 2.6 refuses to load the checkpoint.

### 4.2 ns-render dataset, not camera-path
`ns-render camera-path` requires a `camera_path.json` that doesn't exist by default.
Use `ns-render dataset --split train` instead to render training views.

### 4.3 30k iterations is enough
`--max-num-iterations 30000` produces a clean splat. The 6.2° triangulation
scene exported 182,569 / 183,246 Gaussians (99.6% kept after NaN/degenerate filter).

---

## 5. Gaussian Splat → Godot (GDGS)

### 5.1 Renderer requirement
GDGS requires **Forward+** renderer. Compatibility and Mobile renderers silently
produce no output.

### 5.2 Coordinate system — UNSOLVED
The PLY exported by Nerfstudio and the Godot world coordinate system (Y-up) do
not trivially align. The GDGS addon may apply an implicit rotation.
**In-game experience showed the visual room is correctly oriented** (ceiling up,
floor down) but the axis that corresponds to "toward the floor" in the splat
does not match the PLY Y axis as measured by percentile analysis.

**Implication:** Manual box collider fitting by guessing from PLY percentile
bounds is unreliable. A programmatic approach is needed (see §6).

### 5.3 PLY is gitignored — pipeline is the source of truth
`godot_walk/assets/corridor_splat/*.ply` is gitignored (large binary).
Regenerate with the pipeline; the scripts + the seed image are the real artifacts.

---

## 6. Collider Fitting — Unsolved, Needs Better Approach

### 6.1 Manual binary search is too slow
Hand-tuning box positions (floor Y, wall Z, column XZ) via in-game position
overlay + file edits is viable for one axis but impractical for all six planes
at once. Three iterations failed to converge.

### 6.2 Better approaches to investigate

**Option A — RANSAC plane fitting from PLY**
Filter the PLY to the dense core (10th–90th percentile), run RANSAC to find the
dominant horizontal plane (floor), vertical planes (walls), and vertical cylinder
(column). Export as a Godot `.tres` CollisionShape3D resource.
Script skeleton: `scripts/splat_pipeline/fit_collider.py` (not yet written).

**Option B — Godot editor placement with visual collision debug**
Enable `Project > Project Settings > Debug > Shapes > Show Collision Shapes`
at runtime, then drag StaticBody3D nodes in the editor while the game runs.
The live physics overlay makes misalignment obvious immediately.

**Option C — Low-poly convex hull from PLY cluster**
Voxelize the dense core at low resolution (e.g. 0.2-unit grid), extract the
occupied voxels' surface, import as a trimesh CollisionShape3D.
Godot supports `ConcavePolygonShape3D` from arbitrary mesh — no manual box fitting.

**Option D — NavMesh-first**
Bake a NavigationMesh directly over the floor plane (a large flat StaticBody3D
at the estimated floor Y). The NavMesh will only bake over traversable geometry.
The baked navmesh surface is an implicit floor probe.

### 6.3 What we know about the scene geometry
From PLY percentile analysis (5th/95th percentile, floater-filtered):
- Center of mass: (-0.7, 0.19, 0.02) in Godot world space
- X span: -3.28 to 1.01 (orbit + room depth)
- Y span: -2.56 to 2.74 (floor to ceiling + floaters)
- Z span: -0.76 to 0.84 (narrow — orbit width)
- Column position: approximately (−0.7, mid, 0.02) — confirmed by in-game collision

---

## 7. The Photogrammetry Mesh Path is Dead for This Capture

Proved early: COLMAP dense fusion requires at least 2-view point consistency.
`min_num_pixels 2` → 0 points. The uniform wallpaper prevents cross-view SIFT
matching even with relaxed thresholds. This is a property of the content, not
a tunable parameter. Meshroom hits the same ceiling.

**Gaussian splat works because it optimizes against images directly, not via
cross-view depth.** Splatfacto can reconstruct surfaces that MVS cannot touch.

---

## 8. Pipeline Run Order (Proven Working)

```bash
# 1. Generate clip
python3 scripts/generate_corridor_travel.py

# 2. COLMAP + parallax gate
conda activate nerfstudio
scripts/splat_pipeline/colmap_and_gate.sh \
    data/scenes/corridor_travel/video.mp4 \
    data/scenes/corridor_travel

# 3. Train (only if gate passes)
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 ns-train splatfacto \
    --data data/scenes/corridor_travel \
    --output-dir outputs \
    --experiment-name corridor_travel_v1 \
    --max-num-iterations 30000 \
    --vis tensorboard \
    --viewer.quit-on-train-completion True \
    colmap \
    --colmap-path sparse/0 \
    --images-path images \
    --downscale-factor 1

# 4. Export
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 ns-export gaussian-splat \
    --load-config outputs/corridor_travel_v1/splatfacto/<timestamp>/config.yml \
    --output-dir exports/corridor_travel_v1

# 5. Drop into Godot
cp exports/corridor_travel_v1/splat.ply \
    godot_walk/assets/corridor_splat/corridor.ply
# Reimport in Godot editor, then run corridor.tscn
```

---

## 9. Open Issues at This Point

| # | Priority | Description |
|---|---|---|
| #78 | high | Re-fit collider for open-room splat (blocked on better fitting approach) |
| #79 | medium | Generate additional rooms + portal links |
| #80 | medium | NavMesh + ambient AI wanderers |
| #81 | medium | PSX post-processing shader |
| #82 | low | Ambient audio |
