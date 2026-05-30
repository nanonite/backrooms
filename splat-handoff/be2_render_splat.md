## Goal (Back-end Step 2 — de-risking sequence #2)
Render a KNOWN-GOOD public `.ply` splat in the Bevy scene and fly/walk a camera
through it. Validates the splat renderer + crate version matching IN ISOLATION,
before any of our own front-end output is involved.

## Prereqs / Blockers
- Depends on Back-end Step 1 (crate exists, builds, runs).
- BLOCKER: pick the `bevy_gaussian_splatting` version that matches the pinned Bevy.
  For Bevy 0.18 → `7.x`. For 0.17 → `6.x`. For 0.16 → `5.x`. Mismatch = build errors
  about Bevy types.
- BLOCKER (stable Rust): the splat crate's DEFAULT features need NIGHTLY Rust.
  To build on STABLE: `default-features = false` AND ensure the `nightly_generic_alias`
  feature is OFF. If staying on nightly is acceptable, keep default features for full
  functionality.

## Files to modify/create
- `splat_walk/Cargo.toml` — add the splat dependency.
- `splat_walk/src/splat.rs` — splat-spawning system / plugin.
- `splat_walk/assets/demo/` — drop a known-good demo `.ply` here.

### Cargo.toml addition (verify version)
```toml
bevy_gaussian_splatting = { version = "7", default-features = false }  # 7.x = Bevy 0.18; stable Rust
```

### Acquire a known-good demo `.ply`
Use a demo asset from the `bevy_gaussian_splatting` repo/releases (its example assets
are the safest "known-good" inputs). Place at `splat_walk/assets/demo/demo.ply`.
Do NOT use our own reconstruction yet — the point is to isolate the renderer.

### `src/splat.rs` stub
```rust
use bevy::prelude::*;
use bevy_gaussian_splatting::{GaussianSplattingPlugin, PlanarGaussian3dHandle, CloudSettings};

pub struct DemoSplatPlugin;
impl Plugin for DemoSplatPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(GaussianSplattingPlugin)
           .add_systems(Startup, spawn_demo_splat);
    }
}

fn spawn_demo_splat(mut commands: Commands, assets: Res<AssetServer>) {
    commands.spawn((
        PlanarGaussian3dHandle(assets.load("demo/demo.ply")),
        CloudSettings::default(),
        Transform::IDENTITY,   // identity for now; alignment comes in Step 4
    ));
}
```
Type names (`PlanarGaussian3dHandle`, `CloudSettings`) are version-specific —
reconcile against the exact crate version's docs/source.

## Validation
1. `cargo build` from `splat_walk/`.
2. `cargo run` — the splat renders.
3. Free-fly (or walk) the camera through it; confirm it looks like the demo scene
   from multiple angles and does not flicker/disappear.

## Acceptance criteria
- Demo `.ply` renders correctly in-engine.
- Camera can move through the splat; appearance is stable across viewpoints.
- Build succeeds on the chosen toolchain (document stable-vs-nightly choice in a
  comment in Cargo.toml).

## Escalation conditions
- Won't build on stable even with `default-features = false` → switch the crate's
  toolchain to nightly via `rust-toolchain.toml` scoped to this crate, and note it.
- Renders black/empty with a valid `.ply` → read the crate's examples; confirm the
  handle component name and that a camera with the right render layers exists. This
  crate is the experimental link — budget time to read its source.
