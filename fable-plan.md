# Video → Walkable Scene in Godot 4
**Successor to the Bevy `splat_walk` effort. Target: Godot 4.4+ (4.6 current).**

---

## 0. Post-mortem: why the Bevy attempts failed, and what changes

Every prior failure (`PLAN_splat_collider_fix.md` waves A–D, milestone #2/#8/#10)
traces to one architectural decision: **the collider was derived from the splat**
(splat → SuGaR mesh → decimate → trimesh), then re-aligned to the splat at runtime.
Three independent failure surfaces stacked up:

1. Splat-extracted meshes are holey, non-manifold triangle soup → tunneling, panics.
2. The alignment ritual (rotation/scale/translation) was never completed → non-metric world.
3. The Rust crate stack (bevy + avian3d + tnua + bevy_gaussian_splatting) had to be
   version-pinned in lockstep, multiplying integration bugs unrelated to the actual problem.

**The Godot plan inverts the architecture:**

> **v1 is mesh-first.** The photogrammetry textured mesh IS the world — it is both the
> visual and the collider, exported as one glTF, imported as one Godot scene.
> There is no handoff, no co-registration, no alignment ritual between two assets.
> A textured mesh cannot be misaligned with itself.

The Gaussian splat becomes a **v2 visual upgrade layered on top of an already-walkable
world**, not a prerequisite for it. This is the "Section D Path 2/3 fallback" from the
old plan, promoted to the primary path — because output beauty was explicitly not the
priority, and walkability was.

Godot-specific advantages we exploit:
- `CharacterBody3D` + `move_and_slide()` is built-in. No tnua/avian/PIL version matrix.
- glTF import is first-class; right-click a MeshInstance3D → **Create Trimesh Static Body**
  generates a `StaticBody3D` + `ConcavePolygonShape3D` in one editor action.
- The editor gives you a 3D viewport for the alignment/scale check interactively —
  no compile-run-eyeball loop.

### Vista4D / synthesized-view stitching: ruled out (again), with reasons

The intuition — "if Vista4D can move the camera, I can generate many splats and stitch
them" — fails at three points:
- **No new information.** Synthesized views are hallucinated from the same input video.
  Feeding them to COLMAP/Brush adds consistent-looking *wrong* geometry; reconstruction
  error compounds instead of averaging out.
- **Stitching is registration hell.** Independently trained splats live in independent
  arbitrary coordinate frames. Merging N of them is N-1 alignment rituals — the exact
  task that was never completed once in the Bevy effort.
- **Wrong bottleneck.** The bug was never view coverage or splat density. It was that
  splats have no surfaces. Denser splats → the same holey extracted meshes.

Where Vista4D-style tools *could* legitimately help later: filling visual coverage gaps
(v2 polish), never physics. Park it.

---

## 1. Pipeline overview

```
data/videos/<capture>.mp4
        │
        ▼  ffmpeg (3 fps, blur-cull)                          [reuse existing scripts]
frames/*.jpg
        │
        ▼  COLMAP/GLOMAP  (VGGT fallback)                     [reuse existing scripts]
sparse/  (poses)
        │
        ├──────────────► PATH M (v1, REQUIRED): photogrammetry mesh
        │                 COLMAP dense / Meshroom / RealityScan
        │                 → textured mesh → Blender cleanup → scene.glb
        │                 (visuals + collider in ONE file)
        │
        └──────────────► PATH S (v2, OPTIONAL): gaussian splat
                          Brush → scene.ply  (visuals only, layered over Path M collider)

godot_walk/  (Godot 4 project)
        scene.glb  → imported scene, trimesh static body   ← v1 walkable
        scene.ply  → GDGS GaussianSplatNode                ← v2 visual upgrade
```

---

## 2. Front-end

### 2.1 Stages A–B: unchanged
Frame extraction (ffmpeg @ 2–4 fps, variance-of-Laplacian blur cull) and pose
estimation (COLMAP/GLOMAP default, VGGT fallback) are identical to
`PLAN_video_to_splat.md` §1.3–1.4. Reuse the scripts as-is.

### 2.2 Stage M — textured mesh (the v1 deliverable)

Pick ONE tool, in order of preference:

| Option | Pros | Cons |
|--------|------|------|
| **COLMAP dense + Poisson** (`patch_match_stereo` → `stereo_fusion` → `poisson_mesher`) | already installed; reuses the same sparse model | needs CUDA for MVS; texture via `colmap delaunay`/external |
| **Meshroom** (AliceVision) | one-click video→textured glb; free | re-runs its own SfM (ignore — it's robust) |
| **RealityScan** (free for <$1M rev) | best mesh quality | Windows-leaning, separate workflow |

Output requirement (the entire contract, now trivially short):
- One `scene.glb`: textured triangle mesh, **Y-up, meters** (do the +Z-up→Y-up and
  metric scale once in Blender during cleanup — measure a known doorway ≈ 2.0 m,
  apply scale, `Ctrl+A` apply transforms).
- Blender cleanup pass: delete floating debris, fill floor holes
  (`Select Non-Manifold` → `Fill`), decimate to ≤ 500k tris, ensure the floor is
  one continuous surface. Export glTF 2.0 with textures embedded.

> Because the same mesh is rendered and collided against, "what you see is what you
> stand on" is true by construction. The §6 symptom table from the old plan
> (FALL_THROUGH / SCALE_WRONG / OFFSET) mostly ceases to exist as a class.

### 2.3 Stage S — splat (v2 only)
Brush as before → `scene.ply` (binary little-endian 3DGS layout — GDGS expects this,
not generic point clouds). Cap splat count (~1–3 M). **Same reconstruction** as the
mesh's sparse model so frames coincide up to the one Blender transform — record that
transform (rotation/scale) in `scene_transform.txt` when you bake it, so v2 can apply
the identical transform to the splat node.

---

## 3. Godot back-end

### 3.1 Project setup
- Godot 4.4+ standard (GDScript), **Forward+ renderer** (GDGS requirement for v2).
- Project `godot_walk/` with:
  ```
  godot_walk/
    scenes/world.tscn        # imported scene.glb + player
    scenes/player.tscn       # CharacterBody3D rig
    assets/<scene>/scene.glb
    assets/<scene>/scene.ply         (v2)
    addons/gdgs/                     (v2)
    scripts/player.gd
  ```

### 3.2 Player (build first, on a flat plane — BE-1 equivalent)
- `CharacterBody3D`
  - `CollisionShape3D` (capsule, r=0.3, h=1.8)
  - `Camera3D` at y≈1.6
- `player.gd`: standard FPS controller — gravity, `move_and_slide()`,
  mouse-look via `Input.MOUSE_MODE_CAPTURED` + `_unhandled_input` relative motion,
  WASD via `Input.get_vector`. ~40 lines, no third-party code. Add Esc to release mouse.
- Tuning: walk 4 m/s, jump optional, snap-to-floor via
  `floor_snap_length = 0.3` to handle bumpy reconstructed floors.

### 3.3 World (v1)
1. Drop `scene.glb` into the project; Godot auto-imports.
2. In the import dock, either:
   - set **Generate → Physics: Trimesh static body** on import (automatic), or
   - instance the scene, select the MeshInstance3D, **Mesh → Create Trimesh Static Body**.
3. Verify in-editor with the 1 m default cube next to a doorway: doorway ≈ 2 cubes tall.
   If not — fix scale in Blender, re-export. (This replaces the entire Wave-D
   alignment ritual; it's a 30-second visual check in the editor viewport.)
4. Place a `Marker3D` spawn point 0.5 m above the floor in the editor — by eye,
   in the viewport, not via RANSAC at runtime.

Optional robustness (cheap, recommended): keep the old safety-net idea as a single
invisible `WorldBoundary` or large thin `BoxShape3D` 5 cm under the lowest floor point —
3 nodes in the editor, no code — so a missed floor hole demotes "fall forever" to
"step on the net, notice, patch the mesh."

### 3.4 Splat visuals (v2)
1. Install GDGS (`ReconWorldLab/godot-gaussian-splatting`, MIT) into `addons/gdgs/`.
2. Import `scene.ply` → assign to a `GaussianSplatNode`; add `WorldEnvironment`
   with a `Compositor` + the GDGS `CompositorEffect` script.
3. Apply the recorded `scene_transform.txt` rotation/scale to the splat node so it
   coincides with the (already-walkable, already-metric) mesh.
4. Hide the mesh's visual (set MeshInstance3D invisible, keep its StaticBody3D) —
   GDGS composes depth-aware against remaining scene geometry, so any visible props
   still occlude correctly.
5. Known constraints: desktop Forward+ only; large .ply imports are slow; watch VRAM.

If GDGS proves immature for your scene → v1 stands alone as the shipped result; the
textured mesh is the game. (Fallbacks: 2Retr0/GodotGaussianSplatting,
haztro/godot-gaussian-splatting.)

---

## 4. Build order (de-risk sequence)

| Step | Goal | Done when |
|------|------|-----------|
| G-1 | Player controller on a flat `PlaneMesh` + box | WASD + mouse-look feel right |
| G-2 | Import any known-good textured glb (e.g. a Sketchfab room), trimesh body, walk it | no fall-through in a known-good asset |
| M-1 | Run Stage M on `corridor_straight` capture → `scene.glb` | textured mesh opens clean in Blender, floor continuous, metric |
| G-3 | Import real `scene.glb`, trimesh body, spawn marker, walk | **v1 DONE: walk the real corridor** |
| S-1 | Brush splat from same reconstruction (may already exist: `scene.ply`) | renders in GDGS sample project |
| G-4 | Layer splat over invisible mesh, apply recorded transform | splat and collider coincide while walking |

G-1/G-2 (engine track) parallel with M-1 (asset track). G-3 needs both.
S-1/G-4 strictly after G-3 — never block walkability on splats again.

---

## 5. Verification

1. **G-3 acceptance:** spawn on floor, WASD the full corridor, shoulder-rub every wall,
   stand in corners — no fall-through, no floating, no tunneling, doorway feels door-sized.
2. **Scale check:** player capsule (1.8 m) vs doorway in-game ≈ real proportions.
3. **Perf:** ≥ 60 fps v1; v2 ≥ 30 fps with splats (reduce splat count / viewport
   resolution if VRAM-pressured).
4. **v2 acceptance:** toggle mesh visibility on/off mid-walk — splat and mesh surfaces
   coincide within a few cm everywhere the player can reach.

## 6. Failure modes (new table)

| Symptom | Cause | Fix |
|---|---|---|
| Holes in floor while walking | mesh holes survived cleanup | Blender fill non-manifold; safety net catches meanwhile |
| Doorway wrong size | scale not applied in Blender | re-measure, Apply Transforms, re-export |
| Splat offset from walls (v2) | transform not recorded/applied | re-derive from `scene_transform.txt`; verify with mesh-visibility toggle |
| GDGS glitches / black frames | 4K viewport VRAM pressure, non-Forward+ renderer | Forward+, lower viewport res, fewer splats |
| Meshroom mesh blobby near plants | MVS noise | accept (invisible in v2) or hand-clean |
| Slow .ply import | large file, known GDGS limitation | cap splats in Brush, consider .sog v2 archive |

## 7. Out of scope
Vista4D / synthesized-view stitching (see §0), multi-scene streaming, dynamic scenes,
relighting splats, NPCs, VR (GDGS has VR fixes but don't test on it for v1).