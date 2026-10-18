extends SceneTree

const EVIDENCE_DIR := "res://evidence/2026-10-13-hunyuan-track-a"
const CAPTURE_SIZE := Vector2i(960, 540)
const CAPTURE_FOV_DEGREES := 47.3988056
const CAPTURE_SETTLE_FRAMES := 8
const BASELINE_REPEAT_COUNT := 3
const BASELINE_SCENE := "res://scenes/corridor_splat.tscn"
const HUNYUAN_GLB := "res://generated_mesh_scenes/hunyuan_track_a_full_run/hunyuan_layers.glb"
const ROUTE_REPORT := EVIDENCE_DIR + "/collision_proto/authored_route_around_column/route_report.json"
const SOURCE_METADATA := EVIDENCE_DIR + "/source_selection.json"
const ROUTE_MANIFEST := EVIDENCE_DIR + "/hunyuan_route_scene_manifest.json"

var _capture_directory := ""
var _mode := ""
var _camera: Camera3D
var _poses: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 2 or not ["baseline", "hunyuan"].has(arguments[0]):
		printerr("Usage: --script res://evidence/.../capture_issue_137.gd -- baseline|hunyuan <absolute-output-dir>")
		quit(2)
		return
	_mode = arguments[0]
	_capture_directory = arguments[1]
	root.size = CAPTURE_SIZE
	_poses = _load_capture_poses()
	if _poses.is_empty() or not _ensure_directory(_capture_directory) or not _build_scene():
		quit(1)
		return
	await process_frame
	await process_frame
	if not _save_pose_manifest():
		quit(1)
		return
	if not await _capture_poses():
		quit(1)
		return
	print("ISSUE_137_CAPTURE_OK mode=%s views=%d" % [_mode, _poses.size()])
	quit(0)


func _load_capture_poses() -> Array[Dictionary]:
	var source := _read_json(SOURCE_METADATA)
	var route := _read_json(ROUTE_REPORT)
	if source.is_empty() or route.is_empty():
		return []
	var camera: Dictionary = source.get("camera", {})
	var route_data: Dictionary = route.get("route", {})
	var center: Array = route_data.get("center_xz_m", [])
	if center.size() != 2:
		push_error("Route report is missing its center_xz_m")
		return []
	var floor_y := float(route.get("plane", {}).get("height_m", 0.0))
	var camera_position := _vector3(camera.get("camera_center_godot_world_m", []))
	var camera_forward := _vector3(camera.get("forward_godot_world", []))
	var camera_up := _vector3(camera.get("up_godot_world", []))
	var poses: Array[Dictionary] = [{
		"name": "frame_141",
		"position": camera_position,
		"forward": camera_forward,
		"up": camera_up,
	}]
	var centerline_radius := float(route_data.get("radius_m", 0.0))
	var eye_height := camera_position.y - floor_y
	if centerline_radius <= 0.0 or eye_height <= 0.0:
		push_error("Route radius or frame-141 camera height is invalid")
		return []
	for station in range(8):
		poses.append(_loop_pose(station, center, centerline_radius, floor_y + eye_height))
	return poses


func _loop_pose(station: int, center: Array, radius: float, eye_y: float) -> Dictionary:
	var angle := TAU * float(station) / 8.0
	var forward := Vector3(-sin(angle), 0.0, cos(angle))
	return {
		"name": "loop_station_%02d" % station,
		"position": Vector3(float(center[0]) + radius * cos(angle), eye_y,
			float(center[1]) + radius * sin(angle)),
		"forward": forward,
		"up": Vector3.UP,
	}


func _build_scene() -> bool:
	if _mode == "baseline":
		return _build_baseline_scene()
	return _build_hunyuan_scene()


func _build_baseline_scene() -> bool:
	var packed := load(BASELINE_SCENE) as PackedScene
	if packed == null:
		push_error("Could not load the unchanged #100 corridor scene")
		return false
	var instance := packed.instantiate()
	root.add_child(instance)
	_camera = instance.get_node_or_null("Camera3D") as Camera3D
	if _camera == null:
		push_error("#100 corridor scene has no Camera3D")
		return false
	_prepare_camera()
	return true


func _build_hunyuan_scene() -> bool:
	var packed := load(HUNYUAN_GLB) as PackedScene
	if packed == null:
		push_error("Could not load the run-05 Hunyuan GLB")
		return false
	var scene_root := Node3D.new()
	root.add_child(scene_root)
	_add_matching_environment(scene_root)
	var visual := packed.instantiate()
	_apply_visual_material(visual)
	var transform_root := Node3D.new()
	transform_root.transform = _hunyuan_transform()
	transform_root.add_child(visual)
	scene_root.add_child(transform_root)
	_camera = Camera3D.new()
	scene_root.add_child(_camera)
	_prepare_camera()
	return true


func _prepare_camera() -> void:
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.fov = CAPTURE_FOV_DEGREES
	_camera.make_current()


func _hunyuan_transform() -> Transform3D:
	var metadata := _read_json(SOURCE_METADATA)
	var manifest := _read_json(ROUTE_MANIFEST)
	var camera: Dictionary = metadata.get("camera", {})
	var forward := _vector3(camera.get("forward_godot_world", [])).normalized()
	var up := _vector3(camera.get("up_godot_world", [])).normalized()
	var right := forward.cross(up).normalized()
	var orientation := Basis(-forward, right, up).orthonormalized()
	var transform: Dictionary = manifest.get("transform", {})
	var translation := _vector3(transform.get("plane_aligned_translation_world_m", []))
	var scale := float(transform.get("scale_m_per_hunyuan_unit", 0.0))
	return Transform3D(orientation.scaled(Vector3.ONE * scale), translation)


func _apply_visual_material(instance: Node) -> void:
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var mesh_nodes := instance.find_children("*", "MeshInstance3D", true, false)
	if mesh_nodes.is_empty():
		push_error("The Hunyuan GLB contains no MeshInstance3D nodes")
		return
	for node in mesh_nodes:
		(node as MeshInstance3D).material_override = material


func _add_matching_environment(parent: Node3D) -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.03, 0.035, 0.04, 1.0)
	var world := WorldEnvironment.new()
	world.environment = environment
	parent.add_child(world)


func _capture_poses() -> bool:
	for pose in _poses:
		_camera.global_transform = _pose_transform(pose)
		var repeats := BASELINE_REPEAT_COUNT if _mode == "baseline" else 1
		for repeat_index in range(repeats):
			if not await _capture_one(pose, repeat_index):
				return false
	return true


func _pose_transform(pose: Dictionary) -> Transform3D:
	var forward: Vector3 = pose["forward"].normalized()
	var up: Vector3 = pose["up"].normalized()
	var right := forward.cross(up).normalized()
	var corrected_up := right.cross(forward).normalized()
	return Transform3D(Basis(right, corrected_up, -forward), pose["position"])


func _capture_one(pose: Dictionary, repeat_index: int) -> bool:
	for _frame in range(CAPTURE_SETTLE_FRAMES):
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image.is_empty() or image.get_size() != CAPTURE_SIZE:
		push_error("Capture viewport has invalid dimensions")
		return false
	var repeat_name := "baseline_repeat_%d" % (repeat_index + 1) if _mode == "baseline" else "hunyuan"
	var directory := _capture_directory.path_join(repeat_name)
	var filename := String(pose["name"]) + ".png"
	if not _ensure_directory(directory):
		return false
	var path := directory.path_join(filename)
	if image.save_png(path) != OK:
		push_error("Could not save capture: " + path)
		return false
	print("ISSUE_137_CAPTURE: %s %s" % [repeat_name, filename])
	return true


func _save_pose_manifest() -> bool:
	var views: Array[Dictionary] = []
	for pose in _poses:
		views.append({
			"name": pose["name"],
			"position_world_m": _array3(pose["position"]),
			"forward_world": _array3(pose["forward"].normalized()),
			"up_world": _array3(pose["up"].normalized()),
		})
	var data := {
		"issue": 137,
		"label": "uncalibrated",
		"registration_accepted": false,
		"scale_calibrated": false,
		"renderer": "Godot 4.6.3 Forward+ Vulkan",
		"resolution": [CAPTURE_SIZE.x, CAPTURE_SIZE.y],
		"vertical_fov_degrees": CAPTURE_FOV_DEGREES,
		"settle_frames_before_each_capture": CAPTURE_SETTLE_FRAMES,
		"baseline_repeat_count": BASELINE_REPEAT_COUNT,
		"poses": views,
		"camera_height_m_above_authored_floor_at_loop_stations":
			_poses[0]["position"].y - float(_read_json(ROUTE_REPORT).get("plane", {}).get("height_m", 0.0)),
		"loop_station_heading": "tangent in increasing xz angle from +x toward +z",
	}
	var file := FileAccess.open(_capture_directory.path_join("capture_poses.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write capture pose manifest")
		return false
	file.store_string(JSON.stringify(data, "  ") + "\n")
	return true


func _read_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("Cannot read " + path)
		return {}
	var value: Variant = JSON.parse_string(file.get_as_text())
	if not value is Dictionary:
		push_error("Invalid JSON object in " + path)
		return {}
	return value


func _ensure_directory(path: String) -> bool:
	var error := DirAccess.make_dir_recursive_absolute(path)
	if error != OK and not DirAccess.dir_exists_absolute(path):
		push_error("Could not create capture directory: " + path)
		return false
	return true


func _vector3(values: Array) -> Vector3:
	if values.size() != 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _array3(value: Vector3) -> Array[float]:
	return [value.x, value.y, value.z]
