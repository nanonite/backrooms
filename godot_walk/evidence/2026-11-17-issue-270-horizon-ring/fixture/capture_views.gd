extends SceneTree

# Paired captures for issue 270: identical camera positions, targets and camera
# settings for the baseline (ring disabled) and the finite-ring variant. Views
# come from views_v1.json so they are recorded once and reused byte-for-byte.
# Invoked only through the existing guarded capture wrapper.
const BASELINE_SCENE := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/baseline_sky_v1.tscn"
const VARIANT_SCENE := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/horizon_ring_v1.tscn"
const VIEWS_PATH := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/views_v1.json"
const DEFAULT_OUTPUT := "res://evidence/2026-11-17-issue-270-horizon-ring/captures/paired_v1"

var output_path := DEFAULT_OUTPUT
var views: Array = []
var movement: Array = []
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
	if not _load_views():
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(absolute_output)
	await _capture_scene(absolute_output, "baseline", BASELINE_SCENE)
	await _capture_scene(absolute_output, "variant", VARIANT_SCENE)
	_write_manifest(absolute_output)
	print("ISSUE_270_PAIRED_CAPTURES_READY: ", output_path)
	quit(0)


func _load_views() -> bool:
	var file := FileAccess.open(VIEWS_PATH, FileAccess.READ)
	if file == null:
		printerr("Could not read views record: ", VIEWS_PATH)
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary or not parsed.has("views"):
		printerr("Views record is invalid: ", VIEWS_PATH)
		return false
	views = parsed["views"]
	movement = parsed.get("movement_sequence", {}).get("steps", [])
	return true


func _capture_scene(absolute_output: String, label: String, scene_path: String) -> void:
	var packed := load(scene_path) as PackedScene
	if packed == null:
		push_error("Could not load scene for capture: %s" % scene_path)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	var camera := room.get_node("InspectionCamera") as Camera3D
	var scene_output := absolute_output.path_join(label)
	DirAccess.make_dir_recursive_absolute(scene_output)
	for view: Dictionary in views:
		await _capture_view(camera, view, "view", label, output_path.path_join(label), scene_output)
	for step: Dictionary in movement:
		await _capture_view(camera, step, "movement", label, output_path.path_join(label), scene_output)
	room.free()


func _capture_view(camera: Camera3D, view: Dictionary, kind: String, label: String,
		relative_dir: String, absolute_dir: String) -> void:
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
		push_error("Capture viewport was empty for %s/%s" % [label, view["id"]])
		return
	var error := image.save_png(absolute_dir.path_join("%s.png" % view["id"]))
	if error != OK:
		push_error("Could not save capture %s/%s (error %d)" % [label, view["id"], error])
		return
	manifest_views.append({
		"variant": label,
		"kind": kind,
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
		"record_id": "issue-270-paired-captures-v1",
		"baseline_scene": BASELINE_SCENE,
		"variant_scene": VARIANT_SCENE,
		"views_record": VIEWS_PATH,
		"renderer": "Godot Forward+ Vulkan; static ProceduralSkyMaterial at infinity, finite unshaded silhouette ring in the variant only",
		"camera_settings": "InspectionCamera look_at(target, UP); fov/near/far and exact position/target recorded per view",
		"comparison": "translate_a and translate_b share one orientation; rotated holds translate_a position with a new orientation; movement walks the bounded path",
		"registration_accepted": false,
		"scale_calibrated": false,
		"operator_review": "pending; agent does not approve appearance or source interpretation",
		"views": manifest_views,
	}
	var file := FileAccess.open(absolute_output.path_join("capture_manifest_v1.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write paired capture manifest")
		return
	file.store_string(JSON.stringify(manifest, "\t") + "\n")
