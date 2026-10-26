extends SceneTree

const SCENE_PATH := "res://scenes/issue166_four_room_walkthrough.tscn"
const DEFAULT_OUTPUT := "res://evidence/2026-10-26-four-room-transfer/captures"

var output_path := DEFAULT_OUTPUT
var failure := ""


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out-dir="):
			output_path = argument.trim_prefix("--out-dir=")
	call_deferred("_capture")


func _capture() -> void:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		_quit_with_error("Could not load candidate walkthrough")
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	var ready := false
	for _tick in range(180):
		await process_frame
		if scene.get_meta("walkthrough_ready", false):
			ready = true
			break
	if not ready:
		_quit_with_error("Candidate walkthrough did not become ready")
		return
	var camera := Camera3D.new()
	camera.name = "Issue166ReviewCamera"
	camera.fov = 72.0
	camera.near = 0.05
	camera.far = 160.0
	root.add_child(camera)
	camera.current = true
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output_path))
	var captures := [
		{"name": "connection_large_room_to_corridor.png", "position": Vector3(26.6, 0.33, 3.1), "target": Vector3(30.5, 0.33, 3.1)},
		{"name": "connection_corridor_to_large_room.png", "position": Vector3(30.5, 0.33, 3.1), "target": Vector3(26.6, 0.33, 3.1)},
	]
	for capture: Dictionary in captures:
		var destination := output_path.path_join(capture.name)
		if FileAccess.file_exists(destination):
			_quit_with_error("Refusing to overwrite capture " + destination)
			return
		camera.global_position = capture.position
		camera.look_at(capture.target, Vector3.UP)
		await process_frame
		await RenderingServer.frame_post_draw
		var image := root.get_viewport().get_texture().get_image()
		var absolute := ProjectSettings.globalize_path(destination)
		var error := image.save_png(absolute)
		if error != OK:
			_quit_with_error("Could not save capture " + destination)
			return
		print("ISSUE166_CAPTURE ", destination, " size=", image.get_width(), "x", image.get_height())
	quit(0)


func _quit_with_error(message: String) -> void:
	failure = message
	printerr("ISSUE166_CAPTURE: " + message)
	quit(1)
