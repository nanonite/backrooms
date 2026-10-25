extends SceneTree

const SCENE_PATH := "res://scenes/issue165_corridor_corner_transfer.tscn"
const DEFAULT_OUTPUT := "res://evidence/2026-10-25-issue-165/captures/v1"
const FOV_DEGREES := 75.0
const SETTLE_FRAMES := 24

var output_dir := DEFAULT_OUTPUT
var records: Array[Dictionary] = []


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out-dir="):
			output_dir = argument.trim_prefix("--out-dir=")
	call_deferred("_capture")


func _capture() -> void:
	var absolute_dir := ProjectSettings.globalize_path(output_dir)
	if DirAccess.dir_exists_absolute(absolute_dir) or FileAccess.file_exists(absolute_dir):
		printerr("Refusing to overwrite capture output: %s" % output_dir)
		quit(2)
		return
	var started := Time.get_ticks_msec()
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		printerr("Cannot load #165 candidate: %s" % SCENE_PATH)
		quit(2)
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	if not await _wait_until_ready(scene):
		quit(2)
		return
	var ready_ms := Time.get_ticks_msec() - started
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player != null:
		player.set_physics_process(false)
		player.set_process(false)
		_hide_player_ui(player)
	var camera := _review_camera(scene)
	DirAccess.make_dir_recursive_absolute(absolute_dir)
	for view: Dictionary in _views():
		records.append(await _capture_view(camera, view, ready_ms))
	_write_manifest(ready_ms)
	print("ISSUE165_CAPTURE_COMPLETE views=%d scene_ready_ms=%d" % [records.size(), ready_ms])
	quit()


func _wait_until_ready(scene: Node3D) -> bool:
	for frame in 240:
		if scene.get_meta("walkthrough_ready", false):
			return true
		await process_frame
	printerr("#165 scene did not become ready before capture timeout")
	return false


func _hide_player_ui(player: CharacterBody3D) -> void:
	for child: Node in player.get_children():
		if child is CanvasLayer:
			child.visible = false


func _review_camera(scene: Node3D) -> Camera3D:
	var camera := Camera3D.new()
	camera.name = "Issue165ReviewCamera"
	camera.fov = FOV_DEGREES
	scene.add_child(camera)
	camera.make_current()
	return camera


func _views() -> Array[Dictionary]:
	return [
		_view("entry_column", Vector3(-5.0, 1.1, 1.4), Vector3(-2.5, 1.1, 0.0), "frame_0001"),
		_view("main_leg_turn", Vector3(-0.8, 1.1, 1.0), Vector3(1.7, 1.1, -2.3), "frame_0036"),
		_view("turn_back_to_main", Vector3(2.0, 1.1, -2.2), Vector3(-0.8, 1.1, 0.8), "frame_0059"),
		_view("far_leg_end", Vector3(2.0, 1.1, -5.6), Vector3(2.0, 1.1, -2.6), "frame_0085"),
		_view("far_leg_back", Vector3(2.0, 1.1, -2.7), Vector3(2.0, 1.1, -5.8), "frame_0096"),
		_view("column_face_south", Vector3(-2.5, 1.1, 1.2), Vector3(-2.5, 1.1, 0.0), "frame_0001"),
		_view("column_face_north", Vector3(-2.5, 1.1, -1.2), Vector3(-2.5, 1.1, 0.0), "frame_0001"),
		_view("column_face_east", Vector3(-1.2, 1.1, 0.0), Vector3(-2.5, 1.1, 0.0), "frame_0001"),
		_view("column_face_west", Vector3(-3.8, 1.1, 0.0), Vector3(-2.5, 1.1, 0.0), "frame_0001"),
	]


func _view(view_id: String, eye: Vector3, target: Vector3, source_frame_id: String) -> Dictionary:
	return {"id": view_id, "eye": eye, "target": target, "source_frame_id": source_frame_id}


func _capture_view(camera: Camera3D, view: Dictionary, ready_ms: int) -> Dictionary:
	camera.global_position = view.eye
	camera.look_at(view.target, Vector3.UP)
	for frame in SETTLE_FRAMES:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var path := output_dir.path_join("%s.png" % view.id)
	if image.is_empty() or image.save_png(ProjectSettings.globalize_path(path)) != OK:
		push_error("Cannot save #165 capture: %s" % path)
	return {
		"id": view.id,
		"path": path,
		"source_frame_id": view.source_frame_id,
		"eye": [view.eye.x, view.eye.y, view.eye.z],
		"target": [view.target.x, view.target.y, view.target.z],
		"width": image.get_width(),
		"height": image.get_height(),
		"scene_ready_ms": ready_ms,
		"settle_frames": SETTLE_FRAMES,
	}


func _write_manifest(ready_ms: int) -> void:
	var manifest_path := output_dir.path_join("capture_manifest.json")
	var file := FileAccess.open(manifest_path, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write #165 capture manifest: %s" % manifest_path)
		return
	file.store_string(JSON.stringify({
		"issue": 165,
		"scene": SCENE_PATH,
		"scene_ready_ms": ready_ms,
		"camera_fov_degrees": FOV_DEGREES,
		"views": records,
	}, "\t") + "\n")
