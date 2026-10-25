extends SceneTree

const OUTPUT := "res://evidence/2026-10-22-issue-159-readiness"
const EYE_Y := -0.17099049
const VIEWS := [
	["V01_spawn", Vector2(-4.4, -4.0), Vector2(0.42, 1.05)],
	["V02_southeast", Vector2(3.5, -4.0), Vector2(0.42, 1.05)],
	["V03_northeast", Vector2(3.5, 7.8), Vector2(0.42, 1.05)],
	["V04_northwest", Vector2(-4.4, 7.8), Vector2(0.42, 1.05)],
	["V05_west", Vector2(-4.4, 1.9), Vector2(4.5, 1.9)],
	["V06_east", Vector2(3.5, 1.9), Vector2(-5.4, 1.9)],
	["V07_north_outward", Vector2(-0.45, 7.8), Vector2(-0.45, 12.0)],
	["V08_south_outward", Vector2(-0.45, -4.0), Vector2(-0.45, -9.0)],
	["V09_C02_front", Vector2(-2.0, 3.2), Vector2(-0.7, 4.45)],
	["V10_C02_reverse", Vector2(0.0, 5.6), Vector2(-0.7, 4.45)],
]


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var scene: Node3D = load("res://scenes/library_column_room.tscn").instantiate()
	root.add_child(scene)
	var player := scene.get_node("Player")
	player.set_physics_process(false)
	player.set_process(false)
	for child in player.get_children():
		if child is CanvasLayer:
			child.visible = false
	var camera := Camera3D.new()
	camera.fov = 75
	scene.add_child(camera)
	camera.make_current()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT + "/captures"))
	var records: Array = []
	for view: Array in VIEWS:
		if OS.get_cmdline_user_args().has("--close-only") and not view[0].begins_with("V09") and not view[0].begins_with("V10"):
			continue
		records.append(await _view(camera, view))
	var name := "close_manifest.json" if OS.get_cmdline_user_args().has("--close-only") else "capture_manifest.json"
	var file := FileAccess.open(OUTPUT + "/" + name, FileAccess.WRITE)
	if file == null:
		quit(2)
		return
	file.store_string(JSON.stringify(records, "\t") + "\n")
	print("READINESS_CAPTURE_COMPLETE")
	quit()


func _view(camera: Camera3D, view: Array) -> Dictionary:
	camera.global_position = Vector3(view[1].x, EYE_Y, view[1].y)
	var target := Vector3(view[2].x, EYE_Y, view[2].y)
	camera.look_at(target)
	for frame in 20:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var path: String = OUTPUT + "/captures/" + view[0] + ".png"
	if image.is_empty() or image.save_png(path) != OK:
		push_error("Cannot save " + path)
		quit(2)
	return {"id": view[0], "eye": [view[1].x, EYE_Y, view[1].y],
		"target": [target.x, target.y, target.z], "fov": camera.fov,
		"resolution": [image.get_width(), image.get_height()], "settle_frames": 20,
		"preset": "existing URSC enabled; native post enabled", "path": path}
