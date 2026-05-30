## Epic: Video → Walkable Gaussian Splat in Bevy (v1)

Take a video of a real place, reconstruct it as a 3D Gaussian splat, and let a
user walk around inside it in first person in Bevy. No RL — the user IS the
"robot": a first-person character controller in a photoreal reconstructed scene.

### Mental model (read first)
Two halves, developed/tested independently, meeting at a handoff contract:

1. **Front-end (offline, Python + CLI):** `video → posed frames → trained splat
   (.ply) → collision mesh (.glb)`. Runs once per scene on the GPU workstation.
   Produces TWO static asset files.
2. **Back-end (runtime, Rust + Bevy):** loads the splat (VISUALS) and the
   collision mesh (PHYSICS, invisible), spawns an FPS controller, lets the user walk.

**THE single most important fact:** a Gaussian splat is ONLY appearance — a cloud
of oriented translucent blobs. It has no surfaces, no floor, no collision. A
character falls through it forever unless we supply separate collision geometry.
That is why the front-end produces TWO outputs, not one.

### Per-scene deliverables (the contract)
| File | Role | Consumed by |
|------|------|-------------|
| `scene.ply` | Gaussian splat, visual only | `bevy_gaussian_splatting` |
| `collision.glb` | Coarse mesh, invisible, physics only | Avian trimesh collider |
| `alignment.toml` | up-axis + uniform scale + translation | `SceneAlignment` resource |

Because `scene.ply` and `collision.glb` come from the SAME reconstruction (Stage D
guarantees co-registration), ONE transform fixes both.

### Workspace decisions baked into the subissues (verify before pinning)
- **New sibling crate `splat_walk/`** (do NOT extend `backrooms_infinite/`). Reason:
  the existing crate uses `bevy_rapier3d 0.33` + WFC; this plan uses `avian3d` +
  `bevy-tnua`. Mixing two physics engines in one app is a footgun. Keep them separate.
- **Bevy version: pin 0.18** to match the workspace. `bevy_gaussian_splatting 7.x`
  targets Bevy 0.18 (5.x→0.16, 6.x→0.17). VERIFY on crates.io that avian3d + bevy-tnua
  + bevy-tnua-avian3d all have a 0.18-compatible release before committing. If they do
  NOT, the fallback is a dedicated Bevy-0.16 workspace member for splat_walk only.
- **Front-end scripts live in** `scripts/splat_pipeline/`.
- **Per-scene assets live in** `splat_walk/assets/splats/<scene_name>/`.

### De-risking build order (Section 5 of the plan — the handoff sequence)
1. Back-end controller on a flat plane (no splats).      → subissue [Back-end Step 1]
2. Render a known-good demo .ply.                         → subissue [Back-end Step 2]
3. Hand-made box collider under demo splat.               → subissue [Back-end Step 3]
4. SceneAlignment + alignment ritual.                     → subissue [Back-end Step 4]
   (parallel front-end track: Stages A–D)                 → subissues [FE Stage A..D]
5. Run front-end on one good capture → real assets.       → subissue [Integration Step 4]
6. Integrate real assets + alignment, walk end-to-end.    → subissue [Integration Step 5]

Each step has a clear pass/fail and only depends on the steps before it.

### Biggest honest risks (ranked)
1. Pose estimation on imperfect video — front-end make-or-break. COLMAP→VGGT
   fallback exists precisely because this is fragile.
2. `bevy_gaussian_splatting` maturity — the only experimental runtime link. Pin
   carefully, expect to read its source.
3. Alignment fiddliness — annoying but bounded; one-time per-scene calibration.

Everything else (Avian physics, tnua control, mouse-look) is well-trodden.

### Out of scope (v1)
RL / robot policy, dynamic/4D scenes, generative video input, relighting/dynamic
shadows on the splat, NPCs.

### Reference implementations to study
- PlayCanvas "Turning a Gaussian Splat into a Videogame" — splat+collider+FPS pattern.
- GaussGym (arXiv 2510.15352) — front-end at scale; source of VGGT-instead-of-COLMAP.
- Brush (ArthurBrussee/brush), VGGT (facebookresearch/vggt), SuGaR (Anttwo/SuGaR),
  bevy_gaussian_splatting (mosure/bevy_gaussian_splatting), bevy-tnua (idanarye/bevy-tnua), Avian.
