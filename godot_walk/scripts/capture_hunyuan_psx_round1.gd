extends SceneTree

const DEFAULT_SCENE_PATH := "res://scenes/hunyuan_psx_round1.tscn"
const SETTLE_FRAMES := 12
const VIEWS := [
	{"id": "patch_anchor", "station": "patch_anchor", "heading": 0,
		"position": [2.9209783, -0.1003, 3.703508], "forward": [-0.691, 0.0, -0.723]},
	{"id": "south_end", "station": "far_room", "heading": 0,
		"position": [-0.45, -0.1003, -4.0], "forward": [0.0, 0.0, 1.0]},
	{"id": "north_end", "station": "far_room", "heading": 180,
		"position": [-0.45, -0.1003, 7.8], "forward": [0.0, 0.0, -1.0]},
	{"id": "west_wall", "station": "transition", "heading": 270,
		"position": [-4.4, -0.1003, 1.9], "forward": [1.0, 0.0, 0.0]},
	{"id": "east_wall", "station": "transition", "heading": 90,
		"position": [3.5, -0.1003, 1.9], "forward": [-1.0, 0.0, 0.0]},
	{"id": "column_south", "station": "column", "heading": 180,
		"position": [-0.447, -0.1003, -2.74], "forward": [0.0, 0.0, 1.0]},
	{"id": "column_north", "station": "column", "heading": 0,
		"position": [-0.447, -0.1003, 3.39], "forward": [0.0, 0.0, -1.0]},
	{"id": "column_west", "station": "column", "heading": 270,
		"position": [-3.26, -0.1003, 0.323], "forward": [1.0, 0.0, 0.0]},
	{"id": "column_east", "station": "column", "heading": 90,
		"position": [2.37, -0.1003, 0.323], "forward": [-1.0, 0.0, 0.0]},
]

var variant_id := ""
var out_dir := ""
var scene_path := DEFAULT_SCENE_PATH


func _initialize() -> void:
	if not _parse_arguments():
		quit(2)
		return
	if out_dir.is_empty():
		out_dir = "res://evidence/2026-10-21-issue-151-round-1/captures/%s/repeat_1" % variant_id
	call_deferred("_capture_round")


func _parse_arguments() -> bool:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--variant="):
			variant_id = argument.get_slice("=", 1)
		elif argument.begins_with("--out="):
			out_dir = argument.get_slice("=", 1)
		elif argument.begins_with("--scene="):
			scene_path = argument.get_slice("=", 1)
	if variant_id not in ["preserve_hunyuan", "source_surface_cleanup", "column_box_source_face"]:
		printerr("Unknown Hunyuan PSX review variant: %s" % variant_id)
		return false
	return true


func _capture_round() -> void:
	var packed := load(scene_path) as PackedScene
	if packed == null:
		printerr("Cannot load candidate scene: %s" % scene_path)
		quit(1)
		return
	var scene := packed.instantiate()
	scene.set("variant_id", variant_id)
	root.add_child(scene)
	await process_frame
	if not bool(scene.get_meta("hunyuan_visual_loaded", false)):
		printerr("Hunyuan visual failed to load into candidate scene")
		quit(1)
		return
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player != null:
		player.set_physics_process(false)
		player.set_process(false)
	var camera := Camera3D.new()
	camera.name = "RoundCaptureCamera"
	camera.current = true
	camera.fov = 75.0
	root.add_child(camera)
	var absolute_out := ProjectSettings.globalize_path(out_dir)
	var image_dir := absolute_out.path_join("spawn_headings")
	if not _ensure_directory(image_dir):
		quit(1)
		return
	var captured: Array[String] = []
	for view in VIEWS:
		if not await _capture_view(camera, view, image_dir):
			quit(1)
			return
		captured.append(String(view.id))
	if not _write_capture_manifest(absolute_out, captured):
		quit(1)
		return
	print("HUNYUAN_PSX_CAPTURED: %s (%d views)" % [variant_id, captured.size()])
	quit()


func _capture_view(camera: Camera3D, view: Dictionary, directory: String) -> bool:
	var position := _vector_from_array(view.position)
	var forward := _vector_from_array(view.forward).normalized()
	camera.global_position = position
	camera.look_at(position + forward, Vector3.UP)
	for _frame in SETTLE_FRAMES:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := camera.get_viewport().get_texture().get_image()
	var path := directory.path_join("%s.png" % view.id)
	if image.is_empty() or image.save_png(path) != OK:
		printerr("Failed to save matched capture: %s" % path)
		return false
	return true


func _write_capture_manifest(directory: String, captured: Array[String]) -> bool:
	if captured.size() != VIEWS.size():
		printerr("Capture count does not match the fixed pose set")
		return false
	var captured_views: Array[Dictionary] = []
	for view in VIEWS:
		captured_views.append({
			"filename": "%s.png" % view.id,
			"station": view.station,
			"heading": view.heading,
			"camera_position": view.position,
			"camera_forward": view.forward,
		})
	var manifest := {
		"variant_id": variant_id,
		"resolution": [960, 540],
		"vertical_fov_degrees": 75.0,
		"settle_frames": SETTLE_FRAMES,
		"captured_view_ids": captured,
		"registration_accepted": false,
		"scale_calibrated": false,
		"views": captured_views,
	}
	var file := FileAccess.open(directory.path_join("frames.json"), FileAccess.WRITE)
	if file == null:
		printerr("Cannot write capture manifest: %s" % directory)
		return false
	file.store_string(JSON.stringify(manifest, "\t") + "\n")
	return true


func _ensure_directory(directory: String) -> bool:
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK and not DirAccess.dir_exists_absolute(directory):
		printerr("Cannot create capture directory: %s (%s)" % [directory, error])
		return false
	return true


func _vector_from_array(values: Array) -> Vector3:
	return Vector3(float(values[0]), float(values[1]), float(values[2]))
