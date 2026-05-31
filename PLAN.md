# Video → Walkable Gaussian Splat
**Milestone #10** | All issues tracked in chainlink (`chainlink issue tree`)

---

## Goal

Walk around a video-reconstructed real place in first-person inside Bevy.
A Gaussian splat provides visuals; a co-registered collision mesh provides physics.

---

## Crate

`splat_walk/` at the workspace root (`/home/user/backrooms-workspace/splat_walk/`).
The old `backrooms_infinite/` WFC crate was deleted — do not recreate it.

---

## Pipeline

```
data/videos/<capture>.mp4
        │
        ▼  (ffmpeg → COLMAP/VGGT → Brush)
splat_walk/assets/splats/<scene>/scene.ply        ← VISUAL only
        │
        ▼  (SuGaR/2DGS → Blender decimate → GLB)
splat_walk/assets/splats/<scene>/collision.glb    ← PHYSICS only, invisible
        │
        ▼  + alignment.toml (rotation/scale/translation)
Bevy: splat entity + static trimesh collider + FPS controller
```

---

## Tech Stack

| Crate | Version | Purpose |
|-------|---------|---------|
| `bevy` | 0.18 | engine |
| `avian3d` | 0.6 | physics |
| `bevy-tnua` | 0.31 | character controller |
| `bevy-tnua-avian3d` | 0.11 | tnua ↔ avian (PIL ^0.12) |
| `bevy_gaussian_splatting` | 7 | splat renderer (default-features=false) |

---

## Build Order (de-risking sequence)

| Step | Issue | Goal |
|------|-------|------|
| BE-1 | #101 | Controller + mouse-look on flat plane (no splats) |
| BE-2 | #102 | Render known-good demo .ply |
| BE-3 | #103 | Hand-placed box collider under demo splat |
| BE-4 | #104 | SceneAlignment resource + per-scene ritual |
| FE-A | #105 | Frame extraction (ffmpeg) |
| FE-B | #106 | Pose estimation (COLMAP → VGGT fallback) |
| FE-C | #107 | Train splat (Brush) |
| FE-D | #108 | Collision mesh (SuGaR) |
| INT-4 | #109 | Run full front-end on one good capture |
| INT-5 | #110 | Integrate real assets + alignment, walk end-to-end |

BE-1 through BE-4 and FE-A through FE-D are independent tracks (run in parallel).
INT-4 requires FE-A–D; INT-5 requires BE-1–4 + INT-4.

---

## Verification

1. `cargo build` from `splat_walk/` succeeds.
2. Player spawns, WASD moves, mouse rotates; no falling through floor.
3. Splat renders at real-scene viewpoints; collision is solid and invisible.

---

## Detail Docs

See `splat-handoff/` for per-step scaffolding:

| Doc | Content |
|-----|---------|
| `splat-handoff/epic.md` | Full epic overview |
| `splat-handoff/PLAN_video_to_splat.md` | Detailed implementation plan |
| `splat-handoff/be1_controller.md` | BE-1 scaffold |
| `splat-handoff/be2_render_splat.md` | BE-2 scaffold |
| `splat-handoff/be3_handmade_collider.md` | BE-3 scaffold |
| `splat-handoff/be4_alignment.md` | BE-4 scaffold |
| `splat-handoff/handoff_contract.md` | Front ↔ back interface |
| `splat-handoff/fe_stageA_frames.md` | FE-A frames |
| `splat-handoff/fe_stageB_colmap.md` | FE-B COLMAP |
| `splat-handoff/fe_stageB_vggt.md` | FE-B VGGT fallback |
| `splat-handoff/fe_stageC_brush.md` | FE-C splat training |
| `splat-handoff/fe_stageD_mesh.md` | FE-D collision mesh |
| `splat-handoff/integ4_run_frontend.md` | INT-4 pipeline run |
| `splat-handoff/integ5_full.md` | INT-5 end-to-end |

---

## Quick Reference

```bash
chainlink issue list
chainlink issue ready
chainlink issue tree
chainlink milestone show 10
```
