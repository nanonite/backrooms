extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue149_generated_walkthrough.tscn")

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var walkthrough := WALKTHROUGH.instantiate()
	root.add_child(walkthrough)
	for frame in 120:
		if walkthrough.get_meta("walkthrough_ready", false):
			break
		await process_frame
	_check_ready(walkthrough)
	_check_module_topology(walkthrough)
	_check_safe_reset(walkthrough)
	if failures.is_empty():
		print("ISSUE149_RUNTIME_CONTRACT: PASS")
	else:
		for failure: String in failures:
			printerr("ISSUE149_RUNTIME_CONTRACT: " + failure)
	quit(0 if failures.is_empty() else 1)


func _check_ready(walkthrough: Node3D) -> void:
	if not walkthrough.has_meta("layout_id"):
		failures.append("walkthrough did not finish loading before timeout")
		return
	var module_count := 0
	for child: Node in walkthrough.get_children():
		if child.name.begins_with("R") and child is Node3D:
			module_count += 1
	if module_count != 10:
		failures.append("expected 10 loaded room instances, got %d" % module_count)
	if walkthrough.get_node_or_null("Player") == null:
		failures.append("generated walkthrough has no shared player")
	if not walkthrough.get_meta("psx_applied", false):
		failures.append("existing PSX preset was not applied")
	for flag in ["registration_accepted", "scale_calibrated", "generation_ready", "operator_approved"]:
		if walkthrough.get_meta(flag, true):
			failures.append("%s must remain false" % flag)
	if walkthrough.get_meta("candidate_connections", []).size() != 9:
		failures.append("expected nine provisional connections")


func _check_module_topology(walkthrough: Node3D) -> void:
	var pass_through_count := 0
	var branch_count := 0
	for room: Node in walkthrough.get_children():
		if not room.has_meta("topology_variant"):
			continue
		var variant: String = room.get_meta("topology_variant")
		if variant == "pocket_pass_through":
			pass_through_count += 1
			if room.get_node_or_null("AuthoredBoundaries/NorthBoundary/Wall") == null:
				failures.append("pass-through north closure is missing")
			if room.get_node_or_null("AuthoredBoundaries/SouthBoundary/Wall") == null:
				failures.append("pass-through south closure is missing")
			if room.get_node_or_null("AuthoredBoundaries/EastBoundary/Wall") != null:
				failures.append("pass-through east collision blocks its declared socket")
		elif variant == "pocket_three_way":
			branch_count += 1
			if room.get_node_or_null("AuthoredBoundaries/SouthBoundary/Wall") == null:
				failures.append("three-way south closure is missing")
			if room.get_node_or_null("AuthoredBoundaries/NorthBoundary/Wall") != null:
				failures.append("three-way north collision blocks its declared socket")
	if pass_through_count < 1 or branch_count != 1:
		failures.append("loaded topology does not contain pass-throughs and one branch")
	if walkthrough.find_children("ConnectorThreshold_*", "StaticBody3D", true, false).size() != 9:
		failures.append("connector transitions are missing authored collision thresholds")


func _check_safe_reset(walkthrough: Node3D) -> void:
	var player := walkthrough.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		return
	var expected := Vector3(-3.5, -0.67099049, 0.0)
	player.global_position = Vector3(1000.0, 1000.0, 1000.0)
	player.velocity = Vector3(4.0, 2.0, -3.0)
	walkthrough.call("_reset_player")
	if player.global_position.distance_to(expected) > 0.001:
		failures.append("R reset did not return the player to the declared safe spawn")
	if player.velocity.length() > 0.001:
		failures.append("R reset did not clear player velocity")

