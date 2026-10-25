extends SceneTree

const REVIEW_SCENE := preload("res://scenes/issue157_transition_review.tscn")
const OUTPUT := "res://evidence/2026-10-23-issue-157"
const LAYOUT := "res://evidence/2026-10-23-issue-156/layout_seed_149.json"
const FLOOR_Y := -1.27099049
const CEILING_Y := FLOOR_Y + 2.4
const CEILING_PATCH_DROP := 0.06
const CEILING_BRIDGE_UV_SCALE := Vector2(1.3, 1.18)
const EYE_Y := FLOOR_Y + 1.1
const SETTLE_FRAMES := 18

var _layout: Dictionary
var _review: Node3D
var _scene: Node3D
var _player: CharacterBody3D
var _camera: Camera3D
var _records: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	if not _load_layout() or not await _load_review_scene():
		quit(2)
		return
	if not _affine_off_is_project_default():
		quit(2)
		return
	_player = _scene.get_node("Player") as CharacterBody3D
	_player.set_physics_process(false)
	_player.set_process(false)
	_hide_hud()
	_create_camera()
	_review.call("set_ceiling_candidate_enabled", false)
	for repeat_id in ["ceiling_repeat_a", "ceiling_repeat_b"]:
		for view: Dictionary in _views():
			_records.append(await _capture_view(view, repeat_id))
	_review.call("set_ceiling_candidate_enabled", true)
	for view: Dictionary in _views():
		_records.append(await _capture_view(view, "ceiling_source_bridge"))
	_write_manifest()
	print("ISSUE157_CEILING_CANDIDATE_CAPTURE_COMPLETE views=%d affine_texture_mapping=false" % _records.size())
	quit()


func _affine_off_is_project_default() -> bool:
	var setting: Dictionary = ProjectSettings.get_setting(
		"shader_globals/affine_texture_mapping", {})
	if setting.get("type") == "bool" and setting.get("value") == false:
		return true
	push_error("#157 candidate requires the operator-selected affine-off default")
	return false


func _load_layout() -> bool:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT))
	if not parsed is Dictionary:
		push_error("#157 cannot read the accepted #156 layout")
		return false
	_layout = parsed
	return true


func _load_review_scene() -> bool:
	_review = REVIEW_SCENE.instantiate() as Node3D
	if _review == null:
		push_error("#157 cannot instantiate its transition review scene")
		return false
	root.add_child(_review)
	for frame in 180:
		_scene = _review.get("_walkthrough") as Node3D
		if _scene != null and _scene.get_meta("walkthrough_ready", false):
			var status_label := _review.get("_label") as Label
			if status_label != null:
				status_label.hide()
			return true
		await process_frame
	push_error("#157 accepted walkthrough did not become ready")
	return false


func _views() -> Array[Dictionary]:
	return [
		_view("column_into_pocket", "R000", Vector3(1.4, EYE_Y, 3.1),
			Vector3(6.3, EYE_Y, 3.1), Vector3(2.2, FLOOR_Y + 0.6, 3.1)),
		_view("pocket_into_column", "R001", Vector3(2.2, EYE_Y, 6.9),
			Vector3(-3.0, EYE_Y, 6.9), Vector3(3.0, FLOOR_Y + 0.6, 6.9)),
		_view("threshold_ceiling", "R000", Vector3(1.8, EYE_Y, 4.6),
			Vector3(2.85, CEILING_Y - CEILING_PATCH_DROP, 3.1), Vector3(2.2, FLOOR_Y + 0.6, 3.1)),
		_view("ceiling_under_bridge", "R000", Vector3(2.0, EYE_Y, 3.1),
			Vector3(2.85, CEILING_Y - CEILING_PATCH_DROP, 3.1), Vector3(2.2, FLOOR_Y + 0.6, 3.1)),
	]


func _view(view_id: String, room: String, eye: Vector3, target: Vector3,
		stream_position: Vector3) -> Dictionary:
	return {"id": view_id, "room": room, "eye": eye, "target": target,
		"stream_position": stream_position}


func _capture_view(view: Dictionary, variant: String) -> Dictionary:
	var room: String = view.room
	_player.global_position = _world_point(room, view.stream_position)
	_player.reset_physics_interpolation()
	_scene.get_node("BoundedLayoutStreamer").call("refresh", true)
	_camera.global_position = _world_point(room, view.eye)
	var target := _world_point(room, view.target)
	_camera.look_at(target, Vector3.UP)
	await _settle()
	var image := root.get_texture().get_image()
	var relative := "captures/%s/%s.png" % [variant, view.id]
	var absolute := ProjectSettings.globalize_path(OUTPUT + "/" + relative)
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	if image.is_empty() or image.save_png(absolute) != OK:
		push_error("#157 failed to save %s" % relative)
	return {"variant_id": variant, "view_id": view.id, "room_instance": room,
		"candidate": "source-textured doorway ceiling bridge" if variant == "ceiling_source_bridge" else "unchanged accepted assembly",
		"affine_texture_mapping": false, "floor_uv_scale": [4.0, 4.0],
		"camera_eye": _coordinates(_camera.global_position),
		"camera_target": _coordinates(target), "resolution": [image.get_width(), image.get_height()],
		"settle_frames": SETTLE_FRAMES, "path": relative}


func _world_point(instance_id: String, local: Vector3) -> Vector3:
	var transform: Dictionary = _placement(instance_id).transform
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
	_camera.name = "Issue157CeilingCandidateCamera"
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
	var file := FileAccess.open(OUTPUT + "/ceiling_candidate_manifest.json", FileAccess.WRITE)
	if file == null:
		push_error("#157 cannot write ceiling-candidate manifest")
		quit(2)
		return
	file.store_string(JSON.stringify({"candidate": "source-textured-doorway-ceiling-bridge",
		"source_texture": "res://assets/psx_extension/textures/ceiling_source_video.png",
		"geometry": {"size_m": [2.6, 2.0], "center_m": [3.5, 1.06900951, 3.1],
			"drop_below_ceiling_center_m": CEILING_PATCH_DROP},
		"uv_scale": [CEILING_BRIDGE_UV_SCALE.x, CEILING_BRIDGE_UV_SCALE.y],
		"baseline": "unchanged accepted #160 assembly",
		"visual_only": true, "collision_added": false,
		"production_assets_changed": false, "records": _records}, "\t") + "\n")
