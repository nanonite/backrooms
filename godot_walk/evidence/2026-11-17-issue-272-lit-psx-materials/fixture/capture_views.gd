extends SceneTree

# Paired captures for issue 272: identical camera, light and material settings
# across baseline/lit and solid/textured variants, with a repeatable light
# on/off comparison for each. Views come from views_v1.json and are reused
# byte-for-byte. Invoked only through the existing guarded capture wrapper.
const BASE := "res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/"
const SCENES := {
	"baseline_solid": BASE + "psx_baseline_solid_v1.tscn",
	"lit_solid": BASE + "psx_lit_solid_v1.tscn",
	"baseline_textured": BASE + "psx_baseline_textured_v1.tscn",
	"lit_textured": BASE + "psx_lit_textured_v1.tscn",
}
const VIEWS_PATH := BASE + "views_v1.json"
const DECISION_PATH := BASE + "shader_decision_v1.json"
const DEFAULT_OUTPUT := "res://evidence/2026-11-17-issue-272-lit-psx-materials/captures/paired_v1"

var output_path := DEFAULT_OUTPUT
var views: Array = []
var manifest_views: Array[Dictionary] = []


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_path = argument.trim_prefix("--out=")
	call_deferred("_capture")


func _capture() -> void:
	var absolute_output := ProjectSettings.globalize_path(output_path)
	if DirAccess.dir_exists_absolute(absolute_output) or FileAccess.file_exists(absolute_output):
		printerr("Refusing to overwrite capture output: ", output_path)
		quit(2)
		return
	if not _load_record(VIEWS_PATH, "views"):
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(absolute_output)
	for variant: String in SCENES:
		for light_state: String in ["light_off", "light_on"]:
			await _capture_variant(absolute_output, variant, SCENES[variant], light_state)
	_write_manifest(absolute_output)
	print("ISSUE_272_PAIRED_CAPTURES_READY: ", output_path)
	quit(0)


func _load_record(path: String, key: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		printerr("Could not read record: ", path)
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary or not parsed.has(key):
		printerr("Record is invalid: ", path)
		return false
	if key == "views":
		views = parsed[key]
	return true


func _capture_variant(absolute_output: String, variant: String, scene_path: String,
		light_state: String) -> void:
	var packed := load(scene_path) as PackedScene
	if packed == null:
		push_error("Could not load scene for capture: %s" % scene_path)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	room.call("set_light_on", light_state == "light_on")
	await _frames(2)
	var camera := room.get_node("InspectionCamera") as Camera3D
	var relative_dir := output_path.path_join(variant).path_join(light_state)
	var absolute_dir := absolute_output.path_join(variant).path_join(light_state)
	DirAccess.make_dir_recursive_absolute(absolute_dir)
	for view: Dictionary in views:
		await _capture_view(camera, view, variant, light_state, relative_dir, absolute_dir)
	room.free()


func _capture_view(camera: Camera3D, view: Dictionary, variant: String,
		light_state: String, relative_dir: String, absolute_dir: String) -> void:
	var position_array: Array = view["position"]
	var target_array: Array = view["target"]
	var position := Vector3(position_array[0], position_array[1], position_array[2])
	var target := Vector3(target_array[0], target_array[1], target_array[2])
	camera.position = position
	camera.look_at(target, Vector3.UP)
	for _frame in 6:
		await process_frame
	camera.look_at(target, Vector3.UP)
	for _frame in 18:
		await process_frame
	var image := root.get_texture().get_image()
	if image.is_empty():
		push_error("Capture viewport was empty for %s/%s/%s" % [variant, light_state, view["id"]])
		return
	var error := image.save_png(absolute_dir.path_join("%s.png" % view["id"]))
	if error != OK:
		push_error("Could not save capture %s/%s/%s (error %d)" % [variant, light_state, view["id"], error])
		return
	manifest_views.append({
		"variant": variant,
		"light_state": light_state,
		"id": view["id"],
		"path": relative_dir.path_join("%s.png" % view["id"]),
		"position": position_array,
		"target": target_array,
		"forward": _forward(camera),
		"fov_deg": camera.fov,
		"near": camera.near,
		"far": camera.far,
		"width": image.get_width(),
		"height": image.get_height(),
	})


func _forward(camera: Camera3D) -> Array:
	var direction := -camera.global_transform.basis.z
	return [direction.x, direction.y, direction.z]


func _write_manifest(absolute_output: String) -> void:
	var manifest := {
		"schema_version": 1,
		"record_id": "issue-272-lit-psx-captures-v1",
		"scenes": SCENES,
		"views_record": VIEWS_PATH,
		"shader_decision": DECISION_PATH,
		"renderer": "Godot Forward+ Vulkan; opt-in PSX shader variants, no PSX post-processing in this isolated fixture",
		"camera_settings": "InspectionCamera look_at(target, UP); fov/near/far and exact position/target recorded per view; identical for every variant and light state",
		"light_settings": "Directional key + colour ambient toggled together by set_light_on(bool); fog held at FOG_DISABLED throughout",
		"comparison": "Baseline vs lit and solid vs textured share every camera transform and light setting; only shader and light state differ",
		"registration_accepted": false,
		"scale_calibrated": false,
		"operator_review": "pending; agent does not approve appearance or lighting suitability",
		"views": manifest_views,
	}
	var file := FileAccess.open(absolute_output.path_join("capture_manifest_v1.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write paired capture manifest")
		return
	file.store_string(JSON.stringify(manifest, "\t") + "\n")


func _frames(count: int) -> void:
	for _index in count:
		await process_frame
