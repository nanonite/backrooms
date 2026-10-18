use std::time::{Duration, Instant};

use avian3d::prelude::{CollisionEventsEnabled, RigidBody};
use bevy::{
    asset::{AssetServer, Assets},
    ecs::system::SystemParam,
    gltf::{Gltf, GltfMesh, GltfNode},
    mesh::Mesh,
    prelude::{Commands, Handle, Name, Res, ResMut, Resource, Transform},
};

use crate::walkability_harness::{
    route_mesh::build_route_colliders,
    scenarios::{AuthoredRouteAsset, HarnessSpec},
    simulation::{PlayerConfigHandle, ScenarioReport, spawn_player},
};

const LOAD_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Resource)]
pub struct RouteLoadState {
    handle: Handle<Gltf>,
    started_at: Instant,
    complete: bool,
}

#[derive(Resource)]
pub struct SceneAssetReadiness {
    pub visual_ready: bool,
}

#[derive(SystemParam)]
pub struct RouteImportParams<'w> {
    server: Res<'w, AssetServer>,
    state: ResMut<'w, RouteLoadState>,
    route: Res<'w, AuthoredRouteAsset>,
    spec: Res<'w, HarnessSpec>,
    player_config: Res<'w, PlayerConfigHandle>,
    gltfs: Res<'w, Assets<Gltf>>,
    nodes: Res<'w, Assets<GltfNode>>,
    gltf_meshes: Res<'w, Assets<GltfMesh>>,
    meshes: Res<'w, Assets<Mesh>>,
    report: ResMut<'w, ScenarioReport>,
    scene_readiness: Option<Res<'w, SceneAssetReadiness>>,
}

pub fn start_loading(
    mut commands: Commands,
    server: Res<AssetServer>,
    route: Res<AuthoredRouteAsset>,
) {
    commands.insert_resource(RouteLoadState {
        handle: server.load(route.file_name.clone()),
        started_at: Instant::now(),
        complete: false,
    });
}

pub fn poll_and_install(mut commands: Commands, mut params: RouteImportParams) {
    if params.state.complete {
        return;
    }
    if params
        .scene_readiness
        .as_ref()
        .is_some_and(|readiness| !readiness.visual_ready)
    {
        return;
    }
    if !params
        .server
        .is_loaded_with_dependencies(&params.state.handle)
    {
        mark_timeout(&mut params.state, &mut params.report);
        return;
    }
    match build_route_colliders(
        &params.route,
        &params.state.handle,
        &params.gltfs,
        &params.nodes,
        &params.gltf_meshes,
        &params.meshes,
    ) {
        Ok(colliders) => install_colliders(
            &mut commands,
            &mut params.state,
            &mut params.report,
            colliders,
        ),
        Err(error) => mark_failure(&mut params.state, &mut params.report, error.to_string()),
    }
    if params.report.failure_reason.is_none() {
        spawn_player(
            &mut commands,
            params.spec.start,
            params.player_config.0.clone(),
        );
    }
}

fn install_colliders(
    commands: &mut Commands,
    state: &mut RouteLoadState,
    report: &mut ScenarioReport,
    colliders: Vec<super::route_mesh::RouteCollider>,
) {
    report.collision_nodes = colliders.len();
    report.floor_collision_triangles = colliders
        .iter()
        .find(|collision| collision.name == "AuthoredPlanarRouteFloor")
        .map_or(0, |collision| collision.triangles);
    report.obstacle_collision_triangles = colliders
        .iter()
        .find(|collision| collision.name == "ColumnObstacleProxy")
        .map_or(0, |collision| collision.triangles);
    report.edge_boundary_collision_triangles = colliders
        .iter()
        .filter(|collision| collision.edge_boundary.is_some())
        .map(|collision| collision.triangles)
        .sum();
    for collision in colliders {
        let boundary = collision.edge_boundary;
        let mut entity = commands.spawn((
            Name::new(collision.name),
            RigidBody::Static,
            collision.collider,
            Transform::IDENTITY,
        ));
        if let Some(boundary) = boundary {
            entity.insert((boundary, CollisionEventsEnabled));
        }
    }
    report.collision_asset_loaded = true;
    state.complete = true;
}

fn mark_timeout(state: &mut RouteLoadState, report: &mut ScenarioReport) {
    if state.started_at.elapsed() >= LOAD_TIMEOUT {
        mark_failure(
            state,
            report,
            "timed out loading authored collision GLB".to_owned(),
        );
    }
}

fn mark_failure(state: &mut RouteLoadState, report: &mut ScenarioReport, reason: String) {
    report.failure_reason = Some(reason);
    state.complete = true;
}
