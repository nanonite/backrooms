extends SceneTree

const WALKTHROUGH := "res://scenes/issue156_streamed_walkthrough.tscn"
const OUTPUT := "res://evidence/2026-10-23-issue-156"
const LAYOUT := "res://evidence/2026-10-23-issue-156/layout_seed_149.json"
const FLOOR_Y := -1.27099049
const EYE_Y := FLOOR_Y + 1.1

var records: Array[Dictionary] = []
var layout: Dictionary = {}
var layout_path := LAYOUT


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--layout="):
			layout_path = argument.trim_prefix("--layout=")
	call_deferred("_capture")


func _capture() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(layout_path))
	if not parsed is Dictionary:
		push_error("Invalid #156 capture layout")
		quit(2)
		return
	layout = parsed
	var started := Time.get_ticks_msec()
	var packed := load(WALKTHROUGH) as PackedScene
	var scene := packed.instantiate() as Node3D if packed != null else null
	if scene == null:
		push_error("Cannot instantiate #156 streamed scene")
		quit(2)
		return
	root.add_child(scene)
	if not await _wait_ready(scene):
		push_error("#156 scene did not finish loading before capture")
		quit(2)
		return
	var ready_ms := Time.get_ticks_msec() - started
	var player := scene.get_node("Player") as CharacterBody3D
	player.set_physics_process(false)
	player.set_process(false)
	_hide_player_hud(player)
	var camera := Camera3D.new()
	camera.name = "Issue156CaptureCamera"
	camera.fov = 75.0
	scene.add_child(camera)
	camera.make_current()
	for view: Dictionary in _views():
		records.append(await _capture_view(scene, player, camera, view, ready_ms))
	_write_manifest()
	print("ISSUE156_CAPTURE_COMPLETE views=%d" % records.size())
	quit()


func _wait_ready(scene: Node3D) -> bool:
	for frame in 180:
		if scene.get_meta("walkthrough_ready", false):
			return true
		await process_frame
	return scene.get_meta("walkthrough_ready", false)


func _views() -> Array[Dictionary]:
	return [
		{"id": "spawn_connector", "room": "R000", "local_eye": [2.4, EYE_Y, 3.1],
			"local_target": [5.2, EYE_Y, 3.1], "stream_position": [2.4, FLOOR_Y + 0.6, 3.1]},
		{"id": "three_way_branch", "room": "R006", "local_eye": [3.0, EYE_Y, 6.2],
			"local_target": [3.0, EYE_Y, 11.8], "stream_position": [3.0, FLOOR_Y + 0.6, 6.9]},
		{"id": "branch_leaf", "room": "R007", "local_eye": [3.0, EYE_Y, 10.5],
			"local_target": [3.0, EYE_Y, 1.5], "stream_position": [3.0, FLOOR_Y + 0.6, 6.9]},
		{"id": "far_terminal", "room": "R009", "local_eye": [3.0, EYE_Y, 10.5],
			"local_target": [3.0, EYE_Y, 1.5], "stream_position": [3.0, FLOOR_Y + 0.6, 6.9]},
	]


func _capture_view(scene: Node3D, player: CharacterBody3D, camera: Camera3D,
		view: Dictionary, ready_ms: int) -> Dictionary:
	var room_position := _world_point(view.room, view.stream_position)
	player.global_position = room_position
	player.reset_physics_interpolation()
	var streamer: Node = scene.get_node("BoundedLayoutStreamer")
	streamer.call("refresh", true)
	camera.global_position = _world_point(view.room, view.local_eye)
	camera.look_at(_world_point(view.room, view.local_target), Vector3.UP)
	for frame in 30:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var path := "%s/captures/%s.png" % [OUTPUT, view.id]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
	if image.is_empty() or image.save_png(ProjectSettings.globalize_path(path)) != OK:
		push_error("Cannot save #156 capture: %s" % path)
	return {
		"id": view.id,
		"room_instance": view.room,
		"camera_eye": _coordinates(camera.global_position),
		"camera_target": _coordinates(_world_point(view.room, view.local_target)),
		"resolution": [image.get_width(), image.get_height()],
		"settle_frames": 30,
		"scene_load_to_ready_ms": ready_ms,
		"loaded_ids": scene.get_meta("stream_loaded_ids", PackedStringArray()),
		"frontier_caps": scene.get_meta("stream_frontier_cap_count", 0),
		"cached_module_types": scene.get_meta("stream_cached_module_count", 0),
		"path": path,
	}


func _world_point(instance_id: String, values: Array) -> Vector3:
	var placement := _placement(instance_id)
	var transform: Dictionary = placement.transform
	var origin := Vector3(transform.position[0], transform.position[1], transform.position[2])
	var basis := Basis(Vector3.UP, deg_to_rad(float(transform.yaw_degrees)))
	return Transform3D(basis, origin) * Vector3(values[0], values[1], values[2])


func _placement(instance_id: String) -> Dictionary:
	for placement: Dictionary in layout.placements:
		if placement.instance_id == instance_id:
			return placement
	return {}


func _hide_player_hud(player: CharacterBody3D) -> void:
	for child: Node in player.get_children():
		if child is CanvasLayer:
			child.visible = false


func _write_manifest() -> void:
	var path := OUTPUT + "/capture_manifest.json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write #156 capture manifest")
		return
	file.store_string(JSON.stringify(records, "\t") + "\n")


func _coordinates(point: Vector3) -> Array:
	return [point.x, point.y, point.z]
