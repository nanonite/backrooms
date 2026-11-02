extends SceneTree

const SCENE_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/room.tscn"
const DEFAULT_OUTPUT := "res://evidence/2026-11-01-issue-168-room-candidate/captures"
const VIEWS := [
	{"id": "spawn_into_rock_field", "position": Vector3(0.0, 0.6, 3.8), "target": Vector3(-0.5, 0.8, -3.8)},
	{"id": "window_and_pier", "position": Vector3(-3.5, 0.6, 2.0), "target": Vector3(5.7, 3.1, -1.5)},
	{"id": "west_rock_bank", "position": Vector3(2.0, 0.6, 3.6), "target": Vector3(-4.2, 0.9, -2.5)},
	{"id": "ceiling_beams_and_floor", "position": Vector3(0.0, 0.6, -1.5), "target": Vector3(0.0, 3.8, 0.0)},
	{"id": "closed_far_boundary", "position": Vector3(0.0, 0.6, -3.8), "target": Vector3(0.0, 1.5, 4.8)},
]

var output_path := DEFAULT_OUTPUT
var views_written: Array[Dictionary] = []
var measured_frame_ms: Array[float] = []
var measured_load_ms := 0.0
var measured_instance_ms := 0.0
var measured_ready_ms := 0.0
var static_memory_bytes := 0


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_path = argument.trim_prefix("--out=")
	call_deferred("_capture")


func _capture() -> void:
	var absolute_output := ProjectSettings.globalize_path(output_path)
	if DirAccess.dir_exists_absolute(absolute_output) or FileAccess.file_exists(absolute_output):
		printerr("Refusing to overwrite capture output: ", output_path)
		quit(2)
		return
	var load_started := Time.get_ticks_usec()
	var packed := load(SCENE_PATH) as PackedScene
	measured_load_ms = float(Time.get_ticks_usec() - load_started) / 1000.0
	if packed == null:
		printerr("Could not load debris-window rock room scene")
		quit(1)
		return
	var instance_started := Time.get_ticks_usec()
	var room := packed.instantiate() as Node3D
	measured_instance_ms = float(Time.get_ticks_usec() - instance_started) / 1000.0
	var ready_started := Time.get_ticks_usec()
	root.add_child(room)
	measured_ready_ms = float(Time.get_ticks_usec() - ready_started) / 1000.0
	var player := room.get_node("Player") as CharacterBody3D
	var camera := room.get_node("Player/Head/Camera3D") as Camera3D
	player.set_physics_process(false)
	_hide_player_hud(player)
	DirAccess.make_dir_recursive_absolute(absolute_output)
	await _measure_frames()
	for view: Dictionary in VIEWS:
		await _capture_view(player, camera, view, absolute_output)
	_write_manifest(absolute_output)
	print("DEBRIS_WINDOW_ROCK_ROOM_CAPTURES_READY: ", output_path)
	quit(0)


func _hide_player_hud(player: CharacterBody3D) -> void:
	for child in player.get_children():
		if child is CanvasLayer:
			(child as CanvasLayer).visible = false


func _capture_view(player: CharacterBody3D, camera: Camera3D, view: Dictionary, absolute_output: String) -> void:
	player.global_position = view.position
	camera.look_at(view.target, Vector3.UP)
	for _frame in 18:
		await process_frame
	var image := root.get_texture().get_image()
	if image.is_empty():
		push_error("Viewport capture is empty for %s" % view.id)
		return
	var relative_path := output_path.path_join("%s.png" % view.id)
	var error := image.save_png(absolute_output.path_join("%s.png" % view.id))
	if error != OK:
		push_error("Could not save capture %s (error %d)" % [relative_path, error])
		return
	views_written.append({"id": view.id, "path": relative_path, "width": image.get_width(), "height": image.get_height()})


func _measure_frames() -> void:
	for _frame in 120:
		await process_frame
	var previous := Time.get_ticks_usec()
	for _frame in 300:
		await process_frame
		var current := Time.get_ticks_usec()
		measured_frame_ms.append(float(current - previous) / 1000.0)
		previous = current
	static_memory_bytes = int(Performance.get_monitor(Performance.MEMORY_STATIC))


func _write_manifest(absolute_output: String) -> void:
	var file := FileAccess.open(absolute_output.path_join("capture_manifest.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write capture manifest")
		return
	file.store_string(JSON.stringify({
		"scene": SCENE_PATH,
		"renderer": "Godot Forward+ Vulkan with the accepted project PSX compositor",
		"panorama_role": "attempt-006 is a layout reference only and is not rendered in the room",
		"scene_load_ms": measured_load_ms,
		"scene_instantiate_ms": measured_instance_ms,
		"scene_ready_build_ms": measured_ready_ms,
		"sampled_frame_time_ms": _frame_summary(),
		"godot_static_memory_bytes": static_memory_bytes,
		"registration_accepted": false,
		"scale_calibrated": false,
		"views": views_written,
	}, "\t") + "\n")


func _frame_summary() -> Dictionary:
	measured_frame_ms.sort()
	return {
		"samples": measured_frame_ms.size(),
		"mean": _mean(measured_frame_ms),
		"p95": _percentile(measured_frame_ms, 0.95),
		"p99": _percentile(measured_frame_ms, 0.99),
		"basis": "SceneTree process-frame intervals after a 120-frame warmup, sampled with --max-fps 60 and vsync disabled",
	}


func _mean(samples: Array[float]) -> float:
	var total := 0.0
	for sample in samples:
		total += sample
	return total / maxf(1.0, float(samples.size()))


func _percentile(samples: Array[float], fraction: float) -> float:
	if samples.is_empty():
		return 0.0
	return samples[mini(samples.size() - 1, int(ceil(float(samples.size()) * fraction)) - 1)]
