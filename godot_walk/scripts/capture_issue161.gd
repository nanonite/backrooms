extends SceneTree

const WALKTHROUGH := "res://scenes/issue156_streamed_walkthrough.tscn"
const OUTPUT := "res://evidence/2026-10-23-issue-161"
const LAYOUT := "res://evidence/2026-10-23-issue-156/layout_seed_149.json"
const FLOOR_Y := -1.27099049
const EYE_Y := FLOOR_Y + 1.1
const SETTLE_FRAMES := 18
const NOISE_REPEATS := 3

var _layout: Dictionary
var _scene: Node3D
var _player: CharacterBody3D
var _camera: Camera3D
var _records: Array[Dictionary] = []
var _scene_load_to_ready_ms := 0


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	if not _load_layout():
		quit(2)
		return
	if not await _load_walkthrough():
		quit(2)
		return
	_player = _scene.get_node("Player") as CharacterBody3D
	_player.set_physics_process(false)
	_player.set_process(false)
	_hide_hud()
	_create_camera()
	if _scene.get_node_or_null("LibraryPsxPreset") == null:
		printerr("#161 URSC room preset was not configured")
		quit(2)
		return
	for profile: Dictionary in _profiles():
		await _capture_profile(profile)
	_write_manifest()
	print("ISSUE161_CAPTURE_COMPLETE captures=%d" % _records.size())
	quit()


func _load_layout() -> bool:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT))
	if not parsed is Dictionary:
		printerr("#161 cannot read the serialized #156 layout")
		return false
	_layout = parsed
	return true


func _load_walkthrough() -> bool:
	var started := Time.get_ticks_msec()
	var packed := load(WALKTHROUGH) as PackedScene
	_scene = packed.instantiate() as Node3D if packed != null else null
	if _scene == null:
		printerr("#161 cannot instantiate the #156 streamed scene")
		return false
	root.add_child(_scene)
	for frame in 180:
		if _scene.get_meta("walkthrough_ready", false):
			_scene_load_to_ready_ms = Time.get_ticks_msec() - started
			return true
		await process_frame
	printerr("#161 #156 walkthrough did not become ready")
	return false


func _profiles() -> Array[Dictionary]:
	return [
		{"id": "affine_on", "affine_texture_mapping": true,
			"texture_filtering": false, "vertex_snap_intensity": 1},
		{"id": "affine_off", "affine_texture_mapping": false,
			"texture_filtering": false, "vertex_snap_intensity": 1},
	]


func _capture_profile(profile: Dictionary) -> void:
	RenderingServer.global_shader_parameter_set("affine_texture_mapping",
		profile.affine_texture_mapping)
	await _settle(3)
	var repeat_view := _noise_anchor()
	for repeat in range(1, NOISE_REPEATS + 1):
		_records.append(await _capture_view(profile, repeat_view,
			"repeat_noise_%d" % repeat))
	for view: Dictionary in _views():
		_records.append(await _capture_view(profile, view, view.id))


func _views() -> Array[Dictionary]:
	return [
		_view("column_patch_anchor", "R000", Vector3(2.921, EYE_Y, 3.704),
			Vector3(-1.215, EYE_Y, -0.635), "column, wall, floor, ceiling"),
		_view("column_east_wall", "R000", Vector3(2.37, EYE_Y, 0.323),
			Vector3(-3.63, EYE_Y, 0.323), "wall, floor, ceiling"),
		_view("branch_center", "R006", Vector3(3.0, EYE_Y, 6.2),
			Vector3(3.0, EYE_Y, 11.8), "wall, floor, ceiling"),
		_pan_view("wall_pan_left", -20.0),
		_pan_view("wall_pan_right", 20.0),
		_view("hall_step_left", "R006", Vector3(2.8, EYE_Y, 6.2),
			Vector3(2.8, EYE_Y, 11.8), "wall, floor, ceiling"),
		_view("hall_step_right", "R006", Vector3(3.2, EYE_Y, 6.2),
			Vector3(3.2, EYE_Y, 11.8), "wall, floor, ceiling"),
		_view("floor_walk_line", "R006", Vector3(3.0, EYE_Y, 6.2),
			Vector3(3.0, FLOOR_Y + 0.05, 11.8), "floor, wall"),
		_view("ceiling_walk_line", "R006", Vector3(3.0, EYE_Y, 6.2),
			Vector3(3.0, 1.05, 11.8), "ceiling, wall"),
	]


func _noise_anchor() -> Dictionary:
	return _view("repeat_noise", "R006", Vector3(3.0, EYE_Y, 6.2),
		Vector3(3.0, EYE_Y, 11.8), "wall, floor, ceiling")


func _view(view_id: String, room: String, eye: Vector3,
		target: Vector3, surfaces: String) -> Dictionary:
	var stream_position := Vector3(3.0, FLOOR_Y + 0.6, 6.9)
	if room == "R000":
		stream_position = Vector3(2.4, FLOOR_Y + 0.6, 3.1)
	return {"id": view_id, "room": room, "eye": eye, "target": target,
		"stream_position": stream_position, "surfaces": surfaces}


func _pan_view(view_id: String, angle: float) -> Dictionary:
	var view := _view(view_id, "R006", Vector3(3.0, EYE_Y, 6.2),
		Vector3(3.0, EYE_Y, 11.8), "wall, floor, ceiling")
	view["yaw_offset_degrees"] = angle
	return view


func _capture_view(profile: Dictionary, view: Dictionary, capture_id: String) -> Dictionary:
	var room: String = view.room
	var stream_position: Vector3 = view.stream_position
	var local_eye: Vector3 = view.eye
	var local_target: Vector3 = view.target
	_player.global_position = _world_point(room, stream_position)
	_player.reset_physics_interpolation()
	(_scene.get_node("BoundedLayoutStreamer") as Node).call("refresh", true)
	_camera.global_position = _world_point(room, local_eye)
	var target := _world_point(room, local_target)
	var yaw_offset := deg_to_rad(float(view.get("yaw_offset_degrees", 0.0)))
	if not is_zero_approx(yaw_offset):
		target = _camera.global_position + Basis(Vector3.UP, yaw_offset) \
			* (target - _camera.global_position)
	_camera.look_at(target, Vector3.UP)
	await _settle(SETTLE_FRAMES)
	var image := root.get_texture().get_image()
	var relative_path := "captures/%s/%s.png" % [profile.id, capture_id]
	var absolute_path := ProjectSettings.globalize_path(OUTPUT + "/" + relative_path)
	DirAccess.make_dir_recursive_absolute(absolute_path.get_base_dir())
	if image.is_empty() or image.save_png(absolute_path) != OK:
		push_error("#161 failed to save capture: %s" % relative_path)
	return {
		"profile_id": profile.id, "capture_id": capture_id,
		"view_id": view.id, "room_instance": room,
		"surfaces": view.surfaces,
		"affine_texture_mapping": profile.affine_texture_mapping,
		"texture_filtering": profile.texture_filtering,
		"vertex_snap_intensity": profile.vertex_snap_intensity,
		"camera_eye": _coordinates(_camera.global_position),
		"camera_target": _coordinates(target),
		"resolution": [image.get_width(), image.get_height()],
		"settle_frames": SETTLE_FRAMES,
		"scene_load_to_ready_ms": _scene_load_to_ready_ms,
		"path": relative_path,
	}


func _world_point(instance_id: String, local: Vector3) -> Vector3:
	var placement := _placement(instance_id)
	var transform: Dictionary = placement.transform
	var origin := Vector3(transform.position[0], transform.position[1], transform.position[2])
	var basis := Basis(Vector3.UP, deg_to_rad(float(transform.yaw_degrees)))
	return Transform3D(basis, origin) * local


func _placement(instance_id: String) -> Dictionary:
	for placement: Dictionary in _layout.placements:
		if placement.instance_id == instance_id:
			return placement
	return {}


func _hide_hud() -> void:
	for child: Node in _player.get_children():
		if child is CanvasLayer:
			child.visible = false


func _create_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "Issue161CaptureCamera"
	_camera.fov = 75.0
	_scene.add_child(_camera)
	_camera.make_current()


func _settle(frames: int) -> void:
	for frame in frames:
		await process_frame
	await RenderingServer.frame_post_draw


func _coordinates(point: Vector3) -> Array[float]:
	return [point.x, point.y, point.z]


func _write_manifest() -> void:
	var destination := ProjectSettings.globalize_path(OUTPUT + "/capture_manifest.json")
	var file := FileAccess.open(destination, FileAccess.WRITE)
	if file == null:
		push_error("#161 cannot write the capture manifest")
		quit(2)
		return
	file.store_string(JSON.stringify(_records, "\t") + "\n")
