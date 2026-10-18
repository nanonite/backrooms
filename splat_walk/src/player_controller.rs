use avian3d::prelude::{Collider, LockedAxes, RigidBody};
use bevy::prelude::{Bundle, Component, Handle, Transform, Vec3};
use bevy_tnua::{
    TnuaController, TnuaScheme, TnuaToggle,
    builtins::{TnuaBuiltinWalkConfig, TnuaBuiltinWalkHeadroom},
    prelude::TnuaConfig,
};
use bevy_tnua_avian3d::prelude::TnuaAvian3dSensorShape;

pub const PLAYER_RADIUS_M: f32 = 0.3;
pub const PLAYER_STEM_M: f32 = 0.6;
pub const PLAYER_HEIGHT_M: f32 = PLAYER_STEM_M + PLAYER_RADIUS_M * 2.0;
pub const PLAYER_GROUND_SENSOR_RADIUS_M: f32 = PLAYER_RADIUS_M * 0.25;
pub const CONTROLLER_MAX_SLOPE_DEGREES: f32 = 16.0;
pub const PLAYER_FLOAT_HEIGHT_M: f32 = 0.7;
pub const PLAYER_FREE_FALL_EXTRA_GRAVITY_MPS2: f32 = 0.0;

#[derive(TnuaScheme)]
#[scheme(basis = bevy_tnua::builtins::TnuaBuiltinWalk)]
pub enum ControlScheme {}

#[derive(Bundle)]
pub struct PlayerControllerBundle {
    pub rigid_body: RigidBody,
    pub collider: Collider,
    pub controller: TnuaController<ControlScheme>,
    pub config: TnuaConfig<ControlScheme>,
    pub sensor_shape: TnuaAvian3dSensorShape,
    pub locked_axes: LockedAxes,
    pub transform: Transform,
    pub toggle: TnuaToggle,
    pub steep_ground_hold: SteepGroundHold,
}

/// Set while the character, having arrived from walkable support, is blocked by unwalkable
/// ground and holds its height there.
#[derive(Component, Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct SteepGroundHold(pub bool);

/// What the character's components should be set to for the current ground, from
/// [`steep_ground_command`]. While `hold` is set, the caller must also zero the vertical
/// velocity.
#[derive(Clone, Copy, Debug)]
pub struct SteepGroundCommand {
    pub toggle: TnuaToggle,
    pub hold: SteepGroundHold,
    pub locked_axes: LockedAxes,
}

pub fn walk_config() -> ControlSchemeConfig {
    ControlSchemeConfig {
        basis: TnuaBuiltinWalkConfig {
            speed: 2.0,
            float_height: PLAYER_FLOAT_HEIGHT_M,
            max_slope: CONTROLLER_MAX_SLOPE_DEGREES.to_radians(),
            free_fall_extra_gravity: PLAYER_FREE_FALL_EXTRA_GRAVITY_MPS2,
            cling_distance: 0.2,
            headroom: Some(TnuaBuiltinWalkHeadroom {
                distance_to_collider_top: 0.6,
                sensor_extra_distance: 0.3,
            }),
            ..Default::default()
        },
    }
}

pub fn player_bundle(start: Vec3, config: Handle<ControlSchemeConfig>) -> PlayerControllerBundle {
    PlayerControllerBundle {
        rigid_body: RigidBody::Dynamic,
        collider: Collider::capsule(PLAYER_RADIUS_M, PLAYER_STEM_M),
        controller: TnuaController::<ControlScheme>::default(),
        config: TnuaConfig::<ControlScheme>(config),
        sensor_shape: TnuaAvian3dSensorShape(Collider::cylinder(
            PLAYER_GROUND_SENSOR_RADIUS_M,
            0.0,
        )),
        locked_axes: LockedAxes::ROTATION_LOCKED,
        transform: Transform::from_translation(start),
        toggle: TnuaToggle::Enabled,
        steep_ground_hold: SteepGroundHold::default(),
    }
}

pub fn shape_steep_slope_motion(desired_motion: Vec3, ground_normal: Option<Vec3>) -> Vec3 {
    let Some(normal) = ground_normal else {
        return desired_motion;
    };
    let normal = normal.normalize_or_zero();
    if normal == Vec3::ZERO
        || normal.angle_between(Vec3::Y) <= CONTROLLER_MAX_SLOPE_DEGREES.to_radians()
    {
        return desired_motion;
    }
    let uphill = Vec3::Y - normal * normal.y;
    let uphill = Vec3::new(uphill.x, 0.0, uphill.z).normalize_or_zero();
    let uphill_input = desired_motion.dot(uphill).max(0.0);
    desired_motion - uphill * uphill_input
}

fn is_steep(ground_normal: Option<Vec3>) -> bool {
    ground_normal
        .map(Vec3::normalize_or_zero)
        .is_some_and(|normal| {
            normal != Vec3::ZERO
                && normal.angle_between(Vec3::Y) > CONTROLLER_MAX_SLOPE_DEGREES.to_radians()
        })
}

/// Chooses the Tnua toggle for the current ground. Ground steeper than the max slope is not
/// walkable: Tnua keeps sensing it (and clears `standing_on`), but its motor is not applied
/// unless the shaped motion leads downhill off the incline. Without this, Tnua 0.31 keeps its
/// float spring on while the character rises over steep ground and drops it once rising stops,
/// which makes the capsule repeatedly lift toward float height and fall back onto the incline.
pub fn steep_ground_toggle(shaped_motion: Vec3, ground_normal: Option<Vec3>) -> TnuaToggle {
    if !is_steep(ground_normal) {
        return TnuaToggle::Enabled;
    }
    let normal = ground_normal.unwrap_or(Vec3::Y).normalize_or_zero();
    let downhill = Vec3::new(normal.x, 0.0, normal.z).normalize_or_zero();
    if shaped_motion.dot(downhill) > 1.0e-3 {
        TnuaToggle::Enabled
    } else {
        TnuaToggle::SenseOnly
    }
}

/// Steep ground acts as a wall. When unwalkable ground stops a character that was standing on
/// walkable ground, the character keeps its current height: Y translation is locked until the
/// sensor finds walkable ground (or none) again. Without this, the 10 cm float gap collapses as
/// soon as Tnua drops float support on unwalkable ground. The hold also covers stepping back
/// downhill while the incline is still within float height below the character. Moving
/// downhill over steep ground that drops away beyond float height releases the hold, so the
/// character descends rather than hovering. A character that reaches steep ground without
/// walkable support beforehand (for example while falling) is not held.
pub fn steep_ground_command(
    shaped_motion: Vec3,
    ground_normal: Option<Vec3>,
    ground_proximity: Option<f32>,
    was_supported: bool,
    hold: SteepGroundHold,
) -> SteepGroundCommand {
    let toggle = steep_ground_toggle(shaped_motion, ground_normal);
    let steep = is_steep(ground_normal);
    let within_float = ground_proximity.is_some_and(|value| value <= PLAYER_FLOAT_HEIGHT_M);
    let holding =
        steep && (hold.0 || was_supported) && (toggle == TnuaToggle::SenseOnly || within_float);
    SteepGroundCommand {
        toggle,
        hold: SteepGroundHold(holding),
        locked_axes: if holding {
            LockedAxes::ROTATION_LOCKED.lock_translation_y()
        } else {
            LockedAxes::ROTATION_LOCKED
        },
    }
}

#[cfg(test)]
mod tests {
    use super::{
        SteepGroundHold, shape_steep_slope_motion, steep_ground_command, steep_ground_toggle,
    };
    use bevy::prelude::Vec3;
    use bevy_tnua::TnuaToggle;

    #[test]
    fn steep_slope_removes_only_uphill_input() {
        let normal = slope_normal(17.0);
        let result = shape_steep_slope_motion(Vec3::new(1.0, 0.0, 1.0), Some(normal));
        assert!(result.x.abs() < 1.0e-6);
        assert!((result.z - 1.0).abs() < 1.0e-6);
    }

    #[test]
    fn steep_slope_keeps_downhill_input() {
        let result = shape_steep_slope_motion(Vec3::NEG_X, Some(slope_normal(17.0)));
        assert_eq!(result, Vec3::NEG_X);
    }

    #[test]
    fn walkable_slope_keeps_uphill_input() {
        let result = shape_steep_slope_motion(Vec3::X, Some(slope_normal(15.0)));
        assert_eq!(result, Vec3::X);
    }

    #[test]
    fn missing_or_invalid_normal_keeps_input() {
        assert_eq!(shape_steep_slope_motion(Vec3::X, None), Vec3::X);
        assert_eq!(shape_steep_slope_motion(Vec3::X, Some(Vec3::ZERO)), Vec3::X);
    }

    #[test]
    fn steep_ground_without_downhill_motion_senses_only() {
        let normal = Some(slope_normal(17.0));
        assert_eq!(
            steep_ground_toggle(Vec3::ZERO, normal),
            TnuaToggle::SenseOnly
        );
        assert_eq!(steep_ground_toggle(Vec3::Z, normal), TnuaToggle::SenseOnly);
    }

    #[test]
    fn steep_ground_with_downhill_motion_keeps_motor() {
        let normal = Some(slope_normal(17.0));
        assert_eq!(
            steep_ground_toggle(Vec3::NEG_X, normal),
            TnuaToggle::Enabled
        );
    }

    #[test]
    fn walkable_or_missing_ground_keeps_motor() {
        assert_eq!(
            steep_ground_toggle(Vec3::ZERO, Some(slope_normal(15.0))),
            TnuaToggle::Enabled
        );
        assert_eq!(steep_ground_toggle(Vec3::ZERO, None), TnuaToggle::Enabled);
    }

    #[test]
    fn blocked_from_walkable_support_holds_height() {
        let normal = Some(slope_normal(17.0));
        let first =
            steep_ground_command(Vec3::ZERO, normal, Some(0.65), true, SteepGroundHold(false));
        assert_eq!(first.hold, SteepGroundHold(true));
        let latched = steep_ground_command(Vec3::ZERO, normal, Some(0.6), false, first.hold);
        assert_eq!(latched.hold, SteepGroundHold(true));
    }

    #[test]
    fn hold_releases_on_walkable_or_missing_ground() {
        let held = SteepGroundHold(true);
        let walkable = steep_ground_command(Vec3::ZERO, Some(Vec3::Y), Some(0.7), false, held);
        assert_eq!(walkable.hold, SteepGroundHold(false));
        let missing = steep_ground_command(Vec3::ZERO, None, None, false, held);
        assert_eq!(missing.hold, SteepGroundHold(false));
    }

    #[test]
    fn downhill_input_keeps_hold_only_within_float_height() {
        let held = SteepGroundHold(true);
        let steep = Some(slope_normal(17.0));
        let near = steep_ground_command(Vec3::NEG_X, steep, Some(0.6), false, held);
        assert_eq!(near.hold, SteepGroundHold(true));
        let falling_away = steep_ground_command(Vec3::NEG_X, steep, Some(0.8), false, held);
        assert_eq!(falling_away.hold, SteepGroundHold(false));
    }

    #[test]
    fn steep_ground_without_prior_support_is_not_held() {
        let command = steep_ground_command(
            Vec3::ZERO,
            Some(slope_normal(17.0)),
            Some(0.6),
            false,
            SteepGroundHold(false),
        );
        assert_eq!(command.hold, SteepGroundHold(false));
    }

    fn slope_normal(degrees: f32) -> Vec3 {
        let angle = degrees.to_radians();
        Vec3::new(-angle.sin(), angle.cos(), 0.0)
    }
}
