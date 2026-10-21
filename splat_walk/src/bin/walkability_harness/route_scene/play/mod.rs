mod automation;
mod input;
mod metrics;
mod resources;

use std::path::PathBuf;

use avian3d::prelude::Position;
use bevy::{
    pbr::StandardMaterial,
    prelude::{
        App, AppExit, Assets, Camera3d, Color, Commands, IntoScheduleConfigs, MessageWriter, Node,
        PerspectiveProjection, PositionType, Projection, Quat, Res, ResMut, Text, TextColor,
        TextFont, Transform, Val, Vec3, With, default,
    },
};
use hunyuan_bevy_fixture::player_controller::{
    PLAYER_FLOAT_HEIGHT_M, PlayerMotionInput, yaw_facing_direction,
};

use self::{
    automation::{configure as configure_automation, take_report, timeout_from_args},
    input::{CursorLockState, WalkLook},
    metrics::PlaySessionMetrics,
};
use crate::walkability_harness::{
    route_scene::assets::{SceneVisualConfig, SceneVisualMaterial},
    scenarios::{AuthoredRouteAsset, HarnessSpec},
    simulation::{HarnessPlayer, PlayerResetEvents, ScenarioReport},
};

pub use self::{metrics::PlaySessionReport, resources::ResourcePreflight};

pub fn configure_interactive(app: &mut App, initial_yaw: f32) {
    app.insert_resource(PlayerMotionInput {
        yaw_radians: initial_yaw,
        ..Default::default()
    })
    .insert_resource(WalkLook {
        yaw_radians: initial_yaw,
        pitch_radians: 0.0,
        reset_yaw_radians: initial_yaw,
    })
    .insert_resource(CursorLockState(true))
    .insert_resource(PlaySessionMetrics::default())
    .init_resource::<PlayerResetEvents>()
    .add_systems(
        bevy::prelude::Startup,
        (
            spawn_first_person_camera,
            spawn_status_label,
            setup_visual_material,
        ),
    )
    .add_systems(
        bevy::prelude::Update,
        (
            input::capture_controls,
            sync_first_person_camera,
            metrics::collect_frame_metrics,
        )
            .chain(),
    );
}

pub fn configure_route_input_smoke(app: &mut App) {
    app.insert_resource(PlayerMotionInput {
        reset_requested: true,
        ..Default::default()
    })
    .init_resource::<PlayerResetEvents>();
}

pub fn advance_play_tick(mut scenario: ResMut<ScenarioReport>) {
    scenario.total_ticks += 1;
}

pub fn exit_on_scene_failure(scenario: Res<ScenarioReport>, mut exit: MessageWriter<AppExit>) {
    if scenario.failure_reason.is_some() {
        exit.write(AppExit::error());
    }
}

pub fn check_resources() -> anyhow::Result<ResourcePreflight> {
    resources::check_resources()
}

pub fn write_report(path: std::path::PathBuf, report: &PlaySessionReport) -> anyhow::Result<()> {
    metrics::write_report(path, report)
}

fn spawn_first_person_camera(
    mut commands: Commands,
    spec: Res<HarnessSpec>,
    route: Res<AuthoredRouteAsset>,
    visual: Res<SceneVisualConfig>,
) {
    let tangent =
        (spec.waypoints.get(1).copied().unwrap_or(spec.start) - spec.start).normalize_or_zero();
    let yaw = yaw_facing_direction(tangent);
    let eye_height = visual.camera_origin.y - route.floor_y;
    let local_eye_offset = eye_height - PLAYER_FLOAT_HEIGHT_M;
    let position = spec.start + Vec3::Y * local_eye_offset;
    commands.spawn((
        Camera3d::default(),
        Projection::Perspective(PerspectiveProjection {
            fov: 47.3988_f32.to_radians(),
            ..default()
        }),
        Transform::from_translation(position).with_rotation(Quat::from_rotation_y(yaw)),
    ));
}

fn spawn_status_label(mut commands: Commands) {
    commands.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: Val::Px(16.0),
            top: Val::Px(14.0),
            ..default()
        },
        Text::new("UNCALIBRATED"),
        TextFont {
            font_size: 18.0,
            ..default()
        },
        TextColor(Color::WHITE),
    ));
}

fn setup_visual_material(mut commands: Commands, mut materials: ResMut<Assets<StandardMaterial>>) {
    let material = materials.add(StandardMaterial {
        base_color: Color::WHITE,
        unlit: true,
        cull_mode: None,
        ..default()
    });
    commands.insert_resource(SceneVisualMaterial(material));
}

fn sync_first_person_camera(
    players: bevy::prelude::Query<&Position, With<HarnessPlayer>>,
    mut cameras: bevy::prelude::Query<&mut Transform, bevy::prelude::With<Camera3d>>,
    route: Res<AuthoredRouteAsset>,
    visual: Res<SceneVisualConfig>,
    look: Res<WalkLook>,
) {
    let Ok(player) = players.single() else {
        return;
    };
    let Ok(mut camera) = cameras.single_mut() else {
        return;
    };
    camera.translation =
        player.0 + Vec3::Y * (visual.camera_origin.y - route.floor_y - PLAYER_FLOAT_HEIGHT_M);
    camera.rotation =
        Quat::from_rotation_y(look.yaw_radians) * Quat::from_rotation_x(look.pitch_radians);
}

pub fn initial_yaw(spec: &HarnessSpec) -> f32 {
    let tangent =
        (spec.waypoints.get(1).copied().unwrap_or(spec.start) - spec.start).normalize_or_zero();
    yaw_facing_direction(tangent)
}

pub fn report_path(
    root: &std::path::Path,
    manifest: &super::manifest::SceneManifest,
) -> std::path::PathBuf {
    std::env::args()
        .find_map(|argument| {
            argument
                .strip_prefix("--play-report=")
                .map(std::path::PathBuf::from)
        })
        .or_else(|| {
            super::psx_repair::enabled().then(|| {
                PathBuf::from(
                    "godot_walk/evidence/2026-10-21-issue-153/interactive_play_report.json",
                )
            })
        })
        .or_else(|| {
            manifest
                .output_report_path
                .as_deref()
                .map(|path| PathBuf::from(path).with_file_name("interactive_play_report.json"))
        })
        .map(|path| {
            if path.is_absolute() {
                path
            } else {
                root.join(path)
            }
        })
        .unwrap_or_else(|| {
            root.join("godot_walk/evidence/2026-10-13-hunyuan-track-a/interactive_play_report.json")
        })
}

pub fn start(root: &std::path::Path) -> anyhow::Result<()> {
    let preflight = check_resources()?;
    let timeout = timeout_from_args()?;
    println!(
        "Play-mode resource preflight: {}",
        serde_json::to_string(&preflight)?
    );
    let manifest = super::selected_manifest(root)?;
    let camera = super::load_camera_metadata(root, &manifest)?;
    let transform = super::model_transform(&manifest, &camera)?;
    let route_report_path = super::selected_route_report_path(root, &manifest);
    let (spec, mut route) = super::authored_route_config(&route_report_path)?;
    route.directory = root.to_path_buf();
    route.file_name.clone_from(&manifest.assets.collision.path);
    let initial_yaw = initial_yaw(&spec);
    let mut app = super::build_app(
        spec,
        route,
        transform,
        super::camera_origin(&camera),
        manifest.assets.visual.path.clone(),
        root,
        super::SceneAppMode::Interactive { initial_yaw },
    );
    let report_path = report_path(root, &manifest);
    let report_handle = configure_automation(&mut app, report_path, preflight, timeout);
    let exit = app.run();
    let report = take_report(report_handle)?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    if exit.is_error() {
        anyhow::bail!("interactive Bevy app exited with an error");
    }
    Ok(())
}
