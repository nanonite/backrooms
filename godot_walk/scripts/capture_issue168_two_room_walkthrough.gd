extends SceneTree

const SCENE_PATH := "res://scenes/issue168_two_room_walkthrough.tscn"

var output_path := "res://evidence/2026-11-02-issue-168-two-room/captures"
var scene_ready_ms := 0.0
var frame_profile: Dictionary = {}


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out-dir="):
			output_path = argument.trim_prefix("--out-dir=")
	call_deferred("_capture")


func _capture() -> void:
	var output_absolute := ProjectSettings.globalize_path(output_path)
	var directory_error := DirAccess.make_dir_recursive_absolute(output_absolute)
	if directory_error != OK:
		_quit_with_error("Could not create output directory " + output_path)
		return
	var started_usec := Time.get_ticks_usec()
	var scene := await _load_candidate()
	if scene == null:
		_quit_with_error("Could not load issue #168 walkthrough")
		return
	scene_ready_ms = float(Time.get_ticks_usec() - started_usec) / 1000.0
	_hide_player_hud(scene)
	await process_frame
	var camera := _review_camera()
	root.add_child(camera)
	camera.current = true
	var captures := _capture_definitions()
	camera.global_position = captures[0]["position"]
	camera.look_at(captures[0]["target"], Vector3.UP)
	frame_profile = await _measure_frame_profile()
	for capture: Dictionary in captures:
		if not await _save_capture(camera, capture):
			return
	_write_manifest(captures)
	quit(0)


func _load_candidate() -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		return null
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	for _tick in range(180):
		await process_frame
		if scene.get_meta("walkthrough_ready", false):
			return scene
	return null


func _hide_player_hud(scene: Node3D) -> void:
	var player := scene.get_node_or_null("Player")
	if player == null:
		return
	for layer: CanvasLayer in player.find_children("*", "CanvasLayer", true, false):
		layer.visible = false


func _review_camera() -> Camera3D:
	var camera := Camera3D.new()
	camera.name = "Issue168ReviewCamera"
	camera.fov = 72.0
	camera.near = 0.05
	camera.far = 100.0
	return camera


func _capture_definitions() -> Array[Dictionary]:
	return [
		{"name": "from_industrial_hall_to_rock_room.png", "position": Vector3(0.0, 1.42, 4.85), "target": Vector3(0.0, 1.3, 8.2)},
		{"name": "from_rock_room_to_industrial_hall.png", "position": Vector3(0.0, 1.42, 8.15), "target": Vector3(0.0, 1.3, 4.7)},
		{"name": "rock_room_entry_and_banks.png", "position": Vector3(-1.0, 1.42, 9.0), "target": Vector3(-4.0, 1.1, 8.35)},
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


func _save_capture(camera: Camera3D, capture: Dictionary) -> bool:
	var destination := output_path.path_join(capture["name"])
	if FileAccess.file_exists(destination):
		_quit_with_error("Refusing to overwrite " + destination)
		return false
	camera.global_position = capture["position"]
	camera.look_at(capture["target"], Vector3.UP)
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_viewport().get_texture().get_image()
	var absolute := ProjectSettings.globalize_path(destination)
	if image.save_png(absolute) != OK:
		_quit_with_error("Could not save " + destination)
		return false
	print("ISSUE168_CAPTURE ", destination, " size=", image.get_width(), "x", image.get_height())
	return true


func _write_manifest(captures: Array[Dictionary]) -> void:
	var path := output_path.path_join("capture_manifest.json")
	if FileAccess.file_exists(path):
		_quit_with_error("Refusing to overwrite " + path)
		return
	var views: Array[Dictionary] = []
	for capture: Dictionary in captures:
		views.append({"path": capture["name"], "camera_position": capture["position"], "look_at": capture["target"]})
	var manifest := {
		"scene": SCENE_PATH,
		"engine": Engine.get_version_info()["string"],
		"scene_ready_ms": scene_ready_ms,
		"frame_profile": frame_profile,
		"views": views,
	}
	var output := FileAccess.open(path, FileAccess.WRITE)
	if output == null:
		_quit_with_error("Could not write " + path)
		return
	output.store_string(JSON.stringify(manifest, "\t") + "\n")


func _quit_with_error(message: String) -> void:
	printerr("ISSUE168_CAPTURE_ERROR: " + message)
	quit(1)
