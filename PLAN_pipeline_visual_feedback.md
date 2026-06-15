# Plan: Walkable Corridor via Godot Splat (GDGS) + Fitted Collider

> **Status 2026-06-14:** Track A (visual-feedback harness) DONE. The mesh path
> (Track B) is **abandoned — proven non-viable** for these captures (see §Proof).
> Active direction: **GDGS Gaussian-splat visual + hand-built/fitted collider**,
> per `fable-plan.md` §3.4. User-confirmed.

## Proof the photogrammetry-mesh path is dead (for these low-texture corridors)

The blob in Godot was a COLMAP-dense → Poisson mesh. Diagnosing the rerun:

- Dense fusion with `min_num_pixels 1 / check_num_images 1` → **28,078,934 points**.
- Same depth maps with `min_num_pixels 2 / check_num_images 2` → **0 points**.

No 3D point in the scene is consistently seen by even two views. The "dense
cloud" is 24 single-view depth back-projections that don't agree — there is no
coherent surface under it. Poisson balloons it (the blob); Delaunay OOMs on 28M
incoherent points; a 2-view-consistent cloud is empty. This is **Multi-View
Stereo failing on uniform, textureless backrooms walls** — a property of the
capture, not a tunable parameter. (It also caps Meshroom, same MVS class.)

The Gaussian splat (`scene.ply`, 746k Brush splats) is **good**, because splat
training optimizes directly against the photos rather than via cross-view depth
matching. So: render the splat, fit a simple collider — don't mesh the MVS noise.

Corollary: the B2/#69 fusion tightening that produced "0 fused points" is moot —
even reverted (28M points) the cloud is unmeshable. Stop tuning COLMAP MVS.

---

## Track A — Godot visual-feedback harness — DONE

`screenshot_scene.gd` + `tools/shoot.sh` render a scene headlessly from 3 fixed
cameras to PNGs (vulkan→opengl3 fallback, xvfb for no-DISPLAY). This is the
judgment loop for everything below: *change → re-stage → shoot → compare*.

---

## Track C — GDGS splat visual + fitted collider (the v1 path)

Grounded in `fable-plan.md` §3.3–§3.4, with the architecture inverted: the splat
is the **v1 visual** (not a v2 layer over a mesh), and the collider is a simple
fitted/hand-built body (not the dead reconstructed mesh).

### C1 — De-risk the GDGS renderer in isolation
Install **GDGS** (`ReconWorldLab/godot-gaussian-splatting`, MIT) → `addons/gdgs/`.
Render a **known-good demo `.ply`** (from the GDGS repo) in a throwaway scene:
`GaussianSplatNode` + `WorldEnvironment`(Compositor + GDGS `CompositorEffect`),
Forward+. Fly the camera; confirm stable, non-flickering. Validate via `shoot.sh`.
Fallback forks if immature: `2Retr0/GodotGaussianSplatting`, `haztro/...`.
*Why first:* GDGS is the experimental link — isolate it before our own data.

### C2 — Render our `scene.ply` (corridor_straight)
Point a `GaussianSplatNode` at `assets/corridor_straight/scene.ply`; apply the
`scene_transform.txt` scale (0.800977) / Y-up. Judge via `shoot.sh` screenshots:
does it look like the corridor from the 3 cameras? (Parallel-safe with C3.)

### C3 — Fitted collider from the splat (no MVS mesh)
The splat point positions ARE a clean point cloud (unlike the MVS noise). Two
options, simplest-first:
1. **Editor-built primitive** (fable-plan §3.3): in the Godot editor, size a few
   `BoxShape3D`/`PlaneMesh` colliders (floor + 2 walls + ceiling) against the
   splat in the viewport; add a `Marker3D` spawn 0.5 m above floor and a thin
   `WorldBoundary`/box safety-net 5 cm under the floor. ~minutes, exact, no code.
2. **RANSAC plane-fit** (scriptable, generalizes): fit dominant planes (floor,
   then walls) to `scene.ply` xyz → emit `collision.glb` (box/extruded floor).
   Reusable across all captures; co-registered with the splat by construction.
Start with (1) for `corridor_straight`; promote to (2) for the multi-scene batch.

### C4 — Integrate + walk test
`corridor.tscn` = splat visual (C2) + collider (C3) + player. Run WALKTEST.md
acceptance (spawn on floor, walk end-to-end, shoulder-rub walls, doorway scale,
≥60 fps) and `shoot.sh`. This closes **#70**. Keep mesh out entirely.

### C5 — Multi-scene batch (we have several videos)
`corridor_corner, corridor_t, corridor_x, dead_end, room_large` each have a
capture. Splat each (Brush) and apply C2–C3. Favor the cleanest-splatting
captures. RANSAC collider (C3 opt 2) makes this repeatable per scene.

---

## Dependencies
- C2 ⟵ C1 (renderer must work first).
- C3 ∥ C1/C2 (collider from splat points needs no renderer).
- C4 ⟵ C2 + C3.  C5 ⟵ C4 pattern proven on corridor_straight.

## Files
- `godot_walk/addons/gdgs/` (new), `godot_walk/scenes/corridor.tscn` (splat node
  + collider + player), `godot_walk/assets/<scene>/scene.ply` (staged splat),
  optional `scripts/splat_pipeline/fit_collider.py` (RANSAC → collision.glb).
- Remove the dead `scene.glb` blob from `corridor.tscn` / assets.

## Superseded
Track B (Delaunay/fusion/Meshroom mesh) — abandoned. `scripts/splat_pipeline/
mesh_photogrammetry.sh` + the `--mesher` flag (#68) stay as dormant code; not in
the v1 path. Bevy back-end docs removed (legacy).
