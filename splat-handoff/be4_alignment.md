## Goal (Back-end Step 4 — handoff contract Section 3.2)
Introduce a `SceneAlignment` resource and the per-scene "alignment ritual" that maps
a reconstruction's arbitrary coordinate frame into Bevy's world (Y-up, right-handed,
metric). ONE transform is applied identically to BOTH the splat entity and the
collider entity (they are co-registered by Stage D, so one transform fixes both).

## Prereqs / Blockers
- Depends on Back-end Step 3 (two-entity pattern working).
- Relates to the Handoff-contract subissue (defines the `alignment.toml` format this
  resource is loaded from).

## Coordinate-frame facts
- COLMAP/VGGT/splat tools: Z-up or Y-down, ARBITRARY scale, arbitrary origin.
- Bevy: Y-up, right-handed, roughly METRIC (so a ~1.7m capsule and 9.8 m/s² feel right).

## The ritual (do once per scene)
1. Load splat + collider with IDENTITY transform in a debug scene.
2. Add a 1m reference cube + an origin gizmo.
3. Find the ROTATION that makes the real floor horizontal (gravity along −Y).
   Usually a single −90° about X (Z-up → Y-up): `Quat::from_rotation_x(-FRAC_PI_2)`.
4. Find the uniform SCALE that makes a known real distance (e.g. a doorway ≈ 2m)
   match in Bevy units.
5. Find the TRANSLATION that drops the player spawn onto the floor.
6. BAKE these constants into the scene's `alignment.toml`, loaded into `SceneAlignment`.

## Files to create/modify
- `splat_walk/src/alignment.rs` — the resource + loader + `align()` helper.
- `splat_walk/src/main.rs` — insert the resource, apply transform in scene setup.

### Stub
```rust
#[derive(Resource, serde::Deserialize)]
pub struct SceneAlignment { pub rotation: Quat, pub scale: f32, pub translation: Vec3 }

pub fn align(a: &SceneAlignment) -> Transform {
    Transform { translation: a.translation, rotation: a.rotation, scale: Vec3::splat(a.scale) }
}

// load from assets/splats/<scene>/alignment.toml (see Handoff-contract subissue for schema)
```
Apply `align(&res)` to BOTH the splat entity and the collider entity in scene setup.

## Symptom → cause guide (put this in code comments)
- Falling forever        → collider below/misaligned OR scale wrong.
- Giant / ant-sized      → scale wrong.
- Walking on walls       → rotation wrong (up-axis not fixed).

## Acceptance criteria
- `SceneAlignment` is loaded from a TOML file (not hard-coded), defaulting to the
  Z-up→Y-up rotation, scale 1.0, translation ZERO.
- Splat and collider receive the IDENTICAL transform.
- With the demo splat + a hand-tuned `alignment.toml`, floor is horizontal, player is
  human-sized, and spawn lands on the floor.

## Escalation conditions
- Can't get floor horizontal with a single-axis rotation → the reconstruction may use
  an unusual frame; allow a full Quat in the TOML and tune all three axes.
- Scale ambiguous (no known real distance in frame) → pick a reference during capture
  (a meter stick / known doorway) and record it; note this as a capture requirement.
