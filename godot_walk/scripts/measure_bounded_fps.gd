extends SceneTree

const DEFAULT_EVIDENCE := "res://evidence/2026-10-13-bounded-psx"
const WARMUP := 200
const FRAMES_PER_POSE := 300
var camera: Camera3D
var points: Array = []
var baseline := false
var frame := 0
var started_usec := 0
var frame_times: Array = []
var previous_usec := 0
var loaded_usec := 0
var measured_frames := 0
var capped := false
var frames_per_pose := FRAMES_PER_POSE
var scene_path := ""
var evidence_dir := DEFAULT_EVIDENCE
var result_label := ""


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument == "--baseline":
			baseline = true
		elif argument == "--capped":
			capped = true
		elif argument.begins_with("--scene="):
			scene_path = argument.get_slice("=", 1)
		elif argument.begins_with("--out-dir="):
			evidence_dir = argument.get_slice("=", 1)
		elif argument.begins_with("--label="):
			result_label = argument.get_slice("=", 1)
	if capped:
		frames_per_pose = 60
	call_deferred("_load_scene")


func _load_scene() -> void:
	var default_scene := "corridor_psx" if baseline else "corridor_bounded_psx"
	var selected_scene := scene_path if scene_path != "" else "res://scenes/%s.tscn" % default_scene
	var packed := load(selected_scene) as PackedScene
	if packed == null:
		printerr("Could not load FPS scene: %s" % selected_scene)
		quit(1)
		return
	var scene: Node3D = packed.instantiate()
	root.add_child(scene)
	await physics_frame
	scene.get_node("Player").set_physics_process(false)
	camera = Camera3D.new()
	camera.fov = scene.get_node("Player/Head/Camera3D").fov
	scene.add_child(camera)
	camera.current = true
	for filename in ["route_positions.json", "boundary_positions.json"]:
		var path := evidence_dir.path_join(filename)
		if not FileAccess.file_exists(path):
			printerr("Missing FPS position data: %s" % path)
			quit(1)
			return
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not parsed is Array:
			printerr("Invalid FPS position data: %s" % path)
			quit(1)
			return
		points.append_array(parsed)
	if points.is_empty():
		printerr("No FPS sample positions found")
		quit(1)
		return
	loaded_usec = Time.get_ticks_usec()
	RenderingServer.frame_post_draw.connect(_drawn)


func _drawn() -> void:
	if camera == null or points.is_empty():
		return
	frame += 1
	if frame <= WARMUP or Time.get_ticks_usec() - loaded_usec < 3000000:
		return
	measured_frames += 1
	var measured := measured_frames
	var point: Dictionary = points[mini(measured / frames_per_pose, points.size() - 1)]
	var eye: Array = point.eye
	camera.position = Vector3(eye[0], eye[1], eye[2])
	camera.rotation_degrees = Vector3(30.0 * sin(measured * 0.02), -measured * 1.2, 0)
	var now := Time.get_ticks_usec()
	if started_usec == 0:
		started_usec = now
	else:
		frame_times.append(float(now - previous_usec) / 1000.0)
	previous_usec = now
	if measured >= points.size() * frames_per_pose:
		RenderingServer.frame_post_draw.disconnect(_drawn)
		call_deferred("_report", now)


func _report(now: int) -> void:
	frame_times.sort()
	var elapsed := float(now - started_usec) / 1000000.0
	var result := {"baseline": baseline, "scene": scene_path, "frames": frame_times.size(),
		"poses": points.size(), "elapsed_s": elapsed, "fps": frame_times.size() / elapsed,
		"capped_at_60": capped, "counter": "RenderingServer.frame_post_draw",
		"p95_frame_ms": frame_times[int(frame_times.size() * 0.95)],
		"p99_frame_ms": frame_times[int(frame_times.size() * 0.99)]}
	print("FPS_JSON " + JSON.stringify(result))
	var label := result_label if result_label != "" else ("baseline" if baseline else "candidate")
	if capped:
		label += "_capped"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(evidence_dir))
	root.get_texture().get_image().save_png(ProjectSettings.globalize_path(
		evidence_dir.path_join("fps_%s.png" % label)))
	var file := FileAccess.open(evidence_dir.path_join("fps_%s.json" % label), FileAccess.WRITE)
	if file == null:
		printerr("Cannot write FPS evidence")
		quit(1)
		return
	file.store_string(JSON.stringify(result, "\t") + "\n")
	quit()
