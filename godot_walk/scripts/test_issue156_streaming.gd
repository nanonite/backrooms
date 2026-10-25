extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const FLOOR_Y := -1.27099049

var failures: Array[String] = []
var observations: Dictionary = {}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var walkthrough := WALKTHROUGH.instantiate() as Node3D
	root.add_child(walkthrough)
	for frame in 180:
		if walkthrough.get_meta("walkthrough_ready", false):
			break
		await process_frame
	if not walkthrough.get_meta("walkthrough_ready", false):
		printerr("ISSUE156_STREAMING_CONTRACT: walkthrough did not become ready")
		quit(1)
		return
	_check_initial_window(walkthrough)
	observations["spawn_window"] = _snapshot_window(walkthrough)
	_check_branch_window(walkthrough)
	observations["branch_window"] = _snapshot_window(walkthrough)
	_check_backtracking(walkthrough)
	observations["return_window"] = _snapshot_window(walkthrough)
	_check_contract(walkthrough)
	observations["layout_id"] = walkthrough.get_meta("layout_id", "")
	observations["catalog_sha256"] = walkthrough.get_meta("catalog_sha256", "")
	observations["load_events"] = walkthrough.get_meta("stream_load_events", 0)
	observations["unload_events"] = walkthrough.get_meta("stream_unload_events", 0)
	observations["peak_resident"] = walkthrough.get_meta("stream_peak_resident", 0)
	_write_report()
	if failures.is_empty():
		print("ISSUE156_STREAMING_CONTRACT: PASS")
	else:
		for failure: String in failures:
			printerr("ISSUE156_STREAMING_CONTRACT: " + failure)
	quit(0 if failures.is_empty() else 1)


func _check_initial_window(walkthrough: Node3D) -> void:
	var loaded: PackedStringArray = walkthrough.get_meta("stream_loaded_ids", PackedStringArray())
	if loaded != PackedStringArray(["R000", "R001"]):
		failures.append("spawn window should contain R000 and R001, got %s" % [loaded])
	if walkthrough.get_meta("stream_loaded_count", 0) > 4:
		failures.append("spawn exceeded the resident-module cap")
	if walkthrough.get_meta("stream_frontier_cap_count", 0) < 1:
		failures.append("spawn window has no solid cap at its unloaded frontier")
	for cap: Node in walkthrough.find_children("StreamCap_*", "StaticBody3D", true, false):
		if cap.get_node_or_null("CollisionShape3D") == null:
			failures.append("an unloaded frontier cap has no collision shape")


func _check_branch_window(walkthrough: Node3D) -> void:
	var player := walkthrough.get_node("Player") as CharacterBody3D
	var streamer: Node = walkthrough.get_node("BoundedLayoutStreamer")
	for index in range(1, 7):
		player.global_position = _world_point(walkthrough, "R%03d" % index,
			Vector3(3.0, FLOOR_Y + 0.6, 6.9))
		streamer.call("refresh")
	var expected := PackedStringArray(["R005", "R006", "R007", "R008"])
	var loaded: PackedStringArray = walkthrough.get_meta("stream_loaded_ids", PackedStringArray())
	if loaded != expected:
		failures.append("branch window should load its three neighbors, got %s" % [loaded])
	if walkthrough.get_meta("stream_loaded_count", 0) > walkthrough.get_meta("stream_max_resident", 0):
		failures.append("branch exceeded the configured resident-module cap")
	if walkthrough.get_meta("stream_frontier_cap_count", 0) < 1:
		failures.append("branch window has no solid cap at its unloaded frontier")


func _check_backtracking(walkthrough: Node3D) -> void:
	var player := walkthrough.get_node("Player") as CharacterBody3D
	var streamer: Node = walkthrough.get_node("BoundedLayoutStreamer")
	for index in range(5, -1, -1):
		player.global_position = _world_point(walkthrough, "R%03d" % index,
			Vector3(3.0, FLOOR_Y + 0.6, 6.9)) if index > 0 else walkthrough.global_transform * Vector3(-3.5, FLOOR_Y + 0.6, 0.0)
		streamer.call("refresh")
	var loaded: PackedStringArray = walkthrough.get_meta("stream_loaded_ids", PackedStringArray())
	if loaded != PackedStringArray(["R000", "R001"]):
		failures.append("return to spawn did not restore the original room window")
	if walkthrough.get_meta("stream_load_events", 0) <= 2:
		failures.append("return traversal did not demonstrate a room reload")
	if walkthrough.get_meta("stream_unload_events", 0) < 1:
		failures.append("branch transition did not evict rooms outside the window")


func _check_contract(walkthrough: Node3D) -> void:
	if not walkthrough.get_meta("walkthrough_ready", false):
		failures.append("streamed walkthrough did not become ready")
	if walkthrough.get_meta("stream_peak_resident", 0) > 4:
		failures.append("peak resident count exceeded the hard cap")
	if walkthrough.get_meta("stream_cached_module_count", 0) > 4:
		failures.append("inactive instance cache exceeded its four-module bound")
	if walkthrough.get_meta("stream_total_module_instances", 0) > 8:
		failures.append("active plus cached module instances exceeded the fixed eight-instance bound")
	for flag in ["registration_accepted", "scale_calibrated", "generation_ready", "operator_approved"]:
		if walkthrough.get_meta(flag, true):
			failures.append("%s must remain false" % flag)
	if walkthrough.get_node_or_null("R000") == null:
		failures.append("spawn module did not return after backtracking")


func _world_point(walkthrough: Node3D, instance_id: String, local: Vector3) -> Vector3:
	var placement: Dictionary = walkthrough.call("streaming_placement", instance_id)
	var transform: Dictionary = placement.transform
	var origin := Vector3(transform.position[0], transform.position[1], transform.position[2])
	var basis := Basis(Vector3.UP, deg_to_rad(float(transform.yaw_degrees)))
	return walkthrough.global_transform * Transform3D(basis, origin) * local


func _snapshot_window(walkthrough: Node3D) -> Dictionary:
	return {
		"center": walkthrough.get_meta("stream_center_id", ""),
		"loaded_ids": walkthrough.get_meta("stream_loaded_ids", PackedStringArray()),
		"loaded_count": walkthrough.get_meta("stream_loaded_count", 0),
		"cached_module_types": walkthrough.get_meta("stream_cached_module_count", 0),
		"total_module_instances": walkthrough.get_meta("stream_total_module_instances", 0),
		"frontier_caps": walkthrough.get_meta("stream_frontier_cap_count", 0),
	}


func _write_report() -> void:
	observations["failures"] = failures
	var path := "res://evidence/2026-10-23-issue-156/streaming_contract.json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		failures.append("could not write streaming contract evidence")
		return
	file.store_string(JSON.stringify(observations, "\t") + "\n")
