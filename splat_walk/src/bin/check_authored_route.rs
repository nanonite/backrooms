mod route_import;

use anyhow::Result;
use bevy::{
    asset::{AssetApp, AssetPlugin},
    gltf::{GltfPlugin, convert_coordinates::GltfConvertCoordinates},
    mesh::MeshPlugin,
    pbr::StandardMaterial,
    prelude::{App, MinimalPlugins, Startup, Update, default},
    scene::ScenePlugin,
    transform::TransformPlugin,
};

use crate::route_import::{check_loaded_route, load_route_config, start_loading};

fn main() -> Result<()> {
    let (asset_directory, route) = load_route_config()?;
    App::new()
        .add_plugins(MinimalPlugins)
        .add_plugins(AssetPlugin {
            file_path: asset_directory,
            ..default()
        })
        .add_plugins((TransformPlugin, MeshPlugin, ScenePlugin))
        .init_asset::<StandardMaterial>()
        .add_plugins(GltfPlugin {
            convert_coordinates: GltfConvertCoordinates {
                rotate_scene_entity: false,
                rotate_meshes: false,
            },
            ..default()
        })
        .insert_resource(route)
        .add_systems(Startup, start_loading)
        .add_systems(Update, check_loaded_route)
        .run();
    Ok(())
}
