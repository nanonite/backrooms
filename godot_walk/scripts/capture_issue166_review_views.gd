extends SceneTree

const SCENE_PATH := "res://scenes/issue166_four_room_walkthrough.tscn"
const DEFAULT_OUTPUT := "res://evidence/2026-10-26-four-room-transfer/captures_final"

var output_path := DEFAULT_OUTPUT
var scene_ready_ms := 0.0


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out-dir="):
			output_path = argument.trim_prefix("--out-dir=")
	call_deferred("_capture")


func _capture() -> void:
	var started_usec := Time.get_ticks_usec()
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		_quit_with_error("Could not load candidate walkthrough")
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	if not await _wait_until_ready(scene):
		_quit_with_error("Candidate walkthrough did not become ready")
		return
	scene_ready_ms = float(Time.get_ticks_usec() - started_usec) / 1000.0
	_hide_player_hud(scene)
	await process_frame
	var camera := _review_camera()
	root.add_child(camera)
	camera.current = true
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output_path))
	var captures := _capture_definitions()
	for capture: Dictionary in captures:
		if not await _save_capture(camera, capture):
			return
	_write_manifest(captures)
	quit(0)


func _wait_until_ready(scene: Node3D) -> bool:
	for _tick in range(180):
		await process_frame
		if scene.get_meta("walkthrough_ready", false):
			return true
	return false


func _hide_player_hud(scene: Node3D) -> void:
	var player := scene.get_node_or_null("Player")
	if player == null:
		return
	for child in player.find_children("*", "CanvasLayer", true, false):
		if child is CanvasLayer:
			child.visible = false


func _review_camera() -> Camera3D:
	var camera := Camera3D.new()
	camera.name = "Issue166ReviewCamera"
	camera.fov = 72.0
	camera.near = 0.05
	camera.far = 160.0
	return camera


func _capture_definitions() -> Array[Dictionary]:
	return [
		{
			"name": "connection_large_room_to_corridor.png",
			"position": Vector3(26.6, 0.33, 3.1),
			"target": Vector3(30.5, 0.33, 3.1),
		},
		{
			"name": "connection_corridor_to_large_room.png",
			"position": Vector3(30.5, 0.33, 3.1),
			"target": Vector3(26.6, 0.33, 3.1),
		},
	]


func _save_capture(camera: Camera3D, capture: Dictionary) -> bool:
	var destination: String = output_path.path_join(capture["name"])
	if FileAccess.file_exists(destination):
		_quit_with_error("Refusing to overwrite capture " + destination)
		return false
	camera.global_position = capture["position"]
	camera.look_at(capture["target"], Vector3.UP)
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_viewport().get_texture().get_image()
	var absolute := ProjectSettings.globalize_path(destination)
	if image.save_png(absolute) != OK:
		_quit_with_error("Could not save capture " + destination)
		return false
	print("ISSUE166_REVIEW_CAPTURE ", destination, " size=", image.get_width(), "x", image.get_height())
	return true


func _write_manifest(captures: Array[Dictionary]) -> void:
	var path := output_path.path_join("capture_manifest.json")
	if FileAccess.file_exists(path):
		_quit_with_error("Refusing to overwrite capture manifest " + path)
		return
	var views := []
	for capture: Dictionary in captures:
		views.append({
			"path": capture["name"],
			"camera_position": _vector_array(capture["position"]),
			"look_at": _vector_array(capture["target"]),
		})
	var manifest := {
		"scene": SCENE_PATH,
		"godot_version": Engine.get_version_info()["string"],
		"scene_ready_ms": scene_ready_ms,
		"views": views,
	}
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_quit_with_error("Could not write capture manifest " + path)
		return
	file.store_string(JSON.stringify(manifest, "\t") + "\n")


func _vector_array(value: Vector3) -> Array[float]:
	return [value.x, value.y, value.z]


func _quit_with_error(message: String) -> void:
	printerr("ISSUE166_REVIEW_CAPTURE: " + message)
	quit(1)
