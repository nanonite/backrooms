extends SceneTree

const SCENE_PATH := "res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/room.tscn"

var output_path := "res://evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures"
var scene_ready_ms := 0.0
var frame_profile: Dictionary = {}


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out-dir="):
			output_path = argument.trim_prefix("--out-dir=")
	call_deferred("_capture")


func _capture() -> void:
	var manifest_path := output_path.path_join("capture_manifest.json")
	if FileAccess.file_exists(manifest_path):
		_quit_with_error("Refusing to overwrite " + manifest_path)
		return
	var output_absolute := ProjectSettings.globalize_path(output_path)
	if DirAccess.make_dir_recursive_absolute(output_absolute) != OK:
		_quit_with_error("Could not create " + output_path)
		return
	var started_usec := Time.get_ticks_usec()
	var room := await _load_room()
	if room == null:
		_quit_with_error("Candidate did not become ready")
		return
	scene_ready_ms = float(Time.get_ticks_usec() - started_usec) / 1000.0
	_hide_hud(room)
	var camera := _review_camera()
	root.add_child(camera)
	camera.current = true
	frame_profile = await _measure_frame_profile()
	var views := _capture_definitions()
	for view: Dictionary in views:
		if not await _save_capture(camera, view):
			return
	_write_manifest(manifest_path, views)
	quit(0)


func _load_room() -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		return null
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	for _tick in range(180):
		await process_frame
		if room.get_meta("walkthrough_ready", false):
			return room
	return null


func _hide_hud(room: Node3D) -> void:
	var player := room.get_node_or_null("Player")
	if player == null:
		return
	for layer: CanvasLayer in player.find_children("*", "CanvasLayer", true, false):
		layer.visible = false


func _review_camera() -> Camera3D:
	var camera := Camera3D.new()
	camera.name = "BillViolaReviewCamera"
	camera.fov = 72.0
	camera.near = 0.05
	camera.far = 100.0
	return camera


func _capture_definitions() -> Array[Dictionary]:
	return [
		{"name": "spawn_toward_dresser.png", "position": Vector3(0.0, 1.42, 1.6), "target": Vector3(0.0, 1.9, -3.0)},
		{"name": "left_oblique.png", "position": Vector3(-2.5, 1.42, 1.2), "target": Vector3(-0.2, 1.85, -3.0)},
		{"name": "right_oblique.png", "position": Vector3(2.5, 1.42, 1.2), "target": Vector3(0.2, 1.85, -3.0)},
		{"name": "look_back_at_closed_boundary.png", "position": Vector3(0.0, 1.42, -1.3), "target": Vector3(0.0, 1.2, 3.8)},
	]


func _measure_frame_profile() -> Dictionary:
	for _warmup in range(120):
		await process_frame
	var intervals: Array[float] = []
	var total_usec := 0.0
	for _sample in range(300):
		var started_usec := Time.get_ticks_usec()
		await process_frame
		var interval_usec := float(Time.get_ticks_usec() - started_usec)
		intervals.append(interval_usec / 1000.0)
		total_usec += interval_usec
	intervals.sort()
	return {
		"warmup_frames": 120,
		"measured_frames": intervals.size(),
		"mean_frame_ms": total_usec / float(intervals.size()) / 1000.0,
		"p95_frame_ms": intervals[int(ceil(float(intervals.size()) * 0.95)) - 1],
		"p99_frame_ms": intervals[int(ceil(float(intervals.size()) * 0.99)) - 1],
	}


func _save_capture(camera: Camera3D, view: Dictionary) -> bool:
	var destination := output_path.path_join(view["name"])
	if FileAccess.file_exists(destination):
		_quit_with_error("Refusing to overwrite " + destination)
		return false
	camera.global_position = view["position"]
	camera.look_at(view["target"], Vector3.UP)
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_viewport().get_texture().get_image()
	if image.save_png(ProjectSettings.globalize_path(destination)) != OK:
		_quit_with_error("Could not save " + destination)
		return false
	return true


func _write_manifest(path: String, views: Array[Dictionary]) -> void:
	var document := {
		"scene": SCENE_PATH,
		"engine": Engine.get_version_info()["string"],
		"scene_ready_ms": scene_ready_ms,
		"frame_profile": frame_profile,
		"views": views,
		"registration_accepted": false,
		"scale_calibrated": false,
	}
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_quit_with_error("Could not write " + path)
		return
	file.store_string(JSON.stringify(document, "\t") + "\n")


func _quit_with_error(message: String) -> void:
	printerr("BILL_VIOLA_CAPTURE_ERROR: " + message)
	quit(1)
