## Goal (Integration Step 5 — full end-to-end: walk inside the real splat)
Load the REAL `scene.ply` + `collision.mesh.glb`, perform the per-scene alignment ritual,
and walk around inside the reconstructed place. This closes the loop end-to-end.

## Prereqs / Blockers
- Depends on Integration Step 4 (real assets staged) AND the entire back-end track
  (Steps 1–4: controller, splat render, two-entity collider, SceneAlignment).

## Procedure (the alignment ritual on real assets — Section 3.2)
1. Point the Bevy app at `splat_walk/assets/splats/<scene_name>/`.
2. Spawn splat entity (`scene.ply`) + collider entity (`collision.mesh.glb` as a
   `RigidBody::Static` trimesh, `Visibility::Hidden`) — BOTH with `align(&SceneAlignment)`.
3. Load `alignment.toml` (identity-ish defaults) and iterate the ritual:
   - Rotate so the floor is horizontal (gravity −Y). Usually −90° about X.
   - Scale so a known real distance (doorway ≈ 2m) matches Bevy units.
   - Translate so the player spawn drops onto the floor.
4. Bake the tuned constants back into `alignment.toml` and commit.

### Collider construction (Section 4.4)
Build a STATIC TRIMESH collider from the loaded mesh — correct for arbitrary scanned,
concave geometry. Do NOT use a convex-hull collider — it would fill in rooms/ceilings.
The mesh has no material / `Visibility::Hidden`, so it never draws.
```rust
commands.spawn((
    RigidBody::Static,
    ColliderConstructor::TrimeshFromMesh,                 // names are version-specific
    Mesh3d(assets.load("splats/<scene>/collision.mesh.glb")),
    Visibility::Hidden,
    align(&alignment),                                    // SAME transform as the splat
));
```

### Player confinement (design rule)
The splat is correct ONLY near where the real camera went. Confine the player to
roughly the captured volume (for a corridor/room walkthrough this is natural — keep
them on the path). Add soft bounds / invisible walls if needed.

## Acceptance criteria
- Splat renders; player walks on the invisible trimesh floor and CANNOT fall through.
- Player is human-sized; floor is horizontal; no walking on walls.
- Walking near captured surfaces looks photoreal; far-off-path views may smear (expected).
- Final tuned `alignment.toml` is committed for this scene.

## Escalation (symptom → fix)
- Falling forever → collider missing/misaligned or scale wrong; confirm trimesh built.
- Giant/ant-sized → recalibrate uniform scale against a known real distance.
- Walking on walls / sideways gravity → fix rotation (up-axis) in `alignment.toml`.
- Low FPS / VRAM blowout → too many splats; re-export Stage C with `--max-splats`,
  and/or decimate the scene.
- Janky collision near plants/rails → blobby mesh extraction; accept or hand-clean in Blender.
- Cargo errors about Bevy types → version mismatch across crates; pin all to one Bevy minor.

## Output
A playable build: walk around inside a video-reconstructed real place in first person.
