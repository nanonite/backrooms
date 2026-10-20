use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use bevy::{
    asset::{AssetServer, Assets},
    ecs::system::SystemParam,
    gltf::{Gltf, GltfMesh, GltfNode},
    mesh::{Mesh, Mesh3d, VertexAttributeValues},
    pbr::{MeshMaterial3d, StandardMaterial},
    prelude::{Commands, Handle, Name, Res, ResMut, Resource, Transform},
};
use serde::Serialize;

use crate::walkability_harness::{
    route_collision::SceneAssetReadiness,
    route_scene::{geometry_query::build_visual_query_mesh, visual_metrics::*},
    scenarios::AuthoredRouteAsset,
    simulation::ScenarioReport,
};
use hunyuan_bevy_fixture::player_controller::{PLAYER_RADIUS_M, PLAYER_STEM_M};

const VISUAL_LOAD_TIMEOUT: Duration = Duration::from_secs(120);
const MINIMUM_QUERY_MEMORY_KIB: u64 = 6 * 1024 * 1024;
const VISUAL_NODE_NAMES: [&str; 2] = ["mesh_layer0", "mesh_layer1"];

#[derive(Resource)]
pub struct SceneVisualConfig {
    pub asset_path: String,
    pub model_transform: Transform,
    pub camera_origin: bevy::prelude::Vec3,
    pub analyze_alignment: bool,
}

#[derive(Resource)]
pub struct SceneVisualMaterial(pub Handle<StandardMaterial>);

#[derive(Resource)]
pub struct VisualLoadState {
    handle: Handle<Gltf>,
    started_at: Instant,
    complete: bool,
}

#[derive(Resource, Default)]
pub struct VisualSceneReport(pub Option<VisualSceneReportData>);

#[derive(Serialize, Clone)]
pub struct VisualSceneReportData {
    pub load_time_seconds: f64,
    pub query_preparation_time_seconds: f64,
    pub visual_nodes: Vec<VisualNodeReport>,
    pub visual_alignment: Option<VisualAlignmentMetrics>,
}

#[derive(Serialize, Clone)]
pub struct VisualNodeReport {
    pub node_name: String,
    pub primitive_name: String,
    pub vertex_count: usize,
    pub triangle_count: usize,
    pub world_translation_m: [f32; 3],
    pub world_rotation_xyzw: [f32; 4],
    pub world_scale: [f32; 3],
    pub collider_created: bool,
}

struct VisualBuildContext<'a, 'cw, 'cs, 'pw> {
    commands: &'a mut Commands<'cw, 'cs>,
    params: &'a VisualPollParams<'pw>,
    nodes_report: &'a mut Vec<VisualNodeReport>,
    query_meshes: &'a mut Vec<super::geometry_query::VisualQueryMesh>,
    material: Option<Handle<StandardMaterial>>,
}

struct PrimitiveBuild {
    node_name: String,
    primitive_index: usize,
    primitive_name: String,
    handle: Handle<Mesh>,
    world_transform: Transform,
}

#[derive(SystemParam)]
pub struct VisualPollParams<'w> {
    server: Res<'w, AssetServer>,
    state: ResMut<'w, VisualLoadState>,
    config: Res<'w, SceneVisualConfig>,
    route: Res<'w, AuthoredRouteAsset>,
    gltfs: Res<'w, Assets<Gltf>>,
    nodes: Res<'w, Assets<GltfNode>>,
    gltf_meshes: Res<'w, Assets<GltfMesh>>,
    meshes: Res<'w, Assets<Mesh>>,
    output: ResMut<'w, VisualSceneReport>,
    readiness: ResMut<'w, SceneAssetReadiness>,
    scenario: ResMut<'w, ScenarioReport>,
    material: Option<Res<'w, SceneVisualMaterial>>,
}

pub fn start_visual_loading(
    mut commands: Commands,
    server: Res<AssetServer>,
    config: Res<SceneVisualConfig>,
) {
    commands.insert_resource(VisualLoadState {
        handle: server.load(config.asset_path.clone()),
        started_at: Instant::now(),
        complete: false,
    });
}

pub fn poll_visual_loading(mut commands: Commands, mut params: VisualPollParams) {
    if params.state.complete {
        return;
    }
    if !params
        .server
        .is_loaded_with_dependencies(&params.state.handle)
    {
        if params.state.started_at.elapsed() > VISUAL_LOAD_TIMEOUT {
            fail_visual_load(&mut params, "timed out loading selected Hunyuan visual GLB");
        }
        return;
    }
    if available_memory_kib().is_some_and(|available| available < MINIMUM_QUERY_MEMORY_KIB) {
        fail_visual_load(
            &mut params,
            "host memory guard stopped visual-query preparation below 6 GiB available",
        );
        return;
    }
    match build_visual_scene(&mut commands, &params) {
        Ok(report) => {
            params.output.0 = Some(report);
            params.readiness.visual_ready = true;
            params.state.complete = true;
        }
        Err(error) => fail_visual_load(&mut params, &error.to_string()),
    }
}

fn build_visual_scene<'a, 'cw, 'cs, 'pw>(
    commands: &'a mut Commands<'cw, 'cs>,
    params: &'a VisualPollParams<'pw>,
) -> Result<VisualSceneReportData> {
    let load_time_seconds = params.state.started_at.elapsed().as_secs_f64();
    let build_started = Instant::now();
    let gltf = params
        .gltfs
        .get(&params.state.handle)
        .context("loaded Hunyuan GLB has no Gltf asset")?;
    let mut nodes_report = Vec::new();
    let mut query_meshes = Vec::new();
    let mut context = VisualBuildContext {
        commands,
        params,
        nodes_report: &mut nodes_report,
        query_meshes: &mut query_meshes,
        material: params.material.as_ref().map(|material| material.0.clone()),
    };
    for node_name in VISUAL_NODE_NAMES {
        append_node_visuals(node_name, gltf, &mut context)?;
    }
    let visual_alignment = if params.config.analyze_alignment {
        Some(analyze_visual_alignment(
            &params.route,
            params.config.camera_origin,
            &query_meshes,
            PLAYER_RADIUS_M,
            PLAYER_STEM_M,
        )?)
    } else {
        None
    };
    Ok(VisualSceneReportData {
        load_time_seconds,
        query_preparation_time_seconds: build_started.elapsed().as_secs_f64(),
        visual_nodes: nodes_report,
        visual_alignment,
    })
}

fn append_node_visuals<'a, 'cw, 'cs, 'pw>(
    node_name: &str,
    gltf: &Gltf,
    context: &mut VisualBuildContext<'a, 'cw, 'cs, 'pw>,
) -> Result<()> {
    let node_handle = gltf
        .named_nodes
        .get(node_name)
        .with_context(|| format!("run-05 GLB is missing visual node {node_name}"))?;
    let node = context
        .params
        .nodes
        .get(node_handle)
        .with_context(|| format!("missing GltfNode data for {node_name}"))?;
    let mesh_handle = node
        .mesh
        .as_ref()
        .with_context(|| format!("visual node {node_name} has no mesh"))?;
    let gltf_mesh = context
        .params
        .gltf_meshes
        .get(mesh_handle)
        .with_context(|| format!("missing GltfMesh data for {node_name}"))?;
    let node_transform = context
        .params
        .config
        .model_transform
        .mul_transform(node.transform);
    let primitives: Vec<_> = gltf_mesh
        .primitives
        .iter()
        .enumerate()
        .map(|(primitive_index, primitive)| PrimitiveBuild {
            node_name: node_name.to_owned(),
            primitive_index,
            primitive_name: primitive.name.clone(),
            handle: primitive.mesh.clone(),
            world_transform: node_transform,
        })
        .collect();
    for primitive in primitives {
        append_primitive(context, primitive)?;
    }
    Ok(())
}

fn append_primitive<'a, 'cw, 'cs, 'pw>(
    context: &mut VisualBuildContext<'a, 'cw, 'cs, 'pw>,
    primitive: PrimitiveBuild,
) -> Result<()> {
    let VisualBuildContext {
        commands,
        params,
        nodes_report,
        query_meshes,
        ..
    } = context;
    let mesh = params
        .meshes
        .get(&primitive.handle)
        .with_context(|| format!("mesh data did not load for {}", primitive.node_name))?;
    let vertex_count = mesh
        .attribute(Mesh::ATTRIBUTE_POSITION)
        .and_then(VertexAttributeValues::as_float3)
        .map_or(0, |positions| positions.len());
    let triangle_count = mesh
        .indices()
        .map_or(vertex_count / 3, |indices| indices.len() / 3);
    let name = format!(
        "uncalibrated_{}_{}",
        primitive.node_name, primitive.primitive_index
    );
    let mut entity = commands.spawn((
        Name::new(name),
        Mesh3d(primitive.handle),
        primitive.world_transform,
    ));
    if let Some(material) = context.material.as_ref() {
        entity.insert(MeshMaterial3d(material.clone()));
    }
    if params.config.analyze_alignment {
        query_meshes.push(build_visual_query_mesh(
            &format!("{}_{}", primitive.node_name, primitive.primitive_index),
            mesh,
            primitive.world_transform,
        )?);
    }
    nodes_report.push(VisualNodeReport {
        node_name: primitive.node_name,
        primitive_name: primitive.primitive_name,
        vertex_count,
        triangle_count,
        world_translation_m: primitive.world_transform.translation.to_array(),
        world_rotation_xyzw: primitive.world_transform.rotation.to_array(),
        world_scale: primitive.world_transform.scale.to_array(),
        collider_created: false,
    });
    Ok(())
}

fn fail_visual_load(params: &mut VisualPollParams, reason: &str) {
    params.scenario.failure_reason = Some(reason.to_owned());
    params.state.complete = true;
}

fn available_memory_kib() -> Option<u64> {
    std::fs::read_to_string("/proc/meminfo")
        .ok()?
        .lines()
        .find_map(|line| {
            line.strip_prefix("MemAvailable:")
                .and_then(|value| value.split_whitespace().next())
                .and_then(|value| value.parse().ok())
        })
}
