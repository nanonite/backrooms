extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const OUTPUT := "res://evidence/2026-10-23-issue-156/streaming_performance.json"
const FLOOR_Y := -1.27099049
const CENTER_SEQUENCE := ["R000", "R001", "R002", "R003", "R004", "R005", "R006", "R007", "R006", "R005", "R004", "R003", "R002", "R001", "R000"]

var frame_times_ms: Array[float] = []
var transitions: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_measure")


func _measure() -> void:
	var scene_started := Time.get_ticks_usec()
	var scene := WALKTHROUGH.instantiate() as Node3D
	root.add_child(scene)
	if not await _wait_ready(scene):
		push_error("#156 scene did not become ready for performance measurement")
		quit(2)
		return
	var load_ms := float(Time.get_ticks_usec() - scene_started) / 1000.0
	var player := scene.get_node("Player") as CharacterBody3D
	player.set_physics_process(false)
	player.set_process(false)
	var streamer: Node = scene.get_node("BoundedLayoutStreamer")
	for frame in 450:
		if frame % 30 == 0:
			var center_id: String = CENTER_SEQUENCE[int(frame / 30)]
			player.global_position = _stream_position(scene, center_id)
			var transition_start := Time.get_ticks_usec()
			streamer.call("refresh", true)
			transitions.append({"frame": frame, "center_id": center_id,
				"refresh_ms": float(Time.get_ticks_usec() - transition_start) / 1000.0,
				"resident_count": scene.get_meta("stream_loaded_count", 0),
				"resident_ids": scene.get_meta("stream_loaded_ids", PackedStringArray()),
				"cached_types": scene.get_meta("stream_cached_module_count", 0)})
		var frame_start := Time.get_ticks_usec()
		await process_frame
		await RenderingServer.frame_post_draw
		frame_times_ms.append(float(Time.get_ticks_usec() - frame_start) / 1000.0)
	var result := _result(scene, load_ms)
	_write_result(result)
	print("ISSUE156_PERFORMANCE " + JSON.stringify(result))
	quit()


func _wait_ready(scene: Node3D) -> bool:
	for frame in 180:
		if scene.get_meta("walkthrough_ready", false):
			return true
		await process_frame
	return scene.get_meta("walkthrough_ready", false)


func _result(scene: Node3D, load_ms: float) -> Dictionary:
	var values := frame_times_ms.duplicate()
	values.sort()
	return {
		"layout_id": scene.get_meta("layout_id", ""),
		"catalog_sha256": scene.get_meta("catalog_sha256", ""),
		"window_radius": scene.get_meta("stream_window_radius", 0),
		"max_resident": scene.get_meta("stream_max_resident", 0),
		"peak_resident": scene.get_meta("stream_peak_resident", 0),
		"cached_module_count": scene.get_meta("stream_cached_module_count", 0),
		"total_module_instances": scene.get_meta("stream_total_module_instances", 0),
		"load_events": scene.get_meta("stream_load_events", 0),
		"unload_events": scene.get_meta("stream_unload_events", 0),
		"scene_load_ms": load_ms,
		"frame_samples": values.size(),
		"frame_time_ms": {"p50": _percentile(values, 0.50), "p95": _percentile(values, 0.95),
			"p99": _percentile(values, 0.99), "max": values.back() if not values.is_empty() else 0.0},
		"window_transitions": transitions,
	}


func _percentile(sorted_values: Array[float], fraction: float) -> float:
	if sorted_values.is_empty():
		return 0.0
	var index := int(ceil(float(sorted_values.size() - 1) * fraction))
	return sorted_values[index]


func _world_point(scene: Node3D, instance_id: String, local: Vector3) -> Vector3:
	var placement: Dictionary = scene.call("streaming_placement", instance_id)
	var transform: Dictionary = placement.transform
	var origin := Vector3(transform.position[0], transform.position[1], transform.position[2])
	var basis := Basis(Vector3.UP, deg_to_rad(float(transform.yaw_degrees)))
	return scene.global_transform * Transform3D(basis, origin) * local


func _stream_position(scene: Node3D, instance_id: String) -> Vector3:
	if instance_id == "R000":
		return scene.global_transform * Vector3(-3.5, FLOOR_Y + 0.6, 0.0)
	return _world_point(scene, instance_id, Vector3(3.0, FLOOR_Y + 0.6, 6.9))


func _write_result(result: Dictionary) -> void:
	var file := FileAccess.open(OUTPUT, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write #156 performance report")
		return
	file.store_string(JSON.stringify(result, "\t") + "\n")
