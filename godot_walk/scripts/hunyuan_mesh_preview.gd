extends Node3D

const CAMERA_METADATA_PATH := "res://evidence/2026-10-13-hunyuan-track-a/source_selection.json"
const MESH_SCENE_PATH := "res://generated_mesh_scenes/hunyuan_track_a_full_run/hunyuan_layers.glb"
const PARALLAX_OFFSET_UNITS := 0.25
const YAW_VIEWS := [
	{"name": "forward", "yaw": 0.0},
	{"name": "right", "yaw": -90.0},
	{"name": "back", "yaw": 180.0},
	{"name": "left", "yaw": 90.0},
	{"name": "parallax_right_025", "yaw": 0.0},
]

@onready var preview_camera: Camera3D = $PreviewCamera
@onready var direction_label: Label = $Overlay/Direction

var _base_camera_transform := Transform3D.IDENTITY
var _camera_origin := Vector3.ZERO
var _camera_right := Vector3.RIGHT
var _direction_index := 0


func _ready() -> void:
	if not _load_mesh_scene():
		return
	var camera_data := _load_camera_metadata()
	if camera_data.is_empty() or not _align_candidate(camera_data):
		return
	_set_environment()
	var capture_dir := OS.get_environment("HUNYUAN_MESH_CAPTURE_DIR")
	if not capture_dir.is_empty():
		_capture_yaw_bank.call_deferred(capture_dir)


func _load_mesh_scene() -> bool:
	var packed := load(MESH_SCENE_PATH) as PackedScene
	if packed == null:
		push_error("Cannot load converted Hunyuan GLB: %s" % MESH_SCENE_PATH)
		return false
	var instance := packed.instantiate()
	instance.name = "HunyuanLayers"
	_apply_preview_materials(instance)
	$MeshRoot.add_child(instance)
	return true


func _apply_preview_materials(instance: Node) -> void:
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	for child in instance.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := child as MeshInstance3D
		if mesh_instance != null:
			mesh_instance.material_override = material


func _load_camera_metadata() -> Dictionary:
	var file := FileAccess.open(CAMERA_METADATA_PATH, FileAccess.READ)
	if file == null:
		push_error("Cannot read registered camera metadata: %s" % CAMERA_METADATA_PATH)
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary or not parsed.get("camera", {}) is Dictionary:
		push_error("Registered camera metadata has an invalid shape")
		return {}
	return parsed["camera"]


func _align_candidate(source_camera: Dictionary) -> bool:
	_camera_origin = _vector3_from_array(source_camera.get("camera_center_godot_world_m", []))
	var forward := _vector3_from_array(source_camera.get("forward_godot_world", [])).normalized()
	var up := _vector3_from_array(source_camera.get("up_godot_world", [])).normalized()
	if forward.length_squared() < 0.99 or up.length_squared() < 0.99:
		push_error("Registered camera orientation is missing or invalid")
		return false
	_camera_right = forward.cross(up).normalized()
	var pano_basis := Basis(-forward, _camera_right, up)
	$MeshRoot/HunyuanLayers.transform = Transform3D(pano_basis, _camera_origin)
	preview_camera.keep_aspect = Camera3D.KEEP_WIDTH
	preview_camera.fov = float(source_camera.get("approx_horizontal_fov_degrees", 75.0))
	preview_camera.look_at_from_position(_camera_origin, _camera_origin + forward, up)
	_base_camera_transform = preview_camera.global_transform
	return true


func _set_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.035)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.88, 0.86, 0.78)
	environment.ambient_light_energy = 0.8
	$WorldEnvironment.environment = environment


func _vector3_from_array(values: Array) -> Vector3:
	if values.size() != 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.keycode == KEY_LEFT or event.keycode == KEY_RIGHT:
		_rotate_view(-90.0 if event.keycode == KEY_RIGHT else 90.0)
	elif event.keycode == KEY_R:
		preview_camera.global_transform = _base_camera_transform
		_direction_index = 0
		direction_label.text = "FORWARD"
	elif event.keycode in [KEY_W, KEY_A, KEY_S, KEY_D]:
		_move_view(event.keycode)
	else:
		return
	get_viewport().set_input_as_handled()


func _rotate_view(degrees: float) -> void:
	preview_camera.rotate_y(deg_to_rad(degrees))
	_direction_index = posmod(_direction_index + (1 if degrees < 0.0 else -1), 4)
	direction_label.text = ["FORWARD", "RIGHT", "BACK", "LEFT"][_direction_index]


func _move_view(key: Key) -> void:
	var direction := -preview_camera.global_basis.z
	var right := preview_camera.global_basis.x
	var offset := Vector3.ZERO
	if key == KEY_W:
		offset = direction
	elif key == KEY_S:
		offset = -direction
	elif key == KEY_D:
		offset = right
	else:
		offset = -right
	preview_camera.global_position += offset * PARALLAX_OFFSET_UNITS


func _capture_yaw_bank(directory: String) -> void:
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK and not DirAccess.dir_exists_absolute(directory):
		push_error("Cannot create Hunyuan mesh screenshot directory")
		get_tree().quit(1)
		return
	for view in YAW_VIEWS:
		if not await _capture_view(view, directory):
			get_tree().quit(1)
			return
	get_tree().quit()


func _capture_view(view: Dictionary, directory: String) -> bool:
	preview_camera.global_transform = _base_camera_transform
	preview_camera.rotate_y(deg_to_rad(float(view["yaw"])))
	if view["name"] == "parallax_right_025":
		preview_camera.global_position += _camera_right * PARALLAX_OFFSET_UNITS
	direction_label.text = String(view["name"]).to_upper()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var capture := get_viewport().get_texture().get_image()
	var path := directory.path_join("%s.png" % view["name"])
	if capture.is_empty() or capture.save_png(path) != OK:
		push_error("Could not save Hunyuan mesh screenshot: %s" % path)
		return false
	print("HUNYUAN_MESH_VIEW: %s %s" % [view["name"], path])
	return true
