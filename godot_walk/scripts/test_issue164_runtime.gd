extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue164_three_room_walkthrough.tscn")
const EXPECTED_MODULES := [
	"godot_later_bay_column_bounded_v1",
	"godot_early_pocket_pass_through_v1",
	"godot_source_textured_large_room_hall_end_v1",
]

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var walkthrough := WALKTHROUGH.instantiate() as Node3D
	root.add_child(walkthrough)
	for frame in 240:
		if walkthrough.get_meta("walkthrough_ready", false):
			break
		await process_frame
	_check_loaded_chain(walkthrough)
	_check_connections(walkthrough)
	_check_adapter(walkthrough)
	_check_safe_reset(walkthrough)
	if failures.is_empty():
		print("ISSUE164_RUNTIME_CONTRACT: PASS")
	else:
		for failure: String in failures:
			printerr("ISSUE164_RUNTIME_CONTRACT: " + failure)
	quit(0 if failures.is_empty() else 1)


func _check_loaded_chain(walkthrough: Node3D) -> void:
	if not walkthrough.get_meta("walkthrough_ready", false):
		failures.append("three-room walkthrough did not become ready")
		return
	for index in EXPECTED_MODULES.size():
		var room := walkthrough.get_node_or_null("R%03d" % index) as Node3D
		if room == null or room.get_meta("layout_module_id", "") != EXPECTED_MODULES[index]:
			failures.append("room instance %d differs from the expected design chain" % index)
	if walkthrough.get_node_or_null("Player") == null:
		failures.append("walkthrough has no shared player")
	if walkthrough.get_meta("operator_approved", true):
		failures.append("new connection must remain pending review")
	if walkthrough.get_meta("registration_accepted", true) or walkthrough.get_meta("scale_calibrated", true):
		failures.append("registration and scale flags must remain false")
	if not walkthrough.get_meta("psx_applied", false):
		failures.append("existing PSX profile was not applied")


func _check_connections(walkthrough: Node3D) -> void:
	var connections: Array = walkthrough.get_meta("candidate_connections", [])
	if connections.size() != 2:
		failures.append("expected two provisional connections")
		return
	for connection: Dictionary in connections:
		var left: Dictionary = walkthrough.call("get_connection_socket_world", connection.from)
		var right: Dictionary = walkthrough.call("get_connection_socket_world", connection.to)
		if left.is_empty() or right.is_empty():
			failures.append("connector endpoint did not resolve")
			continue
		if left.position.distance_to(right.position) > 0.001:
			failures.append("connector socket centers do not align")
		if left.normal.dot(right.normal) > -0.999:
			failures.append("connector socket normals do not oppose")
		if left.size != [2.0, 2.1] or right.size != [2.0, 2.1]:
			failures.append("connector clearance differs from the capsule-tested socket size")
	if walkthrough.find_children("ConnectorThreshold_*", "StaticBody3D", true, false).size() != 2:
		failures.append("connector floor thresholds or collision bodies are missing")


func _check_adapter(walkthrough: Node3D) -> void:
	var room := walkthrough.get_node_or_null("R002") as Node3D
	if room == null:
		return
	if room.get_node_or_null("AuthoredBoundaries/HallEndBoundary") != null:
		failures.append("closed hallway end cap remains in the connector adapter")
	if room.get_node_or_null("AuthoredBoundaries/HallSocketNorthReturn") == null:
		failures.append("north socket return wall or collider is missing")
	if room.get_node_or_null("AuthoredBoundaries/HallSocketSouthReturn") == null:
		failures.append("south socket return wall or collider is missing")
	if room.get_node_or_null("AuthoredBoundaries/HallSocketHeader") == null:
		failures.append("socket header or collider is missing")
	if room.find_children("Player", "CharacterBody3D", true, false).size() != 0:
		failures.append("adapter contains a duplicate embedded player")
	if room.get_meta("hunyuan_stage_status", "") != "not_used_authored_source_video_room":
		failures.append("authored #163 module is incorrectly labelled as Hunyuan-generated")
	if room.find_child("ColumnObstacle", true, false) == null:
		failures.append("authored column obstacle collider is missing")


func _check_safe_reset(walkthrough: Node3D) -> void:
	var player := walkthrough.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		return
	var expected := Vector3(-3.5, -0.67099049, 0.0)
	player.global_position = Vector3(1000.0, 1000.0, 1000.0)
	player.velocity = Vector3(3.0, 4.0, -2.0)
	walkthrough.call("_reset_player")
	if player.global_position.distance_to(expected) > 0.001 or player.velocity.length() > 0.001:
		failures.append("R did not return the player to the safe spawn with zero velocity")
