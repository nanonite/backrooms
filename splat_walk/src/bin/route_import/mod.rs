use std::{fs, path::PathBuf, time::Instant};

mod verify;

use anyhow::{Context, Result};
use bevy::{
    asset::{AssetServer, Assets},
    gltf::{Gltf, GltfMesh, GltfNode},
    mesh::Mesh,
    prelude::{Commands, Handle, Res, Resource},
};

const LOAD_TIMEOUT_SECONDS: u64 = 15;

#[derive(Resource)]
pub struct RouteAsset {
    name: String,
    floor_y: f32,
    floor_triangles: usize,
    column_triangles: usize,
    started_at: Instant,
}

#[derive(Resource)]
pub struct LoadedRoute(Handle<Gltf>);

pub fn load_route_config() -> Result<(String, RouteAsset)> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .context("crate has no workspace parent")?
        .to_path_buf();
    let route_dir = root.join(
        "godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column",
    );
    let report = read_report(&route_dir)?;
    let route = RouteAsset {
        name: "authored_route_collision.glb".to_owned(),
        floor_y: report_number(&report, &["plane", "height_m"])? as f32,
        floor_triangles: report_count(&report, "floor_triangles")?,
        column_triangles: report_count(&report, "column_triangles")?,
        started_at: Instant::now(),
    };
    Ok((route_dir.to_string_lossy().into_owned(), route))
}

fn read_report(route_dir: &std::path::Path) -> Result<serde_json::Value> {
    let bytes = fs::read(route_dir.join("route_report.json"))
        .context("cannot read authored route report")?;
    serde_json::from_slice(&bytes).context("authored route report is invalid JSON")
}

fn report_number(report: &serde_json::Value, path: &[&str]) -> Result<f64> {
    let value = path.iter().fold(report, |value, key| &value[*key]);
    value
        .as_f64()
        .with_context(|| format!("report has no numeric {}", path.join(".")))
}

fn report_count(report: &serde_json::Value, key: &str) -> Result<usize> {
    report["export"][key]
        .as_u64()
        .map(|count| count as usize)
        .with_context(|| format!("report has no export.{key}"))
}

pub fn start_loading(mut commands: Commands, server: Res<AssetServer>, route: Res<RouteAsset>) {
    commands.insert_resource(LoadedRoute(server.load(route.name.clone())));
}

pub fn check_loaded_route(
    server: Res<AssetServer>,
    route: Res<RouteAsset>,
    loaded: Res<LoadedRoute>,
    gltfs: Res<Assets<Gltf>>,
    nodes: Res<Assets<GltfNode>>,
    gltf_meshes: Res<Assets<GltfMesh>>,
    meshes: Res<Assets<Mesh>>,
) {
    if !server.is_loaded_with_dependencies(&loaded.0) {
        fail_if_timed_out(&route);
        return;
    }
    let result = verify::verify_route(&route, &loaded.0, &gltfs, &nodes, &gltf_meshes, &meshes);
    finish_check(result);
}

fn finish_check(result: Result<()>) {
    match result {
        Ok(()) => std::process::exit(0),
        Err(error) => {
            eprintln!("BEVY_ROUTE_IMPORT_FAIL {error:#}");
            std::process::exit(1);
        }
    }
}

fn fail_if_timed_out(route: &RouteAsset) {
    if route.started_at.elapsed().as_secs() > LOAD_TIMEOUT_SECONDS {
        eprintln!("BEVY_ROUTE_IMPORT_FAIL timed out loading {}", route.name);
        std::process::exit(1);
    }
}
