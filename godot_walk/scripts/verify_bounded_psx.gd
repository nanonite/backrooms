extends SceneTree

const TRACE := preload("res://scripts/bounded_walk_trace.gd")
const ROUTE := [Vector2(-0.65, 2.9), Vector2(0.5, 2.9), Vector2(0.5, 1.7)]
var player: CharacterBody3D
var scene: Node3D
var results := {}
var boundary_positions: Array = []
var failures: Array = []
var scene_path := "res://scenes/corridor_bounded_psx.tscn"
var mutation := ""


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--scene="):
			scene_path = argument.trim_prefix("--scene=")
		if argument.begins_with("--break="):
			mutation = argument.trim_prefix("--break=")
	call_deferred("_verify")


func _verify() -> void:
	var packed: PackedScene = load(scene_path)
	if packed == null:
		printerr("Cannot load requested scene: %s" % scene_path)
		quit(1)
		return
	scene = packed.instantiate()
	root.add_child(scene)
	player = scene.get_node("Player")
	if not _apply_mutation():
		return
	await _settle()
	results["spawn_eye"] = _coordinates(player.get_node("Head").global_position)
	await _route()
	if scene.has_node("AuthoredBoundaries"):
		await _boundaries()
	_finish_results()


func _apply_mutation() -> bool:
	if mutation == "boundary" and scene.has_node("AuthoredBoundaries/EastPartition"):
		scene.get_node("AuthoredBoundaries/EastPartition").queue_free()
	elif mutation == "floor":
		scene.get_node("GeneratedCollision").queue_free()
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
	var path := "res://evidence/2026-10-13-bounded-psx/physics_%s.json" % label
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
	for target in ROUTE + [ROUTE[1], ROUTE[0]]:
		if not await _drive_to(target, trace):
			failures.append("Route target not reached: %s" % target)
	results["out_and_back"] = trace.report()
	_validate_trace(trace)


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
	for index in range(8):
		player.position = Vector3(0.5, -0.54, 2.6)
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
		var file := FileAccess.open("res://evidence/2026-10-13-bounded-psx/boundary_positions.json", FileAccess.WRITE)
		file.store_string(JSON.stringify(boundary_positions, "\t") + "\n")


func _check_envelope() -> void:
	var point := player.position
	if point.x < -0.94 or point.x > 0.89 or point.z < 1.61 or point.z > 3.04:
		if not failures.has("Escaped bounded envelope"):
			failures.append("Escaped bounded envelope")


func _validate_trace(trace: RefCounted) -> void:
	var data: Dictionary = trace.report()
	if data.floor_fraction < 0.99 or data.safety_contacts > 0 or data.max_step_m > 0.15:
		failures.append("Support, safety or step gate failed: %s" % data)
	if not data.support_bodies.has("GeneratedCollision"):
		failures.append("No generated floor support observed")


func _settle() -> void:
	for tick in range(60):
		await physics_frame


func _coordinates(vector: Vector3) -> Array:
	return [vector.x, vector.y, vector.z]
