extends SceneTree

# Deterministic paired-capture harness for issue 273. The exact same view and
# walk-path constants are used for the v1 baseline and the v2 variant; only the
# --scene argument differs. Camera poses are written to the manifest so a
# read-only verifier can prove the two runs are matched.

const DEFAULT_SCENE := "res://source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v2/room.tscn"
const VIEWS := [
	{"id": "spawn_up_corridor", "position": Vector3(0.0, 0.6, -7.0), "target": Vector3(0.0, 3.0, 6.0)},
	{"id": "bend_turn", "position": Vector3(1.5, 0.6, 3.5), "target": Vector3(8.0, 3.0, 5.0)},
	{"id": "west_wall_strata", "position": Vector3(-1.0, 0.6, -2.0), "target": Vector3(-4.0, 4.0, 1.0)},
	{"id": "open_sky_slot", "position": Vector3(0.0, 0.6, 0.0), "target": Vector3(0.0, 7.0, 1.5)},
]
const WALK_PATH := [
	{"id": "walk_00_spawn", "position": Vector3(0.0, 0.6, -7.0), "target": Vector3(0.0, 3.0, 6.0)},
	{"id": "walk_01_forward", "position": Vector3(0.0, 0.6, -4.0), "target": Vector3(0.0, 3.0, 6.0)},
	{"id": "walk_02_mid", "position": Vector3(0.8, 0.6, -1.0), "target": Vector3(4.0, 3.0, 2.0)},
	{"id": "walk_03_bend", "position": Vector3(2.0, 0.6, 3.5), "target": Vector3(8.0, 3.0, 5.0)},
	{"id": "walk_04_bend_exit", "position": Vector3(6.0, 0.6, 4.5), "target": Vector3(10.0, 3.0, 6.0)},
]

var scene_path := DEFAULT_SCENE
var output_path := ""
var views_written: Array[Dictionary] = []
var walk_written: Array[Dictionary] = []


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--scene="):
			scene_path = argument.trim_prefix("--scene=")
		elif argument.begins_with("--out="):
			output_path = argument.trim_prefix("--out=")
	if output_path.is_empty():
		printerr("An --out= path is required")
		quit(2)
		return
	call_deferred("_capture")


func _capture() -> void:
	var absolute_output := ProjectSettings.globalize_path(output_path)
	if DirAccess.dir_exists_absolute(absolute_output) or FileAccess.file_exists(absolute_output):
		printerr("Refusing to overwrite capture output: ", output_path)
		quit(2)
		return
	var packed := load(scene_path) as PackedScene
	if packed == null:
		printerr("Could not load candidate room scene: ", scene_path)
		quit(1)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	var player := room.get_node("Player") as CharacterBody3D
	var camera := room.get_node("Player/Head/Camera3D") as Camera3D
	player.set_physics_process(false)
	DirAccess.make_dir_recursive_absolute(absolute_output)
	await _settle()
	for view: Dictionary in VIEWS:
		await _capture_view(player, camera, view, absolute_output, views_written)
	for step: Dictionary in WALK_PATH:
		await _capture_view(player, camera, step, absolute_output, walk_written)
	_write_manifest(absolute_output, camera)
	print("ISSUE_273_PAIRED_CAPTURES_READY: ", output_path)
	quit(0)


func _settle() -> void:
	for _frame in 120:
		await process_frame


func _capture_view(player: CharacterBody3D, camera: Camera3D, view: Dictionary, absolute_output: String, target: Array[Dictionary]) -> void:
	player.global_position = view["position"]
	camera.look_at(view["target"], Vector3.UP)
	for _frame in 18:
		await process_frame
	# Re-orient after the transform settles; issue 255 recorded an occluded
	# first capture when look_at was applied before the frame settle.
	camera.look_at(view["target"], Vector3.UP)
	await process_frame
	var image := root.get_texture().get_image()
	if image.is_empty():
		push_error("Capture viewport was empty for %s" % view["id"])
		return
	var error := image.save_png(absolute_output.path_join("%s.png" % view["id"]))
	if error != OK:
		push_error("Could not save capture %s (error %d)" % [view["id"], error])
		return
	target.append({
		"id": view["id"],
		"path": output_path.path_join("%s.png" % view["id"]),
		"position": _vector(view["position"]),
		"target": _vector(view["target"]),
		"width": image.get_width(),
		"height": image.get_height(),
	})


func _vector(value: Vector3) -> Array[float]:
	return [value.x, value.y, value.z]


func _write_manifest(absolute_output: String, camera: Camera3D) -> void:
	var manifest := {
		"scene": scene_path,
		"renderer": "Godot Forward+ Vulkan with the project PSX compositor",
		"panorama_role": "camera-centered background visual; no spatial parallax",
		"camera": {"fov_degrees": camera.fov, "near": camera.near, "far": camera.far, "basis": "Player/Head/Camera3D from the hash-pinned player.tscn"},
		"registration_accepted": false,
		"scale_calibrated": false,
		"views": views_written,
		"walk_path": walk_written,
	}
	var file := FileAccess.open(absolute_output.path_join("capture_manifest.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write capture manifest")
		return
	file.store_string(JSON.stringify(manifest, "\t") + "\n")
