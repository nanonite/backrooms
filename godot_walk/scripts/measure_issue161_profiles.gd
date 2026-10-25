extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const OUTPUT := "res://evidence/2026-10-23-issue-161/profile_performance.json"
const FLOOR_Y := -1.27099049
const SAMPLE_COUNT := 300
const WARMUP_FRAMES := 30

var _samples: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_measure")


func _measure() -> void:
	var started := Time.get_ticks_usec()
	var scene := WALKTHROUGH.instantiate() as Node3D
	root.add_child(scene)
	if not await _wait_ready(scene):
		printerr("#161 walkthrough did not become ready for the profile measurement")
		quit(2)
		return
	var load_ms := float(Time.get_ticks_usec() - started) / 1000.0
	var player := scene.get_node("Player") as CharacterBody3D
	player.set_physics_process(false)
	player.set_process(false)
	_set_camera(scene)
	for profile: Dictionary in _profiles():
		_samples.append(await _measure_profile(profile, scene, load_ms))
	_write_result()
	print("ISSUE161_PROFILE_PERFORMANCE " + JSON.stringify(_samples))
	quit()


func _wait_ready(scene: Node3D) -> bool:
	for frame in 180:
		if scene.get_meta("walkthrough_ready", false):
			return true
		await process_frame
	return scene.get_meta("walkthrough_ready", false)


func _profiles() -> Array[Dictionary]:
	return [
		{"id": "affine_on", "affine_texture_mapping": true,
			"texture_filtering": false, "vertex_snap_intensity": 1},
		{"id": "affine_off", "affine_texture_mapping": false,
			"texture_filtering": false, "vertex_snap_intensity": 1},
	]


func _measure_profile(profile: Dictionary, scene: Node3D, load_ms: float) -> Dictionary:
	RenderingServer.global_shader_parameter_set("affine_texture_mapping",
		profile.affine_texture_mapping)
	await _settle(WARMUP_FRAMES)
	var frame_times: Array[float] = []
	for frame in SAMPLE_COUNT:
		var frame_started := Time.get_ticks_usec()
		await process_frame
		await RenderingServer.frame_post_draw
		frame_times.append(float(Time.get_ticks_usec() - frame_started) / 1000.0)
	frame_times.sort()
	return {
		"profile_id": profile.id,
		"affine_texture_mapping": profile.affine_texture_mapping,
		"texture_filtering": profile.texture_filtering,
		"vertex_snap_intensity": profile.vertex_snap_intensity,
		"scene_load_to_ready_ms": load_ms,
		"warmup_frames": WARMUP_FRAMES,
		"frame_samples": frame_times.size(),
		"frame_interval_ms": {
			"p50": _percentile(frame_times, 0.50),
			"p95": _percentile(frame_times, 0.95),
			"p99": _percentile(frame_times, 0.99),
			"max": frame_times.back() if not frame_times.is_empty() else 0.0,
		},
	}


func _set_camera(scene: Node3D) -> void:
	var camera := Camera3D.new()
	camera.name = "Issue161PerformanceCamera"
	var eye := Vector3(36.5, FLOOR_Y + 1.1, 2.4)
	var target := Vector3(36.5, FLOOR_Y + 1.1, 8.0)
	scene.add_child(camera)
	camera.global_position = eye
	camera.look_at(target, Vector3.UP)
	camera.make_current()
	var player := scene.get_node("Player") as CharacterBody3D
	player.global_position = Vector3(36.5, FLOOR_Y + 0.6, 3.1)
	scene.get_node("BoundedLayoutStreamer").call("refresh", true)


func _settle(frames: int) -> void:
	for frame in frames:
		await process_frame
	await RenderingServer.frame_post_draw


func _percentile(sorted_values: Array[float], fraction: float) -> float:
	if sorted_values.is_empty():
		return 0.0
	var index := int(ceil(float(sorted_values.size() - 1) * fraction))
	return sorted_values[index]


func _write_result() -> void:
	var file := FileAccess.open(OUTPUT, FileAccess.WRITE)
	if file == null:
		push_error("#161 cannot write profile performance report")
		return
	file.store_string(JSON.stringify({"profiles": _samples,
		"measurement": "300 unthrottled rendered frame intervals after 30 warmup frames at one fixed branch pose"}, "\t") + "\n")
