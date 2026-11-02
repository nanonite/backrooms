extends SceneTree

const ASSEMBLY_PATH := "res://scenes/issue168_two_room_walkthrough.tscn"
const HALL_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v4-south-socket/room.tscn"
const ROCK_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v2-north-socket/room.tscn"
const SPAWN := Vector3(0.0, 0.6, 4.1)
const SOCKET_Z := 6.5

var failures: Array[String] = []
var report := {"registration_accepted": false, "scale_calibrated": false}
var report_path := "/tmp/issue168-two-room-test.json"


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.trim_prefix("--report=")
	call_deferred("_run")


func _run() -> void:
	var hall := await _load_scene(HALL_PATH)
	if hall != null:
		await _check_standalone_room(hall, "hall", "SouthBoundary")
		hall.queue_free()
		await process_frame
	var rocks := await _load_scene(ROCK_PATH)
	if rocks != null:
		await _check_standalone_room(rocks, "rocks", "NorthBoundary")
		rocks.queue_free()
		await process_frame
	var assembly := await _load_scene(ASSEMBLY_PATH)
	if assembly != null:
		await _check_assembly(assembly)
		assembly.queue_free()
	_write_report()
	if failures.is_empty():
		print("ISSUE168_TWO_ROOM_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _load_scene(path: String) -> Node3D:
	var packed := load(path) as PackedScene
	_expect(packed != null, "Could not load " + path)
	if packed == null:
		return null
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await _physics_steps(8)
	return scene


func _check_standalone_room(room: Node3D, label: String, socket_wall: String) -> void:
	var player := room.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, label + " standalone adapter omitted its player")
	_expect(room.get_meta("connector_open_ids", []).is_empty(), label + " standalone socket is not capped")
	if player == null:
		return
	_expect(player.is_on_floor(), label + " standalone spawn lacks floor support")
	_check_closed_perimeter(room, label, socket_wall)
	await _walk_standalone(player, label)
	_check_standalone_reset(room, player, label)
	report[label + "_standalone"] = {"spawn_supported": true, "socket_capped": true, "walk_and_reset": true}


func _check_closed_perimeter(room: Node3D, label: String, socket_wall: String) -> void:
	var origin_z := 0.0
	var hits := {
		"west": _ray_hits(room, Vector3(0.0, 1.0, origin_z), Vector3(-9.0, 1.0, origin_z)),
		"east": _ray_hits(room, Vector3(0.0, 1.0, origin_z), Vector3(9.0, 1.0, origin_z)),
		"north": _ray_hits(room, Vector3(0.0, 1.0, origin_z), Vector3(0.0, 1.0, -7.0)),
		"south": _ray_hits(room, Vector3(0.0, 1.0, origin_z), Vector3(0.0, 1.0, 7.0)),
	}
	for direction in hits:
		_expect(hits[direction], "%s standalone %s boundary is open" % [label, direction])
	_expect(room.get_node_or_null("AuthoredBoundaries/" + socket_wall) != null,
		label + " standalone socket cap has no collider")


func _walk_standalone(player: CharacterBody3D, label: String) -> void:
	var start_z := player.global_position.z
	Input.action_press("move_forward")
	await _physics_steps(45)
	Input.action_release("move_forward")
	_expect(absf(player.global_position.z - start_z) > 1.0, label + " standalone route did not move")
	_expect(player.is_on_floor(), label + " standalone route lost floor support")


func _check_standalone_reset(room: Node3D, player: CharacterBody3D, label: String) -> void:
	var spawn: Vector3 = room.get_meta("safe_spawn", player.global_position)
	player.global_position = Vector3(1000.0, 1000.0, 1000.0)
	player.velocity = Vector3(4.0, 2.0, -3.0)
	room.call("_unhandled_key_input", _reset_event())
	_expect(player.global_position.distance_to(spawn) < 0.001, label + " reset did not restore spawn")
	_expect(player.velocity.length() < 0.001, label + " reset did not clear velocity")


func _check_assembly(scene: Node3D) -> void:
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, "assembled walkthrough must have one player")
	_expect(scene.get_node_or_null("IndustrialHall") != null, "assembly omitted industrial hall")
	_expect(scene.get_node_or_null("DebrisWindowRockRoom") != null, "assembly omitted rock room")
	_expect(scene.get_meta("candidate_status", "") == "pending_operator_review", "connector candidate was promoted")
	_expect(not scene.get_meta("registration_accepted") and not scene.get_meta("scale_calibrated"), "calibration flags changed")
	if player == null:
		return
	await _check_socket_pair(scene)
	_check_exterior_boundaries(scene)
	await _check_bidirectional_traversal(scene, player)
	await _check_blocked_connector(scene, player)
	_check_floor_negative(scene)
	_check_boundary_negative(scene)
	_check_render_containment(scene)


func _check_socket_pair(scene: Node3D) -> void:
	var first := scene.call("get_connection_socket_world", ["IndustrialHall", "south"]) as Dictionary
	var second := scene.call("get_connection_socket_world", ["DebrisWindowRockRoom", "north"]) as Dictionary
	_expect(not first.is_empty() and not second.is_empty(), "socket metadata is missing")
	if first.is_empty() or second.is_empty():
		return
	_expect(first.position.distance_to(second.position) < 0.001, "socket centers do not align")
	_expect(first.normal.dot(second.normal) < -0.999, "socket normals do not oppose")
	_expect(first.size == second.size and first.size == [2.4, 2.2], "socket clear dimensions differ")
	var space := scene.get_world_3d().direct_space_state
	var clear_positions: Array[Vector3] = []
	for offset in range(-12, 13):
		clear_positions.append(Vector3(0.0, 0.64, SOCKET_Z + float(offset) * 0.1))
	var clear_count := 0
	for position in clear_positions:
		if _capsule_clear(space, position, scene.get_node("Player").get_rid()):
			clear_count += 1
	_expect(clear_count == clear_positions.size(), "capsule approach clearance failed across doorway")
	_check_opening_geometry(scene)
	_check_floor_seam(scene)
	report["socket_pair"] = {"aligned_centers": true, "opposed_normals": true,
		"clear_size": [2.4, 2.2], "capsule_samples_clear": clear_count}


func _check_opening_geometry(scene: Node3D) -> void:
	var through_opening := _ray_hits(scene, Vector3(0.0, 1.1, 5.9), Vector3(0.0, 1.1, 7.1))
	var header_blocks := _ray_hits(scene, Vector3(0.0, 2.5, 5.9), Vector3(0.0, 2.5, 7.1))
	var side_blocks := _ray_hits(scene, Vector3(1.35, 1.1, 5.9), Vector3(1.35, 1.1, 7.1))
	_expect(not through_opening, "doorway center has a visual/collision mismatch")
	_expect(header_blocks and side_blocks, "doorway header or jamb-side wall collider is missing")
	_expect(scene.get_node_or_null("AuthoredConnectorVisuals/SharedDoorHeader") != null,
		"shared connector header visual is missing")


func _check_floor_seam(scene: Node3D) -> void:
	var supported := true
	for offset in range(-11, 12):
		var x := float(offset) * 0.1
		if not _ray_hits(scene, Vector3(x, 0.45, SOCKET_Z), Vector3(x, -0.2, SOCKET_Z)):
			supported = false
	_expect(supported, "floor support is discontinuous across the socket seam")
	report["floor_seam_supported"] = supported


func _check_exterior_boundaries(scene: Node3D) -> void:
	var probes := [
		[Vector3(0.0, 1.0, 0.0), Vector3(-9.0, 1.0, 0.0), "west"],
		[Vector3(0.0, 1.0, 0.0), Vector3(9.0, 1.0, 0.0), "east"],
		[Vector3(0.0, 1.0, 0.0), Vector3(0.0, 1.0, -7.0), "north"],
		[Vector3(0.0, 1.0, 13.0), Vector3(0.0, 1.0, 18.0), "far_south"],
	]
	for probe in probes:
		_expect(_ray_hits(scene, probe[0], probe[1]), "assembled exposed boundary is open: " + probe[2])
	report["outer_boundary_probes"] = probes.size()


func _check_bidirectional_traversal(scene: Node3D, player: CharacterBody3D) -> void:
	Input.action_press("move_forward")
	await _physics_steps(210)
	Input.action_release("move_forward")
	var reached_rock_room := player.global_position.z > 11.5 and player.is_on_floor()
	_expect(reached_rock_room, "player did not traverse hall-to-rock connection")
	var forward_z := player.global_position.z
	Input.action_press("move_back")
	await _physics_steps(210)
	Input.action_release("move_back")
	var returned := player.global_position.z < SPAWN.z + 0.8 and player.is_on_floor()
	_expect(returned, "player did not traverse rock-to-hall connection")
	scene.call("_reset_player")
	var reset := player.global_position.distance_to(SPAWN) < 0.001
	_expect(reset, "assembled walkthrough reset did not restore the safe spawn")
	report["bidirectional_traversal"] = {"reached_rock_room": reached_rock_room,
		"forward_z": forward_z, "returned_to_spawn_area": returned,
		"final_z": player.global_position.z, "reset_restored_spawn": reset}


func _check_blocked_connector(scene: Node3D, player: CharacterBody3D) -> void:
	var blocker := StaticBody3D.new()
	blocker.name = "NegativeControl_BlockedConnector"
	blocker.position = Vector3(0.0, 1.1, SOCKET_Z)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.5, 2.2, 0.5)
	collision.shape = shape
	blocker.add_child(collision)
	scene.add_child(blocker)
	player.global_position = Vector3(0.0, 0.6, 5.0)
	player.velocity = Vector3.ZERO
	await _physics_steps(3)
	Input.action_press("move_forward")
	await _physics_steps(55)
	Input.action_release("move_forward")
	var blocked := player.global_position.z < SOCKET_Z - 0.45
	_expect(blocked, "blocked-connector negative control allowed passage")
	blocker.queue_free()
	await _physics_steps(2)
	report["blocked_connector_negative_control"] = blocked


func _check_floor_negative(scene: Node3D) -> void:
	var bodies := [
		scene.get_node("IndustrialHall/AuthoredBoundaries/WalkableFloor"),
		scene.get_node("DebrisWindowRockRoom/AuthoredBoundaries/WalkableFloor"),
		scene.get_node("AuthoredConnectorBoundaries/DoorwayFloorSeam"),
	]
	var layers: Array[int] = []
	for body: StaticBody3D in bodies:
		layers.append(body.collision_layer)
		body.collision_layer = 0
	var unsupported := not _ray_hits(scene, Vector3(0.0, 0.45, SOCKET_Z), Vector3(0.0, -0.2, SOCKET_Z))
	for index in bodies.size():
		(bodies[index] as StaticBody3D).collision_layer = layers[index]
	_expect(unsupported, "missing-floor negative control did not expose seam loss")
	report["missing_floor_negative_control"] = unsupported


func _check_boundary_negative(scene: Node3D) -> void:
	var boundary := scene.get_node("IndustrialHall/AuthoredBoundaries/WestBoundary") as StaticBody3D
	var closed_blocks := _ray_hits(scene, Vector3(0.0, 1.0, 0.0), Vector3(-9.0, 1.0, 0.0))
	boundary.collision_layer = 0
	var opened_allows := not _ray_hits(scene, Vector3(0.0, 1.0, 0.0), Vector3(-9.0, 1.0, 0.0))
	boundary.collision_layer = 1
	_expect(closed_blocks and opened_allows, "open-boundary negative control failed")
	report["open_boundary_negative_control"] = {"closed_wall_blocks": closed_blocks, "disabled_wall_allows": opened_allows}


func _check_render_containment(scene: Node3D) -> void:
	var bounds: AABB = scene.get_meta("rendered_envelope_bounds_xyz")
	var escaped: Array[String] = []
	for mesh: MeshInstance3D in scene.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			escaped.append(mesh.get_path())
			continue
		var mesh_bounds := mesh.mesh.get_aabb()
		for corner in _aabb_corners(mesh_bounds):
			if not bounds.has_point(mesh.global_transform * corner):
				escaped.append(mesh.get_path())
			break
	_expect(escaped.is_empty(), "rendered mesh escapes declared envelope: " + str(escaped.slice(0, 4)))
	report["render_containment"] = {"escaped_meshes": escaped.size(), "bounds": [bounds.position, bounds.size]}


func _capsule_clear(space: PhysicsDirectSpaceState3D, position: Vector3, excluded_rid: RID) -> bool:
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3
	capsule.height = 1.2
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = capsule
	query.transform = Transform3D(Basis(), position)
	query.collision_mask = 1
	query.exclude = [excluded_rid]
	return space.intersect_shape(query, 8).is_empty()


func _ray_hits(scene: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	query.collision_mask = 1
	return not scene.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _aabb_corners(bounds: AABB) -> Array[Vector3]:
	var result: Array[Vector3] = []
	for x in [bounds.position.x, bounds.end.x]:
		for y in [bounds.position.y, bounds.end.y]:
			for z in [bounds.position.z, bounds.end.z]:
				result.append(Vector3(x, y, z))
	return result


func _reset_event() -> InputEventKey:
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	return event


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _write_report() -> void:
	if FileAccess.file_exists(report_path):
		_expect(false, "refusing to overwrite test report " + report_path)
		return
	var absolute := ProjectSettings.globalize_path(report_path)
	var directory_error := DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	if directory_error != OK:
		_expect(false, "could not create test report directory " + report_path)
		return
	var output := FileAccess.open(report_path, FileAccess.WRITE)
	if output == null:
		_expect(false, "could not write test report " + report_path)
		return
	report["schema_version"] = 1
	report["candidate_status"] = "pending_operator_review"
	report["failures"] = failures
	output.store_string(JSON.stringify(report, "\t") + "\n")


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures.append(message)
	printerr("ISSUE168_TWO_ROOM_TEST_FAILURE: " + message)
