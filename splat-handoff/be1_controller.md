## Goal (Back-end Step 1 — de-risking sequence #1)
Prove a first-person character controller (bevy-tnua + Avian3d) with mouse-look
feels right walking on a primitive ground plane. NO splats yet. Pure back-end,
zero front-end dependency. This is the foundation everything else builds on.

## Prereqs / Blockers
- BLOCKER (resolve first): create the new crate `splat_walk/` at the workspace root.
  (The old `backrooms_infinite/` WFC crate was DELETED — clean slate. Do not recreate
  it or copy its rapier-based physics; this crate uses avian3d + bevy-tnua.)
- BLOCKER: verify on crates.io that `avian3d`, `bevy-tnua`, `bevy-tnua-avian3d`
  each publish a release compatible with **Bevy 0.18**. The crate `physics-integration-layer`
  version pulled by `bevy-tnua` and `bevy-tnua-avian3d` MUST match between them.
  If no 0.18-compatible set exists, ESCALATE: fall back to a Bevy-0.16 pin for this
  crate only and record the decision in the epic.

## Files to create
- `splat_walk/Cargo.toml`
- `splat_walk/src/main.rs`
- `splat_walk/src/player.rs`   (controller + mouse-look)
- (optional) add `splat_walk` to a workspace `[workspace] members` if one exists,
  else keep it a standalone crate.

### `splat_walk/Cargo.toml` stub (verify every version before building)
```toml
[package]
name = "splat_walk"
version = "0.1.0"
edition = "2021"

[dependencies]
bevy = "0.18"
avian3d = "*"               # PIN to the 0.18-compatible release after verifying
bevy-tnua = "*"             # PIN; must share physics-integration-layer with the line below
bevy-tnua-avian3d = "*"     # PIN
```

### `src/player.rs` stub
```rust
use bevy::prelude::*;
use bevy::input::mouse::MouseMotion;
use avian3d::prelude::*;
use bevy_tnua::prelude::*;
use bevy_tnua_avian3d::*;

#[derive(Component, Default)]
pub struct PlayerLook { pub yaw: f32, pub pitch: f32 }

pub fn setup_player(mut commands: Commands) {
    commands.spawn((
        Camera3d::default(),
        Transform::from_xyz(0.0, 1.7, 0.0),      // eye height; tune after alignment
        RigidBody::Dynamic,
        Collider::capsule(0.3, 1.5),             // (radius, height) — names drift; check docs
        TnuaController::default(),
        PlayerLook::default(),
        // keep upright, allow yaw only:
        LockedAxes::ROTATION_LOCKED,             // then unlock Y if the API supports it
    ));
}

pub fn player_movement(
    keys: Res<ButtonInput<KeyCode>>,
    mut q: Query<&mut TnuaController>,
) {
    let Ok(mut controller) = q.single_mut() else { return; };
    let mut dir = Vec3::ZERO;
    if keys.pressed(KeyCode::KeyW) { dir -= Vec3::Z; }
    if keys.pressed(KeyCode::KeyS) { dir += Vec3::Z; }
    if keys.pressed(KeyCode::KeyA) { dir -= Vec3::X; }
    if keys.pressed(KeyCode::KeyD) { dir += Vec3::X; }
    controller.basis(TnuaBuiltinWalk {
        desired_velocity: dir.normalize_or_zero() * 4.0,
        float_height: 1.5,                        // MUST match capsule geometry — see tnua docs
        ..default()
    });
    if keys.pressed(KeyCode::Space) {
        controller.action(TnuaBuiltinJump { height: 2.0, ..default() });
    }
}

// Mouse-look: capture cursor, accumulate yaw on body / pitch on camera child.
pub fn mouse_look(/* EventReader<MouseMotion>, Query<(&mut Transform, &mut PlayerLook)> */) { /* TODO */ }
```

### `src/main.rs` stub
```rust
fn main() {
    App::new()
        .add_plugins(DefaultPlugins)
        .add_plugins(PhysicsPlugins::default())
        .add_plugins(TnuaControllerPlugin::default())
        .add_plugins(TnuaAvian3dPlugin::default())
        .add_systems(Startup, (setup_ground, setup_player))   // setup_ground = plane + cube + light
        .add_systems(Update, (mouse_look, player_movement.in_set(TnuaUserControlsSystemSet)))
        .run();
}
```
`setup_ground`: spawn a large static plane with `RigidBody::Static` +
`Collider::half_space`/`Collider::cuboid`, a directional light, and a reference cube.

## API reconciliation notes (the stubs WILL drift)
Field/type names move between Bevy/tnua/avian versions. Reconcile against the docs
for your pinned versions, especially: `TnuaBuiltinWalk` fields (`float_height`,
`desired_velocity`), `LockedAxes` API for yaw-only, and Avian's `Collider::capsule`
argument order. The mouse-motion reader API matters: this workspace previously hit a
Bevy-0.18 gotcha (`MessageReader` vs `EventReader<MouseMotion>`). The old fix lives
only in the backup tag `archive/pre-cleanup-2026-05-29`
(`backrooms_infinite/src/player/movement.rs`, `player/camera.rs`) — treat it as
UNTRUSTED reference; prefer the bevy-tnua / bevy_gaussian_splatting examples for your
pinned versions.

## Acceptance criteria
- `cargo build` and `cargo run` from `splat_walk/` succeed.
- WASD moves the capsule along the plane; it does NOT fall through.
- Space jumps; player lands and stays grounded (no jitter — tune `float_height`).
- Mouse moves the view (yaw on body, pitch on camera); cursor is captured; ESC frees it.
- No sideways gravity, no sinking into the floor.

## Escalation conditions
- No mutually-compatible 0.18 release of avian3d/tnua/tnua-avian3d → fall back to Bevy 0.16
  for this crate and note it in the epic; all later subissues inherit that pin.
- Persistent ground jitter that `float_height` tuning can't fix → try `bevy_ahoy`
  (kinematic, Avian-based) as the alternate controller. Pick ONE controller, not both.
