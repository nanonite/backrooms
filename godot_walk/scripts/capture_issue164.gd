extends SceneTree

const WALKTHROUGH := "res://scenes/issue164_three_room_walkthrough.tscn"
const OUTPUT := "res://evidence/2026-10-24-issue-164/captures"
const FLOOR_Y := -1.27099049
const EYE_Y := FLOOR_Y + 1.1

var records: Array[Dictionary] = []
var load_time_ms := 0


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var started := Time.get_ticks_msec()
	var packed := load(WALKTHROUGH) as PackedScene
	if packed == null:
		printerr("Cannot load #164 walkthrough scene")
		quit(2)
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	for frame in 240:
		if scene.get_meta("walkthrough_ready", false):
			break
		await process_frame
	if not scene.get_meta("walkthrough_ready", false):
		printerr("#164 walkthrough did not become ready before capture timeout")
		quit(2)
		return
	load_time_ms = Time.get_ticks_msec() - started
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player != null:
		player.set_physics_process(false)
		player.set_process(false)
		for child: Node in player.get_children():
			if child is CanvasLayer:
				child.visible = false
	var camera := Camera3D.new()
	camera.name = "Issue164ReviewCamera"
	camera.fov = 75.0
	scene.add_child(camera)
	camera.make_current()
	for view: Dictionary in _views():
		records.append(await _capture_view(camera, view))
	_write_manifest()
	print("ISSUE164_CAPTURE_COMPLETE views=%d ready_ms=%d" % [records.size(), load_time_ms])
	quit()


func _views() -> Array[Dictionary]:
	return [
		_view("pocket_to_new_room", Vector3(8.35, EYE_Y, 3.1), Vector3(11.4, EYE_Y, 3.1)),
		_view("new_room_to_pocket", Vector3(10.7, EYE_Y, 3.1), Vector3(7.65, EYE_Y, 3.1)),
		_view("large_room_hall_entry", Vector3(18.0, EYE_Y + 0.1, 1.6), Vector3(11.0, EYE_Y, 3.1)),
		_view("large_room_column_and_hall", Vector3(20.0, EYE_Y, -0.2), Vector3(15.3, EYE_Y, 2.2)),
	]


func _view(view_id: String, eye: Vector3, target: Vector3) -> Dictionary:
	return {"id": view_id, "eye": eye, "target": target}


func _capture_view(camera: Camera3D, view: Dictionary) -> Dictionary:
	camera.global_position = view.eye
	camera.look_at(view.target, Vector3.UP)
	for frame in 24:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var path := OUTPUT.path_join("%s.png" % view.id)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	if image.is_empty() or image.save_png(ProjectSettings.globalize_path(path)) != OK:
		push_error("Cannot save #164 capture: %s" % path)
	return {
		"id": view.id,
		"path": path,
		"eye": [view.eye.x, view.eye.y, view.eye.z],
		"target": [view.target.x, view.target.y, view.target.z],
		"width": image.get_width(),
		"height": image.get_height(),
		"scene_ready_ms": load_time_ms,
	}


func _write_manifest() -> void:
	var path := "res://evidence/2026-10-24-issue-164/capture_manifest.json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write #164 capture manifest")
		return
	file.store_string(JSON.stringify({
		"issue": 164,
		"layout": "layout_three_room.json",
		"scene": WALKTHROUGH,
		"scene_ready_ms": load_time_ms,
		"camera_fov_degrees": 75.0,
		"settle_frames": 24,
		"views": records,
	}, "\t") + "\n")
