extends SceneTree

const EVIDENCE := "res://evidence/2026-10-13-bounded-psx/"
var scene: Node3D
var camera: Camera3D
var diagnostic := false
var baseline := false
var metadata: Array = []


func _initialize() -> void:
	diagnostic = OS.get_cmdline_user_args().has("--diagnostic")
	baseline = OS.get_cmdline_user_args().has("--baseline")
	call_deferred("_capture_all")


func _capture_all() -> void:
	var scene_name := "corridor_psx" if baseline else "corridor_bounded_psx"
	scene = load("res://scenes/%s.tscn" % scene_name).instantiate()
	root.add_child(scene)
	await physics_frame
	var player: CharacterBody3D = scene.get_node("Player")
	player.set_physics_process(false)
	camera = Camera3D.new()
	camera.fov = player.get_node("Head/Camera3D").fov
	scene.add_child(camera)
	camera.current = true
	if diagnostic:
		var effects: Array = scene.get_node("WorldEnvironment").compositor.compositor_effects
		effects[0].debug_view = 5
		effects[1].enabled = false
		await _diagnostics()
	else:
		await _sweeps()
	var folder := "diagnostic" if diagnostic else ("sweep_baseline" if baseline else "sweep_candidate")
	var file := FileAccess.open(EVIDENCE + folder + "/frames.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(metadata, "\t") + "\n")
	print("CAPTURED %s: %d frames" % [folder, metadata.size()])
	quit()


func _diagnostics() -> void:
	var points: Array = JSON.parse_string(FileAccess.get_file_as_string(EVIDENCE + "route_positions.json"))
	for point in points:
		var eye: Array = point.eye
		camera.position = Vector3(eye[0], eye[1], eye[2])
		for index in range(8):
			var yaw := -90.0 - float(index) * 45.0
			camera.rotation_degrees = Vector3(0, yaw, 0)
			await _save("diagnostic", point.id, index, 0, 200)


func _sweeps() -> void:
	var points: Array = JSON.parse_string(FileAccess.get_file_as_string(EVIDENCE + "boundary_positions.json"))
	var folder := "sweep_baseline" if baseline else "sweep_candidate"
	for point_index in [0, 2, 4, 7]:
		var point: Dictionary = points[point_index]
		var eye: Array = point.eye
		camera.position = Vector3(eye[0], eye[1], eye[2])
		for pitch in [-60, 0, 60]:
			for angle in range(24):
				for intermediate in range(15):
					camera.rotation_degrees = Vector3(pitch, -angle * 15 - intermediate, 0)
					await process_frame
				await _save(folder, point.id, angle * 15 + 14, pitch, 20)


func _save(folder: String, point: String, yaw: int, pitch: int, settle: int) -> void:
	for frame in range(settle):
		await process_frame
	await RenderingServer.frame_post_draw
	var directory := EVIDENCE + folder
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var filename := "%s_yaw%d_pitch%d.png" % [point, yaw, pitch]
	var error := root.get_texture().get_image().save_png(ProjectSettings.globalize_path(directory + "/" + filename))
	if error != OK:
		printerr("Could not write sweep capture: %s" % filename)
		quit(1)
	metadata.append({"filename": filename, "point": point, "yaw": yaw, "pitch": pitch,
		"eye": [camera.position.x, camera.position.y, camera.position.z], "fov": camera.fov})
