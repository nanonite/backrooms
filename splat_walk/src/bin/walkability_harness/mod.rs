mod geometry;
mod route_collision;
mod route_mesh;
mod route_scene;
mod scenarios;
mod sensor_shape_diagnostic;
mod simulation;

use std::{
    env, fs,
    path::PathBuf,
    time::{Duration, Instant},
};

use anyhow::{Context, Result, bail};
use avian3d::{prelude::PhysicsPlugins, schedule::PhysicsSystems};
use bevy::{
    asset::{AssetApp, AssetPlugin},
    gltf::{GltfPlugin, convert_coordinates::GltfConvertCoordinates},
    mesh::MeshPlugin,
    pbr::StandardMaterial,
    prelude::{
        App, FixedUpdate, IntoScheduleConfigs, MinimalPlugins, TransformPlugin, Update, default,
    },
    scene::ScenePlugin,
    time::TimeUpdateStrategy,
};
use bevy_tnua::{
    TnuaControllerPlugin,
    prelude::{TnuaPipelineSystems, TnuaUserControlsSystems},
};
use bevy_tnua_avian3d::prelude::TnuaAvian3dPlugin;
use serde::Serialize;

use route_collision::{poll_and_install, start_loading};
use scenarios::{
    AUTHORED_LATERAL_PUSH_TICKS, AUTHORED_LATERAL_RELEASE_TICKS, AuthoredRouteAsset, HarnessSpec,
    authored_column_probe, authored_lateral_push_specs, authored_route_config,
    authored_route_probe, is_authored_lateral_push, is_steep_rejection,
    steep_rejection_diagnostics, synthetic_specs,
};
use simulation::{
    AUTHORED_LATERAL_FINAL_REST_TICKS, AUTHORED_LATERAL_MAX_BOTTOM_RISE_M,
    AUTHORED_LATERAL_MAX_FINAL_POSITION_RADIUS_M, AUTHORED_LATERAL_MAX_FINAL_SPEED_MPS,
    AUTHORED_LATERAL_MAX_OFFSET_M, AUTHORED_LATERAL_MIN_SUPPORT_FRACTION, ControlScheme,
    PLAYER_HEIGHT_M, PLAYER_RADIUS_M, SAFETY_NET_TOP_Y_M, SLOPE_FINAL_REST_WINDOW_TICKS,
    SLOPE_INPUT_TICKS, SLOPE_MAX_BOTTOM_HEIGHT_ABOVE_FLAT_M, SLOPE_MAX_FINAL_SPEED_MPS,
    SLOPE_MAX_POSITION_RADIUS_M, SLOPE_MAX_VERTICAL_SPEED_MPS, SLOPE_MIN_PLAYER_CENTER_Y_M,
    SLOPE_RECOVERY_TICKS, SLOPE_STABILITY_WINDOW_TICKS, ScenarioReport, collect_sample,
    collect_sensor_shape_diagnostics, drive_player, setup_scene,
};

const FIXED_STEP: Duration = Duration::from_nanos(16_666_667);
const REQUIRED_SUPPORT_FRACTION: f32 = 0.95;
const MAX_ALLOWED_STEP_M: f32 = 0.2;

#[derive(Serialize)]
struct HarnessSuite {
    schema_version: u32,
    report_phase: &'static str,
    bevy: &'static str,
    avian3d: &'static str,
    bevy_tnua: &'static str,
    bevy_tnua_avian3d: &'static str,
    rendering_enabled: bool,
    gpu_used: bool,
    tick_rate_hz: u32,
    player_capsule_radius_m: f32,
    player_capsule_height_m: f32,
    safety_net_sensor_present: bool,
    safety_net_top_y_m: f32,
    suite_wall_clock_seconds: f64,
    resident_set_kib_at_completion: Option<u64>,
    peak_rss_kib: Option<u64>,
    slope_gate_design: SlopeGateDesign,
    authored_lateral_push_gate: AuthoredLateralPushGate,
    scenarios: Vec<ScenarioReport>,
}

#[derive(Serialize, Clone, Copy)]
struct AuthoredLateralPushGate {
    family: &'static str,
    station_rule: &'static str,
    station_count: usize,
    target_edges: &'static str,
    input_ticks_per_station_edge: usize,
    release_ticks_per_station_edge: usize,
    no_safety_net_contacts: bool,
    minimum_moving_support_fraction: f32,
    maximum_absolute_lateral_offset_m: f32,
    lateral_offset_definition: &'static str,
    boundary_contact_required: bool,
    boundary_contact_record_fields: &'static str,
    maximum_capsule_bottom_rise_m: f32,
    bottom_rise_definition: &'static str,
    final_rest_window_ticks: usize,
    maximum_final_speed_mps: f32,
    maximum_final_position_radius_m: f32,
    final_rest_definition: &'static str,
    open_ledge_negative_control: &'static str,
}

const AUTHORED_LATERAL_PUSH_GATE: AuthoredLateralPushGate = AuthoredLateralPushGate {
    family: "authored_loop_lateral_push",
    station_rule: "8 evenly spaced stations plus the station nearest the column proxy",
    station_count: 9,
    target_edges: "inner and outer authored_edge_boundary",
    input_ticks_per_station_edge: AUTHORED_LATERAL_PUSH_TICKS,
    release_ticks_per_station_edge: AUTHORED_LATERAL_RELEASE_TICKS,
    no_safety_net_contacts: true,
    minimum_moving_support_fraction: AUTHORED_LATERAL_MIN_SUPPORT_FRACTION,
    maximum_absolute_lateral_offset_m: AUTHORED_LATERAL_MAX_OFFSET_M,
    lateral_offset_definition: "absolute capsule-center displacement from station along the loop radial; 0.10 m lane margin plus 0.02 m tolerance",
    boundary_contact_required: true,
    boundary_contact_record_fields: "tick, expected boundary side and player position",
    maximum_capsule_bottom_rise_m: AUTHORED_LATERAL_MAX_BOTTOM_RISE_M,
    bottom_rise_definition: "maximum capsule-bottom Y minus its initial capsule-bottom Y over input and release",
    final_rest_window_ticks: AUTHORED_LATERAL_FINAL_REST_TICKS,
    maximum_final_speed_mps: AUTHORED_LATERAL_MAX_FINAL_SPEED_MPS,
    maximum_final_position_radius_m: AUTHORED_LATERAL_MAX_FINAL_POSITION_RADIUS_M,
    final_rest_definition: "last 10 release ticks satisfy speed and position-radius bounds",
    open_ledge_negative_control: "open_ledge_0_8m unchanged and must reach SafetyNet",
};

#[derive(Serialize, Clone, Copy)]
struct SlopeGateDesign {
    status: &'static str,
    rationale: &'static str,
    steep_ground_controller_policy: &'static str,
    non_blocking_diagnostics: &'static str,
    input_ticks: usize,
    recovery_budget_ticks: usize,
    recovery_input: &'static str,
    max_capsule_bottom_height_above_flat_m: f32,
    flat_rest_player_center_y_m: f32,
    capsule_half_height_m: f32,
    flat_rest_capsule_bottom_y_m: f32,
    max_additional_capsule_bottom_rise_m: f32,
    min_player_center_y_m: f32,
    flat_rest_height_fall_margin_m: f32,
    max_abs_vertical_velocity_during_input_mps: f32,
    input_stability_window_ticks: usize,
    max_input_position_radius_from_centroid_m: f32,
    final_rest_window_ticks: usize,
    max_final_speed_mps: f32,
    max_final_position_radius_from_centroid_m: f32,
    slope_sensor_required_angle_degrees: f32,
    slope_sensor_condition: &'static str,
    positive_control_condition: &'static str,
    pass_outcome: &'static str,
    implementation_complete: bool,
}

const SLOPE_GATE_DESIGN: SlopeGateDesign = SlopeGateDesign {
    status: "implemented_locked_gate",
    rationale: "Tnua 0.31 clears standing_on above max_slope; that classification is the mechanism check, not success. A fall fails. Climb, vertical speed, oscillation and recovery bounds are unchanged.",
    steep_ground_controller_policy: "Steep ground acts as a wall: uphill input is removed, Tnua runs SenseOnly unless input leads downhill, and a character blocked after walkable support holds its height (Y locked, vertical velocity zeroed) until downhill input or walkable ground. Vertical speed and oscillation while held are zero by this policy, not by settling physics.",
    non_blocking_diagnostics: "steep_rejection_diagnostic_* repeat the gate at 17-30 degrees and 25-100% approach speed; they are reported but do not fail the suite.",
    input_ticks: SLOPE_INPUT_TICKS,
    recovery_budget_ticks: SLOPE_RECOVERY_TICKS,
    recovery_input: "reverse_until_flat_support_then_zero_input",
    max_capsule_bottom_height_above_flat_m: SLOPE_MAX_BOTTOM_HEIGHT_ABOVE_FLAT_M,
    flat_rest_player_center_y_m: 0.7,
    capsule_half_height_m: PLAYER_HEIGHT_M * 0.5,
    flat_rest_capsule_bottom_y_m: 0.1,
    max_additional_capsule_bottom_rise_m: 0.15,
    min_player_center_y_m: SLOPE_MIN_PLAYER_CENTER_Y_M,
    flat_rest_height_fall_margin_m: 0.1,
    max_abs_vertical_velocity_during_input_mps: SLOPE_MAX_VERTICAL_SPEED_MPS,
    input_stability_window_ticks: SLOPE_STABILITY_WINDOW_TICKS,
    max_input_position_radius_from_centroid_m: SLOPE_MAX_POSITION_RADIUS_M,
    final_rest_window_ticks: SLOPE_FINAL_REST_WINDOW_TICKS,
    max_final_speed_mps: SLOPE_MAX_FINAL_SPEED_MPS,
    max_final_position_radius_from_centroid_m: SLOPE_MAX_POSITION_RADIUS_M,
    slope_sensor_required_angle_degrees: simulation::CONTROLLER_MAX_SLOPE_DEGREES,
    slope_sensor_condition: "every_ground_hit_on_tagged_17_degree_incline_has_angle_gt_16_and_standing_on_none",
    positive_control_condition: "every_ground_hit_on_tagged_15_degree_incline_has_angle_lte_16_and_standing_on_some",
    pass_outcome: "controlled_slip_rejection_returned_to_support",
    implementation_complete: true,
};

pub fn run() -> Result<()> {
    if env::args().any(|argument| argument == "--hunyuan-route-scene") {
        return run_route_scene();
    }
    if env::args().any(|argument| argument == "--write-gate-plan") {
        return write_gate_plan();
    }
    let suite_started = Instant::now();
    let mut scenarios = Vec::new();
    for spec in synthetic_specs()
        .into_iter()
        .chain(steep_rejection_diagnostics())
    {
        scenarios.push(run_scenario(spec, None)?);
    }
    let (route_spec, route_asset) = authored_route_config(&route_report_path()?)?;
    scenarios.push(run_scenario(
        authored_route_probe(&route_spec),
        Some(route_asset.clone()),
    )?);
    scenarios.push(run_scenario(
        authored_column_probe(&route_asset),
        Some(route_asset.clone()),
    )?);
    scenarios.push(run_scenario(route_spec, Some(route_asset.clone()))?);
    for spec in authored_lateral_push_specs(&route_asset) {
        scenarios.push(run_scenario(spec, Some(route_asset.clone()))?);
    }
    let suite = HarnessSuite {
        schema_version: 5,
        report_phase: "completed_run",
        bevy: "0.18.0",
        avian3d: "0.6.1",
        bevy_tnua: "0.31.0",
        bevy_tnua_avian3d: "0.11.0",
        rendering_enabled: false,
        gpu_used: false,
        tick_rate_hz: 60,
        player_capsule_radius_m: PLAYER_RADIUS_M,
        player_capsule_height_m: PLAYER_HEIGHT_M,
        safety_net_sensor_present: true,
        safety_net_top_y_m: SAFETY_NET_TOP_Y_M,
        suite_wall_clock_seconds: suite_started.elapsed().as_secs_f64(),
        resident_set_kib_at_completion: current_rss_kib(),
        peak_rss_kib: peak_rss_kib(),
        slope_gate_design: slope_gate_design(),
        authored_lateral_push_gate: AUTHORED_LATERAL_PUSH_GATE,
        scenarios,
    };
    let report_json = serde_json::to_string_pretty(&suite)?;
    println!("{report_json}");
    write_report(&report_json)?;
    if let Some(failed) = suite
        .scenarios
        .iter()
        .find(|scenario| scenario.blocking && !scenario.pass)
    {
        bail!("walkability scenario failed: {}", failed.scenario);
    }
    Ok(())
}

pub fn run_route_scene() -> Result<()> {
    route_scene::run()
}

fn run_scenario(spec: HarnessSpec, route: Option<AuthoredRouteAsset>) -> Result<ScenarioReport> {
    let scenario_started = Instant::now();
    let max_updates = spec.max_updates;
    let mut app = build_app(spec, route);
    app.finish();
    app.cleanup();
    for _ in 0..max_updates {
        app.update();
        if is_complete_and_settled(&app)? {
            break;
        }
    }
    let mut report = app
        .world()
        .get_resource::<ScenarioReport>()
        .context("harness did not create scenario metrics")?
        .clone();
    finalize_metrics(&mut report);
    report.runtime_seconds = scenario_started.elapsed().as_secs_f64();
    report.resident_set_kib_at_completion = current_rss_kib();
    report.pass = scenario_passes(&report);
    Ok(report)
}

fn build_app(spec: HarnessSpec, route: Option<AuthoredRouteAsset>) -> App {
    let mut app = App::new();
    let asset_plugin = route
        .as_ref()
        .map_or_else(AssetPlugin::default, |route| AssetPlugin {
            file_path: route.directory.to_string_lossy().into_owned(),
            ..default()
        });
    app.add_plugins(MinimalPlugins)
        .add_plugins(asset_plugin)
        .add_plugins((TransformPlugin, MeshPlugin, ScenePlugin))
        .init_asset::<StandardMaterial>()
        .add_plugins(GltfPlugin {
            convert_coordinates: GltfConvertCoordinates {
                rotate_scene_entity: false,
                rotate_meshes: false,
            },
            ..default()
        })
        .add_plugins(PhysicsPlugins::new(FixedUpdate))
        .add_plugins(TnuaControllerPlugin::<ControlScheme>::new(FixedUpdate))
        .add_plugins(TnuaAvian3dPlugin::new(FixedUpdate))
        .insert_resource(TimeUpdateStrategy::ManualDuration(FIXED_STEP))
        .insert_resource(spec)
        .init_resource::<ScenarioReport>()
        .add_systems(bevy::prelude::Startup, setup_scene)
        .add_systems(FixedUpdate, drive_player.in_set(TnuaUserControlsSystems))
        .add_systems(
            FixedUpdate,
            collect_sensor_shape_diagnostics
                .after(TnuaPipelineSystems::Sensors)
                .before(TnuaUserControlsSystems),
        )
        .add_systems(
            FixedUpdate,
            collect_sample.after(PhysicsSystems::StepSimulation),
        );
    if let Some(route) = route {
        app.insert_resource(route)
            .add_systems(bevy::prelude::Startup, start_loading)
            .add_systems(Update, poll_and_install);
    }
    app
}

fn is_complete_and_settled(app: &App) -> Result<bool> {
    let report = app
        .world()
        .get_resource::<ScenarioReport>()
        .context("scenario report is unavailable")?;
    if report.failure_reason.is_some() {
        return Ok(true);
    }
    if !report.safety_net_contact_events.is_empty() {
        return Ok(true);
    }
    if is_steep_rejection(&report.scenario) {
        return Ok(report.total_ticks >= SLOPE_INPUT_TICKS + SLOPE_RECOVERY_TICKS);
    }
    if is_authored_lateral_push(&report.scenario) {
        return Ok(
            report.total_ticks >= AUTHORED_LATERAL_PUSH_TICKS + AUTHORED_LATERAL_RELEASE_TICKS
        );
    }
    Ok(report.progress_fraction >= 1.0 && report.total_ticks >= 240)
}

fn slope_gate_design() -> SlopeGateDesign {
    SLOPE_GATE_DESIGN
}

fn write_gate_plan() -> Result<()> {
    let suite = HarnessSuite {
        schema_version: 5,
        report_phase: "gate_plan_only",
        bevy: "0.18.0",
        avian3d: "0.6.1",
        bevy_tnua: "0.31.0",
        bevy_tnua_avian3d: "0.11.0",
        rendering_enabled: false,
        gpu_used: false,
        tick_rate_hz: 60,
        player_capsule_radius_m: PLAYER_RADIUS_M,
        player_capsule_height_m: PLAYER_HEIGHT_M,
        safety_net_sensor_present: true,
        safety_net_top_y_m: SAFETY_NET_TOP_Y_M,
        suite_wall_clock_seconds: 0.0,
        resident_set_kib_at_completion: current_rss_kib(),
        peak_rss_kib: peak_rss_kib(),
        slope_gate_design: slope_gate_design(),
        authored_lateral_push_gate: AUTHORED_LATERAL_PUSH_GATE,
        scenarios: Vec::new(),
    };
    write_report(&serde_json::to_string_pretty(&suite)?)
}

fn finalize_metrics(report: &mut ScenarioReport) {
    report.moving_support_fraction = ratio(report.moving_support_ticks, report.moving_ticks);
    report.moving_floor_ray_fraction =
        ratio(report.moving_floor_ray_hit_ticks, report.moving_ticks);
    report.total_support_fraction = ratio(report.support_ticks, report.total_ticks);
    report.total_floor_ray_fraction = ratio(report.floor_ray_hit_ticks, report.total_ticks);
    report.fallthrough_detected =
        report.min_y < -2.0 || !report.safety_net_contact_events.is_empty();
    report.finalize_distance_summaries();
    report.headroom_clear_distance_lower_bound_m =
        (report.headroom_clear_ticks > 0).then_some(report.headroom_ray_max_distance_m);
    if is_steep_rejection(&report.scenario) {
        report.slope_gate_failures = slope_rejection_failures(report);
        let controlled_rejection = report.slope_gate_failures.is_empty();
        report.controlled_slope_rejection = Some(controlled_rejection);
        report.slope_rejection_outcome = Some(slope_rejection_outcome(report).to_owned());
    }
    if report.scenario == "open_ledge_0_8m" {
        let moved_laterally = report.maximum_ledge_lateral_center_z_m.unwrap_or(0.0) > 0.05;
        let controlled_stop = moved_laterally
            && report.progress_fraction < 0.9
            && report
                .minimum_ledge_edge_clearance_m
                .is_some_and(|clearance| {
                    (0.0..=simulation::OPEN_LEDGE_STOP_TOLERANCE_M).contains(&clearance)
                })
            && report.moving_support_fraction >= REQUIRED_SUPPORT_FRACTION
            && !report.fallthrough_detected
            && report.safety_net_contact_events.is_empty();
        let edge_hazard_observed = moved_laterally
            && (!report.support_loss_events.is_empty()
                || !report.safety_net_contact_events.is_empty());
        report.ledge_boundary_walls_required = Some(!controlled_stop);
        report.ledge_outcome = Some(if controlled_stop {
            "controller_stops_within_0_12m_of_open_edge".to_owned()
        } else if edge_hazard_observed {
            "authored_edge_boundaries_required_before_player_traversal".to_owned()
        } else {
            "open_edge_test_did_not_reach_a_classifiable_outcome".to_owned()
        });
    }
}

fn slope_rejection_failures(report: &ScenarioReport) -> Vec<String> {
    let mut failures = Vec::new();
    record_slope_safety_failures(report, &mut failures);
    record_slope_sensor_failures(report, &mut failures);
    record_slope_progress_failure(report, &mut failures);
    record_slope_ascent_failure(report, &mut failures);
    record_slope_stability_failures(report, &mut failures);
    record_slope_recovery_failures(report, &mut failures);
    failures
}

fn record_slope_safety_failures(report: &ScenarioReport, failures: &mut Vec<String>) {
    push_failure(
        failures,
        report.fallthrough_detected
            || report.min_y < SLOPE_MIN_PLAYER_CENTER_Y_M
            || !report.safety_net_contact_events.is_empty(),
        "fall_or_safety_net_contact",
    );
}

fn record_slope_sensor_failures(report: &ScenarioReport, failures: &mut Vec<String>) {
    push_failure(
        failures,
        report.slope_sensor_hit_ticks == 0 || report.slope_sensor_mismatch_ticks > 0,
        "tnua_steep_slope_sensor_mechanism_not_verified",
    );
}

fn record_slope_progress_failure(report: &ScenarioReport, failures: &mut Vec<String>) {
    push_failure(
        failures,
        report.progress_fraction >= 0.9,
        "steep_slope_progress_reached_90_percent",
    );
}

fn record_slope_ascent_failure(report: &ScenarioReport, failures: &mut Vec<String>) {
    push_failure(
        failures,
        report
            .slope_max_capsule_bottom_height_above_flat_m
            .is_none_or(|height| height > SLOPE_MAX_BOTTOM_HEIGHT_ABOVE_FLAT_M),
        "capsule_bottom_exceeded_0_25m_ascent_bound",
    );
}

fn record_slope_stability_failures(report: &ScenarioReport, failures: &mut Vec<String>) {
    push_failure(
        failures,
        report
            .slope_peak_abs_vertical_velocity_mps
            .is_none_or(|speed| speed > SLOPE_MAX_VERTICAL_SPEED_MPS),
        "peak_vertical_velocity_exceeded_0_50mps_bound",
    );
    push_failure(
        failures,
        report
            .slope_input_position_radius_m
            .is_none_or(|radius| radius > SLOPE_MAX_POSITION_RADIUS_M),
        "input_oscillation_exceeded_0_02m_bound",
    );
}

fn record_slope_recovery_failures(report: &ScenarioReport, failures: &mut Vec<String>) {
    push_failure(
        failures,
        !report.slope_recovered_to_flat
            || report
                .slope_recovery_ticks_to_flat_support
                .is_none_or(|ticks| ticks > SLOPE_RECOVERY_TICKS),
        "flat_support_not_regained_within_60_ticks",
    );
    push_failure(
        failures,
        !report.slope_recovery_end_at_rest,
        "recovery_did_not_end_at_rest",
    );
}

fn push_failure(failures: &mut Vec<String>, failed: bool, name: &str) {
    if failed {
        failures.push(name.to_owned());
    }
}

fn slope_rejection_outcome(report: &ScenarioReport) -> &'static str {
    let Some(first_failure) = slope_rejection_failures(report).first().cloned() else {
        return "controlled_slip_rejection_returned_to_support";
    };
    slope_failure_outcome(&first_failure)
}

fn slope_failure_outcome(failure: &str) -> &'static str {
    match failure {
        "fall_or_safety_net_contact" => "uncontrolled_fall_not_a_slope_rejection",
        "tnua_steep_slope_sensor_mechanism_not_verified" => {
            "tnua_steep_slope_sensor_mechanism_mismatch"
        }
        "steep_slope_progress_reached_90_percent" => "steep_slope_traversed_despite_limit",
        "capsule_bottom_exceeded_0_25m_ascent_bound" => "slope_ascent_limit_exceeded",
        "peak_vertical_velocity_exceeded_0_50mps_bound"
        | "input_oscillation_exceeded_0_02m_bound" => "slope_slip_exceeded_stability_bounds",
        "flat_support_not_regained_within_60_ticks" => {
            "slope_release_did_not_regain_flat_support_within_budget"
        }
        _ => "slope_release_returned_to_support_but_not_rest",
    }
}

fn scenario_passes(report: &ScenarioReport) -> bool {
    match report.scenario.as_str() {
        "synthetic_flat" | "step_020m" => {
            traversable(report) && report.max_vertical_step <= MAX_ALLOWED_STEP_M
        }
        "slope_15_degrees" => {
            traversable(report)
                && report.max_vertical_step <= MAX_ALLOWED_STEP_M
                && report.slope_sensor_hit_ticks > 0
                && report.slope_sensor_mismatch_ticks == 0
        }
        name if is_steep_rejection(name) => report.controlled_slope_rejection == Some(true),
        "slope_17_degrees_nonoverlap_probe" => {
            report.slope_sensor_hit_ticks > 0 && report.slope_sensor_mismatch_ticks == 0
        }
        name if is_authored_lateral_push(name) => authored_lateral_push_passes(report),
        "step_030m_rejection" => {
            report.progress_fraction < 0.9
                && report.moving_support_fraction >= REQUIRED_SUPPORT_FRACTION
                && !report.fallthrough_detected
                && report.safety_net_contact_events.is_empty()
        }
        "hole_030m" => {
            report.floor_ray_miss_ticks > 0
                && report.moving_floor_ray_fraction < 0.99
                && !report.fallthrough_detected
                && report.safety_net_contact_events.is_empty()
        }
        "wide_hole_safety_net_contact" => {
            report.fallthrough_detected
                && report.moving_floor_ray_fraction < 0.75
                && !report.safety_net_contact_events.is_empty()
        }
        "blocking_wall" => {
            report.progress_fraction < 0.6
                && report.moving_support_fraction >= REQUIRED_SUPPORT_FRACTION
                && !report.fallthrough_detected
                && report.safety_net_contact_events.is_empty()
        }
        "open_ledge_0_8m" => report.ledge_outcome.as_deref().is_some_and(|outcome| {
            outcome == "controller_stops_within_0_12m_of_open_edge"
                || outcome == "authored_edge_boundaries_required_before_player_traversal"
        }),
        "cleared_opening" => traversable(report),
        "headroom_ray" => {
            report.headroom_blocked_ticks > 0
                && report.moving_floor_ray_fraction >= 0.95
                && report.safety_net_contact_events.is_empty()
        }
        "authored_route_static_probe" => {
            report.collision_asset_loaded
                && report.collision_nodes == 4
                && report.total_support_fraction >= REQUIRED_SUPPORT_FRACTION
                && report.total_floor_ray_fraction >= REQUIRED_SUPPORT_FRACTION
                && !report.fallthrough_detected
                && report.safety_net_contact_events.is_empty()
        }
        "authored_column_block" => {
            report.collision_asset_loaded
                && report.obstacle_collision_triangles == 12
                && report.progress_fraction < 0.9
                && report.moving_support_fraction >= REQUIRED_SUPPORT_FRACTION
                && report.moving_floor_ray_fraction >= REQUIRED_SUPPORT_FRACTION
                && !report.fallthrough_detected
                && report.safety_net_contact_events.is_empty()
        }
        "authored_route_outbound_inbound" => {
            report.collision_asset_loaded
                && report.collision_nodes == 4
                && report.floor_collision_triangles == 512
                && report.obstacle_collision_triangles == 12
                && report.edge_boundary_collision_triangles > 0
                && report.outbound_progress_fraction >= 1.0
                && report.inbound_progress_fraction >= 0.992
                && traversable(report)
                && report.moving_support_fraction >= 0.993
                && report.max_vertical_step <= MAX_ALLOWED_STEP_M
                && report.safety_net_contact_events.is_empty()
        }
        _ => false,
    }
}

fn authored_lateral_push_passes(report: &ScenarioReport) -> bool {
    let expected_side = report.authored_lateral_expected_boundary.as_deref();
    report.collision_asset_loaded
        && report.edge_boundary_collision_triangles > 0
        && report.safety_net_contact_events.is_empty()
        && report.moving_support_fraction >= AUTHORED_LATERAL_MIN_SUPPORT_FRACTION
        && report
            .authored_lateral_max_abs_offset_m
            .is_some_and(|offset| offset <= AUTHORED_LATERAL_MAX_OFFSET_M)
        && expected_side.is_some_and(|side| {
            report
                .edge_boundary_contact_events
                .iter()
                .any(|contact| contact.boundary_side == side)
        })
        && report
            .authored_lateral_max_capsule_bottom_rise_m
            .is_some_and(|rise| rise <= AUTHORED_LATERAL_MAX_BOTTOM_RISE_M)
        && report.authored_lateral_rest_at_end
}

fn traversable(report: &ScenarioReport) -> bool {
    report.progress_fraction >= 0.9
        && report.moving_support_fraction >= REQUIRED_SUPPORT_FRACTION
        && !report.fallthrough_detected
        && report.safety_net_contact_events.is_empty()
}

fn ratio(numerator: usize, denominator: usize) -> f32 {
    numerator as f32 / denominator.max(1) as f32
}

fn route_report_path() -> Result<PathBuf> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .context("crate has no workspace parent")?
        .to_path_buf();
    Ok(root.join("godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/route_report.json"))
}

fn report_path() -> Result<PathBuf> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .context("crate has no workspace parent")?
        .to_path_buf();
    Ok(root.join("godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/avian_tnua_harness/walkability_report.json"))
}

fn write_report(report_json: &str) -> Result<()> {
    let path = report_path()?;
    fs::create_dir_all(path.parent().context("report path has no parent")?)?;
    fs::write(path, report_json).context("cannot save walkability report")
}

fn peak_rss_kib() -> Option<u64> {
    let status = fs::read_to_string("/proc/self/status").ok()?;
    status.lines().find_map(|line| {
        line.strip_prefix("VmHWM:")
            .and_then(|value| value.split_whitespace().next())
            .and_then(|value| value.parse().ok())
    })
}

fn current_rss_kib() -> Option<u64> {
    let status = fs::read_to_string("/proc/self/status").ok()?;
    status.lines().find_map(|line| {
        line.strip_prefix("VmRSS:")
            .and_then(|value| value.split_whitespace().next())
            .and_then(|value| value.parse().ok())
    })
}
