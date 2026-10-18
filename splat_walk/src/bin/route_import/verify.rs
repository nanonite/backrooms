use anyhow::{Context, Result, bail};
use bevy::{
    asset::Assets,
    gltf::{Gltf, GltfMesh, GltfNode},
    mesh::{Mesh, VertexAttributeValues},
    prelude::{Handle, Quat, Transform, Vec3},
};

use super::RouteAsset;

const FLOOR_NODE: &str = "AuthoredPlanarRouteFloor";
const COLUMN_NODE: &str = "ColumnObstacleProxy";

pub(super) fn verify_route(
    route: &RouteAsset,
    handle: &Handle<Gltf>,
    gltfs: &Assets<Gltf>,
    nodes: &Assets<GltfNode>,
    gltf_meshes: &Assets<GltfMesh>,
    meshes: &Assets<Mesh>,
) -> Result<()> {
    let gltf = gltfs.get(handle).context("loaded GLB has no Gltf asset")?;
    verify_node(
        gltf,
        nodes,
        gltf_meshes,
        meshes,
        FLOOR_NODE,
        Some(route.floor_y),
        route.floor_triangles,
    )?;
    verify_node(
        gltf,
        nodes,
        gltf_meshes,
        meshes,
        COLUMN_NODE,
        None,
        route.column_triangles,
    )?;
    println!("BEVY_ROUTE_IMPORT_OK nodes=2 transforms=identity coordinate_conversion=disabled");
    Ok(())
}

fn verify_node(
    gltf: &Gltf,
    nodes: &Assets<GltfNode>,
    gltf_meshes: &Assets<GltfMesh>,
    meshes: &Assets<Mesh>,
    name: &str,
    expected_floor_y: Option<f32>,
    expected_triangles: usize,
) -> Result<()> {
    let node_handle = gltf
        .named_nodes
        .get(name)
        .with_context(|| format!("missing node {name}"))?;
    let node = nodes
        .get(node_handle)
        .with_context(|| format!("node data missing for {name}"))?;
    ensure_identity(node.transform, name)?;
    let mesh_handle = node
        .mesh
        .as_ref()
        .with_context(|| format!("node {name} has no mesh"))?;
    let gltf_mesh = gltf_meshes
        .get(mesh_handle)
        .with_context(|| format!("mesh data missing for {name}"))?;
    if gltf_mesh.primitives.len() != 1 {
        bail!("node {name} must have exactly one primitive");
    }
    let mesh = meshes
        .get(&gltf_mesh.primitives[0].mesh)
        .context("mesh primitive did not load")?;
    verify_mesh(name, mesh, expected_floor_y, expected_triangles)
}

fn ensure_identity(transform: Transform, name: &str) -> Result<()> {
    if transform.translation != Vec3::ZERO
        || transform.rotation != Quat::IDENTITY
        || transform.scale != Vec3::ONE
    {
        bail!("node {name} transform is not identity: {transform:?}");
    }
    Ok(())
}

fn verify_mesh(
    name: &str,
    mesh: &Mesh,
    expected_floor_y: Option<f32>,
    expected_triangles: usize,
) -> Result<()> {
    let positions = mesh
        .attribute(Mesh::ATTRIBUTE_POSITION)
        .and_then(VertexAttributeValues::as_float3)
        .with_context(|| format!("mesh {name} has no float3 positions"))?;
    if positions.is_empty() {
        bail!("mesh {name} has no vertices");
    }
    let triangles = triangle_count(mesh);
    if triangles != expected_triangles {
        bail!("mesh {name} has {triangles} triangles, expected {expected_triangles}");
    }
    let (lower, upper) = position_bounds(positions);
    verify_floor_y(name, lower.y, upper.y, expected_floor_y)?;
    print_mesh_bounds(name, positions.len(), triangles, lower, upper);
    Ok(())
}

fn triangle_count(mesh: &Mesh) -> usize {
    mesh.indices()
        .map_or(mesh.count_vertices() / 3, |indices| indices.len() / 3)
}

fn verify_floor_y(name: &str, lower_y: f32, upper_y: f32, expected: Option<f32>) -> Result<()> {
    if let Some(expected) = expected
        && ((lower_y - expected).abs() > 1e-5 || (upper_y - expected).abs() > 1e-5)
    {
        bail!("floor {name} Y bounds [{lower_y}, {upper_y}] differ from report {expected}");
    }
    Ok(())
}

fn position_bounds(positions: &[[f32; 3]]) -> (Vec3, Vec3) {
    positions.iter().fold(
        (Vec3::splat(f32::INFINITY), Vec3::splat(f32::NEG_INFINITY)),
        |(lower, upper), point| {
            let point = Vec3::from_array(*point);
            (lower.min(point), upper.max(point))
        },
    )
}

fn print_mesh_bounds(name: &str, vertices: usize, triangles: usize, lower: Vec3, upper: Vec3) {
    println!(
        "BEVY_NODE name={name} vertices={vertices} triangles={triangles} bounds=[{lower:?}..{upper:?}]"
    );
}
