extends SceneTree

const ROOM_SCENE := preload("res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/room.tscn")
const SPAWN := Vector3(0.0, 0.6, 8.4)

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var room := ROOM_SCENE.instantiate() as Node3D
	root.add_child(room)
	await _physics_steps(12)
	var player := room.get_node("Player") as CharacterBody3D
	_assert(player.is_on_floor(), "player did not settle onto the authored floor")
	_assert(_ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -1.0, 0.0)), "floor ray missed")
	# Move the player's own collider off the x=0 doorway ray path before
	# checking the openings (the #275 harness fix).
	player.global_position = Vector3(3.0, 0.6, 6.0)
	await _physics_steps(2)
	_check_socket_openings(room)
	_check_closed_boundaries(room)
	await _traverse_opening(player, Vector3(0.0, 0.6, -8.5), "move_forward", true)
	await _traverse_opening(player, Vector3(0.0, 0.6, 8.5), "move_back", false)
	_check_negative_controls(room)
	_check_reset(room, player)
	if not _failed:
		print("CHEVRON_T_THROUGH_VARIANT_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_socket_openings(room: Node3D) -> void:
	_assert(not _ray_hits(room, Vector3(0.0, 1.0, -8.0), Vector3(0.0, 1.0, -12.0)), "north doorway is blocked below the header")
	_assert(not _ray_hits(room, Vector3(0.0, 1.0, 8.0), Vector3(0.0, 1.0, 12.0)), "south doorway is blocked below the header")
	_assert(_ray_hits(room, Vector3(0.0, 3.0, -8.0), Vector3(0.0, 3.0, -12.0)), "north socket header collider is missing")
	_assert(_ray_hits(room, Vector3(0.0, 3.0, 8.0), Vector3(0.0, 3.0, 12.0)), "south socket header collider is missing")
	_assert(_ray_hits(room, Vector3(4.0, 1.0, -8.0), Vector3(4.0, 1.0, -12.0)), "north side wall collider is missing")
	_assert(_ray_hits(room, Vector3(4.0, 1.0, 8.0), Vector3(4.0, 1.0, 12.0)), "south side wall collider is missing")
	var meta: Array = room.get_meta("authored_sockets")
	_assert(meta.size() == 2, "two authored sockets are not declared")
	_assert(room.get_meta("socket_test_status") == "untested", "sockets must start untested")
	# The inherited interior partitions must remain in place and must not
	# intrude into the x in [-1, 1] doorway approach sector.
	_assert(room.get_node("AuthoredObstacles").get_child_count() >= 4, "inherited partition obstacles are missing")
	_assert(not _ray_hits(room, Vector3(0.0, 1.0, -8.0), Vector3(0.0, 1.0, 8.0)), "central lane is blocked by a partition")


func _check_closed_boundaries(room: Node3D) -> void:
	# z=8.5 is outside every inherited partition z-range, so these rays
	# measure the perimeter wall itself rather than a partition.
	_assert(_ray_hits(room, Vector3(-4.0, 1.0, 8.5), Vector3(-9.0, 1.0, 8.5)), "west boundary is not closed")
	_assert(_ray_hits(room, Vector3(4.0, 1.0, 8.5), Vector3(9.0, 1.0, 8.5)), "east boundary is not closed")
	_assert(room.get_node("AuthoredBoundaries/WestBoundary") != null, "west boundary collider node missing")
	_assert(room.get_node("AuthoredBoundaries/EastBoundary") != null, "east boundary collider node missing")


func _traverse_opening(player: CharacterBody3D, start: Vector3, action: String, expects_north: bool) -> void:
	player.global_position = start
	player.velocity = Vector3.ZERO
	await _physics_steps(2)
	Input.action_press(action)
	await _physics_steps(60)
	Input.action_release(action)
	var crossed := player.global_position.z < -10.1 if expects_north else player.global_position.z > 10.1
	_assert(crossed, "player could not walk through the %s doorway" % ("north" if expects_north else "south"))


func _check_negative_controls(room: Node3D) -> void:
	var floor_body := room.get_node("AuthoredBoundaries/WalkableFloor") as StaticBody3D
	floor_body.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -1.0, 0.0)), "missing-floor negative control unexpectedly hit")
	floor_body.collision_layer = 1
	var wall := room.get_node("AuthoredBoundaries/WestBoundary") as StaticBody3D
	wall.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(-4.0, 1.0, 8.5), Vector3(-9.0, 1.0, 8.5)), "open-boundary negative control unexpectedly hit")
	wall.collision_layer = 1


func _check_reset(room: Node3D, player: CharacterBody3D) -> void:
	player.global_position = Vector3(0.0, -5.0, 0.0)
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	room.call("_unhandled_key_input", event)
	_assert(player.global_position.distance_to(SPAWN) < 0.01, "R reset did not return to safe spawn")


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("CHEVRON_T_THROUGH_VARIANT_TEST_FAILURE: ", message)
