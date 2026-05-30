## Goal (Back-end Step 3 — de-risking sequence #3)
Manually place a box collider as a floor UNDER the demo splat and walk on it.
Validates the two-entity / shared-transform architecture WITHOUT needing the
front-end's Stage-D mesh yet. This proves the runtime pattern that real assets
will later slot into.

## Prereqs / Blockers
- Depends on Back-end Step 2 (demo splat renders) and Step 1 (controller works).

## Architecture being validated (two entities, one transform)
```
Splat entity:    PlanarGaussian3dHandle(demo.ply) + CloudSettings + Transform   [VISIBLE, no collider]
Collider entity: RigidBody::Static + Collider::cuboid(...) + Transform           [INVISIBLE, no render]
Player entity:   from Step 1                                                      [walks on collider]
```
The splat is rendered but has NO collider. The collider is solid but is NEVER
rendered (no mesh material / `Visibility::Hidden`). In this step the collider is a
hand-placed primitive; in the real pipeline it becomes the Stage-D trimesh.

## Files to modify
- `splat_walk/src/splat.rs` (or a new `scene.rs`) — add the static box collider.

### Stub
```rust
fn spawn_floor_collider(mut commands: Commands) {
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(20.0, 0.5, 20.0),   // wide thin slab; tune to sit under the demo splat
        Transform::from_xyz(0.0, -0.25, 0.0),
        Visibility::Hidden,                  // never drawn
    ));
}
```

## Validation
1. `cargo run`; the demo splat renders and the player spawns above the slab.
2. Player stands on the invisible slab, walks around, does not fall through.
3. Position the slab (translation/size) so its top aligns with the splat's apparent floor.

## Acceptance criteria
- Player walks on an invisible collider beneath the visible splat.
- Splat has no collision of its own (confirm by removing the slab → player falls forever).
- Same `Transform` value can be applied to both splat and collider entities
  (prove the shared-transform idea by giving both the SAME transform and offsetting
  geometry, not transforms).

## Escalation conditions
- Player falls through despite the slab → collider not registered as Static, or
  capsule float_height mismatch; re-check Step 1 grounding first.
- Can't visually judge where the floor is → add a debug gizmo / 1m reference cube at
  the origin (you'll need this anyway for Step 4 alignment).
