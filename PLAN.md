# First Walkable GLTF Room
**Milestone #9** | All issues tracked in chainlink (`chainlink issue tree`)

---

## Goal

Player can WASD-walk around a room reconstructed from `data/videos/corridor_corner.mp4`
with working mouse look and floor collision (can't fall through).

This replaces the WFC procedural world with a real video-sourced mesh.

---

## Pipeline

```
data/videos/corridor_corner.mp4
        │
        ▼  (Nerfstudio, conda env `nerfstudio`)
data/nerfstudio/corridor_corner/mesh/mesh.obj
        │
        ▼  (Blender cleanup + GLB export)
backrooms_infinite/assets/scenes/corridor_corner.glb
        │
        ▼  (Bevy SceneRoot + AsyncSceneCollider)
Walkable game room
```

---

## Task Tree

```
Milestone #9: First Walkable GLTF Room
│
├── [PHASE 1 — Unblocked, do first — can run in parallel]
│
├── #70  [bug/high]  Fix mouse look — EventReader<MouseMotion>
│         File: backrooms_infinite/src/player/camera.rs
│         Root cause: wrong Bevy API (bevy::ecs::message::MessageReader)
│         Fix: replace with EventReader<MouseMotion> from bevy::prelude
│         Import: use bevy::input::mouse::MouseMotion;
│
├── #71  [bug/high]  Fix UV mapping — remove atlas tile math
│         File: backrooms_infinite/src/world/room_mesh.rs
│         Root cause: AtlasTile 0–0.25 UV range applied to individual textures
│         Fix: emit full 0.0–1.0 UV range per quad face
│
├── [PHASE 2 — Unblocked, can start parallel with Phase 1]
│
├── #72  [feature/high]  Run Nerfstudio on corridor_corner.mp4
│         Env: conda activate nerfstudio
│         Commands:
│           ns-process-data video \
│             --data data/videos/corridor_corner.mp4 \
│             --output-dir data/nerfstudio/corridor_corner \
│             --matching-method exhaustive
│           ns-train nerfacto \
│             --data data/nerfstudio/corridor_corner \
│             --output-dir data/nerfstudio/corridor_corner/output
│           TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 ns-export tsdf \
│             --load-config data/nerfstudio/corridor_corner/output/<run>/config.yml \
│             --output-dir data/nerfstudio/corridor_corner/mesh
│         Output: data/nerfstudio/corridor_corner/mesh/mesh.obj
│         Fallback: if AI video lacks parallax, hand-model box room in Blender
│
├── #73  [feature/high]  Blender cleanup → GLB export
│         Blocked by: #72
│         - Import mesh.obj into Blender
│         - Decimate to ~5k polys, delete floating fragments
│         - Export: File → Export → glTF 2.0, format = GLB
│         Output: backrooms_infinite/assets/scenes/corridor_corner.glb
│
└── [PHASE 3 — Blocked by #70, #71, #73]

    #74  [feature/high]  Load GLTF scene in Bevy
    │     Blocked by: #70, #71, #73
    │     File: backrooms_infinite/src/main.rs
    │     - Comment out WFC startup: spawn_chunk_tasks, apply_generated_chunks
    │     - Add startup system spawn_gltf_world:
    │         commands.spawn((
    │             SceneRoot(asset_server.load("scenes/corridor_corner.glb#Scene0")),
    │             AsyncSceneCollider::new(Some(ComputedColliderShape::TriMesh)),
    │             RigidBody::Fixed,
    │         ));
    │     - Verify Cargo.toml: bevy_rapier3d features = ["async-collider"]
    │     - Fallback if AsyncSceneCollider unavailable: Collider::cuboid() floor plane
    │
    └── #75  [feature/high]  Set player spawn inside reconstructed room
              Blocked by: #74
              File: backrooms_infinite/src/player/movement.rs, spawn_player()
              Change spawn Transform to origin (0, 1, 0); tune after first run.
```

---

## Dependency Order

| Order | Issue | Can start when |
|-------|-------|----------------|
| 1 | #70 mouse look fix | immediately |
| 1 | #71 UV fix | immediately (parallel) |
| 1 | #72 Nerfstudio reconstruction | immediately (parallel) |
| 2 | #73 Blender → GLB | #72 done |
| 3 | #74 Bevy GLTF load | #70 + #71 + #73 done |
| 4 | #75 player spawn | #74 done |

---

## Verification

1. `cargo run` — game opens, no panic
2. Player spawns inside the corridor corner room (not underground)
3. WASD moves, mouse rotates camera
4. Player cannot fall through the floor (trimesh collider active)
5. Surfaces are visually recognizable as corridor corner geometry

---

## Quick Reference

```bash
chainlink issue list
chainlink issue ready
chainlink issue tree
chainlink milestone show 9
```

---

## Key Files

| File | Role |
|------|------|
| `backrooms_infinite/src/player/camera.rs` | Fix #70: mouse look EventReader |
| `backrooms_infinite/src/world/room_mesh.rs` | Fix #71: UV math |
| `backrooms_infinite/src/main.rs` | #74: disable WFC, add GLTF loader |
| `backrooms_infinite/Cargo.toml` | verify async-collider feature |
| `backrooms_infinite/src/player/movement.rs` | #75: player spawn point |
| `backrooms_infinite/assets/scenes/corridor_corner.glb` | output of #73 |
| `data/videos/corridor_corner.mp4` | source video for #72 |
| `data/nerfstudio/corridor_corner/` | Nerfstudio workspace for #72 |
