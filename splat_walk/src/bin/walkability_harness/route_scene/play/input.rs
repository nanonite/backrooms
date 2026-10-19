use bevy::{
    input::{ButtonInput, keyboard::KeyCode, mouse::AccumulatedMouseMotion, mouse::MouseButton},
    prelude::{Query, Res, ResMut, Resource},
    window::{CursorGrabMode, CursorOptions, PrimaryWindow},
};
use hunyuan_bevy_fixture::player_controller::PlayerMotionInput;

const MOUSE_RADIANS_PER_PIXEL: f32 = 0.002;
const MAX_PITCH_RADIANS: f32 = 1.48;

#[derive(Resource, Clone, Copy, Debug)]
pub struct WalkLook {
    pub yaw_radians: f32,
    pub pitch_radians: f32,
    pub reset_yaw_radians: f32,
}

#[derive(Resource, Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct CursorLockState(pub bool);

pub fn capture_controls(
    keys: Res<ButtonInput<KeyCode>>,
    mouse_buttons: Res<ButtonInput<MouseButton>>,
    mouse_motion: Res<AccumulatedMouseMotion>,
    mut look: ResMut<WalkLook>,
    mut input: ResMut<PlayerMotionInput>,
    mut cursor_state: ResMut<CursorLockState>,
    mut windows: Query<&mut CursorOptions, bevy::prelude::With<PrimaryWindow>>,
) {
    let escape = keys.just_pressed(KeyCode::Escape);
    let recapture = mouse_buttons.just_pressed(MouseButton::Left);
    let reset = keys.just_pressed(KeyCode::KeyR);
    cursor_state.0 = next_cursor_lock(cursor_state.0, escape, recapture);
    if let Ok(mut options) = windows.single_mut() {
        options.visible = !cursor_state.0;
        options.grab_mode = if cursor_state.0 {
            CursorGrabMode::Locked
        } else {
            CursorGrabMode::None
        };
    }
    if reset {
        look.yaw_radians = look.reset_yaw_radians;
        look.pitch_radians = 0.0;
    } else if cursor_state.0 {
        look.yaw_radians -= mouse_motion.delta.x * MOUSE_RADIANS_PER_PIXEL;
        look.pitch_radians = (look.pitch_radians - mouse_motion.delta.y * MOUSE_RADIANS_PER_PIXEL)
            .clamp(-MAX_PITCH_RADIANS, MAX_PITCH_RADIANS);
    }
    input.forward = if cursor_state.0 {
        axis(&keys, KeyCode::KeyW, KeyCode::KeyS)
    } else {
        0.0
    };
    input.right = if cursor_state.0 {
        axis(&keys, KeyCode::KeyD, KeyCode::KeyA)
    } else {
        0.0
    };
    input.yaw_radians = look.yaw_radians;
    input.reset_requested |= reset;
}

fn axis(keys: &ButtonInput<KeyCode>, positive: KeyCode, negative: KeyCode) -> f32 {
    let positive = if keys.pressed(positive) { 1.0 } else { 0.0 };
    let negative = if keys.pressed(negative) { 1.0 } else { 0.0 };
    positive - negative
}

fn next_cursor_lock(current: bool, escape: bool, recapture: bool) -> bool {
    if escape {
        return !current;
    }
    current || recapture
}

#[cfg(test)]
mod tests {
    use super::{axis, next_cursor_lock};
    use bevy::{input::ButtonInput, prelude::KeyCode};

    #[test]
    fn wasd_keys_map_to_forward_and_right_axes() {
        let mut keys = ButtonInput::default();
        keys.press(KeyCode::KeyW);
        keys.press(KeyCode::KeyD);
        assert_eq!(axis(&keys, KeyCode::KeyW, KeyCode::KeyS), 1.0);
        assert_eq!(axis(&keys, KeyCode::KeyD, KeyCode::KeyA), 1.0);

        keys.press(KeyCode::KeyS);
        keys.press(KeyCode::KeyA);
        assert_eq!(axis(&keys, KeyCode::KeyW, KeyCode::KeyS), 0.0);
        assert_eq!(axis(&keys, KeyCode::KeyD, KeyCode::KeyA), 0.0);
    }

    #[test]
    fn escape_toggles_and_click_recaptures_cursor() {
        assert!(!next_cursor_lock(true, true, false));
        assert!(next_cursor_lock(false, false, true));
        assert!(next_cursor_lock(false, true, true));
    }
}
