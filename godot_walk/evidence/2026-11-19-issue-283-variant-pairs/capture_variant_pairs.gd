extends SceneTree

## Guarded-review capture script for issue #283 variant pairs. Run only through
## run_capture_guarded.py with DISPLAY=:1 (Vulkan); --headless is not usable for
## captures. Three views are rendered for each of the four pairs.

const ASSEMBLY := "res://evidence/2026-11-19-issue-283-variant-pairs/variant_pairs_scene.tscn"

var output_path := "res://evidence/2026-11-19-issue-283-variant-pairs/captures"
var scene_ready_ms := 0.0
var frame_profile: Dictionary = {}


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_path = argument.trim_prefix("--out=")
	call_deferred("_capture")


func _pair_definitions() -> Array[Dictionary]:
	return [
		{
			"label": "p1", "id": "p1_chevron175_south__chevron176_north",
			"from_key": "chevron_175", "to_key": "chevron_176",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 20.0),
			"from_yaw": 0, "to_yaw": 0, "spawn": Vector3(0.0, 0.6, 4.0),
		},
		{
			"label": "p2", "id": "p2_chevron176_south__chevron177_north",
			"from_key": "chevron_176", "to_key": "chevron_cross_177",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 20.0),
			"from_yaw": 0, "to_yaw": 0, "spawn": Vector3(0.0, 0.6, 4.0),
		},
		{
			"label": "p3", "id": "p3_chevron177_south__nestedlight173_north",
			"from_key": "chevron_cross_177", "to_key": "nested_light_173",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 22.0),
			"from_yaw": 0, "to_yaw": 0, "spawn": Vector3(0.0, 0.6, 4.0),
		},
		{
			"label": "p4", "id": "p4_nestedlight173_south__chevron175_north",
			"from_key": "nested_light_173", "to_key": "chevron_175",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 22.0),
			"from_yaw": 0, "to_yaw": 0, "spawn": Vector3(0.0, 0.6, 6.0),
		},
	]


func _capture() -> void:
	var output_absolute := ProjectSettings.globalize_path(output_path)
	if DirAccess.make_dir_recursive_absolute(output_absolute) != OK:
		_quit_with_error("Could not create output directory " + output_path)
		return
	var camera := _review_camera()
	root.add_child(camera)
	camera.current = true
	var views: Array[Dictionary] = []
	var placements: Array[Dictionary] = []
	var first := true
	for pair in _pair_definitions():
		var started_usec := Time.get_ticks_usec()
		var scene := await _load_pair(pair)
		if scene == null:
			_quit_with_error("Could not load pair " + String(pair["id"]))
			return
		if first:
			scene_ready_ms = float(Time.get_ticks_usec() - started_usec) / 1000.0
			frame_profile = await _measure_frame_profile()
			first = false
		_hide_player_hud(scene)
		await process_frame
		var socket := scene.call("get_connection_socket_world",
			["FromRoom", String(pair["from_socket"])]) as Dictionary
		if socket.is_empty():
			_quit_with_error("Missing from-socket for pair " + String(pair["id"]))
			return
		var seam: Vector3 = socket["position"]
		for view in _view_definitions(String(pair["label"]), seam):
			if not await _save_capture(camera, view):
				return
			views.append(view)
		placements.append({
			"pair": pair["id"],
			"from_origin": pair["from_origin"], "from_yaw_degrees": pair["from_yaw"],
			"to_origin": pair["to_origin"], "to_yaw_degrees": pair["to_yaw"],
			"seam_world_z": seam.z,
		})
		scene.queue_free()
		await process_frame
	_write_manifest(views, placements)
	quit(0)


func _load_pair(pair: Dictionary) -> Node3D:
	var packed := load(ASSEMBLY) as PackedScene
	if packed == null:
		return null
	var scene := packed.instantiate() as Node3D
	scene.set("pair_id", pair["id"])
	scene.set("from_room_key", pair["from_key"])
	scene.set("to_room_key", pair["to_key"])
	scene.set("from_socket_id", pair["from_socket"])
	scene.set("to_socket_id", pair["to_socket"])
	scene.set("from_origin", pair["from_origin"])
	scene.set("to_origin", pair["to_origin"])
	scene.set("from_yaw_degrees", pair["from_yaw"])
	scene.set("to_yaw_degrees", pair["to_yaw"])
	scene.set("player_spawn", pair["spawn"])
	scene.set("player_yaw_degrees", 180)
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
	camera.name = "Issue283ReviewCamera"
	camera.fov = 72.0
	camera.near = 0.05
	camera.far = 100.0
	return camera


func _view_definitions(label: String, seam: Vector3) -> Array[Dictionary]:
	var z := seam.z
	return [
		{
			"name": label + "_from_a_to_b.png",
			"position": Vector3(0.0, 1.42, z - 3.5), "target": Vector3(0.0, 1.3, z + 4.0),
		},
		{
			"name": label + "_from_b_to_a.png",
			"position": Vector3(0.0, 1.42, z + 3.5), "target": Vector3(0.0, 1.3, z - 4.0),
		},
		{
			"name": label + "_doorway_side.png",
			"position": Vector3(2.6, 1.42, z - 2.4), "target": Vector3(0.0, 1.35, z + 0.4),
		},
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
	var destination := output_path.path_join(String(view["name"]))
	if FileAccess.file_exists(destination):
		_quit_with_error("Refusing to overwrite " + destination)
		return false
	camera.global_position = view["position"]
	camera.look_at(view["target"], Vector3.UP)
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_viewport().get_texture().get_image()
	var absolute := ProjectSettings.globalize_path(destination)
	if image.save_png(absolute) != OK:
		_quit_with_error("Could not save " + destination)
		return false
	print("ISSUE283_CAPTURE ", destination, " size=", image.get_width(), "x", image.get_height())
	return true


func _write_manifest(views: Array[Dictionary], placements: Array[Dictionary]) -> void:
	var path := output_path.path_join("capture_manifest.json")
	if FileAccess.file_exists(path):
		_quit_with_error("Refusing to overwrite " + path)
		return
	var manifest := {
		"scene": ASSEMBLY,
		"engine": Engine.get_version_info()["string"],
		"scene_ready_ms": scene_ready_ms,
		"frame_profile": frame_profile,
		"views": views,
		"placements": placements,
		"registration_accepted": false,
		"scale_calibrated": false,
		"socket_test_status": "untested",
		"layout_eligible": false,
	}
	var output := FileAccess.open(path, FileAccess.WRITE)
	if output == null:
		_quit_with_error("Could not write " + path)
		return
	output.store_string(JSON.stringify(manifest, "\t") + "\n")


func _quit_with_error(message: String) -> void:
	printerr("ISSUE283_CAPTURE_ERROR: " + message)
	quit(1)
