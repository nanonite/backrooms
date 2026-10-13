extends SceneTree

const DEFAULT_EVIDENCE := "res://evidence/2026-10-13-bounded-psx"
const DEFAULT_STATIONS := [0, 2, 4, 7]
var scene: Node3D
var camera: Camera3D
var diagnostic := false
var baseline := false
var metadata: Array = []
var scene_path := ""
var evidence_dir := DEFAULT_EVIDENCE
var positions_dir := ""
var positions_kind := "boundary"
var station_indices: Array = DEFAULT_STATIONS.duplicate()
var stations_explicit := false
var settle_frames := 20
var hide_node_path := ""


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument == "--diagnostic":
			diagnostic = true
		elif argument == "--baseline":
			baseline = true
		elif argument.begins_with("--scene="):
			scene_path = argument.get_slice("=", 1)
		elif argument.begins_with("--out-dir="):
			evidence_dir = argument.get_slice("=", 1)
		elif argument.begins_with("--positions-dir="):
			positions_dir = argument.get_slice("=", 1)
		elif argument.begins_with("--positions="):
			positions_kind = argument.get_slice("=", 1)
		elif argument.begins_with("--stations="):
			if not _parse_stations(argument.get_slice("=", 1)):
				printerr("Invalid --stations list")
				quit(1)
				return
			stations_explicit = true
		elif argument.begins_with("--settle="):
			settle_frames = maxi(0, int(argument.get_slice("=", 1)))
		elif argument.begins_with("--hide-node="):
			hide_node_path = argument.get_slice("=", 1)
	if positions_kind not in ["route", "boundary"]:
		printerr("--positions must be route or boundary")
		quit(1)
		return
	call_deferred("_capture_all")


func _capture_all() -> void:
	var default_scene := "corridor_psx" if baseline else "corridor_bounded_psx"
	var selected_scene := scene_path if scene_path != "" else "res://scenes/%s.tscn" % default_scene
	var packed := load(selected_scene) as PackedScene
	if packed == null:
		printerr("Could not load sweep scene: %s" % selected_scene)
		quit(1)
		return
	scene = packed.instantiate()
	root.add_child(scene)
	await physics_frame
	var player: CharacterBody3D = scene.get_node("Player")
	player.set_physics_process(false)
	if not _hide_requested_node():
		quit(1)
		return
	camera = Camera3D.new()
	camera.fov = player.get_node("Head/Camera3D").fov
	scene.add_child(camera)
	camera.current = true
	var folder := _evidence_folder(selected_scene)
	if diagnostic:
		var effects: Array = scene.get_node("WorldEnvironment").compositor.compositor_effects
		effects[0].debug_view = 5
		effects[1].enabled = false
		await _diagnostics(folder)
	else:
		await _sweeps(folder)
	var file := FileAccess.open(evidence_dir.path_join(folder).path_join("frames.json"), FileAccess.WRITE)
	if file == null:
		printerr("Could not write sweep metadata")
		quit(1)
		return
	file.store_string(JSON.stringify(metadata, "\t") + "\n")
	print("CAPTURED %s: %d frames" % [folder, metadata.size()])
	quit()


func _diagnostics(folder: String) -> void:
	var points := _load_positions("route")
	var selected_indices: Array = range(points.size())
	if stations_explicit:
		selected_indices = station_indices
	for point_index in selected_indices:
		if point_index < 0 or point_index >= points.size():
			printerr("Diagnostic station %d is outside the route position list" % point_index)
			quit(1)
			return
		var point: Dictionary = points[point_index]
		var eye: Array = point.eye
		camera.position = Vector3(eye[0], eye[1], eye[2])
		for index in range(8):
			var yaw := -90.0 - float(index) * 45.0
			camera.rotation_degrees = Vector3(0, yaw, 0)
			await _save(folder, point.id, index, 0, 200)


func _sweeps(folder: String) -> void:
	var points := _load_positions(positions_kind)
	if points.is_empty():
		printerr("No %s positions found under %s" % [positions_kind, evidence_dir])
		quit(1)
		return
	for point_index in station_indices:
		if point_index < 0 or point_index >= points.size():
			printerr("Sweep station %d is outside the %s position list" % [point_index, positions_kind])
			quit(1)
			return
		var point: Dictionary = points[point_index]
		var eye: Array = point.eye
		camera.position = Vector3(eye[0], eye[1], eye[2])
		for pitch in [-60, 0, 60]:
			for angle in range(24):
				for intermediate in range(15):
					camera.rotation_degrees = Vector3(pitch, -angle * 15 - intermediate, 0)
					await process_frame
				await _save(folder, point.id, angle * 15 + 14, pitch, settle_frames)


func _save(folder: String, point: String, yaw: int, pitch: int, settle: int) -> void:
	for frame in range(settle):
		await process_frame
	await RenderingServer.frame_post_draw
	var directory := evidence_dir.path_join(folder)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
	var filename := "%s_yaw%d_pitch%d.png" % [point, yaw, pitch]
	var error := root.get_texture().get_image().save_png(ProjectSettings.globalize_path(directory + "/" + filename))
	if error != OK:
		printerr("Could not write sweep capture: %s" % filename)
		quit(1)
	metadata.append({"filename": filename, "point": point, "yaw": yaw, "pitch": pitch,
		"eye": [camera.position.x, camera.position.y, camera.position.z], "fov": camera.fov})


func _load_positions(kind: String) -> Array:
	var source_dir := evidence_dir if positions_dir == "" else positions_dir
	var path := source_dir.path_join("%s_positions.json" % kind)
	if not FileAccess.file_exists(path):
		return []
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Array else []


func _parse_stations(value: String) -> bool:
	var parsed: Array = []
	for part in value.split(",", false):
		var station := part.strip_edges()
		if not station.is_valid_int():
			return false
		parsed.append(int(station))
	if parsed.is_empty():
		return false
	station_indices = parsed
	return true


func _hide_requested_node() -> bool:
	if hide_node_path == "":
		return true
	var target := scene.get_node_or_null(hide_node_path)
	if target == null:
		printerr("Cannot find requested hidden node: %s" % hide_node_path)
		return false
	var visuals := []
	if target is VisualInstance3D:
		visuals.append(target)
	visuals.append_array(target.find_children("*", "VisualInstance3D", true, false))
	if visuals.is_empty():
		printerr("Requested node has no VisualInstance3D descendants: %s" % hide_node_path)
		return false
	for visual in visuals:
		visual.visible = false
	return true


func _evidence_folder(selected_scene: String) -> String:
	if diagnostic:
		return "diagnostic"
	if scene_path != "":
		return "sweep_%s" % selected_scene.get_file().get_basename()
	return "sweep_baseline" if baseline else "sweep_candidate"
