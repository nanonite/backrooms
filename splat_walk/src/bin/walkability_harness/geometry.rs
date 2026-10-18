use avian3d::prelude::{Collider, RigidBody};
use bevy::prelude::{Commands, Component, Quat, Transform, Vec3};

use crate::walkability_harness::scenarios::SyntheticGeometry;

#[derive(Component)]
pub struct SlopeSurface;

#[derive(Component)]
pub struct SlopeApproachFloor;

pub fn spawn_synthetic_scene(commands: &mut Commands, geometry: &SyntheticGeometry) {
    match geometry {
        SyntheticGeometry::Flat => spawn_flat_floor(commands),
        SyntheticGeometry::Slope { degrees } => spawn_slope(commands, *degrees),
        SyntheticGeometry::SeparatedSlope { degrees } => spawn_separated_slope(commands, *degrees),
        SyntheticGeometry::Step { rise_m } => spawn_steps(commands, *rise_m),
        SyntheticGeometry::Gap { width_m } => spawn_gap(commands, *width_m),
        SyntheticGeometry::BlockingWall => {
            spawn_flat_floor(commands);
            spawn_wall_segment(commands, Vec3::ZERO, 4.0);
        }
        SyntheticGeometry::ClearedOpening => spawn_wall_with_opening(commands),
        SyntheticGeometry::OpenLedge { strip_width_m } => spawn_ledge(commands, *strip_width_m),
        SyntheticGeometry::LowCeiling => {
            spawn_flat_floor(commands);
            spawn_barrier(
                commands,
                Vec3::new(0.0, 1.6, 0.0),
                Vec3::new(12.0, 0.1, 4.0),
            );
        }
        SyntheticGeometry::AuthoredRoute => {}
        SyntheticGeometry::AuthoredColumnProbe { floor_y_m } => {
            spawn_flat_floor_at(commands, *floor_y_m)
        }
    }
}

fn spawn_ledge(commands: &mut Commands, strip_width_m: f32) {
    spawn_barrier(
        commands,
        Vec3::new(0.0, -0.1, 0.0),
        Vec3::new(4.0, 0.2, strip_width_m),
    );
}

fn spawn_flat_floor(commands: &mut Commands) {
    spawn_flat_floor_at(commands, 0.0);
}

fn spawn_flat_floor_at(commands: &mut Commands, floor_y: f32) {
    spawn_barrier(
        commands,
        Vec3::new(0.0, floor_y - 0.1, 0.0),
        Vec3::new(12.0, 0.2, 4.0),
    );
}

const SLOPE_LENGTH_M: f32 = 6.0;
const SLOPE_CENTER_X_M: f32 = 1.0;
const SLAB_THICKNESS_M: f32 = 0.2;

/// Incline placement whose top face starts exactly on the flat floor (y = 0) at `foot_x`, where
/// the approach floor ends, and ends at `top` where the upper landing begins. The junctions have
/// no lip and no colliders overlap, so no buried end faces are exposed to the ground sensor.
struct SlopeLayout {
    rotation: Quat,
    center: Vec3,
    foot_x: f32,
    top: Vec3,
}

fn slope_layout(degrees: f32) -> SlopeLayout {
    let angle = degrees.to_radians();
    let half_length = SLOPE_LENGTH_M * 0.5;
    let half_thickness = SLAB_THICKNESS_M * 0.5;
    let center = Vec3::new(
        SLOPE_CENTER_X_M,
        half_length * angle.sin() - half_thickness * angle.cos(),
        0.0,
    );
    let rotation = Quat::from_rotation_z(angle);
    SlopeLayout {
        rotation,
        center,
        foot_x: (center + rotation * Vec3::new(-half_length, half_thickness, 0.0)).x,
        top: center + rotation * Vec3::new(half_length, half_thickness, 0.0),
    }
}

fn spawn_slope(commands: &mut Commands, degrees: f32) {
    let layout = slope_layout(degrees);
    let approach_length = layout.foot_x + 6.0;
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(approach_length, SLAB_THICKNESS_M, 4.0),
        Transform::from_xyz((layout.foot_x - 6.0) * 0.5, -0.1, 0.0),
        SlopeApproachFloor,
    ));
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(SLOPE_LENGTH_M, SLAB_THICKNESS_M, 4.0),
        Transform {
            translation: layout.center,
            rotation: layout.rotation,
            ..Default::default()
        },
        SlopeSurface,
    ));
    spawn_barrier(
        commands,
        Vec3::new(layout.top.x + 2.0, layout.top.y - 0.1, 0.0),
        Vec3::new(4.0, SLAB_THICKNESS_M, 4.0),
    );
}

fn spawn_separated_slope(commands: &mut Commands, degrees: f32) {
    let angle = degrees.to_radians();
    let slope_left_x = 1.0 - 3.0 * angle.cos() - 0.1 * angle.sin();
    let approach_end_x = slope_left_x - 0.05;
    let approach_length = approach_end_x + 6.0;
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(approach_length, 0.2, 4.0),
        Transform::from_xyz((-6.0 + approach_end_x) * 0.5, -0.1, 0.0),
        SlopeApproachFloor,
    ));
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(6.0, 0.2, 4.0),
        Transform {
            translation: Vec3::new(1.0, 3.0 * angle.tan() - 0.1 / angle.cos(), 0.0),
            rotation: Quat::from_rotation_z(angle),
            ..Default::default()
        },
        SlopeSurface,
    ));
}

fn spawn_steps(commands: &mut Commands, rise_m: f32) {
    spawn_barrier(
        commands,
        Vec3::new(-3.0, -0.1, 0.0),
        Vec3::new(6.0, 0.2, 4.0),
    );
    spawn_barrier(
        commands,
        Vec3::new(3.0, rise_m - 0.1, 0.0),
        Vec3::new(6.0, 0.2, 4.0),
    );
}

fn spawn_gap(commands: &mut Commands, width_m: f32) {
    let side_length = 6.0 - width_m * 0.5;
    let half_gap = width_m * 0.5;
    spawn_barrier(
        commands,
        Vec3::new((-6.0 - half_gap) * 0.5, -0.1, 0.0),
        Vec3::new(side_length, 0.2, 4.0),
    );
    spawn_barrier(
        commands,
        Vec3::new((6.0 + half_gap) * 0.5, -0.1, 0.0),
        Vec3::new(side_length, 0.2, 4.0),
    );
}

fn spawn_wall_with_opening(commands: &mut Commands) {
    spawn_flat_floor(commands);
    let pillar_depth = 1.4;
    for center_z in [-1.3, 1.3] {
        spawn_wall_segment(commands, Vec3::new(0.0, 0.0, center_z), pillar_depth);
    }
}

fn spawn_wall_segment(commands: &mut Commands, center: Vec3, depth: f32) {
    spawn_barrier(
        commands,
        center + Vec3::Y * 1.25,
        Vec3::new(0.2, 2.5, depth),
    );
}

fn spawn_barrier(commands: &mut Commands, center: Vec3, dimensions: Vec3) {
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(dimensions.x, dimensions.y, dimensions.z),
        Transform::from_translation(center),
    ));
}

#[cfg(test)]
mod tests {
    use super::{SLAB_THICKNESS_M, SLOPE_LENGTH_M, slope_layout};
    use bevy::prelude::Vec3;

    #[test]
    fn slope_top_face_meets_flat_floor_without_lip() {
        for degrees in [15.0, 17.0, 25.0] {
            let layout = slope_layout(degrees);
            let low_edge = layout.center
                + layout.rotation * Vec3::new(-SLOPE_LENGTH_M * 0.5, SLAB_THICKNESS_M * 0.5, 0.0);
            assert!(
                low_edge.y.abs() < 1.0e-3,
                "{degrees} deg lip {}",
                low_edge.y
            );
            assert!((low_edge.x - layout.foot_x).abs() < 1.0e-6);
        }
    }

    #[test]
    fn slope_slab_stays_right_of_approach_floor_end() {
        for degrees in [15.0, 17.0, 25.0] {
            let layout = slope_layout(degrees);
            let low_bottom_edge = layout.center
                + layout.rotation * Vec3::new(-SLOPE_LENGTH_M * 0.5, -SLAB_THICKNESS_M * 0.5, 0.0);
            assert!(low_bottom_edge.x >= layout.foot_x);
        }
    }

    #[test]
    fn slope_top_matches_nominal_rise_and_angle() {
        for degrees in [15.0_f32, 17.0, 25.0] {
            let layout = slope_layout(degrees);
            let rise = layout.top.y;
            let run = layout.top.x - layout.foot_x;
            assert!((rise - SLOPE_LENGTH_M * degrees.to_radians().sin()).abs() < 1.0e-4);
            assert!((rise.atan2(run).to_degrees() - degrees).abs() < 0.1);
        }
    }
}
