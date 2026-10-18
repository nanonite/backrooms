use avian3d::prelude::{
    Collider, CollisionEventsEnabled, CollisionStart, LinearVelocity, LockedAxes, Position,
    RigidBody, Sensor, ShapeCastConfig, SpatialQuery, SpatialQueryFilter,
};
use bevy::ecs::system::SystemParam;
use bevy::prelude::{
    Assets, Commands, Component, Dir3, Entity, Handle, MessageReader, Name, Quat, Res, ResMut,
    Resource, Transform, Vec3,
};
use bevy_tnua::{
    TnuaController, TnuaProximitySensor, TnuaSensorsEntities, TnuaToggle, builtins::TnuaBuiltinWalk,
};
use bevy_tnua_avian3d::prelude::TnuaAvian3dSensorShape;
use hunyuan_bevy_fixture::player_controller;
pub use hunyuan_bevy_fixture::player_controller::{
    CONTROLLER_MAX_SLOPE_DEGREES, ControlScheme, PLAYER_HEIGHT_M, PLAYER_RADIUS_M,
};
use hunyuan_bevy_fixture::player_controller::{ControlSchemeConfig, SteepGroundHold};
use serde::Serialize;

use crate::walkability_harness::{
    geometry::{SlopeApproachFloor, SlopeSurface, spawn_synthetic_scene},
    route_mesh::AuthoredEdgeBoundary,
    scenarios::{
        AUTHORED_LATERAL_PUSH_TICKS, HarnessSpec, STEEP_REJECTION_SCENARIO, SyntheticGeometry,
        is_steep_rejection,
    },
    sensor_shape_diagnostic::{
        self, CollisionObjectData, SensorShapeDiagnosticSample, SeparatedSlopeApproachFloor,
        SeparatedSlopeSurface,
    },
};

const PLAYER_HALF_HEIGHT: f32 = PLAYER_HEIGHT_M * 0.5;
const WAYPOINT_TOLERANCE: f32 = 0.08;
const FLOOR_RAY_LENGTH: f32 = 1.4;
const HEADROOM_RAY_LENGTH: f32 = 0.55;
pub const SAFETY_NET_CENTER_Y_M: f32 = -2.0;
const SAFETY_NET_THICKNESS_M: f32 = 0.5;
pub const SAFETY_NET_TOP_Y_M: f32 = SAFETY_NET_CENTER_Y_M + SAFETY_NET_THICKNESS_M * 0.5;
pub const OPEN_LEDGE_STOP_TOLERANCE_M: f32 = 0.12;
pub const SLOPE_INPUT_TICKS: usize = 240;
pub const SLOPE_RECOVERY_TICKS: usize = 60;
pub const SLOPE_MAX_BOTTOM_HEIGHT_ABOVE_FLAT_M: f32 = 0.25;
pub const SLOPE_MIN_PLAYER_CENTER_Y_M: f32 = 0.60;
pub const SLOPE_MAX_VERTICAL_SPEED_MPS: f32 = 0.50;
pub const SLOPE_STABILITY_WINDOW_TICKS: usize = 60;
pub const SLOPE_MAX_POSITION_RADIUS_M: f32 = 0.02;
pub const SLOPE_FINAL_REST_WINDOW_TICKS: usize = 10;
pub const SLOPE_MAX_FINAL_SPEED_MPS: f32 = 0.10;
pub const AUTHORED_LATERAL_MAX_OFFSET_M: f32 = 0.12;
pub const AUTHORED_LATERAL_MAX_BOTTOM_RISE_M: f32 = 0.02;
pub const AUTHORED_LATERAL_MIN_SUPPORT_FRACTION: f32 = 0.95;
pub const AUTHORED_LATERAL_FINAL_REST_TICKS: usize = 10;
pub const AUTHORED_LATERAL_MAX_FINAL_SPEED_MPS: f32 = 0.10;
pub const AUTHORED_LATERAL_MAX_FINAL_POSITION_RADIUS_M: f32 = 0.02;

#[derive(Resource, Clone, Copy)]
pub struct SafetyNetEntity(pub Entity);

#[derive(Component)]
pub(super) struct HarnessPlayer;

#[derive(Resource)]
pub struct PathProgress {
    waypoints: Vec<Vec3>,
    next_waypoint: usize,
    waypoint_split: Option<usize>,
    pub active: bool,
}

impl PathProgress {
    pub fn new(waypoints: Vec<Vec3>, waypoint_split: Option<usize>) -> Self {
        Self {
            waypoints,
            next_waypoint: 0,
            waypoint_split,
            active: true,
        }
    }

    fn fraction(&self) -> f32 {
        if self.waypoints.len() < 2 {
            return 1.0;
        }
        self.next_waypoint.min(self.waypoints.len()) as f32 / (self.waypoints.len() - 1) as f32
    }

    fn segment_fractions(&self) -> (f32, f32) {
        let Some(split) = self.waypoint_split else {
            return (self.fraction().clamp(0.0, 1.0), 0.0);
        };
        let outbound = ratio(self.next_waypoint.min(split), split.saturating_sub(1));
        let inbound = ratio(
            self.next_waypoint.saturating_sub(split),
            self.waypoints.len().saturating_sub(split),
        );
        (outbound.min(1.0), inbound.min(1.0))
    }

    fn distance_to_path(&self, position: Vec3) -> f32 {
        self.waypoints
            .windows(2)
            .map(|segment| point_segment_distance(position, segment[0], segment[1]))
            .fold(f32::INFINITY, f32::min)
    }
}

#[derive(Resource)]
pub struct PlayerConfigHandle(pub Handle<ControlSchemeConfig>);

#[derive(Serialize, Default, Clone)]
pub struct DistanceSummary {
    pub sample_count: usize,
    pub min_m: Option<f32>,
    pub median_m: Option<f32>,
    pub q90_m: Option<f32>,
    pub max_m: Option<f32>,
}

#[derive(Serialize, Clone)]
pub struct SafetyNetContactEvent {
    pub tick: usize,
    pub player_position_m: [f32; 3],
}

#[derive(Serialize, Clone)]
pub struct SupportLossEvent {
    pub tick: usize,
    pub player_position_m: [f32; 3],
}

#[derive(Serialize, Clone)]
pub struct UnsupportedAuthoredRouteSample {
    pub tick: usize,
    pub player_position_m: [f32; 3],
}

#[derive(Serialize, Clone)]
pub struct LedgeEdgeSample {
    pub tick: usize,
    pub lateral_center_z_m: f32,
    pub capsule_edge_clearance_m: f32,
    pub supported: bool,
}

#[derive(Serialize, Clone)]
pub struct EdgeBoundaryContactEvent {
    pub tick: usize,
    pub boundary_side: String,
    pub player_position_m: [f32; 3],
    pub distance_m: f32,
    pub detection: String,
}

#[derive(Serialize, Clone)]
pub struct AuthoredLateralPushSample {
    pub tick: usize,
    pub phase: String,
    pub lateral_offset_m: f32,
    pub capsule_bottom_rise_m: f32,
    pub speed_mps: f32,
    pub supported: bool,
    pub player_position_m: [f32; 3],
}

#[derive(Serialize, Clone)]
pub struct SlopeSensorSample {
    pub tick: usize,
    pub phase: String,
    pub ground_hit_slope: bool,
    pub ground_hit_flat_approach: bool,
    pub ground_normal: Option<[f32; 3]>,
    pub ground_normal_angle_degrees: Option<f32>,
    pub ground_proximity_m: Option<f32>,
    pub standing_on: bool,
    pub standing_on_flat_approach: bool,
    pub player_position_m: [f32; 3],
    pub player_velocity_mps: [f32; 3],
    pub capsule_bottom_height_above_flat_m: f32,
    pub vertical_velocity_mps: f32,
}

#[derive(Default)]
struct SlopeGroundReading {
    hit_slope: bool,
    hit_flat_approach: bool,
    normal: Option<Vec3>,
    angle_degrees: Option<f32>,
    proximity_m: Option<f32>,
    standing_on: bool,
    standing_on_flat_approach: bool,
}

type PlayerSampleData = (
    Entity,
    &'static Position,
    &'static TnuaController<ControlScheme>,
    &'static TnuaSensorsEntities<ControlScheme>,
    Option<&'static LinearVelocity>,
);

type PlayerDriveData = (
    &'static Position,
    &'static mut TnuaController<ControlScheme>,
    &'static TnuaSensorsEntities<ControlScheme>,
    &'static mut TnuaToggle,
    &'static mut SteepGroundHold,
    &'static mut LockedAxes,
    &'static mut LinearVelocity,
);

#[derive(SystemParam)]
pub(super) struct SampleQueries<'w, 's> {
    players: bevy::prelude::Query<'w, 's, PlayerSampleData, bevy::prelude::With<HarnessPlayer>>,
    sensors: bevy::prelude::Query<'w, 's, &'static TnuaProximitySensor>,
    sensor_shapes: bevy::prelude::Query<'w, 's, (), bevy::prelude::With<TnuaAvian3dSensorShape>>,
    collision_objects: bevy::prelude::Query<'w, 's, CollisionObjectData>,
    slope_surfaces: bevy::prelude::Query<'w, 's, (), bevy::prelude::With<SlopeSurface>>,
    approach_floors: bevy::prelude::Query<'w, 's, (), bevy::prelude::With<SlopeApproachFloor>>,
    separated_slope_surfaces:
        bevy::prelude::Query<'w, 's, (), bevy::prelude::With<SeparatedSlopeSurface>>,
    separated_approach_floors:
        bevy::prelude::Query<'w, 's, (), bevy::prelude::With<SeparatedSlopeApproachFloor>>,
    edge_boundaries: bevy::prelude::Query<'w, 's, &'static AuthoredEdgeBoundary>,
}

#[derive(Resource, Serialize, Default, Clone)]
pub struct ScenarioReport {
    pub scenario: String,
    pub blocking: bool,
    pub pass: bool,
    pub runtime_seconds: f64,
    pub resident_set_kib_at_completion: Option<u64>,
    pub total_ticks: usize,
    pub moving_ticks: usize,
    pub support_ticks: usize,
    pub moving_support_ticks: usize,
    pub floor_ray_hit_ticks: usize,
    pub moving_floor_ray_hit_ticks: usize,
    pub headroom_clear_ticks: usize,
    pub headroom_blocked_ticks: usize,
    pub floor_ray_miss_ticks: usize,
    pub floor_clearance_from_capsule_bottom: DistanceSummary,
    pub headroom_block_distance: DistanceSummary,
    pub headroom_clear_distance_lower_bound_m: Option<f32>,
    pub floor_ray_max_distance_m: f32,
    pub headroom_ray_max_distance_m: f32,
    pub controller_max_slope_degrees: f32,
    pub outbound_progress_fraction: f32,
    pub inbound_progress_fraction: f32,
    pub moving_support_fraction: f32,
    pub moving_floor_ray_fraction: f32,
    pub total_support_fraction: f32,
    pub total_floor_ray_fraction: f32,
    pub progress_fraction: f32,
    pub final_position: [f32; 3],
    pub min_y: f32,
    pub max_vertical_step: f32,
    pub max_route_deviation_m: f32,
    pub fallthrough_detected: bool,
    pub controlled_slope_rejection: Option<bool>,
    pub slope_rejection_outcome: Option<String>,
    pub slope_gate_failures: Vec<String>,
    pub slope_sensor_hit_ticks: usize,
    pub slope_sensor_mismatch_ticks: usize,
    pub slope_sensor_samples: Vec<SlopeSensorSample>,
    pub sensor_shape_diagnostic_samples: Vec<SensorShapeDiagnosticSample>,
    pub slope_release_tick: Option<usize>,
    pub slope_recovery_ticks_to_flat_support: Option<usize>,
    pub slope_recovered_to_flat: bool,
    pub slope_max_capsule_bottom_height_above_flat_m: Option<f32>,
    pub slope_peak_abs_vertical_velocity_mps: Option<f32>,
    pub slope_input_position_radius_m: Option<f32>,
    pub slope_recovery_end_max_speed_mps: Option<f32>,
    pub slope_recovery_position_radius_m: Option<f32>,
    pub slope_recovery_end_at_rest: bool,
    pub ledge_boundary_walls_required: Option<bool>,
    pub ledge_outcome: Option<String>,
    pub minimum_ledge_edge_clearance_m: Option<f32>,
    pub maximum_ledge_lateral_center_z_m: Option<f32>,
    pub ledge_edge_samples: Vec<LedgeEdgeSample>,
    pub safety_net_contact_events: Vec<SafetyNetContactEvent>,
    pub support_loss_events: Vec<SupportLossEvent>,
    pub unsupported_authored_route_samples: Vec<UnsupportedAuthoredRouteSample>,
    pub collision_asset_loaded: bool,
    pub collision_nodes: usize,
    pub floor_collision_triangles: usize,
    pub obstacle_collision_triangles: usize,
    pub edge_boundary_collision_triangles: usize,
    pub edge_boundary_contact_events: Vec<EdgeBoundaryContactEvent>,
    pub authored_lateral_station: Option<String>,
    pub authored_lateral_expected_boundary: Option<String>,
    pub authored_lateral_max_abs_offset_m: Option<f32>,
    pub authored_lateral_max_capsule_bottom_rise_m: Option<f32>,
    pub authored_lateral_rest_max_speed_mps: Option<f32>,
    pub authored_lateral_rest_position_radius_m: Option<f32>,
    pub authored_lateral_rest_at_end: bool,
    pub authored_lateral_samples: Vec<AuthoredLateralPushSample>,
    pub failure_reason: Option<String>,
    #[serde(skip)]
    previous_y: Option<f32>,
    #[serde(skip)]
    previous_support: Option<bool>,
    #[serde(skip)]
    floor_clearance_samples: Vec<f32>,
    #[serde(skip)]
    headroom_block_samples: Vec<f32>,
    #[serde(skip)]
    slope_input_positions: Vec<Vec3>,
    #[serde(skip)]
    slope_recovery_positions: Vec<Vec3>,
    #[serde(skip)]
    slope_recovery_speeds: Vec<f32>,
    #[serde(skip)]
    authored_lateral_rest_positions: Vec<Vec3>,
    #[serde(skip)]
    authored_lateral_rest_speeds: Vec<f32>,
}

pub fn summarize_distances(samples: &mut [f32]) -> DistanceSummary {
    if samples.is_empty() {
        return DistanceSummary::default();
    }
    samples.sort_by(f32::total_cmp);
    let middle = samples.len() / 2;
    let median = if samples.len().is_multiple_of(2) {
        (samples[middle - 1] + samples[middle]) * 0.5
    } else {
        samples[middle]
    };
    let q90_index = (samples.len() * 9).div_ceil(10) - 1;
    DistanceSummary {
        sample_count: samples.len(),
        min_m: samples.first().copied(),
        median_m: Some(median),
        q90_m: samples.get(q90_index).copied(),
        max_m: samples.last().copied(),
    }
}

impl ScenarioReport {
    pub fn finalize_distance_summaries(&mut self) {
        self.floor_clearance_from_capsule_bottom =
            summarize_distances(&mut self.floor_clearance_samples);
        self.headroom_block_distance = summarize_distances(&mut self.headroom_block_samples);
        self.slope_input_position_radius_m =
            position_radius(&self.slope_input_positions, SLOPE_STABILITY_WINDOW_TICKS);
        let final_positions = tail(
            &self.slope_recovery_positions,
            SLOPE_FINAL_REST_WINDOW_TICKS,
        );
        let final_speeds = tail(&self.slope_recovery_speeds, SLOPE_FINAL_REST_WINDOW_TICKS);
        self.slope_recovery_end_max_speed_mps = final_speeds.iter().copied().reduce(f32::max);
        self.slope_recovery_position_radius_m =
            position_radius(final_positions, SLOPE_FINAL_REST_WINDOW_TICKS);
        self.slope_recovery_end_at_rest = self.slope_recovered_to_flat
            && final_speeds.len() == SLOPE_FINAL_REST_WINDOW_TICKS
            && self
                .slope_recovery_end_max_speed_mps
                .is_some_and(|speed| speed <= SLOPE_MAX_FINAL_SPEED_MPS)
            && self
                .slope_recovery_position_radius_m
                .is_some_and(|radius| radius <= SLOPE_MAX_POSITION_RADIUS_M);
        let final_positions = tail(
            &self.authored_lateral_rest_positions,
            AUTHORED_LATERAL_FINAL_REST_TICKS,
        );
        let final_speeds = tail(
            &self.authored_lateral_rest_speeds,
            AUTHORED_LATERAL_FINAL_REST_TICKS,
        );
        self.authored_lateral_rest_max_speed_mps = final_speeds.iter().copied().reduce(f32::max);
        self.authored_lateral_rest_position_radius_m =
            position_radius(final_positions, AUTHORED_LATERAL_FINAL_REST_TICKS);
        self.authored_lateral_rest_at_end = final_speeds.len() == AUTHORED_LATERAL_FINAL_REST_TICKS
            && self
                .authored_lateral_rest_max_speed_mps
                .is_some_and(|speed| speed <= AUTHORED_LATERAL_MAX_FINAL_SPEED_MPS)
            && self
                .authored_lateral_rest_position_radius_m
                .is_some_and(|radius| radius <= AUTHORED_LATERAL_MAX_FINAL_POSITION_RADIUS_M);
    }
}

fn tail<T>(values: &[T], count: usize) -> &[T] {
    &values[values.len().saturating_sub(count)..]
}

fn position_radius(positions: &[Vec3], required_count: usize) -> Option<f32> {
    if positions.len() < required_count {
        return None;
    }
    let window = tail(positions, required_count);
    let centroid = window.iter().copied().sum::<Vec3>() / window.len() as f32;
    window
        .iter()
        .map(|position| position.distance(centroid))
        .reduce(f32::max)
}

pub fn setup_scene(
    mut commands: Commands,
    mut configs: ResMut<Assets<ControlSchemeConfig>>,
    spec: Res<HarnessSpec>,
    mut report: ResMut<ScenarioReport>,
) {
    report.scenario.clone_from(&spec.name);
    report.blocking = spec.blocking;
    report.controller_max_slope_degrees = CONTROLLER_MAX_SLOPE_DEGREES;
    report.floor_ray_max_distance_m = FLOOR_RAY_LENGTH;
    report.headroom_ray_max_distance_m = HEADROOM_RAY_LENGTH;
    commands.insert_resource(PathProgress::new(
        spec.waypoints.clone(),
        spec.waypoint_split,
    ));
    spawn_synthetic_scene(&mut commands, &spec.geometry);
    if spec.name == STEEP_REJECTION_SCENARIO {
        sensor_shape_diagnostic::spawn_separated_geometry(&mut commands);
    }
    spawn_safety_net(&mut commands);
    let config = configs.add(player_controller::walk_config());
    if matches!(
        &spec.geometry,
        SyntheticGeometry::AuthoredRoute
            | SyntheticGeometry::AuthoredColumnProbe { .. }
            | SyntheticGeometry::AuthoredLateralPush { .. }
    ) {
        commands.insert_resource(PlayerConfigHandle(config));
    } else {
        spawn_player(&mut commands, spec.start, config);
    }
}

fn spawn_safety_net(commands: &mut Commands) {
    let sensor = commands
        .spawn((
            Name::new("SafetyNet"),
            RigidBody::Static,
            Collider::cuboid(100.0, SAFETY_NET_THICKNESS_M, 100.0),
            Sensor,
            CollisionEventsEnabled,
            Transform::from_xyz(0.0, SAFETY_NET_CENTER_Y_M, 0.0),
        ))
        .id();
    commands.insert_resource(SafetyNetEntity(sensor));
}

pub fn spawn_player(commands: &mut Commands, start: Vec3, config: Handle<ControlSchemeConfig>) {
    commands.spawn((
        HarnessPlayer,
        player_controller::player_bundle(start, config),
    ));
}

pub fn drive_player(
    mut players: bevy::prelude::Query<PlayerDriveData, bevy::prelude::With<HarnessPlayer>>,
    sensors: bevy::prelude::Query<&TnuaProximitySensor>,
    mut path: ResMut<PathProgress>,
    spec: Res<HarnessSpec>,
    report: Res<ScenarioReport>,
) {
    let Ok((
        position,
        mut controller,
        sensor_entities,
        mut toggle,
        mut hold,
        mut locked_axes,
        mut velocity,
    )) = players.single_mut()
    else {
        return;
    };
    while let Some(target) = path.waypoints.get(path.next_waypoint)
        && horizontal_distance(position.0, *target) <= WAYPOINT_TOLERANCE
    {
        path.next_waypoint += 1;
    }
    let reversing_slope = is_steep_rejection(&spec.name) && report.total_ticks >= SLOPE_INPUT_TICKS;
    let mut direction = if let SyntheticGeometry::AuthoredLateralPush {
        outward_direction_xz,
        boundary_side,
        ..
    } = &spec.geometry
    {
        if report.total_ticks >= AUTHORED_LATERAL_PUSH_TICKS {
            Vec3::ZERO
        } else {
            let direction_sign = if boundary_side == "inner" { -1.0 } else { 1.0 };
            Vec3::new(
                outward_direction_xz[0] * direction_sign,
                0.0,
                outward_direction_xz[1] * direction_sign,
            )
        }
    } else if reversing_slope {
        if report.slope_recovered_to_flat {
            Vec3::ZERO
        } else {
            Vec3::NEG_X
        }
    } else {
        path.waypoints
            .get(path.next_waypoint)
            .map_or(Vec3::ZERO, |target| {
                horizontal_delta(position.0, *target).normalize_or_zero() * spec.speed_scale
            })
    };
    let ground_hit = sensor_entities
        .ground
        .and_then(|entity| sensors.get(entity).ok())
        .and_then(|sensor| sensor.output.as_ref());
    let ground_normal = ground_hit.map(|hit| hit.normal.as_vec3());
    let ground_proximity = ground_hit.map(|hit| hit.proximity);
    direction = player_controller::shape_steep_slope_motion(direction, ground_normal);
    let was_supported = controller.basis_memory.standing_on_entity().is_some();
    let command = player_controller::steep_ground_command(
        direction,
        ground_normal,
        ground_proximity,
        was_supported,
        *hold,
    );
    *toggle = command.toggle;
    *hold = command.hold;
    *locked_axes = command.locked_axes;
    if hold.0 {
        velocity.y = 0.0;
    }
    path.active = direction.length_squared() > 0.0;
    controller.initiate_action_feeding();
    controller.basis = TnuaBuiltinWalk {
        desired_motion: direction,
        ..Default::default()
    };
}

pub(super) fn collect_sample(
    queries: SampleQueries,
    spec: Res<HarnessSpec>,
    path: Res<PathProgress>,
    safety_net: Res<SafetyNetEntity>,
    mut collision_starts: MessageReader<CollisionStart>,
    spatial_query: SpatialQuery,
    mut report: ResMut<ScenarioReport>,
) {
    let Ok((player, position, controller, sensor_entities, linear_velocity)) =
        queries.players.single()
    else {
        return;
    };
    sample_motion(position.0, path.active, &mut report);
    let supported = sample_support(controller, path.active, position.0, &spec.name, &mut report);
    let velocity = linear_velocity.map_or(Vec3::ZERO, |velocity| velocity.0);
    sample_authored_lateral_push(position.0, velocity, supported, &spec, &mut report);
    let sensor = sensor_entities
        .ground
        .and_then(|entity| queries.sensors.get(entity).ok());
    let ground_reading = read_ground_sensor(
        controller,
        sensor,
        &queries.slope_surfaces,
        &queries.approach_floors,
    );
    sample_slope(
        report.total_ticks,
        position.0,
        linear_velocity.map_or(Vec3::ZERO, |velocity| velocity.0),
        ground_reading,
        &spec,
        &mut report,
    );
    sample_rays(
        player,
        safety_net.0,
        position.0,
        path.active,
        &spatial_query,
        &mut report,
    );
    sample_safety_net_contacts(
        &mut collision_starts,
        safety_net.0,
        player,
        position.0,
        &mut report,
        &queries.edge_boundaries,
    );
    sample_lateral_boundary_contact(
        player,
        position.0,
        &spec,
        &spatial_query,
        &queries.edge_boundaries,
        &mut report,
    );
    sample_ledge_edge(position.0, supported, &spec, &mut report);
    report.progress_fraction = path.fraction().min(1.0);
    (
        report.outbound_progress_fraction,
        report.inbound_progress_fraction,
    ) = path.segment_fractions();
    if spec.waypoint_split.is_some() {
        report.max_route_deviation_m = report
            .max_route_deviation_m
            .max(path.distance_to_path(position.0));
    }
    report.final_position = position.0.to_array();
}

pub fn collect_sensor_shape_diagnostics(
    queries: SampleQueries,
    spatial_query: SpatialQuery,
    mut report: ResMut<ScenarioReport>,
) {
    if report.scenario != STEEP_REJECTION_SCENARIO {
        return;
    }
    let tick = report.total_ticks + 1;
    if !sensor_shape_diagnostic::is_probe_tick(tick) {
        return;
    }
    let Ok((player, position, _, sensors, _)) = queries.players.single() else {
        return;
    };
    let sensor_entity = sensors.ground;
    let sensor = sensor_entity.and_then(|entity| queries.sensors.get(entity).ok());
    let output = sensor.and_then(|sensor| sensor.output.as_ref());
    let owner_collision_layers = queries
        .collision_objects
        .get(player)
        .ok()
        .and_then(|(layers, _, _, _)| layers.copied())
        .unwrap_or_default();
    let hit_target = output.map(|hit| {
        if queries.slope_surfaces.contains(hit.entity) {
            "slope".to_owned()
        } else if queries.approach_floors.contains(hit.entity) {
            "flat_approach".to_owned()
        } else {
            "other".to_owned()
        }
    });
    report
        .sensor_shape_diagnostic_samples
        .push(sensor_shape_diagnostic::collect_diagnostics(
            tick,
            player,
            position.0,
            queries.sensor_shapes.contains(player),
            sensor_entity.is_some_and(|entity| queries.sensor_shapes.contains(entity)),
            hit_target,
            output.map(|hit| hit.proximity),
            owner_collision_layers,
            &spatial_query,
            &queries.collision_objects,
            &queries.slope_surfaces,
            &queries.approach_floors,
            &queries.separated_slope_surfaces,
            &queries.separated_approach_floors,
        ));
}

fn sample_motion(position: Vec3, moving: bool, report: &mut ScenarioReport) {
    report.total_ticks += 1;
    report.min_y = if report.total_ticks == 1 {
        position.y
    } else {
        report.min_y.min(position.y)
    };
    if moving {
        report.moving_ticks += 1;
    }
    if let Some(previous_y) = report.previous_y {
        report.max_vertical_step = report
            .max_vertical_step
            .max((position.y - previous_y).abs());
    }
    report.previous_y = Some(position.y);
}

fn sample_support(
    controller: &TnuaController<ControlScheme>,
    moving: bool,
    position: Vec3,
    scenario: &str,
    report: &mut ScenarioReport,
) -> bool {
    let supported = controller.basis_memory.standing_on_entity().is_some();
    if report.previous_support == Some(true) && !supported {
        report.support_loss_events.push(SupportLossEvent {
            tick: report.total_ticks,
            player_position_m: position.to_array(),
        });
    }
    if !supported && scenario == "authored_route_outbound_inbound" {
        report
            .unsupported_authored_route_samples
            .push(UnsupportedAuthoredRouteSample {
                tick: report.total_ticks,
                player_position_m: position.to_array(),
            });
    }
    report.previous_support = Some(supported);
    if !supported {
        return false;
    }
    report.support_ticks += 1;
    if moving {
        report.moving_support_ticks += 1;
    }
    true
}

fn sample_slope(
    tick: usize,
    position: Vec3,
    velocity: Vec3,
    ground: SlopeGroundReading,
    spec: &HarnessSpec,
    report: &mut ScenarioReport,
) {
    if !matches!(
        &spec.geometry,
        SyntheticGeometry::Slope { .. } | SyntheticGeometry::SeparatedSlope { .. }
    ) {
        return;
    }
    record_slope_sensor_result(spec, &ground, report);
    let phase = slope_phase(&spec.name, tick, report.slope_recovered_to_flat);
    let bottom_height = position.y - PLAYER_HALF_HEIGHT;
    record_slope_motion(&spec.name, phase, position, velocity, &ground, report);
    let sample = slope_sensor_sample(tick, phase, position, velocity, bottom_height, ground);
    record_slope_recovery(&sample, report);
    report.slope_sensor_samples.push(sample);
}

fn read_ground_sensor(
    controller: &TnuaController<ControlScheme>,
    sensor: Option<&TnuaProximitySensor>,
    slope_surfaces: &bevy::prelude::Query<(), bevy::prelude::With<SlopeSurface>>,
    approach_floors: &bevy::prelude::Query<(), bevy::prelude::With<SlopeApproachFloor>>,
) -> SlopeGroundReading {
    let output = sensor.and_then(|ground| ground.output.as_ref());
    let standing_entity = controller.basis_memory.standing_on_entity();
    let normal = output.map(|hit| hit.normal.as_vec3());
    SlopeGroundReading {
        hit_slope: output.is_some_and(|hit| slope_surfaces.contains(hit.entity)),
        hit_flat_approach: output.is_some_and(|hit| approach_floors.contains(hit.entity)),
        normal,
        angle_degrees: normal.map(|value| value.angle_between(Vec3::Y).to_degrees()),
        proximity_m: output.map(|hit| hit.proximity),
        standing_on: standing_entity.is_some(),
        standing_on_flat_approach: output.is_some_and(|hit| {
            approach_floors.contains(hit.entity) && standing_entity == Some(hit.entity)
        }),
    }
}

fn record_slope_sensor_result(
    spec: &HarnessSpec,
    ground: &SlopeGroundReading,
    report: &mut ScenarioReport,
) {
    if !ground.hit_slope {
        return;
    }
    report.slope_sensor_hit_ticks += 1;
    let angle_valid = ground.angle_degrees.is_some_and(|value| {
        if spec.name == "slope_15_degrees" {
            value <= CONTROLLER_MAX_SLOPE_DEGREES
        } else {
            value > CONTROLLER_MAX_SLOPE_DEGREES
        }
    });
    let standing_valid = if spec.name == "slope_15_degrees" {
        ground.standing_on
    } else {
        !ground.standing_on
    };
    if !angle_valid || !standing_valid {
        report.slope_sensor_mismatch_ticks += 1;
    }
}

fn record_slope_motion(
    scenario: &str,
    phase: &str,
    position: Vec3,
    velocity: Vec3,
    ground: &SlopeGroundReading,
    report: &mut ScenarioReport,
) {
    if is_steep_rejection(scenario) && ground.hit_slope {
        update_maximum(
            &mut report.slope_max_capsule_bottom_height_above_flat_m,
            position.y - PLAYER_HALF_HEIGHT,
        );
    }
    if is_steep_rejection(scenario) && phase == "forward_input" && report.slope_sensor_hit_ticks > 0
    {
        update_maximum(
            &mut report.slope_peak_abs_vertical_velocity_mps,
            velocity.y.abs(),
        );
        report.slope_input_positions.push(position);
    }
}

fn slope_sensor_sample(
    tick: usize,
    phase: &str,
    position: Vec3,
    velocity: Vec3,
    bottom_height: f32,
    ground: SlopeGroundReading,
) -> SlopeSensorSample {
    SlopeSensorSample {
        tick,
        phase: phase.to_owned(),
        ground_hit_slope: ground.hit_slope,
        ground_hit_flat_approach: ground.hit_flat_approach,
        ground_normal: ground.normal.map(|normal| normal.to_array()),
        ground_normal_angle_degrees: ground.angle_degrees,
        ground_proximity_m: ground.proximity_m,
        standing_on: ground.standing_on,
        standing_on_flat_approach: ground.standing_on_flat_approach,
        player_position_m: position.to_array(),
        player_velocity_mps: velocity.to_array(),
        capsule_bottom_height_above_flat_m: bottom_height,
        vertical_velocity_mps: velocity.y,
    }
}

fn record_slope_recovery(sample: &SlopeSensorSample, report: &mut ScenarioReport) {
    if sample.phase == "forward_input" {
        return;
    }
    let release_tick = *report.slope_release_tick.get_or_insert(SLOPE_INPUT_TICKS);
    report
        .slope_recovery_positions
        .push(Vec3::from_array(sample.player_position_m));
    report
        .slope_recovery_speeds
        .push(Vec3::from_array(sample.player_velocity_mps).length());
    if sample.standing_on_flat_approach && report.slope_recovery_ticks_to_flat_support.is_none() {
        report.slope_recovery_ticks_to_flat_support = Some(sample.tick - release_tick);
        report.slope_recovered_to_flat = true;
    }
}

fn update_maximum(value: &mut Option<f32>, candidate: f32) {
    *value = Some(value.unwrap_or(candidate).max(candidate));
}

fn slope_phase(scenario: &str, tick: usize, recovered_to_flat: bool) -> &'static str {
    if !is_steep_rejection(scenario) || tick <= SLOPE_INPUT_TICKS {
        return "forward_input";
    }
    if recovered_to_flat {
        "settling_after_recovery"
    } else {
        "reverse_recovery"
    }
}

fn sample_rays(
    player: Entity,
    safety_net: Entity,
    position: Vec3,
    moving: bool,
    query: &SpatialQuery,
    report: &mut ScenarioReport,
) {
    let exclude_sensors = |entity| entity != player && entity != safety_net;
    let filter = SpatialQueryFilter::default();
    let floor_hit = query.cast_ray_predicate(
        position,
        Dir3::NEG_Y,
        FLOOR_RAY_LENGTH,
        true,
        &filter,
        &exclude_sensors,
    );
    if let Some(hit) = floor_hit {
        report.floor_ray_hit_ticks += 1;
        report
            .floor_clearance_samples
            .push(hit.distance - PLAYER_HALF_HEIGHT);
        if moving {
            report.moving_floor_ray_hit_ticks += 1;
        }
    } else {
        report.floor_ray_miss_ticks += 1;
    }
    let headroom_origin = position + Vec3::Y * PLAYER_HALF_HEIGHT;
    let headroom_hit = query.cast_ray_predicate(
        headroom_origin,
        Dir3::Y,
        HEADROOM_RAY_LENGTH,
        true,
        &filter,
        &exclude_sensors,
    );
    if let Some(hit) = headroom_hit {
        report.headroom_blocked_ticks += 1;
        report.headroom_block_samples.push(hit.distance);
    } else {
        report.headroom_clear_ticks += 1;
    }
}

fn sample_safety_net_contacts(
    collision_starts: &mut MessageReader<CollisionStart>,
    safety_net: Entity,
    player: Entity,
    position: Vec3,
    report: &mut ScenarioReport,
    edge_boundaries: &bevy::prelude::Query<&AuthoredEdgeBoundary>,
) {
    for event in collision_starts.read() {
        let is_player_net_pair = (event.collider1 == safety_net && event.collider2 == player)
            || (event.collider2 == safety_net && event.collider1 == player);
        if is_player_net_pair {
            report
                .safety_net_contact_events
                .push(SafetyNetContactEvent {
                    tick: report.total_ticks,
                    player_position_m: position.to_array(),
                });
        }
        let boundary_entity = if event.collider1 == player {
            Some(event.collider2)
        } else if event.collider2 == player {
            Some(event.collider1)
        } else {
            None
        };
        if let Some(boundary_entity) = boundary_entity
            && let Ok(boundary) = edge_boundaries.get(boundary_entity)
        {
            report
                .edge_boundary_contact_events
                .push(EdgeBoundaryContactEvent {
                    tick: report.total_ticks,
                    boundary_side: boundary.side.to_owned(),
                    player_position_m: position.to_array(),
                    distance_m: 0.0,
                    detection: "avian_collision_start".to_owned(),
                });
        }
    }
}

fn sample_lateral_boundary_contact(
    player: Entity,
    position: Vec3,
    spec: &HarnessSpec,
    spatial_query: &SpatialQuery,
    edge_boundaries: &bevy::prelude::Query<&AuthoredEdgeBoundary>,
    report: &mut ScenarioReport,
) {
    let SyntheticGeometry::AuthoredLateralPush {
        outward_direction_xz,
        boundary_side,
        ..
    } = &spec.geometry
    else {
        return;
    };
    if report
        .edge_boundary_contact_events
        .iter()
        .any(|contact| contact.boundary_side == *boundary_side)
    {
        return;
    }
    let direction_sign = if boundary_side == "inner" { -1.0 } else { 1.0 };
    let direction = Vec3::new(
        outward_direction_xz[0] * direction_sign,
        0.0,
        outward_direction_xz[1] * direction_sign,
    );
    let Ok(direction) = Dir3::new(direction) else {
        return;
    };
    let shape = Collider::capsule(PLAYER_RADIUS_M, PLAYER_HEIGHT_M - 2.0 * PLAYER_RADIUS_M);
    let cast_config = ShapeCastConfig {
        max_distance: 0.02,
        ignore_origin_penetration: false,
        ..Default::default()
    };
    let hits = spatial_query.shape_hits(
        &shape,
        position,
        Quat::IDENTITY,
        direction,
        8,
        &cast_config,
        &SpatialQueryFilter::from_excluded_entities([player]),
    );
    if let Some(hit) = hits.into_iter().find(|hit| {
        hit.distance <= 0.02
            && edge_boundaries
                .get(hit.entity)
                .is_ok_and(|boundary| boundary.side == boundary_side)
    }) {
        report
            .edge_boundary_contact_events
            .push(EdgeBoundaryContactEvent {
                tick: report.total_ticks,
                boundary_side: boundary_side.clone(),
                player_position_m: position.to_array(),
                distance_m: hit.distance,
                detection: "avian_capsule_shape_cast".to_owned(),
            });
    }
}

fn sample_ledge_edge(
    position: Vec3,
    supported: bool,
    spec: &HarnessSpec,
    report: &mut ScenarioReport,
) {
    let crate::walkability_harness::scenarios::SyntheticGeometry::OpenLedge { strip_width_m } =
        &spec.geometry
    else {
        return;
    };
    let edge_z = *strip_width_m * 0.5;
    let clearance = edge_z - position.z - PLAYER_RADIUS_M;
    report.minimum_ledge_edge_clearance_m = Some(
        report
            .minimum_ledge_edge_clearance_m
            .map_or(clearance, |minimum| minimum.min(clearance)),
    );
    report.maximum_ledge_lateral_center_z_m = Some(
        report
            .maximum_ledge_lateral_center_z_m
            .map_or(position.z, |maximum| maximum.max(position.z)),
    );
    report.ledge_edge_samples.push(LedgeEdgeSample {
        tick: report.total_ticks,
        lateral_center_z_m: position.z,
        capsule_edge_clearance_m: clearance,
        supported,
    });
}

fn sample_authored_lateral_push(
    position: Vec3,
    velocity: Vec3,
    supported: bool,
    spec: &HarnessSpec,
    report: &mut ScenarioReport,
) {
    let SyntheticGeometry::AuthoredLateralPush {
        station,
        center_xz,
        outward_direction_xz,
        boundary_side,
    } = &spec.geometry
    else {
        return;
    };
    let offset = (position.x - center_xz[0]) * outward_direction_xz[0]
        + (position.z - center_xz[1]) * outward_direction_xz[1];
    let bottom_rise = position.y - spec.start.y;
    let speed = velocity.length();
    report.authored_lateral_station = Some(station.clone());
    report.authored_lateral_expected_boundary = Some(boundary_side.clone());
    report.authored_lateral_max_abs_offset_m = Some(
        report
            .authored_lateral_max_abs_offset_m
            .unwrap_or_default()
            .max(offset.abs()),
    );
    report.authored_lateral_max_capsule_bottom_rise_m = Some(
        report
            .authored_lateral_max_capsule_bottom_rise_m
            .unwrap_or(f32::NEG_INFINITY)
            .max(bottom_rise),
    );
    let phase = if report.total_ticks <= AUTHORED_LATERAL_PUSH_TICKS {
        "lateral_input"
    } else {
        "release"
    };
    if phase == "release" {
        report.authored_lateral_rest_positions.push(position);
        report.authored_lateral_rest_speeds.push(speed);
    }
    report
        .authored_lateral_samples
        .push(AuthoredLateralPushSample {
            tick: report.total_ticks,
            phase: phase.to_owned(),
            lateral_offset_m: offset,
            capsule_bottom_rise_m: bottom_rise,
            speed_mps: speed,
            supported,
            player_position_m: position.to_array(),
        });
}

fn horizontal_distance(first: Vec3, second: Vec3) -> f32 {
    horizontal_delta(first, second).length()
}

fn horizontal_delta(first: Vec3, second: Vec3) -> Vec3 {
    Vec3::new(second.x - first.x, 0.0, second.z - first.z)
}

fn point_segment_distance(point: Vec3, start: Vec3, end: Vec3) -> f32 {
    let segment = horizontal_delta(start, end);
    let offset = horizontal_delta(start, point);
    let fraction =
        (offset.dot(segment) / segment.length_squared().max(f32::EPSILON)).clamp(0.0, 1.0);
    horizontal_delta(point, start + segment * fraction).length()
}

fn ratio(numerator: usize, denominator: usize) -> f32 {
    numerator as f32 / denominator.max(1) as f32
}

#[cfg(test)]
mod tests {
    use super::{position_radius, summarize_distances};
    use bevy::prelude::Vec3;

    #[test]
    fn summarizes_empty_distance_samples() {
        let summary = summarize_distances(&mut []);
        assert_eq!(summary.sample_count, 0);
        assert_eq!(summary.q90_m, None);
    }

    #[test]
    fn summarizes_distance_distribution() {
        let summary = summarize_distances(&mut [4.0, 1.0, 3.0, 2.0, 5.0]);
        assert_eq!(summary.sample_count, 5);
        assert_eq!(summary.min_m, Some(1.0));
        assert_eq!(summary.median_m, Some(3.0));
        assert_eq!(summary.q90_m, Some(5.0));
        assert_eq!(summary.max_m, Some(5.0));
    }

    #[test]
    fn position_radius_uses_the_requested_tail_window() {
        let radius = position_radius(
            &[
                Vec3::ZERO,
                Vec3::new(2.0, 0.0, 0.0),
                Vec3::new(4.0, 0.0, 0.0),
            ],
            2,
        );
        assert_eq!(radius, Some(1.0));
    }

    #[test]
    fn position_radius_requires_a_full_window() {
        let radius = position_radius(&[Vec3::ZERO], 2);
        assert_eq!(radius, None);
    }
}
