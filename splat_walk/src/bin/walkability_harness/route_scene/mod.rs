mod assets;
// The companion hunyuan_route_scene binary uses this renderer-only path.
#[allow(dead_code)]
mod capture;
mod geometry_query;
mod manifest;
#[allow(dead_code)]
mod play;
mod report;
mod visual_metrics;

use std::{
    fs, thread,
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
        App, DefaultPlugins, Fixed, FixedUpdate, IntoScheduleConfigs, MinimalPlugins, PluginGroup,
        Startup, Time, TransformPlugin, Update, Window, default,
    },
    scene::ScenePlugin,
    time::TimeUpdateStrategy,
    window::{CursorGrabMode, CursorOptions, WindowPlugin, WindowResolution},
};
use bevy_tnua::{
    TnuaControllerPlugin,
    prelude::{TnuaPipelineSystems, TnuaUserControlsSystems},
};
use bevy_tnua_avian3d::prelude::TnuaAvian3dPlugin;
use serde::{Deserialize, Serialize};

use crate::walkability_harness::{
    route_collision::{SceneAssetReadiness, poll_and_install, start_loading},
    scenarios::{AuthoredRouteAsset, authored_route_config},
    simulation::{
        ControlScheme, PlayerResetEvent, PlayerResetEvents, ScenarioReport, collect_sample,
        collect_sensor_shape_diagnostics, drive_player, reset_player_from_input,
        reset_player_on_safety_net, route_smoke_input, setup_scene,
    },
};

use self::{
    assets::{SceneVisualConfig, VisualSceneReport, poll_visual_loading, start_visual_loading},
    manifest::{SceneManifest, load_manifest, repo_root},
    report::{
        ComparisonSceneReport, SceneRunReportData, TraversalGateReport, UpdateTimeReport,
        baseline_comparison, scene_report,
    },
};

const FIXED_STEP: Duration = Duration::from_nanos(16_666_667);
const SCENE_TIMEOUT: Duration = Duration::from_secs(300);
const UPDATE_SLEEP: Duration = Duration::from_millis(1);
const ROUTE_REPORT_RELATIVE_PATH: &str = "godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/route_report.json";
const BASELINE_REPORT_RELATIVE_PATH: &str = "godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/avian_tnua_harness/walkability_report.json";
const OUTPUT_REPORT_RELATIVE_PATH: &str =
    "godot_walk/evidence/2026-10-13-hunyuan-track-a/hunyuan_route_scene_report.json";
#[allow(dead_code)]
const PLAY_SMOKE_REPORT_RELATIVE_PATH: &str =
    "godot_walk/evidence/2026-10-13-hunyuan-track-a/interactive_play_smoke_report.json";

#[derive(Serialize)]
struct InputSmokeReport<'a> {
    schema_version: u32,
    label: &'static str,
    status: &'static str,
    keyboard_motion_mapping_exercised: bool,
    locked_route_gate_passed: bool,
    keyboard_reset_events: &'a [PlayerResetEvent],
    traversal: &'a ComparisonSceneReport,
}

#[derive(Clone, Copy)]
#[allow(dead_code)]
enum SceneAppMode {
    Headless,
    InputSmoke,
    Interactive { initial_yaw: f32 },
}

#[derive(Deserialize)]
struct CameraMetadata {
    camera: CameraRecord,
}

#[derive(Deserialize)]
struct CameraRecord {
    camera_center_godot_world_m: [f32; 3],
    forward_godot_world: [f32; 3],
    up_godot_world: [f32; 3],
}

pub fn run() -> Result<()> {
    run_with_mode(SceneAppMode::Headless, OUTPUT_REPORT_RELATIVE_PATH)
}

#[allow(dead_code)]
pub fn run_play_smoke() -> Result<()> {
    run_with_mode(SceneAppMode::InputSmoke, PLAY_SMOKE_REPORT_RELATIVE_PATH)
}

#[allow(dead_code)]
pub fn run_interactive_play() -> Result<()> {
    let root = repo_root()?;
    play::start(&root)
}

fn run_with_mode(mode: SceneAppMode, output_report_path: &str) -> Result<()> {
    let started = Instant::now();
    let root = repo_root()?;
    let manifest = load_manifest(&root)?;
    let camera = load_camera_metadata(&root, &manifest)?;
    let model_transform = model_transform(&manifest, &camera)?;
    let (spec, mut route) = authored_route_config(&root.join(ROUTE_REPORT_RELATIVE_PATH))?;
    if (route.floor_y - manifest.transform.declared_collision_floor_y_m).abs() > 1.0e-4 {
        bail!("#139 route floor differs from the locked #100 collision floor");
    }
    route.directory.clone_from(&root);
    route.file_name.clone_from(&manifest.assets.collision.path);

    let mut app = build_app(
        spec.clone(),
        route,
        model_transform,
        camera_origin(&camera),
        manifest.assets.visual.path.clone(),
        &root,
        mode,
    );
    app.finish();
    app.cleanup();
    let mut update_times_seconds = Vec::new();
    let mut route_loaded = false;
    let mut route_simulation_started = None;
    let mut failure_reason = None;
    while started.elapsed() < SCENE_TIMEOUT {
        let route_was_loaded = route_loaded;
        let update_started = Instant::now();
        app.update();
        let update_time = update_started.elapsed().as_secs_f64();
        let report = app
            .world()
            .get_resource::<ScenarioReport>()
            .context("scene app did not create traversal metrics")?;
        if report.collision_asset_loaded {
            route_loaded = true;
            if route_was_loaded {
                update_times_seconds.push(update_time);
            } else {
                route_simulation_started = Some(Instant::now());
            }
        }
        if let Some(reason) = &report.failure_reason {
            failure_reason = Some(reason.clone());
            break;
        }
        if route_loaded && super::is_complete_and_settled(&app)? {
            break;
        }
        if route_loaded && report.total_ticks >= spec.max_updates {
            failure_reason =
                Some("authored-route traversal exceeded its locked update budget".to_owned());
            break;
        }
        thread::sleep(UPDATE_SLEEP);
    }
    if !route_loaded && failure_reason.is_none() {
        failure_reason = Some("timed out before visual and collision assets were ready".to_owned());
    }
    if route_loaded && failure_reason.is_none() && started.elapsed() >= SCENE_TIMEOUT {
        failure_reason = Some("timed out during authored-route traversal".to_owned());
    }

    let mut traversal = app
        .world()
        .get_resource::<ScenarioReport>()
        .context("scene app lost traversal metrics")?
        .clone();
    if failure_reason.is_some() {
        traversal.failure_reason.clone_from(&failure_reason);
    }
    super::finalize_metrics(&mut traversal);
    let route_simulation_wall_time =
        route_simulation_started.map_or(0.0, |started| started.elapsed().as_secs_f64());
    traversal.runtime_seconds = route_simulation_wall_time;
    traversal.resident_set_kib_at_completion = current_rss_kib();
    traversal.pass = super::scenario_passes(&traversal);

    let visual = app
        .world()
        .get_resource::<VisualSceneReport>()
        .and_then(|report| report.0.as_ref())
        .cloned();
    let baseline = baseline_comparison(&traversal, &root.join(BASELINE_REPORT_RELATIVE_PATH))?;
    let update_time = UpdateTimeReport::from_samples(&update_times_seconds);
    let mut report = scene_report(
        &manifest,
        SceneRunReportData {
            visual,
            traversal,
            baseline_comparison: baseline,
            traversal_gate: TraversalGateReport::from_manifest(&manifest),
            model_rotation_xyzw: model_transform.rotation.to_array(),
            update_time_ms: update_time,
            scene_total_wall_time_seconds: started.elapsed().as_secs_f64(),
            route_simulation_wall_time_seconds: route_simulation_wall_time,
            peak_rss_kib: peak_rss_kib(),
            current_rss_kib: current_rss_kib(),
        },
    );
    if matches!(mode, SceneAppMode::InputSmoke) && input_smoke_route_gate_passes(&report) {
        report.status = "interactive_input_route_smoke_passed";
    }
    if matches!(mode, SceneAppMode::InputSmoke) {
        let resets = app
            .world()
            .get_resource::<PlayerResetEvents>()
            .cloned()
            .context("play input smoke did not record reset events")?;
        if !resets.0.iter().any(|event| event.reason == "keyboard_r") {
            bail!("play input smoke did not consume a keyboard reset input");
        }
        let locked_route_gate_passed = input_smoke_route_gate_passes(&report);
        write_input_smoke_report(
            &root,
            output_report_path,
            &report,
            &resets,
            locked_route_gate_passed,
        )?;
    } else {
        write_report(&root, output_report_path, &report)?;
    }
    println!("{}", serde_json::to_string_pretty(&report)?);
    if let Some(reason) = failure_reason {
        bail!("uncalibrated comparison scene did not complete: {reason}");
    }
    let passed = if matches!(mode, SceneAppMode::InputSmoke) {
        input_smoke_route_gate_passes(&report)
    } else {
        report.traversal.pass && report.baseline_comparison.matches_within_1e_6
    };
    if !passed {
        let reason = if matches!(mode, SceneAppMode::InputSmoke) {
            "interactive input smoke failed its locked route gate"
        } else {
            "uncalibrated comparison scene failed traversal or #135 parity checks"
        };
        bail!("{reason}");
    }
    Ok(())
}

#[allow(dead_code)]
pub fn run_capture() -> Result<()> {
    capture::run()
}

fn build_app(
    spec: crate::walkability_harness::scenarios::HarnessSpec,
    route: AuthoredRouteAsset,
    model_transform: bevy::prelude::Transform,
    frame_141_camera_origin: bevy::prelude::Vec3,
    visual_asset_path: String,
    root: &std::path::Path,
    mode: SceneAppMode,
) -> App {
    let mut app = App::new();
    match mode {
        SceneAppMode::Interactive { .. } => {
            app.add_plugins(
                DefaultPlugins
                    .set(AssetPlugin {
                        file_path: root.to_string_lossy().into_owned(),
                        ..default()
                    })
                    .set(WindowPlugin {
                        primary_window: Some(Window {
                            title: "Uncalibrated Hunyuan route".into(),
                            resolution: WindowResolution::new(1280, 720)
                                .with_scale_factor_override(1.0),
                            ..default()
                        }),
                        primary_cursor_options: Some(CursorOptions {
                            visible: false,
                            grab_mode: CursorGrabMode::Locked,
                            ..default()
                        }),
                        ..default()
                    })
                    .set(GltfPlugin {
                        convert_coordinates: GltfConvertCoordinates {
                            rotate_scene_entity: false,
                            rotate_meshes: false,
                        },
                        ..default()
                    }),
            );
            app.insert_resource(Time::<Fixed>::from_hz(60.0));
        }
        SceneAppMode::Headless | SceneAppMode::InputSmoke => {
            app.add_plugins(MinimalPlugins)
                .add_plugins(AssetPlugin {
                    file_path: root.to_string_lossy().into_owned(),
                    ..default()
                })
                .add_plugins((TransformPlugin, MeshPlugin, ScenePlugin))
                .init_asset::<StandardMaterial>()
                .add_plugins(GltfPlugin {
                    convert_coordinates: GltfConvertCoordinates {
                        rotate_scene_entity: false,
                        rotate_meshes: false,
                    },
                    ..default()
                })
                .insert_resource(TimeUpdateStrategy::ManualDuration(FIXED_STEP));
        }
    }
    app.add_plugins(PhysicsPlugins::new(FixedUpdate))
        .add_plugins(TnuaControllerPlugin::<ControlScheme>::new(FixedUpdate))
        .add_plugins(TnuaAvian3dPlugin::new(FixedUpdate))
        .insert_resource(spec)
        .insert_resource(route)
        .insert_resource(SceneAssetReadiness {
            visual_ready: false,
        })
        .insert_resource(SceneVisualConfig {
            asset_path: visual_asset_path,
            model_transform,
            frame_141_camera_origin,
            analyze_alignment: !matches!(mode, SceneAppMode::Interactive { .. }),
        })
        .init_resource::<ScenarioReport>()
        .init_resource::<VisualSceneReport>()
        .add_systems(Startup, (setup_scene, start_loading, start_visual_loading))
        .add_systems(
            FixedUpdate,
            (reset_player_from_input, drive_player)
                .chain()
                .in_set(TnuaUserControlsSystems),
        )
        .add_systems(
            FixedUpdate,
            collect_sensor_shape_diagnostics
                .after(TnuaPipelineSystems::Sensors)
                .before(TnuaUserControlsSystems),
        )
        .add_systems(Update, poll_visual_loading)
        .add_systems(Update, poll_and_install);
    match mode {
        SceneAppMode::Interactive { initial_yaw } => {
            app.add_systems(
                FixedUpdate,
                (reset_player_on_safety_net, play::advance_play_tick)
                    .chain()
                    .after(PhysicsSystems::StepSimulation),
            )
            .add_systems(Update, play::exit_on_scene_failure);
            play::configure_interactive(&mut app, initial_yaw);
        }
        SceneAppMode::InputSmoke => {
            app.add_systems(
                FixedUpdate,
                route_smoke_input
                    .after(reset_player_from_input)
                    .before(drive_player)
                    .in_set(TnuaUserControlsSystems),
            );
            app.add_systems(
                FixedUpdate,
                reset_player_on_safety_net
                    .after(PhysicsSystems::StepSimulation)
                    .before(collect_sample),
            )
            .add_systems(
                FixedUpdate,
                collect_sample.after(PhysicsSystems::StepSimulation),
            );
            play::configure_route_input_smoke(&mut app);
        }
        SceneAppMode::Headless => {
            app.add_systems(
                FixedUpdate,
                reset_player_on_safety_net
                    .after(PhysicsSystems::StepSimulation)
                    .before(collect_sample),
            )
            .add_systems(
                FixedUpdate,
                collect_sample.after(PhysicsSystems::StepSimulation),
            );
        }
    }
    app
}

fn load_camera_metadata(root: &std::path::Path, manifest: &SceneManifest) -> Result<CameraRecord> {
    let path = root.join(&manifest.assets.camera_metadata.path);
    let metadata: CameraMetadata = serde_json::from_slice(
        &fs::read(&path)
            .with_context(|| format!("cannot read camera metadata {}", path.display()))?,
    )
    .context("frame-141 camera metadata is invalid JSON")?;
    Ok(metadata.camera)
}

fn camera_origin(camera: &CameraRecord) -> bevy::prelude::Vec3 {
    bevy::prelude::Vec3::from_array(camera.camera_center_godot_world_m)
}

fn model_transform(
    manifest: &SceneManifest,
    camera: &CameraRecord,
) -> Result<bevy::prelude::Transform> {
    use bevy::prelude::{Transform, Vec3};

    let forward = Vec3::from_array(camera.forward_godot_world).normalize_or_zero();
    let up = Vec3::from_array(camera.up_godot_world).normalize_or_zero();
    let right = forward.cross(up).normalize_or_zero();
    let camera_origin = camera_origin(camera);
    let registered_anchor = Vec3::from_array(
        manifest
            .transform
            .registered_frame_141_camera_anchor_world_m,
    );
    let plane_translation = Vec3::from_array(manifest.transform.plane_aligned_translation_world_m);
    if forward == Vec3::ZERO
        || up == Vec3::ZERO
        || right == Vec3::ZERO
        || forward.dot(up).abs() > 1.0e-3
        || camera_origin.distance(registered_anchor) > 0.01
        || (plane_translation.x - camera_origin.x).abs() > 1.0e-4
        || (plane_translation.z - camera_origin.z).abs() > 1.0e-4
        || ((plane_translation.y - camera_origin.y) - manifest.transform.camera_anchor_shift_y_m)
            .abs()
            > 1.0e-4
    {
        bail!("frame-141 camera metadata and locked plane-aligned transform disagree");
    }
    let rotation = convention_rotation(forward, right, up);
    Ok(Transform {
        translation: plane_translation,
        rotation,
        scale: Vec3::splat(manifest.transform.scale_m_per_hunyuan_unit),
    })
}

fn convention_rotation(
    forward: bevy::prelude::Vec3,
    right: bevy::prelude::Vec3,
    up: bevy::prelude::Vec3,
) -> bevy::prelude::Quat {
    use bevy::prelude::{Mat3, Quat};

    Quat::from_mat3(&Mat3::from_cols(-forward, right, up))
}

fn write_report(
    root: &std::path::Path,
    report_path: &str,
    report: &ComparisonSceneReport,
) -> Result<()> {
    let path = root.join(report_path);
    fs::write(&path, serde_json::to_vec_pretty(report)?)
        .with_context(|| format!("cannot write comparison scene report {}", path.display()))
}

fn write_input_smoke_report(
    root: &std::path::Path,
    report_path: &str,
    traversal: &ComparisonSceneReport,
    resets: &PlayerResetEvents,
    locked_route_gate_passed: bool,
) -> Result<()> {
    let report = InputSmokeReport {
        schema_version: 1,
        label: "uncalibrated",
        status: if locked_route_gate_passed {
            "interactive_input_route_smoke_passed"
        } else {
            "interactive_input_route_smoke_failed"
        },
        keyboard_motion_mapping_exercised: true,
        locked_route_gate_passed,
        keyboard_reset_events: &resets.0,
        traversal,
    };
    let path = root.join(report_path);
    fs::write(&path, serde_json::to_vec_pretty(&report)?)
        .with_context(|| format!("cannot write input-smoke report {}", path.display()))
}

fn input_smoke_route_gate_passes(report: &ComparisonSceneReport) -> bool {
    let traversal = &report.traversal;
    let baseline = &report.baseline_comparison;
    traversal.pass
        && baseline.outbound_progress_delta.abs() <= 1.0e-6
        && baseline.inbound_progress_delta.abs() <= 1.0e-6
        && baseline.moving_support_delta.abs() <= 1.0e-6
        && baseline.safety_net_contact_count_delta == 0
        && traversal.safety_net_contact_events.is_empty()
        && traversal.edge_boundary_collision_triangles > 0
        && traversal.max_vertical_step <= report.traversal_gate.max_vertical_step_m
}

fn peak_rss_kib() -> Option<u64> {
    proc_status_metric("VmHWM:")
}

fn current_rss_kib() -> Option<u64> {
    proc_status_metric("VmRSS:")
}

fn proc_status_metric(name: &str) -> Option<u64> {
    fs::read_to_string("/proc/self/status")
        .ok()?
        .lines()
        .find_map(|line| {
            line.strip_prefix(name)
                .and_then(|value| value.split_whitespace().next())
                .and_then(|value| value.parse().ok())
        })
}

#[cfg(test)]
mod tests {
    use bevy::prelude::Vec3;

    use super::convention_rotation;

    #[test]
    fn hunyuan_axes_map_to_frame_camera_axes() {
        let forward = Vec3::new(-0.528622, 0.001250, -0.848856).normalize();
        let up = Vec3::new(0.003274, 0.999994, -0.000566).normalize();
        let right = forward.cross(up).normalize();
        let rotation = convention_rotation(forward, right, up);
        assert!((rotation * Vec3::X + forward).length() < 1.0e-5);
        assert!((rotation * Vec3::Y - right).length() < 1.0e-5);
        assert!((rotation * Vec3::Z - up).length() < 1.0e-5);
    }
}
