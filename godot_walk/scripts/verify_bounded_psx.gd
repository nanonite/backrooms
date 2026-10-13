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


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--scene="):
			scene_path = argument.trim_prefix("--scene=")
		elif argument.begins_with("--out-dir="):
			evidence_dir = argument.trim_prefix("--out-dir=")
		if argument.begins_with("--break="):
			mutation = argument.trim_prefix("--break=")
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
	player = scene.get_node("Player")
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
		var boundary := scene.get_node_or_null(boundary_path)
		if boundary == null:
			printerr("Boundary negative control target is missing: %s" % boundary_path)
			quit(1)
			return false
		boundary.queue_free()
	elif mutation == "floor":
		var floor_bodies: PackedStringArray = scene.get_meta(
			"walk_floor_bodies", PackedStringArray(["GeneratedCollision"]))
		for body_name in floor_bodies:
			var floor_body := scene.find_child(body_name, true, false)
			if floor_body != null:
				floor_body.queue_free()
	elif mutation != "":
		printerr("Mutation requires a bounded scene and boundary or floor")
		quit(1)
		return false
	return true


func _finish_results() -> void:
	results["failures"] = failures
	results["scene"] = scene_path
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
	Input.action_release("move_forward")
	return false


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
