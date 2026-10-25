extends SceneTree

const WALKTHROUGH := preload("res://scenes/issue164_three_room_walkthrough.tscn")
const FLOOR_Y := -1.27099049
const SPAWN := Vector3(-3.5, FLOOR_Y + 0.6, 0.0)
const CONNECTOR_CENTER := Vector3(3.5, FLOOR_Y, 3.1)
const COLUMN_CENTER := Vector3(24.56, FLOOR_Y + 1.6, 3.1)
const EVIDENCE_PATH := "res://evidence/2026-10-24-issue-164/mechanics/physics_controls.json"

var results: Dictionary = {"issue": 164, "controls": {}}
var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	await _check_connector_control()
	await _check_floor_control()
	await _check_boundary_control()
	await _check_column_obstacle()
	results["failures"] = failures
	_write_results()
	for failure: String in failures:
		printerr("ISSUE164_PHYSICS_CONTROL: " + failure)
	print("ISSUE164_PHYSICS_CONTROLS: %s" % ("PASS" if failures.is_empty() else "FAIL"))
	quit(0 if failures.is_empty() else 1)


func _new_walkthrough() -> Node3D:
	var scene := WALKTHROUGH.instantiate() as Node3D
	root.add_child(scene)
	for frame in 240:
		if scene.get_meta("walkthrough_ready", false):
			break
		await process_frame
	await physics_frame
	if not scene.get_meta("walkthrough_ready", false):
		failures.append("walkthrough failed to load for a physics control")
	return scene


func _probe(scene: Node3D, position: Vector3, motion: Vector3) -> bool:
	var player := scene.get_node("Player") as CharacterBody3D
	player.global_position = position
	player.velocity = Vector3.ZERO
	await physics_frame
	return player.test_move(player.global_transform, motion, KinematicCollision3D.new())


func _check_connector_control() -> void:
	var scene := await _new_walkthrough()
	var position := Vector3(2.2, FLOOR_Y + 0.6, 3.1)
	var motion := Vector3(1.4, 0.0, 0.0)
	var clear_before := not await _probe(scene, position, motion)
	var blocker := StaticBody3D.new()
	blocker.name = "Issue164BlockedConnectorControl"
	blocker.position = CONNECTOR_CENTER + Vector3.UP * 1.05
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(0.3, 2.1, 2.0)
	shape.shape = box
	blocker.add_child(shape)
	scene.add_child(blocker)
	await physics_frame
	var blocked_after := await _probe(scene, position, motion)
	results.controls["blocked_connector"] = {
		"unblocked_crossing_clear": clear_before,
		"blocked_crossing_collides": blocked_after,
	}
	if not clear_before or not blocked_after:
		failures.append("blocked-connector control did not distinguish clear and blocked traversal")
	scene.queue_free()
	await process_frame


func _check_floor_control() -> void:
	var scene := await _new_walkthrough()
	var fall_motion := Vector3.DOWN * 2.0
	var supported_before := await _probe(scene, SPAWN + Vector3.UP * 1.0, fall_motion)
	var names := PackedStringArray(["AuthoredFloor", "AuthoredPlanarRouteFloor"])
	for floor_name: String in names:
		for body: Node in scene.find_children(floor_name, "StaticBody3D", true, false):
			body.queue_free()
	for body: Node in scene.find_children("ConnectorThreshold_*", "StaticBody3D", true, false):
		body.queue_free()
	await process_frame
	await physics_frame
	var unsupported_after := not await _probe(scene, SPAWN + Vector3.UP * 1.0, fall_motion)
	results.controls["missing_floor"] = {
		"floor_blocks_fall_before_removal": supported_before,
		"fall_path_clear_after_removal": unsupported_after,
	}
	if not supported_before or not unsupported_after:
		failures.append("missing-floor control did not distinguish supported and unsupported motion")
	scene.queue_free()
	await process_frame


func _check_boundary_control() -> void:
	var scene := await _new_walkthrough()
	var wall_path := "R000/AuthoredBoundaries/WestBoundary"
	var wall := scene.get_node_or_null(wall_path)
	if wall == null:
		failures.append("open-boundary control could not find the column-room west wall")
		return
	var position := SPAWN
	var motion := Vector3.LEFT * 2.0
	var closed_before := await _probe(scene, position, motion)
	wall.queue_free()
	await process_frame
	await physics_frame
	var escape_after := not await _probe(scene, position, motion)
	results.controls["open_boundary"] = {
		"closed_boundary_blocks_escape": closed_before,
		"removed_boundary_allows_escape": escape_after,
	}
	if not closed_before or not escape_after:
		failures.append("open-boundary control did not distinguish closed and removed boundary")
	scene.queue_free()
	await process_frame


func _check_column_obstacle() -> void:
	var scene := await _new_walkthrough()
	var position := Vector3(25.6, FLOOR_Y + 0.6, 3.1)
	var motion := Vector3(-2.0, 0.0, 0.0)
	var collides := await _probe(scene, position, motion)
	var column := scene.get_node_or_null("R002/AuthoredBoundaries/ColumnObstacle")
	results.controls["source_room_column_obstacle"] = {
		"collision_node_present": column != null,
		"approach_collides": collides,
		"center_world": [COLUMN_CENTER.x, COLUMN_CENTER.y, COLUMN_CENTER.z],
	}
	if column == null or not collides:
		failures.append("third-room column is missing or its authored obstacle collider is ineffective")
	scene.queue_free()
	await process_frame


func _write_results() -> void:
	var path := ProjectSettings.globalize_path(EVIDENCE_PATH)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(EVIDENCE_PATH, FileAccess.WRITE)
	if file == null:
		failures.append("cannot write physics-control evidence")
		return
	file.store_string(JSON.stringify(results, "\t") + "\n")
