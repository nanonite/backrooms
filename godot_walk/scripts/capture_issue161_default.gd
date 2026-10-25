extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const OUTPUT := "res://evidence/2026-10-23-issue-161/captures/project_default/branch_center.png"
const FLOOR_Y := -1.27099049
const SETTLE_FRAMES := 18


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var setting: Dictionary = ProjectSettings.get_setting(
		"shader_globals/affine_texture_mapping", {})
	if setting.get("type") != "bool" or setting.get("value") != false:
		push_error("#161 affine mapping project default must be false")
		quit(1)
		return
	var scene := WALKTHROUGH.instantiate() as Node3D
	root.add_child(scene)
	if not await _wait_ready(scene):
		push_error("#161 walkthrough did not become ready")
		quit(1)
		return
	var player := scene.get_node("Player") as CharacterBody3D
	player.set_physics_process(false)
	player.set_process(false)
	_hide_hud(player)
	player.global_position = Vector3(36.5, FLOOR_Y + 0.6, 3.1)
	scene.get_node("BoundedLayoutStreamer").call("refresh", true)
	_add_camera(scene)
	await _settle()
	var image := root.get_texture().get_image()
	var path := ProjectSettings.globalize_path(OUTPUT)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	if image.is_empty() or image.save_png(path) != OK:
		push_error("#161 failed to save default-profile capture")
		quit(1)
		return
	var manifest := FileAccess.open(OUTPUT.get_base_dir() + "/project_default.json", FileAccess.WRITE)
	if manifest == null:
		push_error("#161 failed to write default-profile manifest")
		quit(1)
		return
	manifest.store_string(JSON.stringify({"affine_texture_mapping": false,
		"source": "project.godot shader global; no runtime override",
		"camera_eye": [36.5, FLOOR_Y + 1.1, 2.4],
		"camera_target": [36.5, FLOOR_Y + 1.1, 8.0],
		"resolution": [image.get_width(), image.get_height()],
		"settle_frames": SETTLE_FRAMES, "path": OUTPUT}, "\t") + "\n")
	print("ISSUE161_DEFAULT_CAPTURE affine_texture_mapping=false path=" + OUTPUT)
	quit()


func _wait_ready(scene: Node3D) -> bool:
	for frame in 180:
		if scene.get_meta("walkthrough_ready", false):
			return true
		await process_frame
	return scene.get_meta("walkthrough_ready", false)


func _hide_hud(player: CharacterBody3D) -> void:
	for child: Node in player.get_children():
		if child is CanvasLayer:
			child.visible = false


func _add_camera(scene: Node3D) -> void:
	var camera := Camera3D.new()
	camera.name = "Issue161DefaultCamera"
	camera.fov = 75.0
	scene.add_child(camera)
	camera.global_position = Vector3(36.5, FLOOR_Y + 1.1, 2.4)
	camera.look_at(Vector3(36.5, FLOOR_Y + 1.1, 8.0), Vector3.UP)
	camera.make_current()


func _settle() -> void:
	for frame in SETTLE_FRAMES:
		await process_frame
	await RenderingServer.frame_post_draw
