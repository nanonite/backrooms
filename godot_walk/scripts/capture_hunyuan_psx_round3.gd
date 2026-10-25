extends SceneTree

const SCENE_PATH := "res://scenes/hunyuan_psx_round3.tscn"
const SETTLE_FRAMES := 20
const VARIANTS := ["preserve_hunyuan", "column_face_extrusion"]
const VIEWS := [
	{
		"id": "patch_anchor",
		"position": Vector3(2.9209783, -0.1003, 3.703508),
		"forward": Vector3(-0.691, 0.0, -0.723),
	},
	{
		"id": "column_east",
		"position": Vector3(2.37, -0.1003, 0.323),
		"forward": Vector3(-1.0, 0.0, 0.0),
	},
]


func _initialize() -> void:
	call_deferred("_capture_round")


func _capture_round() -> void:
	var out_dir := _output_directory()
	if out_dir.is_empty() or not _ensure_directory(out_dir):
		quit(2)
		return
	var camera := Camera3D.new()
	camera.name = "Round3CaptureCamera"
	camera.fov = 75.0
	camera.current = true
	root.add_child(camera)
	var records: Array[Dictionary] = []
	for variant in VARIANTS:
		var scene := await _instantiate_variant(variant)
		if scene == null:
			quit(1)
			return
		for view in VIEWS:
			if not await _capture_view(camera, view, variant, out_dir):
				quit(1)
				return
			records.append(_view_record(view, variant))
		scene.queue_free()
		await process_frame
	if not _write_manifest(out_dir, records):
		quit(1)
		return
	print("HUNYUAN_PSX_ROUND3_CAPTURED: %s" % out_dir)
	quit()


func _output_directory() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			return ProjectSettings.globalize_path(argument.get_slice("=", 1))
	return ""


func _instantiate_variant(variant: String) -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		push_error("Cannot load Hunyuan round 3 scene: %s" % SCENE_PATH)
		return null
	var scene := packed.instantiate() as Node3D
	scene.set("variant_id", variant)
	root.add_child(scene)
	for _frame in SETTLE_FRAMES:
		await process_frame
	if not bool(scene.get_meta("hunyuan_visual_loaded", false)):
		push_error("Hunyuan visual did not load for variant: %s" % variant)
		return null
	if variant == "column_face_extrusion" and not bool(scene.get_meta("column_face_texture_loaded", false)):
		push_error("Source-face material did not load for variant: %s" % variant)
		return null
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player != null:
		player.set_physics_process(false)
		player.set_process(false)
	return scene


func _capture_view(camera: Camera3D, view: Dictionary, variant: String,
		out_dir: String) -> bool:
	var position: Vector3 = view.position
	var forward: Vector3 = view.forward.normalized()
	camera.make_current()
	camera.global_position = position
	camera.look_at(position + forward, Vector3.UP)
	for _frame in SETTLE_FRAMES:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := camera.get_viewport().get_texture().get_image()
	var destination := out_dir.path_join(variant).path_join("%s.png" % view.id)
	if image.is_empty() or image.save_png(destination) != OK:
		push_error("Failed to save Hunyuan round 3 view: %s" % destination)
		return false
	return true


func _view_record(view: Dictionary, variant: String) -> Dictionary:
	return {
		"variant_id": variant,
		"view_id": view.id,
		"position": [view.position.x, view.position.y, view.position.z],
		"forward": [view.forward.x, view.forward.y, view.forward.z],
		"resolution": [960, 540],
		"settle_frames": SETTLE_FRAMES,
	}


func _write_manifest(out_dir: String, records: Array[Dictionary]) -> bool:
	var document := {
		"round_id": "hunyuan-psx-r3",
		"issue": 151,
		"registration_accepted": false,
		"scale_calibrated": false,
		"views": records,
	}
	var file := FileAccess.open(out_dir.path_join("capture_manifest.json"), FileAccess.WRITE)
	if file == null:
		push_error("Cannot write round 3 capture manifest")
		return false
	file.store_string(JSON.stringify(document, "\t") + "\n")
	return true


func _ensure_directory(directory: String) -> bool:
	var error := DirAccess.make_dir_recursive_absolute(directory)
	if error != OK and not DirAccess.dir_exists_absolute(directory):
		push_error("Cannot create capture directory: %s (%s)" % [directory, error])
		return false
	for variant in VARIANTS:
		var variant_directory := directory.path_join(variant)
		error = DirAccess.make_dir_recursive_absolute(variant_directory)
		if error != OK and not DirAccess.dir_exists_absolute(variant_directory):
			push_error("Cannot create variant capture directory: %s" % variant_directory)
			return false
	return true
