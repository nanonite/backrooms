use anyhow::{Context, Result, bail};
use avian3d::parry::{
    math::{Pose, Vector as QueryVector},
    query::{Ray, RayCast, contact},
    shape::{Capsule, TriMesh},
};
use bevy::{
    mesh::{Indices, Mesh, PrimitiveTopology, VertexAttributeValues},
    prelude::{Transform, Vec3},
};

pub struct VisualQueryMesh {
    pub name: String,
    pub triangle_count: usize,
    pub shape: TriMesh,
}

pub fn build_visual_query_mesh(
    name: &str,
    mesh: &Mesh,
    world_transform: Transform,
) -> Result<VisualQueryMesh> {
    if mesh.primitive_topology() != PrimitiveTopology::TriangleList {
        bail!("visual node {name} is not a triangle-list mesh");
    }
    let positions = mesh
        .attribute(Mesh::ATTRIBUTE_POSITION)
        .and_then(VertexAttributeValues::as_float3)
        .with_context(|| format!("visual node {name} has no float3 positions"))?;
    let vertices = positions
        .iter()
        .map(|position| {
            to_query_vector(world_transform.transform_point(Vec3::from_array(*position)))
        })
        .collect();
    let indices = triangle_indices(mesh)?;
    let triangle_count = indices.len();
    let shape = TriMesh::new(vertices, indices)
        .with_context(|| format!("cannot build query BVH for visual node {name}"))?;
    Ok(VisualQueryMesh {
        name: name.to_owned(),
        triangle_count,
        shape,
    })
}

pub fn floor_gap_m(
    visual_meshes: &[VisualQueryMesh],
    route_position: Vec3,
    collision_floor_y: f32,
) -> Option<f32> {
    let origin = route_position.with_y(collision_floor_y + 0.5);
    let ray = Ray::new(to_query_vector(origin), -QueryVector::Y);
    visual_meshes
        .iter()
        .filter_map(|mesh| {
            let hit = mesh
                .shape
                .cast_ray_and_get_normal(&Pose::identity(), &ray, 1.0, false)?;
            (hit.normal.y >= 0.7).then_some(0.5 - hit.time_of_impact)
        })
        .min_by(|first, second| first.abs().total_cmp(&second.abs()))
}

pub fn capsule_penetration_m(
    visual_meshes: &[VisualQueryMesh],
    capsule_center: Vec3,
    radius_m: f32,
    stem_m: f32,
) -> Result<Option<f32>> {
    let capsule = Capsule::new_y(stem_m * 0.5, radius_m);
    let capsule_pose = Pose::translation(capsule_center.x, capsule_center.y, capsule_center.z);
    visual_meshes
        .iter()
        .map(|mesh| {
            contact(&capsule_pose, &capsule, &Pose::identity(), &mesh.shape, 0.0)
                .with_context(|| format!("cannot query capsule against visual node {}", mesh.name))
        })
        .collect::<Result<Vec<_>>>()
        .map(|contacts| {
            contacts
                .into_iter()
                .flatten()
                .filter(|contact| contact.dist <= 0.0)
                .map(|contact| -contact.dist)
                .reduce(f32::max)
        })
}

fn triangle_indices(mesh: &Mesh) -> Result<Vec<[u32; 3]>> {
    let indices: Vec<[u32; 3]> = match mesh.indices() {
        Some(Indices::U16(indices)) => {
            if indices.is_empty() || !indices.len().is_multiple_of(3) {
                bail!("indexed visual mesh has an empty or incomplete triangle list");
            }
            indices
                .chunks_exact(3)
                .map(|face| [u32::from(face[0]), u32::from(face[1]), u32::from(face[2])])
                .collect()
        }
        Some(Indices::U32(indices)) => {
            if indices.is_empty() || !indices.len().is_multiple_of(3) {
                bail!("indexed visual mesh has an empty or incomplete triangle list");
            }
            indices
                .chunks_exact(3)
                .map(|face| [face[0], face[1], face[2]])
                .collect()
        }
        None => {
            let vertex_count = mesh.count_vertices();
            if !vertex_count.is_multiple_of(3) {
                bail!("non-indexed visual mesh has an incomplete triangle");
            }
            (0..vertex_count)
                .step_by(3)
                .map(|index| [index as u32, index as u32 + 1, index as u32 + 2])
                .collect()
        }
    };
    if indices.is_empty() {
        bail!("visual mesh has no complete triangles");
    }
    let vertex_count = mesh.count_vertices();
    if indices
        .iter()
        .flatten()
        .any(|index| *index as usize >= vertex_count)
    {
        bail!("visual mesh has an out-of-range triangle index");
    }
    Ok(indices)
}

fn to_query_vector(vector: Vec3) -> QueryVector {
    QueryVector::new(vector.x, vector.y, vector.z)
}
