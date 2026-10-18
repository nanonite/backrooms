use bevy::{mesh::VertexAttributeValues, prelude::*};

pub struct MeshReport {
    pub node_name: String,
    pub primitive_name: String,
    pub vertex_count: usize,
    pub triangle_count: usize,
    pub color_count: usize,
    pub normal_count: usize,
    local_min: Vec3,
    local_max: Vec3,
    world_min: Vec3,
    world_max: Vec3,
}

impl MeshReport {
    pub fn from_mesh(
        node_name: &str,
        primitive_name: &str,
        mesh: &Mesh,
        world_transform: Transform,
    ) -> Self {
        let positions = mesh
            .attribute(Mesh::ATTRIBUTE_POSITION)
            .and_then(VertexAttributeValues::as_float3)
            .unwrap_or_default();
        let (local_min, local_max) = bounds(positions.iter().map(|point| Vec3::from_array(*point)));
        let corners = box_corners(local_min, local_max);
        let (world_min, world_max) = bounds(
            corners
                .iter()
                .map(|point| world_transform.transform_point(*point)),
        );
        let color_count = mesh
            .attribute(Mesh::ATTRIBUTE_COLOR)
            .map_or(0, |values| values.len());
        let normal_count = mesh
            .attribute(Mesh::ATTRIBUTE_NORMAL)
            .map_or(0, |values| values.len());
        let triangle_count = mesh
            .indices()
            .map_or(positions.len() / 3, |indices| indices.len() / 3);

        Self {
            node_name: node_name.to_owned(),
            primitive_name: primitive_name.to_owned(),
            vertex_count: positions.len(),
            triangle_count,
            color_count,
            normal_count,
            local_min,
            local_max,
            world_min,
            world_max,
        }
    }

    pub fn to_line(&self) -> String {
        format!(
            "node={} primitive={} vertices={} triangles={} color_attributes={} normal_attributes={} local_bounds=[{:?}..{:?}] aligned_world_bounds_m=[{:?}..{:?}]",
            self.node_name,
            self.primitive_name,
            self.vertex_count,
            self.triangle_count,
            self.color_count,
            self.normal_count,
            self.local_min,
            self.local_max,
            self.world_min,
            self.world_max,
        )
    }
}

fn bounds(points: impl Iterator<Item = Vec3>) -> (Vec3, Vec3) {
    let mut min = Vec3::splat(f32::INFINITY);
    let mut max = Vec3::splat(f32::NEG_INFINITY);
    for point in points {
        min = min.min(point);
        max = max.max(point);
    }
    (min, max)
}

fn box_corners(min: Vec3, max: Vec3) -> [Vec3; 8] {
    [
        Vec3::new(min.x, min.y, min.z),
        Vec3::new(min.x, min.y, max.z),
        Vec3::new(min.x, max.y, min.z),
        Vec3::new(min.x, max.y, max.z),
        Vec3::new(max.x, min.y, min.z),
        Vec3::new(max.x, min.y, max.z),
        Vec3::new(max.x, max.y, min.z),
        Vec3::new(max.x, max.y, max.z),
    ]
}
