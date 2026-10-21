use bevy::{
    asset::Assets,
    mesh::{Mesh, Mesh3d},
    pbr::{MeshMaterial3d, StandardMaterial},
    prelude::{Color, Commands, Cuboid, Name, Transform, Vec3, default},
};
use serde::Serialize;

use crate::walkability_harness::scenarios::AuthoredRouteAsset;

const COLUMN_COVER_PADDING_M: f32 = 0.24;
const WALL_COLOR: Color = Color::srgb(0.76, 0.72, 0.54);
const COLUMN_COLOR: Color = Color::srgb(0.82, 0.78, 0.63);

#[derive(Serialize, Clone)]
pub struct AuthoredVisualSurface {
    pub name: String,
    pub origin: &'static str,
    pub center_world_m: [f32; 3],
    pub size_m: [f32; 3],
}

pub fn spawn_room_visuals(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    route: &AuthoredRouteAsset,
) -> Vec<AuthoredVisualSurface> {
    let Some(layout) = route.room_layout.as_ref() else {
        return Vec::new();
    };
    let column = spawn_column_cover(commands, meshes, materials, route);
    let walls = spawn_room_walls(commands, meshes, materials, route, layout);
    std::iter::once(column).chain(walls).collect()
}

fn spawn_column_cover(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    route: &AuthoredRouteAsset,
) -> AuthoredVisualSurface {
    let lower = Vec3::new(
        route.column_lower_xz[0],
        route.floor_y,
        route.column_lower_xz[1],
    );
    let upper = Vec3::new(
        route.column_upper_xz[0],
        route.floor_y + route.column_height_m,
        route.column_upper_xz[1],
    );
    let size = upper - lower + Vec3::new(COLUMN_COVER_PADDING_M, 0.0, COLUMN_COVER_PADDING_M);
    let center = (lower + upper) * 0.5;
    spawn_box(
        commands,
        meshes,
        materials,
        "authored_column_artifact_cover",
        center,
        size,
        COLUMN_COLOR,
    );
    AuthoredVisualSurface {
        name: "authored_column_artifact_cover".to_owned(),
        origin: "authored visual cover; separate from collision proxy and Hunyuan mesh",
        center_world_m: center.to_array(),
        size_m: size.to_array(),
    }
}

fn spawn_room_walls(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    route: &AuthoredRouteAsset,
    layout: &crate::walkability_harness::scenarios::AuthoredRoomLayout,
) -> Vec<AuthoredVisualSurface> {
    let lower = layout.lower_xz;
    let upper = layout.upper_xz;
    let thickness = layout.boundary_thickness_m;
    let height = route.boundary_height_m;
    let floor_y = route.floor_y;
    let width_x = upper[0] - lower[0];
    let width_z = upper[1] - lower[1];
    let surfaces = [
        surface(
            "authored_room_wall_west",
            [
                lower[0] - thickness * 0.5,
                floor_y + height * 0.5,
                (lower[1] + upper[1]) * 0.5,
            ],
            [thickness, height, width_z + thickness * 2.0],
        ),
        surface(
            "authored_room_wall_east",
            [
                upper[0] + thickness * 0.5,
                floor_y + height * 0.5,
                (lower[1] + upper[1]) * 0.5,
            ],
            [thickness, height, width_z + thickness * 2.0],
        ),
        surface(
            "authored_room_wall_south",
            [
                (lower[0] + upper[0]) * 0.5,
                floor_y + height * 0.5,
                lower[1] - thickness * 0.5,
            ],
            [width_x, height, thickness],
        ),
        surface(
            "authored_room_wall_north",
            [
                (lower[0] + upper[0]) * 0.5,
                floor_y + height * 0.5,
                upper[1] + thickness * 0.5,
            ],
            [width_x, height, thickness],
        ),
    ];
    for surface in &surfaces {
        let center = Vec3::from_array(surface.center_world_m);
        let size = Vec3::from_array(surface.size_m);
        spawn_box(
            commands,
            meshes,
            materials,
            &surface.name,
            center,
            size,
            WALL_COLOR,
        );
    }
    surfaces.into_iter().collect()
}

fn surface(name: &str, center_world_m: [f32; 3], size_m: [f32; 3]) -> AuthoredVisualSurface {
    AuthoredVisualSurface {
        name: name.to_owned(),
        origin: "authored room-shell visual; separate from Hunyuan mesh",
        center_world_m,
        size_m,
    }
}

fn spawn_box(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    name: &str,
    center: Vec3,
    size: Vec3,
    color: Color,
) {
    let mesh = meshes.add(Mesh::from(Cuboid::from_size(size)));
    let material = materials.add(StandardMaterial {
        base_color: color,
        unlit: true,
        ..default()
    });
    commands.spawn((
        Name::new(name.to_owned()),
        Mesh3d(mesh),
        MeshMaterial3d(material),
        Transform::from_translation(center),
    ));
}
