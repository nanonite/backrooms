mod frame;
mod inspection;

use std::{env, fs, path::PathBuf, time::Instant};

use anyhow::{Context, Result};
use bevy::{
    asset::{AssetPlugin, Assets},
    ecs::system::SystemParam,
    gltf::{Gltf, GltfMesh, GltfNode},
    pbr::StandardMaterial,
    prelude::*,
    render::view::screenshot::{Screenshot, save_to_disk},
    window::{WindowPlugin, WindowResolution},
};

use crate::{frame::FrameCamera, inspection::MeshReport};

const REQUIRED_LAYER_NODES: [&str; 2] = ["mesh_layer0", "mesh_layer1"];
const FRAME_LIMIT: u32 = 180;
const SCREENSHOT_FRAME: u32 = 8;

#[derive(Resource)]
struct FixtureConfig {
    gltf_asset: String,
    source_camera: FrameCamera,
    screenshot_path: PathBuf,
}

#[derive(Resource)]
struct LoadedModel(Handle<Gltf>);

#[derive(Resource)]
struct RunMetrics {
    started_at: Instant,
    ready_at: Option<Instant>,
    frames_after_ready: u32,
    screenshot_queued: bool,
}

#[derive(SystemParam)]
struct GltfAssets<'w> {
    asset_server: Res<'w, AssetServer>,
    gltfs: Res<'w, Assets<Gltf>>,
    nodes: Res<'w, Assets<GltfNode>>,
    gltf_meshes: Res<'w, Assets<GltfMesh>>,
    meshes: Res<'w, Assets<Mesh>>,
}

fn main() -> Result<()> {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest.parent().context("crate has no workspace parent")?;
    let default_asset = repo_root
        .join("godot_walk/generated_mesh_scenes/hunyuan_track_a_full_run/hunyuan_layers.glb");
    let asset_path = env::var_os("HUNYUAN_GLB")
        .map(PathBuf::from)
        .unwrap_or(default_asset);
    let asset_path = asset_path
        .canonicalize()
        .with_context(|| format!("cannot resolve GLB at {}", asset_path.display()))?;
    let asset_root = asset_path.parent().context("GLB path has no parent")?;
    let asset_name = asset_path
        .file_name()
        .and_then(|name| name.to_str())
        .context("GLB file name is not valid UTF-8")?
        .to_owned();
    let camera_path =
        repo_root.join("godot_walk/evidence/2026-10-13-hunyuan-track-a/source_selection.json");
    let source_camera = FrameCamera::from_json(&camera_path)?;
    let screenshot_path = env::var_os("HUNYUAN_BEVY_SCREENSHOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            repo_root
                .join("godot_walk/evidence/2026-10-13-hunyuan-track-a/bevy_fixture/frame_141.png")
        });
    if let Some(parent) = screenshot_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("cannot create screenshot directory {}", parent.display()))?;
    }

    App::new()
        .insert_resource(FixtureConfig {
            gltf_asset: asset_name,
            source_camera,
            screenshot_path,
        })
        .insert_resource(RunMetrics {
            started_at: Instant::now(),
            ready_at: None,
            frames_after_ready: 0,
            screenshot_queued: false,
        })
        .add_plugins(
            DefaultPlugins
                .set(AssetPlugin {
                    file_path: asset_root.to_string_lossy().into_owned(),
                    ..default()
                })
                .set(WindowPlugin {
                    primary_window: Some(Window {
                        title: "HunyuanWorld run-05 | Bevy 0.18 fixture".into(),
                        resolution: WindowResolution::new(960, 540),
                        ..default()
                    }),
                    ..default()
                }),
        )
        .add_systems(Startup, (start_load, spawn_camera))
        .add_systems(
            Update,
            (spawn_loaded_meshes, collect_runtime_metrics).chain(),
        )
        .run();

    Ok(())
}

fn start_load(mut commands: Commands, asset_server: Res<AssetServer>, config: Res<FixtureConfig>) {
    commands.insert_resource(LoadedModel(asset_server.load(config.gltf_asset.clone())));
}

fn spawn_camera(mut commands: Commands, config: Res<FixtureConfig>) {
    commands.spawn((
        Camera3d::default(),
        Projection::Perspective(PerspectiveProjection {
            fov: config.source_camera.vertical_fov_radians,
            ..default()
        }),
        config.source_camera.camera_transform(),
    ));
}

fn spawn_loaded_meshes(
    mut commands: Commands,
    config: Res<FixtureConfig>,
    loaded_model: Res<LoadedModel>,
    assets: GltfAssets,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut metrics: ResMut<RunMetrics>,
) {
    if metrics.ready_at.is_some()
        || !assets
            .asset_server
            .is_loaded_with_dependencies(&loaded_model.0)
    {
        return;
    }
    let Some(gltf) = assets.gltfs.get(&loaded_model.0) else {
        return;
    };

    let model_material = materials.add(StandardMaterial {
        base_color: Color::WHITE,
        unlit: true,
        cull_mode: None,
        ..default()
    });
    let root_transform = config.source_camera.transform();
    let mut all_reports = Vec::new();

    for node_name in REQUIRED_LAYER_NODES {
        let Some((node, mesh)) = named_layer(node_name, gltf, &assets.nodes, &assets.gltf_meshes)
        else {
            eprintln!("missing expected glTF node or mesh: {node_name}");
            std::process::exit(2);
        };
        println!(
            "NODE name={} mesh={} primitives={}",
            node.name,
            mesh.name,
            mesh.primitives.len()
        );
        let world_transform = root_transform.mul_transform(node.transform);
        spawn_layer_primitives(
            &mut commands,
            &assets.meshes,
            &model_material,
            &mut all_reports,
            node,
            mesh,
            world_transform,
        );
    }

    if all_reports.is_empty() {
        eprintln!("loaded GLB contains no mesh primitives in the expected nodes");
        std::process::exit(2);
    }
    print_scene_report(
        &all_reports,
        &config.source_camera,
        metrics.started_at.elapsed(),
    );
    metrics.ready_at = Some(Instant::now());
}

fn spawn_layer_primitives(
    commands: &mut Commands,
    meshes: &Assets<Mesh>,
    material: &Handle<StandardMaterial>,
    reports: &mut Vec<MeshReport>,
    node: &GltfNode,
    mesh: &GltfMesh,
    world_transform: Transform,
) {
    for primitive in &mesh.primitives {
        let Some(loaded_mesh) = meshes.get(&primitive.mesh) else {
            eprintln!("mesh primitive did not load: {}", primitive.name);
            std::process::exit(2);
        };
        let report =
            MeshReport::from_mesh(&node.name, &primitive.name, loaded_mesh, world_transform);
        println!("MESH {}", report.to_line());
        reports.push(report);
        commands.spawn((
            Mesh3d(primitive.mesh.clone()),
            MeshMaterial3d(material.clone()),
            world_transform,
        ));
    }
}

fn named_layer<'a>(
    name: &str,
    gltf: &'a Gltf,
    nodes: &'a Assets<GltfNode>,
    meshes: &'a Assets<GltfMesh>,
) -> Option<(&'a GltfNode, &'a GltfMesh)> {
    let node_handle = gltf.named_nodes.get(name)?;
    let node = nodes.get(node_handle)?;
    let mesh_handle = node.mesh.as_ref()?;
    Some((node, meshes.get(mesh_handle)?))
}

fn print_scene_report(
    reports: &[MeshReport],
    camera: &FrameCamera,
    load_elapsed: std::time::Duration,
) {
    let total_vertices: usize = reports.iter().map(|report| report.vertex_count).sum();
    let total_triangles: usize = reports.iter().map(|report| report.triangle_count).sum();
    let color_vertices: usize = reports.iter().map(|report| report.color_count).sum();
    let normal_vertices: usize = reports.iter().map(|report| report.normal_count).sum();
    println!(
        "LOAD elapsed_s={:.3} layers={} vertices={} triangles={} color_vertices={} normal_vertices={}",
        load_elapsed.as_secs_f64(),
        reports.len(),
        total_vertices,
        total_triangles,
        color_vertices,
        normal_vertices
    );
    println!(
        "FRAME origin_m={:?} forward={:?} up={:?} right={:?} vfov_deg={:.4} mapping=(-X forward,+Y right,+Z up)",
        camera.origin,
        camera.forward,
        camera.up,
        camera.right,
        camera.vertical_fov_radians.to_degrees()
    );
}

fn collect_runtime_metrics(
    mut commands: Commands,
    config: Res<FixtureConfig>,
    mut metrics: ResMut<RunMetrics>,
) {
    let Some(ready_at) = metrics.ready_at else {
        return;
    };
    metrics.frames_after_ready += 1;

    if metrics.frames_after_ready == SCREENSHOT_FRAME && !metrics.screenshot_queued {
        commands
            .spawn(Screenshot::primary_window())
            .observe(save_to_disk(config.screenshot_path.clone()));
        metrics.screenshot_queued = true;
    }
    if metrics.frames_after_ready < FRAME_LIMIT {
        return;
    }

    let elapsed = ready_at.elapsed();
    let wall_ms_per_update = elapsed.as_secs_f64() * 1000.0 / f64::from(metrics.frames_after_ready);
    let wall_updates_per_second = f64::from(metrics.frames_after_ready) / elapsed.as_secs_f64();
    println!(
        "RENDER updates={} wall_elapsed_s={:.3} wall_ms_per_update={:.3} wall_updates_per_second={:.2} screenshot={}",
        metrics.frames_after_ready,
        elapsed.as_secs_f64(),
        wall_ms_per_update,
        wall_updates_per_second,
        config.screenshot_path.display(),
    );
    std::process::exit(0);
}
