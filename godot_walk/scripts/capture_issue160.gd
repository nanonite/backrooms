extends SceneTree

const OUTPUT := "res://evidence/2026-10-22-issue-160"
const EYE_Y := -0.17099049
const VIEW_SETS := [
	{
		"room": "column",
		"scene": "res://scenes/issue160_bounded_column_room.tscn",
		"views": [
			["spawn_to_C01", Vector3(-3.5, EYE_Y, 0.0), Vector3(0.42, EYE_Y, 1.05)],
			["C01_west", Vector3(-1.5, EYE_Y, 1.05), Vector3(0.42, EYE_Y, 1.05)],
			["C01_north", Vector3(0.42, EYE_Y, 3.8), Vector3(0.42, EYE_Y, 1.05)],
			["C02_front", Vector3(-2.0, EYE_Y, 3.2), Vector3(-0.7125, EYE_Y, 4.425)],
			["C02_reverse", Vector3(0.0, EYE_Y, 5.2), Vector3(-0.7125, EYE_Y, 4.425)],
			["east_socket_closed", Vector3(2.5, EYE_Y, 3.1), Vector3(3.5, EYE_Y, 3.1)],
		],
	},
	{
		"room": "pocket",
		"scene": "res://scenes/issue160_bounded_pocket_room.tscn",
		"views": [
			["entry", Vector3(0.8, EYE_Y, 0.8), Vector3(5.2, EYE_Y, 0.8)],
			["far_end", Vector3(5.2, EYE_Y, 13.0), Vector3(0.8, EYE_Y, 13.0)],
			["west_socket_closed", Vector3(1.0, EYE_Y, 6.9), Vector3(0.0, EYE_Y, 6.9)],
			["east_wall", Vector3(5.0, EYE_Y, 6.9), Vector3(6.0, EYE_Y, 6.9)],
		],
	},
	{
		"room": "assembly",
		"scene": "res://scenes/issue160_assembled_walkthrough.tscn",
		"views": [
			["column_approach", Vector3(2.5, EYE_Y, 3.1), Vector3(4.3, EYE_Y, 3.1)],
			["connector_midpoint", Vector3(3.5, EYE_Y, 3.1), Vector3(5.2, EYE_Y, 3.1)],
			["pocket_return", Vector3(4.3, EYE_Y, 3.1), Vector3(2.2, EYE_Y, 3.1)],
			["pocket_far", Vector3(8.7, EYE_Y, 9.0), Vector3(4.3, EYE_Y, 9.2)],
			["seam_floor", Vector3(3.1, FLOOR_Y + 0.35, 3.1), Vector3(3.9, FLOOR_Y + 0.35, 3.1)],
		],
	},
]
const FLOOR_Y := -1.27099049
var records: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	for set_data: Dictionary in VIEW_SETS:
		await _capture_set(set_data)
	var file := FileAccess.open(OUTPUT + "/capture_manifest.json", FileAccess.WRITE)
	if file == null:
		printerr("Cannot write issue #160 capture manifest")
		quit(2)
		return
	file.store_string(JSON.stringify(records, "\t") + "\n")
	print("ISSUE160_CAPTURE_COMPLETE views=", records.size())
	quit()


func _capture_set(set_data: Dictionary) -> void:
	var scene_path: String = set_data.scene
	var started := Time.get_ticks_msec()
	var scene := (load(scene_path) as PackedScene).instantiate() as Node3D
	root.add_child(scene)
	await process_frame
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player != null:
		player.set_physics_process(false)
		player.set_process(false)
		for child in player.get_children():
			if child is CanvasLayer:
				child.visible = false
	var camera := Camera3D.new()
	camera.name = "Issue160CaptureCamera"
	camera.fov = 75.0
	scene.add_child(camera)
	camera.make_current()
	var ready_ms := Time.get_ticks_msec() - started
	for view: Array in set_data.views:
		records.append(await _capture_view(camera, set_data.room, scene_path, view, ready_ms))
	scene.queue_free()
	await process_frame


func _capture_view(camera: Camera3D, room: String, scene_path: String,
		view: Array, ready_ms: int) -> Dictionary:
	var eye: Vector3 = view[1]
	var target: Vector3 = view[2]
	camera.global_position = eye
	camera.look_at(target, Vector3.UP)
	for frame in 24:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var directory := "%s/captures/%s" % [OUTPUT, room]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var path := "%s/%s.png" % [directory, view[0]]
	if image.is_empty() or image.save_png(ProjectSettings.globalize_path(path)) != OK:
		push_error("Cannot save issue #160 capture: %s" % path)
		quit(2)
	return {
		"room": room,
		"id": view[0],
		"scene": scene_path,
		"eye": _coordinates(eye),
		"target": _coordinates(target),
		"fov": camera.fov,
		"resolution": [image.get_width(), image.get_height()],
		"settle_frames": 24,
		"scene_load_to_ready_ms": ready_ms,
		"psx_preset": "URSC 1.5 subset / existing compositor",
		"path": path,
	}


func _coordinates(point: Vector3) -> Array:
	return [point.x, point.y, point.z]
