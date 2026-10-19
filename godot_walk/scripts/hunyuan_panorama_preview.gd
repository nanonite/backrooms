extends Node3D

const CAMERA_METADATA_PATH := "res://evidence/2026-10-13-hunyuan-track-a/source_selection.json"
const DEFAULT_PANORAMA_PATH := "res://evidence/2026-10-13-hunyuan-track-a/candidate_measured_fov_75.93_seed_42.png"
const DIRECTION_NAMES := ["FORWARD", "RIGHT", "BACK", "LEFT"]
const YAW_BANK := [
	{"name": "forward", "offset": 0.0, "label": "FORWARD"},
	{"name": "right", "offset": -90.0, "label": "RIGHT"},
	{"name": "back", "offset": 180.0, "label": "BACK"},
	{"name": "left", "offset": 90.0, "label": "LEFT"},
]

@onready var preview_camera: Camera3D = $PreviewCamera
@onready var direction_label: Label = $Overlay/Direction

var _base_camera_transform := Transform3D.IDENTITY
var _direction_index := 0


func _ready() -> void:
	var panorama_path := OS.get_environment("HUNYUAN_PANORAMA_PATH")
	if panorama_path.is_empty():
		panorama_path = ProjectSettings.globalize_path(DEFAULT_PANORAMA_PATH)
	if not _load_panorama(panorama_path):
		return
	var source_camera := _load_camera_metadata()
	if source_camera.is_empty():
		return
	_align_camera(source_camera)
	var capture_dir := OS.get_environment("HUNYUAN_CAPTURE_DIR")
	if not capture_dir.is_empty():
		_capture_yaw_bank.call_deferred(capture_dir)


func _load_panorama(path: String) -> bool:
	if not FileAccess.file_exists(path):
		push_error("HUNYUAN_PANORAMA_PATH does not exist: %s" % path)
		return false
	var image := Image.load_from_file(path)
	if image.is_empty() or image.get_width() != 2 * image.get_height():
		push_error("Hunyuan panorama must be a readable 2:1 equirectangular image")
		return false
	var material := PanoramaSkyMaterial.new()
	material.panorama = ImageTexture.create_from_image(image)
	var sky := Sky.new()
	sky.sky_material = material
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	$WorldEnvironment.environment = environment
	return true


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


func _align_camera(source_camera: Dictionary) -> void:
	var origin := _vector3_from_array(source_camera.get("camera_center_godot_world_m", []))
	var forward := _vector3_from_array(source_camera.get("forward_godot_world", [])).normalized()
	var up := _vector3_from_array(source_camera.get("up_godot_world", [])).normalized()
	if forward.length_squared() < 0.99 or up.length_squared() < 0.99:
		push_error("Registered camera orientation is missing or invalid")
		return
	preview_camera.keep_aspect = Camera3D.KEEP_WIDTH
	preview_camera.fov = float(source_camera.get("approx_horizontal_fov_degrees", 75.0))
	preview_camera.look_at_from_position(origin, origin + forward, up)
	_base_camera_transform = preview_camera.transform
	$WorldEnvironment.environment.sky_rotation = Vector3(
		0.0, deg_to_rad(float(source_camera.get("yaw_degrees", 0.0)) + 180.0), 0.0
	)


func _vector3_from_array(values: Array) -> Vector3:
	if values.size() != 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.keycode == KEY_LEFT:
		preview_camera.rotate_y(deg_to_rad(90.0))
		_direction_index = posmod(_direction_index - 1, DIRECTION_NAMES.size())
	elif event.keycode == KEY_RIGHT:
		preview_camera.rotate_y(deg_to_rad(-90.0))
		_direction_index = posmod(_direction_index + 1, DIRECTION_NAMES.size())
	else:
		return
	direction_label.text = DIRECTION_NAMES[_direction_index]
	get_viewport().set_input_as_handled()


func _capture_yaw_bank(directory: String) -> void:
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK and not DirAccess.dir_exists_absolute(directory):
		push_error("Cannot create panorama screenshot directory")
		get_tree().quit(1)
		return
	for view in YAW_BANK:
		preview_camera.transform = _base_camera_transform
		preview_camera.rotate_y(deg_to_rad(float(view["offset"])))
		direction_label.text = String(view["label"])
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var capture := get_viewport().get_texture().get_image()
		var output_path := directory.path_join("%s.png" % view["name"])
		if capture.is_empty() or capture.save_png(output_path) != OK:
			push_error("Could not save panorama screenshot: %s" % output_path)
			get_tree().quit(1)
			return
		print("PANORAMA_VIEW: %s %s" % [view["name"], output_path])
	get_tree().quit()
