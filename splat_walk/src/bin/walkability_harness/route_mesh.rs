use anyhow::{Context, Result, bail};
use avian3d::prelude::{Collider, TrimeshFlags};
use bevy::{
    asset::Assets,
    gltf::{Gltf, GltfMesh, GltfNode},
    mesh::{Indices, Mesh, PrimitiveTopology, VertexAttributeValues},
    prelude::{Component, Handle, Quat, Vec3},
};

use crate::walkability_harness::scenarios::AuthoredRouteAsset;

const FLOOR_NODE: &str = "AuthoredPlanarRouteFloor";
const COLUMN_NODE: &str = "ColumnObstacleProxy";
const INNER_BOUNDARY_NODE: &str = "authored_edge_boundary_inner";
const OUTER_BOUNDARY_NODE: &str = "authored_edge_boundary_outer";

#[derive(Component, Clone, Copy)]
pub struct AuthoredEdgeBoundary {
    pub side: &'static str,
}

pub struct RouteCollider {
    pub name: &'static str,
    pub collider: Collider,
    pub triangles: usize,
    pub edge_boundary: Option<AuthoredEdgeBoundary>,
}

#[derive(Clone, Copy)]
enum MeshExpectation<'a> {
    None,
    RouteFloor(&'a AuthoredRouteAsset),
    EdgeBoundary { floor_y: f32, height_m: f32 },
}

pub fn build_route_colliders(
    route: &AuthoredRouteAsset,
    handle: &Handle<Gltf>,
    gltfs: &Assets<Gltf>,
    nodes: &Assets<GltfNode>,
    gltf_meshes: &Assets<GltfMesh>,
    meshes: &Assets<Mesh>,
) -> Result<Vec<RouteCollider>> {
    let gltf = gltfs.get(handle).context("loaded GLB has no Gltf asset")?;
    if gltf.named_nodes.len() != 4 {
        bail!(
            "authored route GLB has {} nodes, expected floor, column and two edge boundaries",
            gltf.named_nodes.len()
        );
    }
    Ok(vec![
        build_node(
            FLOOR_NODE,
            route.floor_triangles,
            MeshExpectation::RouteFloor(route),
            gltf,
            nodes,
            gltf_meshes,
            meshes,
        )?,
        build_node(
            COLUMN_NODE,
            route.column_triangles,
            MeshExpectation::None,
            gltf,
            nodes,
            gltf_meshes,
            meshes,
        )?,
        build_node(
            INNER_BOUNDARY_NODE,
            route.inner_boundary_triangles,
            MeshExpectation::EdgeBoundary {
                floor_y: route.floor_y,
                height_m: route.boundary_height_m,
            },
            gltf,
            nodes,
            gltf_meshes,
            meshes,
        )?,
        build_node(
            OUTER_BOUNDARY_NODE,
            route.outer_boundary_triangles,
            MeshExpectation::EdgeBoundary {
                floor_y: route.floor_y,
                height_m: route.boundary_height_m,
            },
            gltf,
            nodes,
            gltf_meshes,
            meshes,
        )?,
    ])
}

fn build_node(
    name: &'static str,
    expected_triangles: usize,
    expectation: MeshExpectation<'_>,
    gltf: &Gltf,
    nodes: &Assets<GltfNode>,
    gltf_meshes: &Assets<GltfMesh>,
    meshes: &Assets<Mesh>,
) -> Result<RouteCollider> {
    let node_handle = gltf
        .named_nodes
        .get(name)
        .with_context(|| format!("missing GLB node {name}"))?;
    let node = nodes
        .get(node_handle)
        .with_context(|| format!("missing data for GLB node {name}"))?;
    verify_identity(node, name)?;
    let mesh_handle = node
        .mesh
        .as_ref()
        .with_context(|| format!("GLB node {name} has no mesh"))?;
    let gltf_mesh = gltf_meshes
        .get(mesh_handle)
        .with_context(|| format!("missing mesh data for {name}"))?;
    if gltf_mesh.primitives.len() != 1 {
        bail!(
            "GLB node {name} must have one primitive, got {}",
            gltf_mesh.primitives.len()
        );
    }
    build_primitive(
        name,
        expected_triangles,
        expectation,
        &gltf_mesh.primitives[0].mesh,
        meshes,
    )
}

fn build_primitive(
    name: &'static str,
    expected_triangles: usize,
    expectation: MeshExpectation<'_>,
    handle: &Handle<Mesh>,
    meshes: &Assets<Mesh>,
) -> Result<RouteCollider> {
    let mesh = meshes
        .get(handle)
        .context("GLB primitive mesh did not load")?;
    if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
        bail!("GLB node {name} is not a triangle-list mesh");
    }
    let positions = mesh
        .attribute(Mesh::ATTRIBUTE_POSITION)
        .and_then(VertexAttributeValues::as_float3)
        .with_context(|| format!("GLB node {name} has no float3 positions"))?;
    let triangles = mesh_triangles(mesh)?;
    verify_mesh(name, positions, &triangles, expected_triangles, expectation)?;
    let vertices = positions
        .iter()
        .map(|point| Vec3::from_array(*point))
        .collect();
    let collider =
        Collider::try_trimesh_with_config(vertices, triangles, TrimeshFlags::FIX_INTERNAL_EDGES)
            .with_context(|| format!("cannot build collision trimesh for {name}"))?;
    Ok(RouteCollider {
        name,
        collider,
        triangles: expected_triangles,
        edge_boundary: match name {
            INNER_BOUNDARY_NODE => Some(AuthoredEdgeBoundary { side: "inner" }),
            OUTER_BOUNDARY_NODE => Some(AuthoredEdgeBoundary { side: "outer" }),
            _ => None,
        },
    })
}

fn mesh_triangles(mesh: &Mesh) -> Result<Vec<[u32; 3]>> {
    let indices: Vec<u32> = match mesh.indices() {
        Some(Indices::U16(values)) => values.iter().map(|index| u32::from(*index)).collect(),
        Some(Indices::U32(values)) => values.to_vec(),
        None => (0..mesh.count_vertices())
            .map(|index| index as u32)
            .collect(),
    };
    if indices.is_empty() || !indices.len().is_multiple_of(3) {
        bail!("GLB collision mesh has an empty or incomplete triangle index list");
    }
    Ok(indices
        .chunks_exact(3)
        .map(|face| [face[0], face[1], face[2]])
        .collect())
}

fn verify_mesh(
    name: &str,
    positions: &[[f32; 3]],
    triangles: &[[u32; 3]],
    expected_triangles: usize,
    expectation: MeshExpectation<'_>,
) -> Result<()> {
    if positions.is_empty() || triangles.len() != expected_triangles {
        bail!("GLB node {name} geometry does not match route report triangle/vertex counts");
    }
    if triangles
        .iter()
        .flatten()
        .any(|index| *index as usize >= positions.len())
    {
        bail!("GLB node {name} has an out-of-range triangle index");
    }
    match expectation {
        MeshExpectation::None => {}
        MeshExpectation::RouteFloor(route) => verify_floor_geometry(name, positions, route)?,
        MeshExpectation::EdgeBoundary { floor_y, height_m } => {
            verify_edge_boundary_geometry(name, positions, floor_y, height_m)?;
        }
    }
    Ok(())
}

fn verify_edge_boundary_geometry(
    name: &str,
    positions: &[[f32; 3]],
    floor_y: f32,
    height_m: f32,
) -> Result<()> {
    let min_y = positions
        .iter()
        .map(|point| point[1])
        .fold(f32::INFINITY, f32::min);
    let max_y = positions
        .iter()
        .map(|point| point[1])
        .fold(f32::NEG_INFINITY, f32::max);
    if (min_y - floor_y).abs() > 1e-4 || (max_y - floor_y - height_m).abs() > 1e-4 {
        bail!(
            "edge boundary {name} Y bounds [{min_y}, {max_y}] differ from floor {floor_y} and height {height_m}"
        );
    }
    Ok(())
}

fn verify_floor_geometry(
    name: &str,
    positions: &[[f32; 3]],
    route: &AuthoredRouteAsset,
) -> Result<()> {
    let min_y = positions
        .iter()
        .map(|point| point[1])
        .fold(f32::INFINITY, f32::min);
    let max_y = positions
        .iter()
        .map(|point| point[1])
        .fold(f32::NEG_INFINITY, f32::max);
    if (min_y - route.floor_y).abs() > 1e-5 || (max_y - route.floor_y).abs() > 1e-5 {
        bail!(
            "floor node {name} Y bounds [{min_y}, {max_y}] differ from report {}",
            route.floor_y
        );
    }
    verify_floor_bounds(name, positions, route)
}

fn verify_floor_bounds(
    name: &str,
    positions: &[[f32; 3]],
    route: &AuthoredRouteAsset,
) -> Result<()> {
    let outer_radius = route.radius_m + route.width_m * 0.5;
    let actual_min = positions
        .iter()
        .fold(Vec3::splat(f32::INFINITY), |bounds, point| {
            bounds.min(Vec3::from_array(*point))
        });
    let actual_max = positions
        .iter()
        .fold(Vec3::splat(f32::NEG_INFINITY), |bounds, point| {
            bounds.max(Vec3::from_array(*point))
        });
    let expected_min = Vec3::new(
        route.center_xz[0] - outer_radius,
        route.floor_y,
        route.center_xz[1] - outer_radius,
    );
    let expected_max = Vec3::new(
        route.center_xz[0] + outer_radius,
        route.floor_y,
        route.center_xz[1] + outer_radius,
    );
    if actual_min.distance(expected_min) > 1e-4 || actual_max.distance(expected_max) > 1e-4 {
        bail!("floor node {name} bounds do not match the route report center and radius");
    }
    Ok(())
}

fn verify_identity(node: &GltfNode, name: &str) -> Result<()> {
    let transform = node.transform;
    if transform.translation != Vec3::ZERO
        || transform.rotation != Quat::IDENTITY
        || transform.scale != Vec3::ONE
    {
        bail!("GLB node {name} transform is not identity: {transform:?}");
    }
    Ok(())
}
