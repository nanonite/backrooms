# Video → Walkable Gaussian Splat in Bevy — Implementation Plan

**Goal:** Take a video of a real place, reconstruct it as a 3D Gaussian splat, and let a user walk around inside it in first person using the Bevy game engine. No reinforcement learning. The user *is* the "robot" — a first-person character controller in a photoreal reconstructed environment.

**Audience:** This document is a handoff spec for an implementing agent. It assumes Rust, Python, and command-line competence. It does **not** assume prior knowledge of Gaussian splatting.

---

## 0. Mental model (read this first)

The project has two halves that are developed and tested independently:

1. **Front-end (offline, Python + CLI tools):** `video → posed frames → trained splat (.ply) → collision mesh (.obj/.glb)`. Runs once per scene on a workstation/GPU. Produces two static asset files.
2. **Back-end (runtime, Rust + Bevy):** loads the splat (for *visuals*) and the collision mesh (for *physics*, invisible), spawns a first-person character controller, and lets the user walk around.

The two halves meet at a **handoff contract** (Section 3). Get that contract right and the halves can be built in parallel.

**Critical conceptual point:** A Gaussian splat is *only an appearance representation* — a cloud of oriented translucent blobs. It has no surfaces, no collision, no floor. A character will fall through it forever unless we supply separate collision geometry. That is why the front-end produces **two** outputs, not one. This is the single most important thing to understand about the whole project.

---

## 1. Front-end: video → splat + mesh

### 1.1 Input video format (the conforming format)

The reconstruction quality is dominated by the input. Treat these as **hard requirements** for v1 and reject/flag videos that violate them:

- **Static scene.** Nothing moves: no people, no cars, minimal wind/water. Moving content corrupts geometry. (Dynamic-scene reconstruction is out of scope.)
- **Real parallax.** The camera must *translate* through space. Pure panning/rotation in place produces **zero** parallax and reconstructs to nothing.
- **Even, consistent lighting.** No auto-exposure swings, no flashing lights.
- **Low motion blur.** Slow, smooth camera movement.
- **Resolution:** 1080p minimum, 4K ideal.
- **Coverage:** every surface the player will see observed from at least 2–3 distinct angles.

> **Design rule:** the splat looks correct only from viewpoints near where the real camera went. Confine the player to roughly the captured volume.

### 1.2 Pipeline stages

```
video.mp4
  └─(ffmpeg)→ frames/*.jpg
        └─(pose estimation: COLMAP/GLOMAP  OR  VGGT fallback)→ sparse/ (COLMAP format)
              └─(Brush)→ scene.ply  (the splat — VISUAL asset)
                    └─(SuGaR or 2DGS)→ collision.obj  (the mesh — PHYSICS asset)
```

### 1.3 Stage A — Frame extraction (ffmpeg)

Extract 2–4 frames/sec. More is not better.

```bash
mkdir -p scene_dir/images
ffmpeg -i video.mp4 -vf "fps=3" -q:v 2 scene_dir/images/frame_%04d.jpg
```

Then **cull blurry frames** (variance-of-Laplacian; drop bottom ~15–20%):

```python
import cv2, os, glob, numpy as np
frames = sorted(glob.glob("scene_dir/images/*.jpg"))
scores = {f: cv2.Laplacian(cv2.imread(f, cv2.IMREAD_GRAYSCALE), cv2.CV_64F).var() for f in frames}
thresh = np.percentile(list(scores.values()), 18)
for f, s in scores.items():
    if s < thresh:
        os.remove(f)
print(f"kept {sum(1 for s in scores.values() if s >= thresh)} / {len(frames)} frames")
```

### 1.4 Stage B — Pose estimation (the decision point)

**Default to Path 1.** Use Path 2 only when Path 1 fails.

#### Path 1 — COLMAP / GLOMAP (default)

```bash
colmap feature_extractor --database_path scene_dir/database.db --image_path scene_dir/images --ImageReader.single_camera 1
colmap exhaustive_matcher --database_path scene_dir/database.db
# (sequential_matcher for long walkthroughs — far faster)
glomap mapper --database_path scene_dir/database.db --image_path scene_dir/images --output_path scene_dir/sparse
```

**Success check:** `scene_dir/sparse/0/` has `cameras.bin`, `images.bin`, `points3D.bin`, most images registered. Else → Path 2.

#### Path 2 — VGGT (fallback)

```bash
git clone https://github.com/facebookresearch/vggt
cd vggt && pip install -r requirements.txt
python demo_colmap.py --scene_dir=/abs/path/to/scene_dir --use_ba
```

VGGT poses are less metrically precise but vastly more robust. Exports directly to COLMAP format.

### 1.5 Stage C — Train the splat (Brush)

```bash
brush scene_dir/ --total-steps 30000 --export-path scene_dir/scene.ply
# --max-splats <N> caps memory
```

Stop when quality plateaus (7k–30k steps). Watch splat count: 1–3M comfortable, 10M+ strains Bevy.

### 1.6 Stage D — Extract collision mesh (SuGaR or 2DGS)

Mesh is **surface-aligned to the same Gaussians** → co-registered with the splat for free.

```bash
python train.py -s scene_dir/ -c <gs_checkpoint> -r density --export_obj True --low_poly True
```

Mesh can be ugly/low-poly — never rendered. Decimate to <200k tris, continuous floor, export `.glb`.

---

## 2. Front-end deliverables

| File | Role | Consumed by |
|------|------|-------------|
| `scene.ply` | Gaussian splat, visual only | `bevy_gaussian_splatting` |
| `collision.glb` | Coarse mesh, invisible, physics only | Avian/Rapier collider |

Plus the **up-axis + uniform scale transform** (Section 3.2).

---

## 3. The handoff contract

### 3.1 Coordinate frame
- COLMAP/VGGT: Z-up/Y-down, arbitrary scale + origin.
- Bevy: Y-up, right-handed, metric.
- Same reconstruction → **one transform fixes both** splat and collider.

### 3.2 Determining the alignment transform (once per scene)
1. Load both with identity transform.
2. Add 1m reference cube + origin gizmo.
3. Rotation → floor horizontal (usually −90° about X).
4. Scale → known real distance (doorway ≈ 2m) matches.
5. Translation → spawn drops onto floor.
6. Bake into `SceneAlignment { rotation, scale, translation }`.

> *Falling forever* = collider misaligned/scale wrong; *giant/ant* = scale wrong; *walking on walls* = rotation wrong.

---

## 4. Back-end: the Bevy runtime

### 4.1 Crate selection
Version-match everything to one Bevy minor. Baseline (verify on crates.io):

| Crate | Purpose |
|-------|---------|
| `bevy` | engine (pin one minor) |
| `bevy_gaussian_splatting` | render splat (5.x→0.16, 6.x→0.17, 7.x→0.18; `default-features=false` for stable Rust) |
| `avian3d` | physics |
| `bevy-tnua` + `bevy-tnua-avian3d` | character controller (matching physics-integration-layer) |
| `bevy_enhanced_input` | optional input |

### 4.2 Architecture: two entities, one transform
- Splat entity: `PlanarGaussian3dHandle(scene.ply)` + `CloudSettings` + alignment transform [VISIBLE, no collider]
- Collider entity: mesh + trimesh `Collider` + `RigidBody::Static` + same transform [INVISIBLE]
- Player entity: `Camera3d` + `TnuaController` + capsule + `RigidBody::Dynamic` + input

### 4.3–4.5
See subissue stubs for the plugin wiring, trimesh-from-mesh collider construction
(do NOT use convex hull), and mouse-look. Field/type names drift between versions —
reconcile against pinned-version docs.

---

## 5. Build & test order (de-risking sequence)
1. Bevy + tnua + Avian + mouse-look on a flat plane (no splats).
2. Render a known-good demo `.ply`.
3. Hand-made box collider under the demo splat.
4. SceneAlignment + alignment ritual.
5. Run the front-end on one good capture → real `scene.ply` + `collision.glb`.
6. Integrate real assets + alignment, walk around.

---

## 6. Known failure modes
| Symptom | Cause | Fix |
|---|---|---|
| COLMAP registers few images | low parallax/blur/textureless | VGGT (Path 2) |
| Smears up close | left captured volume | confine player, capture more angles |
| Falls through floor | collider missing/misaligned/scale | re-check alignment, confirm trimesh |
| Giant/ant-sized | wrong scale | recalibrate against known distance |
| Walking on walls | up-axis wrong | fix rotation |
| Low FPS / VRAM | too many splats | `--max-splats`, decimate |
| Janky collision near plants | blobby mesh | accept or hand-clean |
| Bevy type build errors | version mismatch | pin all to one Bevy minor |
| Splat crate won't build on stable | needs nightly | `default-features=false`, drop `nightly_generic_alias` |

**Ranked risks:** (1) pose estimation on imperfect video; (2) `bevy_gaussian_splatting` maturity; (3) alignment fiddliness.

## 7. Out of scope (v1)
RL/robot policy, dynamic/4D scenes, generative video input, relighting/shadows on splat, NPCs.

## 8. References
PlayCanvas "Turning a Gaussian Splat into a Videogame"; GaussGym (arXiv 2510.15352);
Brush; VGGT; SuGaR; bevy_gaussian_splatting; bevy-tnua; Avian.
