use bevy::{
    asset::AssetServer,
    prelude::{Commands, Name, Transform},
    scene::SceneRoot,
};

pub const REPAIR_SCENE_PATH: &str =
    "godot_walk/evidence/2026-10-21-issue-153/generated/column_corner_repair.glb#Scene0";

pub fn enabled() -> bool {
    std::env::args().any(|argument| argument == "--issue153")
}

pub fn spawn(commands: &mut Commands, server: &AssetServer) {
    commands.spawn((
        Name::new("issue153_blender_visual_only_repair"),
        SceneRoot(server.load(REPAIR_SCENE_PATH)),
        Transform::IDENTITY,
    ));
}

pub fn spawn_if_enabled(commands: &mut Commands, server: &AssetServer) {
    if enabled() {
        spawn(commands, server);
    }
}
