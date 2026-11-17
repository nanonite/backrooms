extends SceneTree

const SCENE_PATH := "res://source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/room.tscn"
const DEFAULT_OUTPUT := "res://source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/captures"
# The first four views are byte-for-byte the v1 viewpoints; the last two are new.
const VIEWS := [
	{"id": "spawn_toward_bench", "position": Vector3(0.0, 0.6, 6.0), "target": Vector3(0.0, 1.3, 0.0)},
	{"id": "tree_line", "position": Vector3(0.0, 0.6, 4.0), "target": Vector3(-3.8, 4.0, -5.5)},
	{"id": "stone_bench", "position": Vector3(0.0, 0.6, 3.0), "target": Vector3(0.0, 1.1, -0.5)},
	{"id": "open_winter_sky", "position": Vector3(0.0, 0.6, 0.0), "target": Vector3(0.0, 7.0, 1.5)},
	{"id": "snow_drift_and_posts", "position": Vector3(-6.0, 0.6, 4.6), "target": Vector3(-6.5, 0.35, -2.0)},
	{"id": "statue_detail", "position": Vector3(-1.6, 0.6, 2.6), "target": Vector3(-4.6, 1.2, 0.8)},
]

var output_path := DEFAULT_OUTPUT
var views_written: Array[Dictionary] = []
var measured_frame_ms: Array[float] = []
var measured_load_ms := 0.0
var measured_instance_ms := 0.0
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
		printerr("Could not load candidate room scene")
		quit(1)
		return
	var instance_started := Time.get_ticks_usec()
	var room := packed.instantiate() as Node3D
	measured_instance_ms = float(Time.get_ticks_usec() - instance_started) / 1000.0
	root.add_child(room)
	var player := room.get_node("Player") as CharacterBody3D
	var camera := room.get_node("Player/Head/Camera3D") as Camera3D
	player.set_physics_process(false)
	DirAccess.make_dir_recursive_absolute(absolute_output)
	await _measure_frames()
	for view: Dictionary in VIEWS:
		await _capture_view(player, camera, view, absolute_output)
	_write_manifest(absolute_output)
	print("SNOW_GARDEN_V2_CAPTURES_READY: ", output_path)
	quit(0)


func _capture_view(player: CharacterBody3D, camera: Camera3D, view: Dictionary, absolute_output: String) -> void:
	player.global_position = view.position
	camera.look_at(view.target, Vector3.UP)
	for _frame in 6:
		await process_frame
	camera.look_at(view.target, Vector3.UP)
	for _frame in 18:
		await process_frame
	var image := root.get_texture().get_image()
	if image.is_empty():
		push_error("Capture viewport was empty for %s" % view.id)
		return
	var relative_path := output_path.path_join("%s.png" % view.id)
	var error := image.save_png(absolute_output.path_join("%s.png" % view.id))
	if error != OK:
		push_error("Could not save capture %s (error %d)" % [relative_path, error])
		return
	views_written.append({"id": view.id, "path": relative_path, "width": image.get_width(), "height": image.get_height()})


func _write_manifest(absolute_output: String) -> void:
	var manifest := {
		"scene": SCENE_PATH,
		"renderer": "Godot Forward+ Vulkan with the project PSX compositor",
		"panorama_role": "camera-centered background visual; no spatial parallax",
		"scene_load_ms": measured_load_ms,
		"scene_instantiate_ms": measured_instance_ms,
		"sampled_frame_time_ms": _frame_summary(),
		"godot_static_memory_bytes": static_memory_bytes,
		"registration_accepted": false,
		"scale_calibrated": false,
		"views": views_written,
	}
	var file := FileAccess.open(absolute_output.path_join("capture_manifest.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write capture manifest")
		return
	file.store_string(JSON.stringify(manifest, "\t") + "\n")


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


func _frame_summary() -> Dictionary:
	var samples := measured_frame_ms.duplicate()
	samples.sort()
	return {
		"samples": samples.size(),
		"mean": _mean(samples),
		"p95": _percentile(samples, 0.95),
		"p99": _percentile(samples, 0.99),
		"basis": "SceneTree process-frame intervals after 120-frame warmup; includes display sync",
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
