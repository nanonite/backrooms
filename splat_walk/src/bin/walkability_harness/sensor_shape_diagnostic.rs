use avian3d::prelude::{
    Collider, CollisionLayers, RigidBody, Sensor, ShapeCastConfig, SpatialQuery, SpatialQueryFilter,
};
use bevy::prelude::{Commands, Component, Dir3, Quat, Query, Transform, Vec3, With};
use bevy_tnua::{TnuaGhostPlatform, TnuaNotPlatform};
use hunyuan_bevy_fixture::player_controller::{
    PLAYER_FLOAT_HEIGHT_M, PLAYER_GROUND_SENSOR_RADIUS_M, PLAYER_RADIUS_M,
};
use serde::Serialize;

use crate::walkability_harness::geometry::{SlopeApproachFloor, SlopeSurface};

pub type CollisionObjectData = (
    Option<&'static CollisionLayers>,
    bevy::prelude::Has<Sensor>,
    bevy::prelude::Has<TnuaGhostPlatform>,
    bevy::prelude::Has<TnuaNotPlatform>,
);

const PROBE_TICKS: std::ops::RangeInclusive<usize> = 55..=65;
const SEPARATED_VARIANT_Z_M: f32 = 8.0;
const FLOOR_START_X_M: f32 = -6.0;
const SLOPE_CENTER_X_M: f32 = 1.0;
const SLOPE_HALF_LENGTH_M: f32 = 3.0;
const SLOPE_HALF_THICKNESS_M: f32 = 0.1;
const PROBE_SEPARATION_GAP_M: f32 = 0.05;
const APPROACH_FLOOR_HALF_WIDTH_M: f32 = 2.0;
const PROBE_RADIUS_M: f32 = PLAYER_RADIUS_M * 0.83;
const THIN_CYLINDER_HEIGHT_M: f32 = 0.02;
const CAST_RANGE_M: f32 = PLAYER_FLOAT_HEIGHT_M + 0.2;

#[derive(Component)]
pub struct SeparatedSlopeSurface;

#[derive(Component)]
pub struct SeparatedSlopeApproachFloor;

#[derive(Serialize, Clone)]
pub struct ShapeCastCheck {
    pub shape: String,
    pub hit_order: Vec<ShapeCastHitSample>,
    pub hit_slope: bool,
    pub slope_distance_m: Option<f32>,
    pub hit_flat_approach: bool,
    pub flat_approach_distance_m: Option<f32>,
}

#[derive(Serialize, Clone)]
pub struct ShapeCastHitSample {
    pub target: String,
    pub distance_m: f32,
    pub tnua_eligible: bool,
    pub rejected_by: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct SensorShapeDiagnosticSample {
    pub tick: usize,
    pub logged_player_position_m: [f32; 3],
    pub owner_has_sensor_shape: bool,
    pub ground_sensor_has_shape_override: bool,
    pub tnua_sensor_hit_target: Option<String>,
    pub tnua_sensor_hit_distance_m: Option<f32>,
    pub overlapping_geometry: Vec<ShapeCastCheck>,
    pub separated_geometry: Vec<ShapeCastCheck>,
}

pub fn is_probe_tick(tick: usize) -> bool {
    PROBE_TICKS.contains(&tick)
}

pub fn spawn_separated_geometry(commands: &mut Commands) {
    let angle = 17.0_f32.to_radians();
    let slope_left_x =
        SLOPE_CENTER_X_M - SLOPE_HALF_LENGTH_M * angle.cos() - SLOPE_HALF_THICKNESS_M * angle.sin();
    let approach_end_x = slope_left_x - PROBE_SEPARATION_GAP_M;
    let approach_length = approach_end_x - FLOOR_START_X_M;
    let approach_center_x = (FLOOR_START_X_M + approach_end_x) * 0.5;
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(approach_length, 0.2, APPROACH_FLOOR_HALF_WIDTH_M * 2.0),
        Transform::from_xyz(approach_center_x, -0.1, SEPARATED_VARIANT_Z_M),
        SeparatedSlopeApproachFloor,
    ));
    commands.spawn((
        RigidBody::Static,
        Collider::cuboid(6.0, 0.2, 4.0),
        Transform {
            translation: Vec3::new(
                SLOPE_CENTER_X_M,
                3.0 * angle.tan() - SLOPE_HALF_THICKNESS_M / angle.cos(),
                SEPARATED_VARIANT_Z_M,
            ),
            rotation: Quat::from_rotation_z(angle),
            ..Default::default()
        },
        SeparatedSlopeSurface,
    ));
}

#[allow(clippy::too_many_arguments)] // Diagnostic probe mirrors the Tnua cast inputs.
pub fn collect_diagnostics(
    tick: usize,
    owner_entity: bevy::prelude::Entity,
    player_position: Vec3,
    owner_has_sensor_shape: bool,
    ground_sensor_has_shape_override: bool,
    tnua_sensor_hit_target: Option<String>,
    tnua_sensor_hit_distance_m: Option<f32>,
    owner_collision_layers: CollisionLayers,
    spatial_query: &SpatialQuery,
    collision_objects: &Query<CollisionObjectData>,
    slope_surfaces: &Query<(), With<SlopeSurface>>,
    approach_floors: &Query<(), With<SlopeApproachFloor>>,
    separated_slope_surfaces: &Query<(), With<SeparatedSlopeSurface>>,
    separated_approach_floors: &Query<(), With<SeparatedSlopeApproachFloor>>,
) -> SensorShapeDiagnosticSample {
    SensorShapeDiagnosticSample {
        tick,
        logged_player_position_m: player_position.to_array(),
        owner_has_sensor_shape,
        ground_sensor_has_shape_override,
        tnua_sensor_hit_target,
        tnua_sensor_hit_distance_m,
        overlapping_geometry: cast_shapes(
            player_position,
            owner_entity,
            owner_collision_layers,
            spatial_query,
            collision_objects,
            slope_surfaces,
            approach_floors,
        ),
        separated_geometry: cast_shapes(
            player_position + Vec3::Z * SEPARATED_VARIANT_Z_M,
            owner_entity,
            owner_collision_layers,
            spatial_query,
            collision_objects,
            separated_slope_surfaces,
            separated_approach_floors,
        ),
    }
}

fn cast_shapes<SlopeTag: Component, ApproachTag: Component>(
    origin: Vec3,
    owner_entity: bevy::prelude::Entity,
    owner_collision_layers: CollisionLayers,
    spatial_query: &SpatialQuery,
    collision_objects: &Query<CollisionObjectData>,
    slope_surfaces: &Query<(), With<SlopeTag>>,
    approach_floors: &Query<(), With<ApproachTag>>,
) -> Vec<ShapeCastCheck> {
    let shapes = [
        (
            "zero_height_cylinder",
            Collider::cylinder(PROBE_RADIUS_M, 0.0),
        ),
        (
            "thin_cylinder_0_02m",
            Collider::cylinder(PROBE_RADIUS_M, THIN_CYLINDER_HEIGHT_M),
        ),
        ("sphere", Collider::sphere(PROBE_RADIUS_M)),
        (
            "narrow_controller_cylinder",
            Collider::cylinder(PLAYER_GROUND_SENSOR_RADIUS_M, 0.0),
        ),
    ];
    shapes
        .into_iter()
        .map(|(name, shape)| {
            cast_shape(
                name,
                &shape,
                origin,
                owner_entity,
                owner_collision_layers,
                spatial_query,
                collision_objects,
                slope_surfaces,
                approach_floors,
            )
        })
        .collect()
}

#[allow(clippy::too_many_arguments)] // Diagnostic probe mirrors the Tnua cast inputs.
fn cast_shape<SlopeTag: Component, ApproachTag: Component>(
    name: &str,
    shape: &Collider,
    origin: Vec3,
    owner_entity: bevy::prelude::Entity,
    owner_collision_layers: CollisionLayers,
    spatial_query: &SpatialQuery,
    collision_objects: &Query<CollisionObjectData>,
    slope_surfaces: &Query<(), With<SlopeTag>>,
    approach_floors: &Query<(), With<ApproachTag>>,
) -> ShapeCastCheck {
    let config = ShapeCastConfig {
        max_distance: CAST_RANGE_M,
        ignore_origin_penetration: true,
        ..Default::default()
    };
    let hits = spatial_query.shape_hits(
        shape,
        origin,
        Quat::IDENTITY,
        Dir3::NEG_Y,
        8,
        &config,
        &SpatialQueryFilter::from_excluded_entities([owner_entity]),
    );
    let mut slope_distance_m: Option<f32> = None;
    let mut flat_approach_distance_m: Option<f32> = None;
    let mut hit_order = Vec::with_capacity(hits.len());
    for hit in hits {
        let target_data = collision_objects.get(hit.entity).ok();
        let rejected_by = target_data.and_then(|(layers, is_sensor, is_ghost, is_not_platform)| {
            if is_not_platform {
                Some("tnua_not_platform".to_owned())
            } else if is_ghost {
                Some("ghost_platform".to_owned())
            } else if is_sensor {
                Some("sensor_entity".to_owned())
            } else if !owner_collision_layers.interacts_with(layers.copied().unwrap_or_default()) {
                Some("collision_layers".to_owned())
            } else {
                None
            }
        });
        let is_slope = slope_surfaces.contains(hit.entity);
        let is_approach = approach_floors.contains(hit.entity);
        let target = if is_slope {
            "slope"
        } else if is_approach {
            "flat_approach"
        } else {
            "other"
        };
        hit_order.push(ShapeCastHitSample {
            target: target.to_owned(),
            distance_m: hit.distance,
            tnua_eligible: target_data.is_some() && rejected_by.is_none(),
            rejected_by,
        });
        if is_slope {
            record_nearest_distance(&mut slope_distance_m, hit.distance);
        }
        if is_approach {
            record_nearest_distance(&mut flat_approach_distance_m, hit.distance);
        }
    }
    ShapeCastCheck {
        shape: name.to_owned(),
        hit_order,
        hit_slope: slope_distance_m.is_some(),
        slope_distance_m,
        hit_flat_approach: flat_approach_distance_m.is_some(),
        flat_approach_distance_m,
    }
}

fn record_nearest_distance(distance: &mut Option<f32>, candidate: f32) {
    *distance = Some(distance.map_or(candidate, |current| current.min(candidate)));
}
