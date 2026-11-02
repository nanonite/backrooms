extends SceneTree

const ROOM_SCENE := preload("res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/room.tscn")


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var room := ROOM_SCENE.instantiate() as Node3D
	root.add_child(room)
	await _physics_steps(12)
	var player := room.get_node("Player") as CharacterBody3D
	_assert(player.is_on_floor(), "player did not settle on the authored floor")
	_assert(_ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -1.0, 0.0)), "floor ray missed")
	_check_boundaries(room)
	_check_rock_field(room)
	await _check_capsule_boundaries(player)
	await _walk_and_backtrack(player)
	await _check_obstacle_block(player, room)
	_check_floor_negative(room)
	_check_boundary_negative(room)
	_check_reset(room, player)
	if not _failed:
		print("DEBRIS_WINDOW_ROCK_ROOM_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


var _failed := false


func _check_boundaries(room: Node3D) -> void:
	var center := Vector3(0.0, 1.0, 0.0)
	_assert(_ray_hits(room, center, Vector3(-7.0, 1.0, 0.0)), "west boundary ray missed")
	_assert(_ray_hits(room, center, Vector3(7.0, 1.0, 0.0)), "east boundary ray missed")
	_assert(_ray_hits(room, center, Vector3(0.0, 1.0, 6.0)), "south boundary ray missed")
	_assert(_ray_hits(room, center, Vector3(0.0, 1.0, -6.0)), "north boundary ray missed")


func _check_capsule_boundaries(player: CharacterBody3D) -> void:
	await _probe_boundary(player, "move_left", Vector3(-5.25, 0.6, 4.65), Vector2(-1.0, 0.0))
	await _probe_boundary(player, "move_right", Vector3(5.25, 0.6, 4.65), Vector2(1.0, 0.0))
	await _probe_boundary(player, "move_forward", Vector3(0.0, 0.6, -4.25), Vector2(0.0, -1.0))
	await _probe_boundary(player, "move_back", Vector3(0.0, 0.6, 4.25), Vector2(0.0, 1.0))
	player.global_position = Vector3(0.0, 0.6, 3.8)
	player.velocity = Vector3.ZERO
	await _physics_steps(4)


func _probe_boundary(player: CharacterBody3D, action: String, start: Vector3, direction: Vector2) -> void:
	player.global_position = start
	player.velocity = Vector3.ZERO
	await _physics_steps(4)
	Input.action_press(action)
	await _physics_steps(60)
	Input.action_release(action)
	var position := player.global_position
	_assert(absf(position.x) < 6.0 and absf(position.z) < 5.0, "%s capsule crossed a closed boundary" % action)
	_assert(Vector2(position.x - start.x, position.z - start.z).dot(direction) > 0.1, "%s boundary probe did not move" % action)
	_assert(player.is_on_floor(), "%s boundary probe lost floor support" % action)


func _check_rock_field(room: Node3D) -> void:
	_assert(room.get_node("AuthoredObstacles").get_child_count() >= 74, "rock obstacle set is too small")
	_assert(_ray_hits(room, Vector3(2.1, 2.0, -0.6), Vector3(2.1, -1.0, -0.6)), "pathside boulder collision ray missed")
	_assert(room.get_node("AuthoredVisuals").get_child_count() >= 350, "visible gravel field is incomplete")


func _walk_and_backtrack(player: CharacterBody3D) -> void:
	var start := player.global_position
	Input.action_press("move_forward")
	await _physics_steps(100)
	Input.action_release("move_forward")
	_assert(player.global_position.z < start.z - 4.0, "player did not traverse the center lane")
	_assert(player.is_on_floor(), "player lost floor support while crossing the room")
	_assert(_inside_room(player.global_position), "player crossed a closed room boundary")
	Input.action_press("move_back")
	await _physics_steps(100)
	Input.action_release("move_back")
	_assert(absf(player.global_position.z - start.z) < 0.9, "player could not backtrack to spawn")


func _check_obstacle_block(player: CharacterBody3D, room: Node3D) -> void:
	player.global_position = Vector3(0.8, 0.6, -0.6)
	player.velocity = Vector3.ZERO
	await _physics_steps(8)
	Input.action_press("move_right")
	await _physics_steps(60)
	Input.action_release("move_right")
	_assert(player.global_position.x < 1.65, "pathside boulder did not stop the capsule")
	_assert(player.is_on_floor(), "player fell while contacting a boulder")


func _check_floor_negative(room: Node3D) -> void:
	var floor_body := room.get_node("AuthoredBoundaries/WalkableFloor") as StaticBody3D
	floor_body.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -1.0, 0.0)), "missing-floor negative control unexpectedly hit")
	floor_body.collision_layer = 1


func _check_boundary_negative(room: Node3D) -> void:
	var wall := room.get_node("AuthoredBoundaries/NorthBoundary") as StaticBody3D
	wall.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 1.0, 0.0), Vector3(0.0, 1.0, -6.0)), "open-boundary negative control unexpectedly hit")
	wall.collision_layer = 1


func _check_reset(room: Node3D, player: CharacterBody3D) -> void:
	player.global_position = Vector3(0.0, -5.0, 0.0)
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	room.call("_unhandled_key_input", event)
	_assert(player.global_position.distance_to(Vector3(0.0, 0.6, 3.8)) < 0.01, "R did not restore the safe spawn")


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _inside_room(position: Vector3) -> bool:
	return absf(position.x) < 5.4 and absf(position.z) < 4.4 and position.y > 0.4


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("DEBRIS_WINDOW_ROCK_ROOM_TEST_FAILURE: ", message)
