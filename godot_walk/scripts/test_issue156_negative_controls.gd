extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const FLOOR_Y := -1.27099049
const SPAWN := Vector3(-3.5, FLOOR_Y + 0.6, 0.0)

var failures: Array[String] = []
var results: Dictionary = {}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	await _test_missing_floor()
	await _test_open_boundary()
	await _test_blocked_connector()
	results["failures"] = failures
	_write_results()
	if failures.is_empty():
		print("ISSUE156_NEGATIVE_CONTROLS: PASS")
	else:
		for failure: String in failures:
			printerr("ISSUE156_NEGATIVE_CONTROLS: " + failure)
	quit(0 if failures.is_empty() else 1)


func _test_missing_floor() -> void:
	var scene := await _new_walkthrough()
	if scene == null:
		return
	scene.call("stream_set_floor_negative", true)
	var player: CharacterBody3D = scene.get_node("Player")
	for tick in 120:
		await physics_frame
	var failed_support := player.global_position.y < FLOOR_Y - 0.25
	results["missing_floor"] = {"fell_below_floor": failed_support,
		"player_y": player.global_position.y, "on_lower_collision": player.is_on_floor()}
	if not failed_support:
		failures.append("missing-floor negative control did not remove walkable support")
	await _dispose(scene)


func _test_open_boundary() -> void:
	var scene := await _new_walkthrough()
	if scene == null:
		return
	scene.call("stream_set_boundary_negative", "R000", "AuthoredBoundaries/WestBoundary")
	var player: CharacterBody3D = scene.get_node("Player")
	player.global_position = SPAWN
	player.rotation.y = PI * 0.5
	Input.action_press("move_forward")
	for tick in 150:
		await physics_frame
	Input.action_release("move_forward")
	var crossed := player.global_position.x < -4.4 or player.global_position.y < FLOOR_Y - 0.25
	results["open_boundary"] = {"escaped_or_fell": crossed,
		"player_position": _coordinates(player.global_position)}
	if not crossed:
		failures.append("open-boundary negative control remained enclosed")
	await _dispose(scene)


func _test_blocked_connector() -> void:
	var scene := await _new_walkthrough()
	if scene == null:
		return
	var connections: Array = scene.get_meta("candidate_connections", [])
	var socket: Dictionary = scene.call("get_connection_socket_world", connections[0].from)
	var blocker := StaticBody3D.new()
	blocker.name = "NegativeControlBlockedConnector"
	blocker.position = scene.to_local(socket.position + Vector3.UP * 1.05)
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.35, 2.1, 2.0)
	var collision := CollisionShape3D.new()
	collision.shape = shape
	blocker.add_child(collision)
	scene.add_child(blocker)
	var player: CharacterBody3D = scene.get_node("Player")
	player.global_position = Vector3(2.4, FLOOR_Y + 0.6, 3.1)
	player.rotation.y = -PI * 0.5
	Input.action_press("move_forward")
	for tick in 90:
		await physics_frame
	Input.action_release("move_forward")
	var blocked := player.global_position.x < 3.25 and player.is_on_floor()
	results["blocked_connector"] = {"player_x": player.global_position.x,
		"remained_on_floor": player.is_on_floor(), "blocked": blocked}
	if not blocked:
		failures.append("blocked-connector negative control allowed traversal")
	await _dispose(scene)


func _new_walkthrough() -> Node3D:
	var scene := WALKTHROUGH.instantiate() as Node3D
	root.add_child(scene)
	for frame in 180:
		if scene.get_meta("walkthrough_ready", false):
			return scene
		await process_frame
	failures.append("negative-control walkthrough did not become ready")
	await _dispose(scene)
	return null


func _dispose(scene: Node3D) -> void:
	Input.action_release("move_forward")
	scene.queue_free()
	await process_frame


func _coordinates(point: Vector3) -> Array:
	return [point.x, point.y, point.z]


func _write_results() -> void:
	var path := "res://evidence/2026-10-23-issue-156/negative_controls.json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		failures.append("could not write negative-control evidence")
		return
	file.store_string(JSON.stringify(results, "\t") + "\n")
