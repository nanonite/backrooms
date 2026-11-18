extends SceneTree

# Paired captures for issue 269: identical camera positions for the baseline and
# the relief/shadow variant. Views come from views_v1.json so they are recorded
# once and reused byte-for-byte. Invoked only through the existing guarded wrapper.
const BASELINE_SCENE := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/baseline_relief_v1.tscn"
const VARIANT_SCENE := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/relief_shadows_v1.tscn"
const VIEWS_PATH := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/views_v1.json"
const DEFAULT_OUTPUT := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/captures/paired_v1"

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
	if not _load_views():
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(absolute_output)
	await _capture_scene(absolute_output, "baseline", BASELINE_SCENE)
	await _capture_scene(absolute_output, "variant", VARIANT_SCENE)
	_write_manifest(absolute_output)
	print("ISSUE_269_PAIRED_CAPTURES_READY: ", output_path)
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
	return true


func _capture_scene(absolute_output: String, label: String, scene_path: String) -> void:
	var packed := load(scene_path) as PackedScene
	if packed == null:
		push_error("Could not load scene for capture: %s" % scene_path)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	var player := room.get_node("Player") as CharacterBody3D
	var camera := room.get_node("Player/Head/Camera3D") as Camera3D
	player.set_physics_process(false)
	var scene_output := absolute_output.path_join(label)
	DirAccess.make_dir_recursive_absolute(scene_output)
	for view: Dictionary in views:
		await _capture_view(player, camera, view, label, output_path.path_join(label), scene_output)
	room.free()


func _capture_view(player: CharacterBody3D, camera: Camera3D, view: Dictionary,
		label: String, relative_dir: String, absolute_dir: String) -> void:
	var position_array: Array = view["position"]
	var target_array: Array = view["target"]
	var position := Vector3(position_array[0], position_array[1], position_array[2])
	var target := Vector3(target_array[0], target_array[1], target_array[2])
	player.global_position = position
	player.rotation = Vector3.ZERO
	player.get_node("Head").rotation = Vector3.ZERO
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
	var filename := "%s.png" % view["id"]
	var error := image.save_png(absolute_dir.path_join(filename))
	if error != OK:
		push_error("Could not save capture %s/%s (error %d)" % [label, view["id"], error])
		return
	manifest_views.append({
		"variant": label,
		"id": view["id"],
		"path": relative_dir.path_join(filename),
		"position": position_array,
		"target": target_array,
		"width": image.get_width(),
		"height": image.get_height(),
	})


func _write_manifest(absolute_output: String) -> void:
	var manifest := {
		"schema_version": 1,
		"record_id": "issue-269-paired-captures-v1",
		"baseline_scene": BASELINE_SCENE,
		"variant_scene": VARIANT_SCENE,
		"views_record": VIEWS_PATH,
		"renderer": "Godot Forward+ Vulkan; unshaded materials with baked vertex-colour relief and authored shadow polygons in the variant only",
		"registration_accepted": false,
		"scale_calibrated": false,
		"operator_review": "pending; agent does not approve appearance or catalog admission",
		"views": manifest_views,
	}
	var file := FileAccess.open(absolute_output.path_join("capture_manifest_v1.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write paired capture manifest")
		return
	file.store_string(JSON.stringify(manifest, "\t") + "\n")
