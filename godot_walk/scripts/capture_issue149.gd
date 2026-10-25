extends SceneTree

const OUTPUT := "res://evidence/2026-10-22-issue-149"
const FLOOR_Y := -1.27099049
const EYE_Y := FLOOR_Y + 1.1
const GENERATED_SCENE := "res://scenes/issue149_generated_walkthrough.tscn"
const REFERENCE_SCENE := "res://scenes/issue160_assembled_walkthrough.tscn"

var records: Array[Dictionary] = []
var layout: Dictionary = {}
var layout_path := "res://evidence/2026-10-22-issue-149/layout_seed_149.json"


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--layout="):
			layout_path = argument.trim_prefix("--layout=")
	call_deferred("_capture")


func _capture() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(layout_path))
	if not parsed is Dictionary:
		printerr("Invalid #149 layout for capture: %s" % layout_path)
		quit(2)
		return
	layout = parsed
	await _capture_set("issue160-regression", REFERENCE_SCENE, _reference_views())
	await _capture_set("seed-149", GENERATED_SCENE, _generated_views())
	var manifest := FileAccess.open(OUTPUT + "/capture_manifest.json", FileAccess.WRITE)
	if manifest == null:
		printerr("Cannot write #149 capture manifest")
		quit(2)
		return
	manifest.store_string(JSON.stringify(records, "\t") + "\n")
	print("ISSUE149_CAPTURE_COMPLETE views=%d layout=%s" % [records.size(), layout.layout_id])
	quit()


func _reference_views() -> Array[Dictionary]:
	return [
		_view("accepted_pair_column_to_pocket", Vector3(2.5, EYE_Y, 3.1), Vector3(5.2, EYE_Y, 3.1)),
		_view("accepted_pair_pocket_return", Vector3(4.3, EYE_Y, 3.1), Vector3(2.4, EYE_Y, 3.1)),
		_view("accepted_pair_pocket_far_end", Vector3(8.7, EYE_Y, 9.0), Vector3(4.3, EYE_Y, 9.2)),
	]


func _generated_views() -> Array[Dictionary]:
	var branch_id: String = layout.topology.branch_instance_id
	var branch: Dictionary = _placement(branch_id)
	var side_leaf: Dictionary = _placements_by_module("godot_early_pocket_single_west_v1")[0]
	var terminal: Dictionary = _placements_by_module("godot_early_pocket_single_west_v1")[-1]
	var first: Dictionary = _placement("R001")
	var second: Dictionary = _placement("R002")
	var final_trunk: Dictionary = _placement("R008")
	var views: Array[Dictionary] = []
	views.append(_view("seed_start_connector", Vector3(2.5, EYE_Y, 3.1), Vector3(5.2, EYE_Y, 3.1)))
	views.append(_view("seed_pass_through", _world_point(first, [5.0, 6.9]),
		_world_point(second, [1.0, 6.9])))
	views.append(_view("seed_branch_opening", _world_point(branch, [3.0, 6.9]),
		_world_point(branch, [3.0, 12.0])))
	views.append(_view("seed_branch_dead_end", _world_point(side_leaf, [0.8, 6.9]),
		_world_point(side_leaf, [3.0, 6.9])))
	views.append(_view("seed_terminal_dead_end", _world_point(terminal, [0.8, 6.9]),
		_world_point(terminal, [5.2, 6.9])))
	views.append(_view("seed_branch_return_to_trunk", _world_point(branch, [3.0, 6.9]),
		_world_point(final_trunk, [2.0, 6.9])))
	return views


func _view(label: String, eye: Vector3, target: Vector3) -> Dictionary:
	return {"id": label, "eye": eye, "target": target}


func _capture_set(group: String, scene_path: String, views: Array[Dictionary]) -> void:
	var started := Time.get_ticks_msec()
	var packed := load(scene_path) as PackedScene
	if packed == null:
		push_error("Cannot load capture scene: %s" % scene_path)
		quit(2)
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	if scene_path == GENERATED_SCENE:
		for frame in 180:
			if scene.get_meta("walkthrough_ready", false):
				break
			await process_frame
	else:
		await process_frame
	if scene_path == GENERATED_SCENE and not scene.get_meta("walkthrough_ready", false):
		push_error("Generated walkthrough did not initialize before capture")
		quit(2)
		return
	var player := scene.find_child("Player", true, false) as CharacterBody3D
	if player != null:
		player.set_physics_process(false)
		player.set_process(false)
		for child: Node in player.get_children():
			if child is CanvasLayer:
				child.visible = false
	var camera := Camera3D.new()
	camera.name = "Issue149CaptureCamera"
	camera.fov = 75.0
	scene.add_child(camera)
	camera.make_current()
	var ready_ms := Time.get_ticks_msec() - started
	for view: Dictionary in views:
		records.append(await _capture_view(camera, group, scene_path, view, ready_ms))
	scene.queue_free()
	await process_frame


func _capture_view(camera: Camera3D, group: String, scene_path: String,
		view: Dictionary, ready_ms: int) -> Dictionary:
	var eye: Vector3 = view.eye
	var target: Vector3 = view.target
	camera.global_position = eye
	camera.look_at(target, Vector3.UP)
	for frame in 24:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var relative := "%s/captures/%s/%s.png" % [OUTPUT, group, view.id]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(relative.get_base_dir()))
	if image.is_empty() or image.save_png(ProjectSettings.globalize_path(relative)) != OK:
		push_error("Cannot save #149 capture: %s" % relative)
		quit(2)
	return {
		"group": group,
		"id": view.id,
		"scene": scene_path,
		"layout_id": layout.layout_id if group == "seed-149" else "issue160_assembled_walkthrough",
		"eye": _coordinates(eye),
		"target": _coordinates(target),
		"fov": camera.fov,
		"resolution": [image.get_width(), image.get_height()],
		"settle_frames": 24,
		"scene_load_to_ready_ms": ready_ms,
		"psx_preset": "URSC 1.5 subset / existing compositor",
		"path": relative,
	}


func _placement(instance_id: String) -> Dictionary:
	for placement: Dictionary in layout.placements:
		if placement.instance_id == instance_id:
			return placement
	return {}


func _placements_by_module(module_id: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for placement: Dictionary in layout.placements:
		if placement.module_id == module_id:
			result.append(placement)
	return result


func _world_point(placement: Dictionary, local_xz: Array) -> Vector3:
	var yaw := int(placement.transform.yaw_degrees) % 360
	var local := Vector2(local_xz[0], local_xz[1])
	var rotated := local.rotated(deg_to_rad(-float(yaw)))
	var origin: Array = placement.transform.position
	return Vector3(origin[0] + rotated.x, EYE_Y, origin[2] + rotated.y)


func _coordinates(point: Vector3) -> Array:
	return [point.x, point.y, point.z]
