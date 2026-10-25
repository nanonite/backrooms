extends "res://scripts/capture_hunyuan_psx_round3.gd"


func _instantiate_variant(variant: String) -> Node3D:
	var scene := load("res://scenes/hunyuan_psx_column_box.tscn").instantiate() as Node3D
	var candidate := "four_sided_box" if variant == "column_face_extrusion" else variant
	scene.set("variant_id", candidate)
	root.add_child(scene)
	for _frame_index in SETTLE_FRAMES:
		await process_frame
	if not bool(scene.get_meta("hunyuan_visual_loaded", false)):
		push_error("Hunyuan visual missing")
		return null
	if candidate == "four_sided_box" and not bool(scene.get_meta("column_face_texture_loaded", false)):
		push_error("Accepted source-face texture missing")
		return null
	var player := scene.get_node("Player") as CharacterBody3D
	player.set_physics_process(false)
	player.set_process(false)
	return scene


func _view_record(view: Dictionary, variant: String) -> Dictionary:
	var record := super._view_record(view, variant)
	if variant == "column_face_extrusion":
		record.variant_id = "four_sided_box"
	return record


func _capture_view(camera: Camera3D, view: Dictionary, variant: String,
		out_dir: String) -> bool:
	var candidate := "four_sided_box" if variant == "column_face_extrusion" else variant
	return await super._capture_view(camera, view, candidate, out_dir)


func _ensure_directory(directory: String) -> bool:
	for variant in ["preserve_hunyuan", "four_sided_box"]:
		var error := DirAccess.make_dir_recursive_absolute(directory.path_join(variant))
		if error != OK:
			push_error("Cannot create column-box capture directory: %s" % error)
			return false
	return true


func _write_manifest(out_dir: String, records: Array[Dictionary]) -> bool:
	var file := FileAccess.open(out_dir.path_join("capture_manifest.json"), FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify({
		"round_id": "hunyuan-psx-column-box-review",
		"issue": 151,
		"status": "candidate_not_selected",
		"registration_accepted": false,
		"scale_calibrated": false,
		"candidate_capture_directory": "four_sided_box",
		"views": records,
	}, "\t") + "\n")
	return true
