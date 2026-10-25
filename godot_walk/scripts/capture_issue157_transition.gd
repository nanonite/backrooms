extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const OUTPUT := "res://evidence/2026-10-23-issue-157"
const LAYOUT := "res://evidence/2026-10-23-issue-156/layout_seed_149.json"
const FLOOR_Y := -1.27099049
const CEILING_Y := FLOOR_Y + 2.4
const EYE_Y := FLOOR_Y + 1.1
const SETTLE_FRAMES := 18

var _layout: Dictionary
var _scene: Node3D
var _player: CharacterBody3D
var _camera: Camera3D
var _records: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	if not _load_layout() or not await _load_walkthrough():
		quit(2)
		return
	var setting: Dictionary = ProjectSettings.get_setting(
		"shader_globals/affine_texture_mapping", {})
	if setting.get("value") != false:
		push_error("#157 capture requires the operator-selected affine-off default")
		quit(2)
		return
	_player = _scene.get_node("Player") as CharacterBody3D
	_player.set_physics_process(false)
	_player.set_process(false)
	_hide_hud()
	_create_camera()
	for view: Dictionary in _views():
		_records.append(await _capture_view(view))
	_write_manifest()
	print("ISSUE157_TRANSITION_CAPTURE_COMPLETE views=%d affine_texture_mapping=false" % _records.size())
	quit()


func _load_layout() -> bool:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT))
	if not parsed is Dictionary:
		push_error("#157 cannot read the accepted #156 layout")
		return false
	_layout = parsed
	return true


func _load_walkthrough() -> bool:
	var packed := load("res://scenes/issue156_streamed_walkthrough.tscn") as PackedScene
	_scene = packed.instantiate() as Node3D if packed != null else null
	if _scene == null:
		push_error("#157 cannot instantiate the accepted #156 walkthrough")
		return false
	root.add_child(_scene)
	for frame in 180:
		if _scene.get_meta("walkthrough_ready", false):
			return true
		await process_frame
	push_error("#157 walkthrough did not become ready")
	return false


func _views() -> Array[Dictionary]:
	return [
		_view("column_into_pocket", "R000", Vector3(1.4, EYE_Y, 3.1),
			Vector3(6.3, EYE_Y, 3.1), Vector3(2.2, FLOOR_Y + 0.6, 3.1), "door, walls, floor, ceiling"),
		_view("pocket_into_column", "R001", Vector3(2.2, EYE_Y, 6.9),
			Vector3(-3.0, EYE_Y, 6.9), Vector3(3.0, FLOOR_Y + 0.6, 6.9), "door, walls, floor, ceiling"),
		_view("threshold_floor", "R000", Vector3(1.8, FLOOR_Y + 0.9, 4.6),
			Vector3(3.5, FLOOR_Y - 0.02, 3.1), Vector3(2.2, FLOOR_Y + 0.6, 3.1), "floor, threshold, jambs"),
		_view("threshold_ceiling", "R000", Vector3(1.8, EYE_Y, 4.6),
			Vector3(3.5, CEILING_Y - 0.02, 3.1), Vector3(2.2, FLOOR_Y + 0.6, 3.1), "ceiling, lintel, walls"),
		_view("column_socket_jamb", "R000", Vector3(2.1, EYE_Y, 1.7),
			Vector3(3.5, EYE_Y, 3.2), Vector3(2.2, FLOOR_Y + 0.6, 3.1), "wall, jamb, column-room floor"),
		_view("pocket_socket_jamb", "R001", Vector3(1.8, EYE_Y, 4.8),
			Vector3(0.0, EYE_Y, 6.9), Vector3(3.0, FLOOR_Y + 0.6, 6.9), "wall, jamb, pocket floor"),
	]


func _view(view_id: String, room: String, eye: Vector3, target: Vector3,
		stream_position: Vector3, surfaces: String) -> Dictionary:
	return {"id": view_id, "room": room, "eye": eye, "target": target,
		"stream_position": stream_position, "surfaces": surfaces}


func _capture_view(view: Dictionary) -> Dictionary:
	var room: String = view.room
	_player.global_position = _world_point(room, view.stream_position)
	_player.reset_physics_interpolation()
	_scene.get_node("BoundedLayoutStreamer").call("refresh", true)
	_camera.global_position = _world_point(room, view.eye)
	var target := _world_point(room, view.target)
	_camera.look_at(target, Vector3.UP)
	await _settle()
	var image := root.get_texture().get_image()
	var relative := "captures/%s.png" % view.id
	var absolute := ProjectSettings.globalize_path(OUTPUT + "/" + relative)
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	if image.is_empty() or image.save_png(absolute) != OK:
		push_error("#157 failed to save %s" % relative)
	return {"view_id": view.id, "room_instance": room, "surfaces": view.surfaces,
		"affine_texture_mapping": false, "camera_eye": _coordinates(_camera.global_position),
		"camera_target": _coordinates(target), "resolution": [image.get_width(), image.get_height()],
		"settle_frames": SETTLE_FRAMES, "path": relative}


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
	_camera.name = "Issue157TransitionCamera"
	_camera.fov = 75.0
	_scene.add_child(_camera)
	_camera.make_current()


func _settle() -> void:
	for frame in SETTLE_FRAMES:
		await process_frame
	await RenderingServer.frame_post_draw


func _coordinates(point: Vector3) -> Array[float]:
	return [point.x, point.y, point.z]


func _write_manifest() -> void:
	var file := FileAccess.open(OUTPUT + "/capture_manifest.json", FileAccess.WRITE)
	if file == null:
		push_error("#157 cannot write capture manifest")
		quit(2)
		return
	file.store_string(JSON.stringify(_records, "\t") + "\n")
