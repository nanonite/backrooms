use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::Instant,
};

use anyhow::{Context, Result, bail};
use bevy::{
    app::AppExit,
    asset::{AssetPlugin, AssetServer, Assets},
    ecs::system::SystemParam,
    gltf::{Gltf, GltfMesh, GltfNode, GltfPlugin, convert_coordinates::GltfConvertCoordinates},
    mesh::Mesh,
    pbr::StandardMaterial,
    prelude::*,
    render::view::screenshot::{Screenshot, ScreenshotCaptured, save_to_disk},
    window::{WindowPlugin, WindowResolution},
};
use serde::{Deserialize, Serialize};

use super::{authored_visuals::spawn_room_visuals, selected_route_report_path};
use super::{load_camera_metadata, model_transform, play::ResourcePreflight, selected_manifest};
use crate::walkability_harness::route_scene::manifest::repo_root;
use crate::walkability_harness::scenarios::{AuthoredRouteAsset, authored_route_config};

const POSES_PATH: &str =
    "godot_walk/evidence/2026-10-13-hunyuan-track-a/captures/capture_poses.json";
const DEFAULT_OUTPUT_PATH: &str =
    "godot_walk/evidence/2026-10-13-hunyuan-track-a/captures/bevy_hunyuan";
const VISUAL_NODES: [&str; 2] = ["mesh_layer0", "mesh_layer1"];
const VIEW_NAMES: [&str; 9] = [
    "frame_141",
    "loop_station_00",
    "loop_station_01",
    "loop_station_02",
    "loop_station_03",
    "loop_station_04",
    "loop_station_05",
    "loop_station_06",
    "loop_station_07",
];
const MAX_ASSET_WAIT_SECONDS: u64 = 120;

#[derive(Clone, Deserialize)]
struct PoseManifest {
    issue: u32,
    label: String,
    registration_accepted: bool,
    scale_calibrated: bool,
    resolution: [u32; 2],
    vertical_fov_degrees: f32,
    settle_frames_before_each_capture: u32,
    poses: Vec<CapturePose>,
}

#[derive(Clone, Deserialize)]
struct CapturePose {
    name: String,
    position_world_m: [f32; 3],
    forward_world: [f32; 3],
    up_world: [f32; 3],
}

#[derive(Resource)]
struct CaptureConfig {
    visual_asset_path: String,
    model_transform: Transform,
    poses: Vec<CapturePose>,
    vertical_fov_radians: f32,
    output_directory: PathBuf,
    settle_frames: u32,
    authored_route: Option<AuthoredRouteAsset>,
}

#[derive(Resource)]
struct LoadedVisual(Handle<Gltf>, Instant);

#[derive(Resource)]
struct CaptureProgress {
    ready: bool,
    pose_index: usize,
    settle_frames: u32,
    in_flight: bool,
    failure: Option<String>,
}

#[derive(Component)]
struct CaptureCamera;

#[derive(SystemParam)]
struct GltfAssets<'w> {
    server: Res<'w, AssetServer>,
    gltfs: Res<'w, Assets<Gltf>>,
    nodes: Res<'w, Assets<GltfNode>>,
    gltf_meshes: Res<'w, Assets<GltfMesh>>,
    meshes: ResMut<'w, Assets<Mesh>>,
    materials: ResMut<'w, Assets<StandardMaterial>>,
}

struct CaptureVisualAssets<'a> {
    nodes: &'a Assets<GltfNode>,
    gltf_meshes: &'a Assets<GltfMesh>,
    meshes: &'a mut Assets<Mesh>,
    materials: &'a mut Assets<StandardMaterial>,
}

#[derive(Serialize)]
struct CaptureReport {
    schema_version: u32,
    issue: u32,
    label: &'static str,
    renderer: &'static str,
    bevy_version: &'static str,
    resolution: [u32; 2],
    vertical_fov_degrees: f32,
    captured_views: Vec<String>,
    visual_only_nodes: [&'static str; 2],
    authored_visual_surfaces_included: Vec<&'static str>,
    collision_loaded: bool,
    resource_preflight: ResourcePreflight,
    gpu_compute_processes_before_capture: usize,
    registration_accepted: bool,
    scale_calibrated: bool,
    wall_time_seconds: f64,
    peak_rss_kib: Option<u64>,
}

pub fn run() -> Result<()> {
    let started = Instant::now();
    let resource_preflight = super::play::check_resources()?;
    let gpu_compute_processes = ensure_no_competing_gpu_jobs()?;
    let root = repo_root()?;
    let scene_manifest = selected_manifest(&root)?;
    let camera = load_camera_metadata(&root, &scene_manifest)?;
    let transform = model_transform(&scene_manifest, &camera)?;
    let pose_path = scene_manifest
        .capture_poses_path
        .as_deref()
        .unwrap_or(POSES_PATH);
    let capture_manifest = read_pose_manifest(&root.join(pose_path))?;
    validate_pose_manifest(&capture_manifest)?;
    if capture_manifest.issue != scene_manifest.issue {
        bail!("capture-pose issue does not match the selected scene manifest");
    }
    let output_directory = capture_output_directory(&root, &scene_manifest);
    let authored_route = if scene_manifest.issue == 150 {
        let report_path = selected_route_report_path(&root, &scene_manifest);
        let (_, mut route) = authored_route_config(&report_path)?;
        route.directory = root.clone();
        Some(route)
    } else {
        None
    };
    fs::create_dir_all(&output_directory).with_context(|| {
        format!(
            "cannot create capture directory {}",
            output_directory.display()
        )
    })?;
    let output_directory = output_directory.canonicalize().with_context(|| {
        format!(
            "cannot resolve capture directory {}",
            output_directory.display()
        )
    })?;
    run_bevy_capture(
        &root,
        &scene_manifest.assets.visual.path,
        transform,
        capture_manifest.clone(),
        &output_directory,
        authored_route,
    )?;
    verify_capture_outputs(&output_directory, &capture_manifest)?;
    write_capture_report(
        &output_directory,
        &capture_manifest,
        started.elapsed().as_secs_f64(),
        resource_preflight,
        gpu_compute_processes,
    )?;
    Ok(())
}

fn read_pose_manifest(path: &Path) -> Result<PoseManifest> {
    serde_json::from_slice(
        &fs::read(path).with_context(|| format!("cannot read {}", path.display()))?,
    )
    .with_context(|| format!("invalid capture-pose manifest {}", path.display()))
}

fn validate_pose_manifest(manifest: &PoseManifest) -> Result<()> {
    let valid_view_count = if manifest.issue == 137 {
        manifest.poses.len() == VIEW_NAMES.len()
    } else {
        (1..=32).contains(&manifest.poses.len())
    };
    if ![137, 147, 150].contains(&manifest.issue)
        || manifest.label != "uncalibrated"
        || manifest.registration_accepted
        || manifest.scale_calibrated
        || manifest.resolution != [960, 540]
        || manifest.settle_frames_before_each_capture != 8
        || !valid_view_count
        || !manifest.vertical_fov_degrees.is_finite()
        || !(0.0..180.0).contains(&manifest.vertical_fov_degrees)
    {
        bail!("capture poses have invalid issue, calibration or capture settings");
    }
    for (index, pose) in manifest.poses.iter().enumerate() {
        if manifest.issue == 137 && pose.name != VIEW_NAMES[index] {
            bail!("capture pose order differs from the locked #137 view set");
        }
        if !pose
            .name
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '_')
        {
            bail!("capture pose name contains unsafe characters");
        }
        pose_transform(pose)?;
    }
    Ok(())
}

fn pose_transform(pose: &CapturePose) -> Result<Transform> {
    let position = Vec3::from_array(pose.position_world_m);
    let forward = Vec3::from_array(pose.forward_world);
    let up = Vec3::from_array(pose.up_world);
    if !position.is_finite()
        || !forward.is_finite()
        || !up.is_finite()
        || forward.length_squared() < 0.99
        || up.length_squared() < 0.99
        || forward.normalize().dot(up.normalize()).abs() > 1.0e-3
    {
        bail!(
            "capture pose {} has invalid or non-orthogonal axes",
            pose.name
        );
    }
    Ok(Transform::from_translation(position).looking_to(forward, up))
}

fn capture_output_directory(
    root: &Path,
    scene_manifest: &crate::walkability_harness::route_scene::manifest::SceneManifest,
) -> PathBuf {
    std::env::args()
        .find_map(|argument| argument.strip_prefix("--capture-dir=").map(PathBuf::from))
        .map(|path| {
            if path.is_absolute() {
                path
            } else {
                root.join(path)
            }
        })
        .or_else(|| {
            scene_manifest
                .capture_output_path
                .as_deref()
                .map(PathBuf::from)
        })
        .map(|path| {
            if path.is_absolute() {
                path
            } else {
                root.join(path)
            }
        })
        .unwrap_or_else(|| root.join(DEFAULT_OUTPUT_PATH))
}

fn run_bevy_capture(
    root: &Path,
    visual_asset_path: &str,
    model_transform: Transform,
    manifest: PoseManifest,
    output_directory: &Path,
    authored_route: Option<AuthoredRouteAsset>,
) -> Result<()> {
    let resolution = manifest.resolution;
    let config = CaptureConfig {
        visual_asset_path: visual_asset_path.to_owned(),
        model_transform,
        poses: manifest.poses,
        vertical_fov_radians: manifest.vertical_fov_degrees.to_radians(),
        output_directory: output_directory.to_path_buf(),
        settle_frames: manifest.settle_frames_before_each_capture,
        authored_route,
    };
    let mut app = App::new();
    app.insert_resource(CaptureProgress {
        ready: false,
        pose_index: 0,
        settle_frames: 0,
        in_flight: false,
        failure: None,
    })
    .insert_resource(config)
    .add_plugins(
        DefaultPlugins
            .set(AssetPlugin {
                file_path: root.to_string_lossy().into_owned(),
                ..default()
            })
            .set(WindowPlugin {
                primary_window: Some(Window {
                    title: "HunyuanWorld standalone Bevy review".into(),
                    resolution: WindowResolution::new(resolution[0], resolution[1])
                        .with_scale_factor_override(1.0),
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
    )
    .add_systems(Startup, (start_visual_load, spawn_camera))
    .add_systems(Update, (poll_visual_load, capture_next_pose).chain());
    let app_exit = app.run();
    if app_exit.is_error() {
        bail!("Bevy capture app exited with an error");
    }
    Ok(())
}

fn start_visual_load(mut commands: Commands, server: Res<AssetServer>, config: Res<CaptureConfig>) {
    commands.insert_resource(LoadedVisual(
        server.load(config.visual_asset_path.clone()),
        Instant::now(),
    ));
}

fn spawn_camera(mut commands: Commands, config: Res<CaptureConfig>) {
    let Ok(transform) = pose_transform(&config.poses[0]) else {
        return;
    };
    commands.spawn((
        CaptureCamera,
        Camera3d::default(),
        Projection::Perspective(PerspectiveProjection {
            fov: config.vertical_fov_radians,
            ..default()
        }),
        transform,
    ));
}

fn poll_visual_load(
    mut commands: Commands,
    config: Res<CaptureConfig>,
    loaded: Res<LoadedVisual>,
    mut assets: GltfAssets,
    mut progress: ResMut<CaptureProgress>,
) {
    if progress.ready || progress.failure.is_some() {
        return;
    }
    if !assets.server.is_loaded_with_dependencies(&loaded.0) {
        if loaded.1.elapsed().as_secs() > MAX_ASSET_WAIT_SECONDS {
            fail_capture(
                &mut commands,
                &mut progress,
                "timed out loading Hunyuan visual GLB",
            );
        }
        return;
    }
    let material = assets.materials.add(StandardMaterial {
        base_color: Color::WHITE,
        unlit: true,
        cull_mode: None,
        ..default()
    });
    let GltfAssets {
        gltfs,
        nodes,
        gltf_meshes,
        meshes,
        materials,
        ..
    } = &mut assets;
    let Some(gltf) = gltfs.get(&loaded.0) else {
        fail_capture(&mut commands, &mut progress, "loaded GLB has no Gltf asset");
        return;
    };
    let visual_assets = CaptureVisualAssets {
        nodes,
        gltf_meshes,
        meshes,
        materials,
    };
    match spawn_visual_nodes(&mut commands, &config, visual_assets, gltf, &material) {
        Ok(()) => progress.ready = true,
        Err(error) => fail_capture(&mut commands, &mut progress, &error.to_string()),
    }
}

fn spawn_visual_nodes(
    commands: &mut Commands,
    config: &CaptureConfig,
    assets: CaptureVisualAssets<'_>,
    gltf: &Gltf,
    material: &Handle<StandardMaterial>,
) -> Result<()> {
    for node_name in VISUAL_NODES {
        let node_handle = gltf
            .named_nodes
            .get(node_name)
            .with_context(|| format!("GLB is missing visual layer {node_name}"))?;
        let node = assets
            .nodes
            .get(node_handle)
            .context("GLB visual node did not load")?;
        let mesh_handle = node.mesh.as_ref().context("GLB visual node has no mesh")?;
        let mesh = assets
            .gltf_meshes
            .get(mesh_handle)
            .context("GLB visual mesh did not load")?;
        let world_transform = config.model_transform.mul_transform(node.transform);
        for primitive in &mesh.primitives {
            commands.spawn((
                Name::new(format!("uncalibrated_visual_{node_name}")),
                Mesh3d(primitive.mesh.clone()),
                MeshMaterial3d(material.clone()),
                world_transform,
            ));
        }
    }
    if let Some(route) = config.authored_route.as_ref() {
        spawn_room_visuals(commands, assets.meshes, assets.materials, route);
    }
    Ok(())
}

fn capture_next_pose(
    mut commands: Commands,
    config: Res<CaptureConfig>,
    mut progress: ResMut<CaptureProgress>,
    mut camera: Query<&mut Transform, With<CaptureCamera>>,
    mut app_exit: MessageWriter<AppExit>,
) {
    if progress.failure.is_some() || !progress.ready || progress.in_flight {
        return;
    }
    if progress.pose_index >= config.poses.len() {
        app_exit.write(AppExit::Success);
        progress.in_flight = true;
        return;
    }
    let pose = &config.poses[progress.pose_index];
    let Ok(mut transform) = camera.single_mut() else {
        fail_capture(&mut commands, &mut progress, "capture camera is missing");
        return;
    };
    let Ok(pose_transform) = pose_transform(pose) else {
        fail_capture(&mut commands, &mut progress, "capture pose is invalid");
        return;
    };
    *transform = pose_transform;
    if progress.settle_frames < config.settle_frames {
        progress.settle_frames += 1;
        return;
    }
    let path = config.output_directory.join(format!("{}.png", pose.name));
    commands
        .spawn(Screenshot::primary_window())
        .observe(save_to_disk(path))
        .observe(mark_capture_complete);
    progress.in_flight = true;
}

fn mark_capture_complete(_: On<ScreenshotCaptured>, mut progress: ResMut<CaptureProgress>) {
    progress.pose_index += 1;
    progress.settle_frames = 0;
    progress.in_flight = false;
}

fn fail_capture(commands: &mut Commands, progress: &mut CaptureProgress, message: &str) {
    progress.failure = Some(message.to_owned());
    eprintln!("Hunyuan Bevy capture failed: {message}");
    commands.write_message(AppExit::error());
}

fn verify_capture_outputs(directory: &Path, poses: &PoseManifest) -> Result<()> {
    for pose in &poses.poses {
        let path = directory.join(format!("{}.png", pose.name));
        if !path.is_file() {
            bail!("expected Bevy capture was not written: {}", path.display());
        }
    }
    Ok(())
}

fn write_capture_report(
    directory: &Path,
    manifest: &PoseManifest,
    wall_time_seconds: f64,
    resource_preflight: ResourcePreflight,
    gpu_compute_processes_before_capture: usize,
) -> Result<()> {
    let report = CaptureReport {
        schema_version: 1,
        issue: manifest.issue,
        label: "uncalibrated",
        renderer: "Bevy 0.18.0 / wgpu",
        bevy_version: "0.18.0",
        resolution: manifest.resolution,
        vertical_fov_degrees: manifest.vertical_fov_degrees,
        captured_views: manifest
            .poses
            .iter()
            .map(|pose| pose.name.clone())
            .collect(),
        visual_only_nodes: VISUAL_NODES,
        authored_visual_surfaces_included: if manifest.issue == 150 {
            vec![
                "authored_column_artifact_cover",
                "authored_room_wall_west",
                "authored_room_wall_east",
                "authored_room_wall_south",
                "authored_room_wall_north",
            ]
        } else {
            Vec::new()
        },
        collision_loaded: false,
        resource_preflight,
        gpu_compute_processes_before_capture,
        registration_accepted: false,
        scale_calibrated: false,
        wall_time_seconds,
        peak_rss_kib: process_peak_rss_kib(),
    };
    let path = directory.join("bevy_capture_report.json");
    fs::write(&path, serde_json::to_vec_pretty(&report)?)
        .with_context(|| format!("cannot write Bevy capture report {}", path.display()))
}

fn ensure_no_competing_gpu_jobs() -> Result<usize> {
    let output = Command::new("nvidia-smi")
        .args([
            "--query-compute-apps=pid,process_name",
            "--format=csv,noheader",
        ])
        .output()
        .context("cannot inspect active GPU compute processes before capture")?;
    if !output.status.success() {
        bail!("nvidia-smi failed while checking for competing GPU jobs");
    }
    let process_list = String::from_utf8(output.stdout)
        .context("nvidia-smi returned non-UTF8 active-process data")?;
    let process_count = process_list
        .lines()
        .filter(|line| !line.trim().is_empty())
        .count();
    if process_count > 0 {
        bail!("GPU capture refused while {process_count} compute process(es) are active");
    }
    Ok(process_count)
}

fn process_peak_rss_kib() -> Option<u64> {
    fs::read_to_string("/proc/self/status")
        .ok()?
        .lines()
        .find_map(|line| {
            line.strip_prefix("VmHWM:")
                .and_then(|value| value.split_whitespace().next())
                .and_then(|value| value.parse().ok())
        })
}

#[cfg(test)]
mod tests {
    use super::{CapturePose, PoseManifest, VIEW_NAMES, pose_transform, validate_pose_manifest};

    fn locked_manifest() -> PoseManifest {
        PoseManifest {
            issue: 137,
            label: "uncalibrated".to_owned(),
            registration_accepted: false,
            scale_calibrated: false,
            resolution: [960, 540],
            vertical_fov_degrees: 47.398_806,
            settle_frames_before_each_capture: 8,
            poses: VIEW_NAMES
                .iter()
                .map(|name| CapturePose {
                    name: (*name).to_owned(),
                    position_world_m: [0.0, 1.0, 0.0],
                    forward_world: [0.0, 0.0, 1.0],
                    up_world: [0.0, 1.0, 0.0],
                })
                .collect(),
        }
    }

    #[test]
    fn accepts_locked_uncalibrated_capture_manifest() {
        assert!(validate_pose_manifest(&locked_manifest()).is_ok());
    }

    #[test]
    fn rejects_capture_manifest_with_accepted_registration() {
        let mut manifest = locked_manifest();
        manifest.registration_accepted = true;
        assert!(validate_pose_manifest(&manifest).is_err());
    }

    #[test]
    fn capture_camera_faces_the_declared_world_forward() -> anyhow::Result<()> {
        let transform = pose_transform(&locked_manifest().poses[0])?;
        assert!(
            (transform.rotation * -bevy::prelude::Vec3::Z - bevy::prelude::Vec3::Z).length() < 1e-5
        );
        Ok(())
    }
}
