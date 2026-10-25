extends SceneTree

const TRACE := preload("res://scripts/bounded_walk_trace.gd")
const AREA_GRID := preload("res://scripts/walkable_area_grid.gd")
const ROUTE := [Vector2(-0.65, 2.9), Vector2(0.5, 2.9), Vector2(0.5, 1.7)]
var player: CharacterBody3D
var scene: Node3D
var results := {}
var boundary_positions: Array = []
var failures: Array = []
var scene_path := "res://scenes/corridor_bounded_psx.tscn"
var evidence_dir := "res://evidence/2026-10-13-bounded-psx"
var mutation := ""
var record_state_trace := false
var route_state_trace: Array[Dictionary] = []
var route_state_tick := 0


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--scene="):
			scene_path = argument.trim_prefix("--scene=")
		elif argument.begins_with("--out-dir="):
			evidence_dir = argument.trim_prefix("--out-dir=")
		if argument.begins_with("--break="):
			mutation = argument.trim_prefix("--break=")
		elif argument == "--trace-state":
			record_state_trace = true
	call_deferred("_verify")


func _verify() -> void:
	var packed: PackedScene = load(scene_path)
	if packed == null:
		printerr("Cannot load requested scene: %s" % scene_path)
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(evidence_dir))
	scene = packed.instantiate()
	root.add_child(scene)
	await process_frame
	player = scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		printerr("Requested scene did not provide a Player after initialization")
		quit(1)
		return
	if not _apply_mutation():
		return
	await _settle()
	results["spawn_eye"] = _coordinates(player.get_node("Head").global_position)
	await _route()
	if scene.has_meta("walk_envelope"):
		_measure_walkable_area()
	if scene.has_node("AuthoredBoundaries"):
		await _boundaries()
	_finish_results()


func _apply_mutation() -> bool:
	if mutation == "boundary":
		var boundary_path: String = scene.get_meta(
			"boundary_test_path", "AuthoredBoundaries/EastPartition")
		if scene.has_method("stream_set_boundary_negative"):
			var path_parts := boundary_path.split("/", false)
			if path_parts.size() < 2 or not scene.call("stream_set_boundary_negative",
					path_parts[0], "/".join(path_parts.slice(1))):
				printerr("Boundary negative control target is missing: %s" % boundary_path)
				quit(1)
				return false
		else:
			var boundary := scene.get_node_or_null(boundary_path)
			if boundary == null:
				printerr("Boundary negative control target is missing: %s" % boundary_path)
				quit(1)
				return false
			boundary.queue_free()
	elif mutation == "floor":
		var floor_bodies: PackedStringArray = scene.get_meta(
			"walk_floor_bodies", PackedStringArray(["GeneratedCollision"]))
		var removed := 0
		if scene.has_method("stream_set_floor_negative"):
			for body_name in floor_bodies:
				var pattern := "ConnectorThreshold*" if body_name == "ConnectorThreshold" else body_name
				removed += scene.find_children(pattern, "StaticBody3D", true, false).size()
			scene.call("stream_set_floor_negative", true)
		else:
			removed = _remove_configured_floors(floor_bodies)
		if removed == 0:
			printerr("Floor negative control found no configured floor bodies")
			quit(1)
			return false
		print("FLOOR_NEGATIVE_CONTROL removed=%d" % removed)
	elif mutation == "connector":
		if not _block_first_connector():
			return false
	elif mutation != "":
		printerr("Mutation requires a bounded scene and boundary, floor or connector")
		quit(1)
		return false
	return true


func _block_first_connector() -> bool:
	var connections: Array = scene.get_meta("candidate_connections", [])
	if connections.is_empty() or not scene.has_method("get_connection_socket_world"):
		printerr("Connector negative control requires generated connection metadata")
		quit(1)
		return false
	var socket: Dictionary = scene.call("get_connection_socket_world", connections[0].from)
	if socket.is_empty():
		printerr("Connector negative control could not resolve a socket")
		quit(1)
		return false
	var center: Vector3 = socket.position
	var normal: Vector3 = socket.normal
	var size: Array = socket.size
	var clear_height := float(size[1])
	var clear_width := float(size[0])
	var dimensions := Vector3(0.35, clear_height, clear_width) if absf(normal.x) > 0.9 else Vector3(clear_width, clear_height, 0.35)
	var blocker := StaticBody3D.new()
	blocker.name = "NegativeControlBlockedConnector"
	blocker.position = center + Vector3.UP * (clear_height * 0.5)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = dimensions
	collision.shape = shape
	blocker.add_child(collision)
	scene.add_child(blocker)
	print("CONNECTOR_NEGATIVE_CONTROL blocked=%s" % connections[0].id)
	return true


func _remove_configured_floors(floor_bodies: PackedStringArray) -> int:
	var removed := 0
	for body_name in floor_bodies:
		var pattern := "ConnectorThreshold*" if body_name == "ConnectorThreshold" else body_name
		for floor_body in scene.find_children(pattern, "StaticBody3D", true, false):
			floor_body.queue_free()
			removed += 1
	return removed


func _finish_results() -> void:
	results["failures"] = failures
	results["scene"] = scene_path
	if scene.get_meta("streaming_enabled", false):
		results["streaming"] = _streaming_report()
	var label := "candidate" if scene.has_node("AuthoredBoundaries") else "baseline"
	if mutation != "":
		label += "_broken_" + mutation
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(evidence_dir))
	var path := evidence_dir.path_join("physics_%s.json" % label)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		printerr("Cannot write physics evidence: %s" % path)
		quit(1)
		return
	file.store_string(JSON.stringify(results, "\t") + "\n")
	print("BOUNDED_PHYSICS " + JSON.stringify(results))
	quit(0 if failures.is_empty() else 1)


func _streaming_report() -> Dictionary:
	return {
		"center_id": scene.get_meta("stream_center_id", ""),
		"loaded_ids": scene.get_meta("stream_loaded_ids", PackedStringArray()),
		"loaded_count": scene.get_meta("stream_loaded_count", 0),
		"peak_resident": scene.get_meta("stream_peak_resident", 0),
		"cached_module_count": scene.get_meta("stream_cached_module_count", 0),
		"total_module_instances": scene.get_meta("stream_total_module_instances", 0),
		"max_cached_module_types": scene.get_meta("stream_max_cached_module_types", 0),
		"max_resident": scene.get_meta("stream_max_resident", 0),
		"load_events": scene.get_meta("stream_load_events", 0),
		"unload_events": scene.get_meta("stream_unload_events", 0),
		"frontier_caps": scene.get_meta("stream_frontier_cap_count", 0),
	}


func _route() -> void:
	var trace := TRACE.new()
	var route_points: Array = Array(scene.get_meta("walk_route", ROUTE))
	if route_points.size() < 2:
		failures.append("Walk route metadata must contain at least two points")
		return
	var targets := route_points.duplicate()
	for index in range(route_points.size() - 2, -1, -1):
		targets.append(route_points[index])
	var segments := []
	for target in targets:
		var reached := await _drive_to(target, trace)
		segments.append({"target": [target.x, target.y], "reached": reached,
			"player": _coordinates(player.position)})
		if not reached:
			failures.append("Route target not reached: %s" % target)
	results["out_and_back"] = trace.report()
	results["route_segments"] = segments
	if record_state_trace:
		results["route_state_trace"] = route_state_trace
	_validate_trace(trace)
	_write_route_positions(route_points)


func _drive_to(target: Vector2, trace: RefCounted) -> bool:
	for tick in range(180):
		var delta := target - Vector2(player.position.x, player.position.z)
		if delta.length() < 0.09:
			Input.action_release("move_forward")
			return true
		player.rotation.y = atan2(-delta.x, -delta.y)
		Input.action_press("move_forward")
		await physics_frame
		trace.sample(player)
		_record_route_state(target)
	Input.action_release("move_forward")
	return false


func _record_route_state(target: Vector2) -> void:
	if not record_state_trace:
		return
	var contacts: Array = []
	for index in player.get_slide_collision_count():
		var collision := player.get_slide_collision(index)
		var body: Node = collision.get_collider()
		contacts.append({"body": body.name,
			"normal": _coordinates(collision.get_normal())})
	route_state_trace.append({"tick": route_state_tick,
		"target": [target.x, target.y],
		"position": _coordinates(player.global_position),
		"eye": _coordinates(player.get_node("Head").global_position),
		"velocity": _coordinates(player.velocity),
		"on_floor": player.is_on_floor(), "contacts": contacts})
	route_state_tick += 1


func _boundaries() -> void:
	var probes := {}
	var probe_origin: Vector3 = scene.get_meta(
		"boundary_probe_origin", Vector3(0.5, -0.54, 2.6))
	for index in range(8):
		player.position = probe_origin
		player.velocity = Vector3.ZERO
		await _settle()
		player.rotation.y = TAU * float(index) / 8.0
		var trace := TRACE.new()
		Input.action_press("move_forward")
		for tick in range(240):
			await physics_frame
			trace.sample(player)
			_check_envelope()
		Input.action_release("move_forward")
		_validate_trace(trace)
		probes[str(index)] = {"trace": trace.report(), "end": _coordinates(player.position)}
		boundary_positions.append({"id": "boundary_%d" % index,
			"eye": _coordinates(player.get_node("Head").global_position)})
	results["boundary_pushes"] = probes
	if mutation == "":
		var file := FileAccess.open(evidence_dir.path_join("boundary_positions.json"), FileAccess.WRITE)
		file.store_string(JSON.stringify(boundary_positions, "\t") + "\n")


func _check_envelope() -> void:
	var point := player.position
	var envelope: Rect2 = scene.get_meta("walk_envelope", Rect2(-0.94, 1.61, 1.83, 1.43))
	if (point.x < envelope.position.x or point.x > envelope.end.x
			or point.z < envelope.position.y or point.z > envelope.end.y):
		if not failures.has("Escaped bounded envelope"):
			failures.append("Escaped bounded envelope")


func _validate_trace(trace: RefCounted) -> void:
	var data: Dictionary = trace.report()
	if data.floor_fraction < 0.99 or data.safety_contacts > 0 or data.max_step_m > 0.15:
		failures.append("Support, safety or step gate failed: %s" % data)
	var floor_bodies: PackedStringArray = scene.get_meta(
		"walk_floor_bodies", PackedStringArray(["GeneratedCollision"]))
	var has_allowed_support := false
	for body_name in floor_bodies:
		has_allowed_support = has_allowed_support or data.support_bodies.has(body_name)
	if not has_allowed_support:
		failures.append("No configured walkable floor support observed: %s" % floor_bodies)


func _write_route_positions(route_points: Array) -> void:
	if mutation != "":
		return
	var positions := []
	var eye_y: float = player.get_node("Head").global_position.y
	for index in range(route_points.size()):
		var point: Vector2 = route_points[index]
		positions.append({"id": "route_%d" % index, "eye": [point.x, eye_y, point.y]})
	var file := FileAccess.open(evidence_dir.path_join("route_positions.json"), FileAccess.WRITE)
	if file == null:
		failures.append("Cannot write route positions")
		return
	file.store_string(JSON.stringify(positions, "\t") + "\n")


func _measure_walkable_area() -> void:
	if scene.get_meta("streaming_enabled", false):
		results["walkable_area"] = {"measured": false,
			"reason": "bounded layout streaming exposes only the resident window to the physics query"}
		return
	var collision := player.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if (collision == null or collision.shape == null
			or not (collision.shape is CapsuleShape3D)):
		failures.append("Walkable-area estimate requires the player's capsule shape")
		return
	var route_points: Array = Array(scene.get_meta("walk_route", ROUTE))
	if route_points.is_empty():
		failures.append("Walkable-area estimate requires a route start")
		return
	var floor_bodies: PackedStringArray = scene.get_meta(
		"walk_floor_bodies", PackedStringArray(["GeneratedCollision"]))
	var measurement: Dictionary = AREA_GRID.measure(
		player.get_world_3d().direct_space_state,
		collision.shape,
		player.collision_mask,
		player.get_rid(),
		scene.get_meta("walk_envelope"),
		scene.get_meta("walk_floor_y", -1.143),
		floor_bodies,
		route_points[0])
	results["walkable_area"] = measurement
	if mutation == "" and measurement.spawn_connected_center_samples == 0:
		failures.append("Walkable-area grid found no spawn-connected floor samples")


func _settle() -> void:
	for tick in range(60):
		await physics_frame


func _coordinates(vector: Vector3) -> Array:
	return [vector.x, vector.y, vector.z]
