extends SceneTree

const ROOM_SCENE := preload("res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/room.tscn")
const PLAYER_SPEED := 4.0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var room := ROOM_SCENE.instantiate() as Node3D
	root.add_child(room)
	await _physics_steps(12)
	var player := room.get_node("Player") as CharacterBody3D
	_assert(player.is_on_floor(), "player did not settle onto the authored floor")
	_assert(_ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -1.0, 0.0)), "floor ray missed")
	_assert(_ray_hits(room, Vector3(0.0, 1.0, 0.0), Vector3(0.0, 1.0, -9.0)), "north boundary ray missed")
	_assert(_ray_hits(room, Vector3(-5.6, 4.0, -1.5), Vector3(-5.6, 0.0, -1.5)), "support post ray missed")
	await _walk_and_backtrack(player, room)
	_check_floor_negative(room)
	_check_boundary_negative(room)
	_check_reset(room, player)
	if not _failed:
		print("INDUSTRIAL_HALL_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


var _failed := false


func _walk_and_backtrack(player: CharacterBody3D, room: Node3D) -> void:
	var start := player.global_position
	Input.action_press("move_right")
	await _physics_steps(55)
	Input.action_release("move_right")
	_assert(player.global_position.x > start.x + 2.2, "player did not walk across the room")
	_assert(player.is_on_floor(), "player lost floor support during traversal")
	Input.action_press("move_left")
	await _physics_steps(55)
	Input.action_release("move_left")
	_assert(absf(player.global_position.x - start.x) < 0.8, "player could not backtrack to the spawn lane")
	_assert(_inside_room(player.global_position), "walked player crossed an exposed boundary")
	_assert(room.get_node("AuthoredObstacles").get_child_count() >= 7, "authored supports or rubble obstacles are missing")


func _check_floor_negative(room: Node3D) -> void:
	var floor_body := room.get_node("AuthoredBoundaries/WalkableFloor") as StaticBody3D
	floor_body.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -1.0, 0.0)), "missing-floor negative control unexpectedly hit")
	floor_body.collision_layer = 1


func _check_boundary_negative(room: Node3D) -> void:
	var wall := room.get_node("AuthoredBoundaries/NorthBoundary") as StaticBody3D
	wall.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 1.0, 0.0), Vector3(0.0, 1.0, -9.0)), "open-boundary negative control unexpectedly hit")
	wall.collision_layer = 1


func _check_reset(room: Node3D, player: CharacterBody3D) -> void:
	player.global_position = Vector3(0.0, -5.0, 0.0)
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	room.call("_unhandled_key_input", event)
	_assert(player.global_position.distance_to(Vector3(0.0, 0.6, 4.1)) < 0.01, "R reset did not return to safe spawn")


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _inside_room(position: Vector3) -> bool:
	return position.x > -7.3 and position.x < 7.3 and position.z > -5.8 and position.z < 5.8


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("INDUSTRIAL_HALL_TEST_FAILURE: ", message)
