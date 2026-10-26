extends SceneTree

const ASSEMBLY := "res://scenes/issue166_four_room_walkthrough.tscn"
const CORRIDOR_STANDALONE := "res://scenes/issue166_transfer_room_socket_standalone.tscn"
const LARGE_STANDALONE := "res://scenes/issue166_room_large_dual_socket_standalone.tscn"
const DEFAULT_OUTPUT := "res://evidence/2026-10-26-four-room-transfer/mechanics/connection_controls.json"
const FLOOR_Y := -1.27099049

var failures: Array[String] = []
var report := {"registration_accepted": false, "scale_calibrated": false}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var assembly := await _instance(ASSEMBLY)
	if assembly == null:
		quit(1)
		return
	_check_assembly(assembly)
	_check_new_connection(assembly)
	await _check_connector_negative(assembly)
	assembly.queue_free()
	await process_frame
	var corridor := await _instance(CORRIDOR_STANDALONE)
	if corridor != null:
		_check_standalone(corridor, "corridor")
		_check_corridor_perimeter(corridor)
		await _check_boundary_negative(corridor)
		await _check_floor_negative(corridor)
		corridor.queue_free()
		await process_frame
	var large_room := await _instance(LARGE_STANDALONE)
	if large_room != null:
		_check_standalone(large_room, "large_room")
		_check_large_room_caps(large_room)
		large_room.queue_free()
	_write_report()
	quit(0 if failures.is_empty() else 1)


func _instance(path: String) -> Node3D:
	var packed := load(path) as PackedScene
	_expect(packed != null, "Scene failed to load: " + path)
	if packed == null:
		return null
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	for _tick in range(3):
		await physics_frame
	if path == ASSEMBLY:
		for _tick in range(2):
			await process_frame
	return scene


func _check_assembly(scene: Node3D) -> void:
	var expected := ["R000", "R001", "R002", "R003"]
	var seen: Array[String] = []
	for instance_id in expected:
		var room := scene.get_node_or_null(instance_id)
		_expect(room != null, "Missing assembled room " + instance_id)
		if room != null:
			seen.append(String(room.get_meta("room_id", room.get_meta("layout_module_id", ""))))
	_expect(scene.get_meta("walkthrough_ready", false), "Assembly did not reach its ready state")
	_expect(scene.get_meta("operator_approved", true) == false, "Candidate was promoted before review")
	_expect(scene.get_meta("registration_accepted", true) == false, "Registration flag changed")
	_expect(scene.get_meta("scale_calibrated", true) == false, "Scale flag changed")
	var expected_designs := [
		"godot_later_bay_column_bounded_v1",
		"godot_early_pocket_pass_through_v1",
		"godot_source_textured_large_room_dual_socket_candidate_v1",
		"godot_corridor_corner_socket_candidate_v1",
	]
	for index in expected.size():
		var room := scene.get_node_or_null(expected[index])
		if room != null:
			_expect(room.get_meta("layout_module_id", "") == expected_designs[index],
				"Room %s has unexpected module identity" % expected[index])
	report["four_distinct_room_designs"] = true


func _check_new_connection(scene: Node3D) -> void:
	var edges: Array = scene.get_meta("candidate_connections", [])
	_expect(edges.size() == 3, "Four-room chain should have exactly three connections")
	if edges.size() != 3:
		return
	var edge: Dictionary = edges[2]
	var left: Dictionary = scene.call("get_connection_socket_world", edge.from)
	var right: Dictionary = scene.call("get_connection_socket_world", edge.to)
	_expect(not left.is_empty() and not right.is_empty(), "New socket world transforms are missing")
	if left.is_empty() or right.is_empty():
		return
	_expect(left.position.distance_to(right.position) < 0.001, "New socket centers do not align")
	_expect(left.normal.dot(right.normal) < -0.999, "New socket normals do not oppose")
	_expect(left.size == right.size and absf(left.floor_y - right.floor_y) < 0.001,
		"New socket dimensions or floor elevations differ")
	var space := scene.get_world_3d().direct_space_state
	var west_position: Vector3 = left.position + Vector3(-0.5, 0.6, 0.0)
	var east_position: Vector3 = left.position + Vector3(0.7, 0.6, 0.0)
	var clear_west := _capsule_hits(space, west_position, []).is_empty()
	var clear_east := _capsule_hits(space, east_position, []).is_empty()
	_expect(clear_west and clear_east, "Full capsule approach is obstructed on one side")
	var seam_support := _check_seam_floor(space, left.position)
	_expect(seam_support, "Floor support is discontinuous across the new seam")
	var jambs := _check_socket_frames(scene)
	_expect(jambs, "Socket frame visuals and collision do not match")
	var contained := _check_render_containment(scene)
	_expect(contained, "New receiver or corridor geometry escaped its rendered envelope")
	report["new_connection"] = {
		"id": edge.id,
		"socket_center": [left.position.x, left.position.y, left.position.z],
		"normal_dot": left.normal.dot(right.normal),
		"clear_size": left.size,
		"approach_capsule_clear_both_sides": clear_west and clear_east,
		"floor_support_across_seam": seam_support,
		"jamb_header_visual_collision_match": jambs,
		"rendered_meshes_within_declared_envelopes": contained,
	}


func _check_seam_floor(space: PhysicsDirectSpaceState3D, center: Vector3) -> bool:
	for offset in range(-10, 11):
		var x := center.x + float(offset) * 0.1
		var query := PhysicsRayQueryParameters3D.create(
			Vector3(x, center.y + 0.5, center.z), Vector3(x, center.y - 0.15, center.z))
		query.collision_mask = 1
		if space.intersect_ray(query).is_empty():
			return false
	return true


func _check_socket_frames(scene: Node3D) -> bool:
	var declarations := [
		["R002/AuthoredBoundaries/WestBackReturn_Left", Vector3(0.12, 3.2, 4.0)],
		["R002/AuthoredBoundaries/WestBackReturn_Right", Vector3(0.12, 3.2, 4.0)],
		["R002/AuthoredBoundaries/WestBackHeader", Vector3(0.12, 1.1, 2.0)],
		["R003/AuthoredBoundaries/WestSocketReturn_Left", Vector3(0.16, 3.0, 1.08)],
		["R003/AuthoredBoundaries/WestSocketReturn_Right", Vector3(0.16, 3.0, 1.08)],
		["R003/AuthoredBoundaries/WestSocketHeader", Vector3(0.16, 0.9, 2.0)],
	]
	for declaration in declarations:
		var body := scene.get_node_or_null(declaration[0]) as StaticBody3D
		if body == null:
			print("SOCKET_FRAME_MISSING ", declaration[0])
			var parent := scene.get_node_or_null(declaration[0].get_base_dir())
			if parent != null:
				for child in parent.get_children():
					print("SOCKET_FRAME_CHILD ", child.name)
			return false
		var visual := body.get_node_or_null(body.name + "Visual") as MeshInstance3D
		var collider := body.get_node_or_null("CollisionShape3D") as CollisionShape3D
		if visual == null or collider == null:
			print("SOCKET_FRAME_CHILD_MISSING ", body.name, " visual=", visual, " collider=", collider)
			return false
		var mesh := visual.mesh as BoxMesh
		var shape := collider.shape as BoxShape3D
		if mesh == null or shape == null or mesh.size != declaration[1] or shape.size != declaration[1]:
			print("SOCKET_FRAME_SIZE_MISMATCH ", body.name, " mesh=", mesh, " shape=", shape, " expected=", declaration[1])
			return false
	return true


func _check_render_containment(scene: Node3D) -> bool:
	for instance_id in ["R002", "R003"]:
		var room := scene.get_node(instance_id) as Node3D
		var bounds: AABB = room.get_meta("rendered_envelope_bounds_xyz", AABB())
		if bounds.size == Vector3.ZERO:
			return false
		var inverse := room.global_transform.affine_inverse()
		for mesh_instance: MeshInstance3D in room.find_children("*", "MeshInstance3D", true, false):
			if mesh_instance.mesh == null:
				return false
			var local_bounds := mesh_instance.mesh.get_aabb()
			for point in _aabb_corners(local_bounds):
				var room_point := inverse * mesh_instance.global_transform * point
				if not _bounds_contain(bounds, room_point):
					print("RENDER_ESCAPE room=", instance_id, " mesh=", mesh_instance.name,
						" point=", room_point, " bounds=", bounds)
					return false
	return true


func _aabb_corners(bounds: AABB) -> Array[Vector3]:
	var points: Array[Vector3] = []
	for x in [bounds.position.x, bounds.end.x]:
		for y in [bounds.position.y, bounds.end.y]:
			for z in [bounds.position.z, bounds.end.z]:
				points.append(Vector3(x, y, z))
	return points


func _bounds_contain(bounds: AABB, point: Vector3) -> bool:
	return point.x >= bounds.position.x - 0.001 and point.x <= bounds.end.x + 0.001 \
		and point.y >= bounds.position.y - 0.001 and point.y <= bounds.end.y + 0.001 \
		and point.z >= bounds.position.z - 0.001 and point.z <= bounds.end.z + 0.001


func _check_connector_negative(scene: Node3D) -> void:
	var edges: Array = scene.get_meta("candidate_connections", [])
	if edges.size() != 3:
		return
	var socket: Dictionary = scene.call("get_connection_socket_world", edges[2].from)
	var blocker := StaticBody3D.new()
	blocker.name = "NegativeControl_NewConnectorBlocker"
	blocker.position = socket.position + Vector3.UP * 1.05
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.32, 2.1, 2.0)
	collision.shape = shape
	blocker.add_child(collision)
	scene.add_child(blocker)
	await physics_frame
	var hit := _capsule_hits(scene.get_world_3d().direct_space_state,
		socket.position + Vector3.UP * 0.6, [])
	var detected := hit.has("NegativeControl_NewConnectorBlocker")
	_expect(detected, "Blocked-connector negative control did not block the doorway")
	report["blocked_connector_negative_control"] = detected
	blocker.queue_free()
	await physics_frame


func _check_standalone(scene: Node3D, label: String) -> void:
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, "%s standalone scene omitted its player" % label)
	if player == null:
		return
	var spawn := player.global_position
	var has_floor := _floor_at(scene.get_world_3d().direct_space_state, spawn.x, spawn.z,
		FLOOR_Y if label == "large_room" else 0.0)
	player.global_position = Vector3(1000.0, 1000.0, 1000.0)
	player.velocity = Vector3(4.0, 2.0, -3.0)
	scene.call("_reset_player")
	_expect(player.global_position.distance_to(spawn) < 0.001, "%s reset did not restore its spawn" % label)
	_expect(player.velocity.length() < 0.001, "%s reset did not clear velocity" % label)
	_expect(has_floor, "%s spawn lacks floor support" % label)
	_expect(scene.get_meta("registration_accepted", true) == false, "%s changed registration flag" % label)
	_expect(scene.get_meta("scale_calibrated", true) == false, "%s changed scale flag" % label)
	report[label + "_standalone"] = {"safe_spawn": true, "reset_restores_spawn": true,
		"reset_clears_velocity": true, "spawn_floor_supported": has_floor,
		"open_socket_ids": scene.get_meta("open_socket_ids", PackedStringArray())}


func _check_corridor_perimeter(scene: Node3D) -> void:
	var player := scene.get_node("Player") as CharacterBody3D
	var space := scene.get_world_3d().direct_space_state
	var probes := [
		["Boundary_WestOuter", Vector3(-6.0, 0.6, 0.0)],
		["Boundary_SouthMain", Vector3(-3.0, 0.6, -2.0)],
		["Boundary_InnerElbow", Vector3(0.0, 0.6, -4.5)],
		["Boundary_FarCap", Vector3(2.0, 0.6, -7.0)],
		["Boundary_EastOuter", Vector3(4.0, 0.6, -2.5)],
		["Boundary_NorthMain", Vector3(-1.0, 0.6, 2.0)],
	]
	var results := {}
	for probe in probes:
		var hits := _capsule_hits(space, probe[1], [])
		var blocked := hits.has(probe[0])
		results[probe[0]] = blocked
		_expect(blocked, "Closed standalone perimeter is missing or capsule-passable: " + probe[0])
	report["corridor_closed_perimeter"] = results


func _check_boundary_negative(scene: Node3D) -> void:
	var player := scene.get_node("Player") as CharacterBody3D
	var boundary := scene.get_node_or_null("AuthoredBoundaries/Boundary_EastOuter")
	if boundary == null:
		_expect(false, "Boundary negative control has no east perimeter collider")
		return
	player.global_position = Vector3(3.5, 0.6, -2.5)
	var before := player.test_move(player.global_transform, Vector3(1.0, 0.0, 0.0))
	boundary.queue_free()
	await physics_frame
	var after := player.test_move(player.global_transform, Vector3(1.0, 0.0, 0.0))
	var passed := before and not after
	_expect(passed, "Open-boundary negative control did not permit boundary escape")
	report["open_boundary_negative_control"] = {"closed_wall_blocks": before, "removed_wall_allows_escape": not after}


func _check_floor_negative(scene: Node3D) -> void:
	var player := scene.get_node("Player") as CharacterBody3D
	player.global_position = Vector3(2.0, 0.6, -5.0)
	var from := player.global_transform
	var before := player.test_move(from, Vector3.DOWN * 1.0)
	var floor_body := scene.get_node_or_null("AuthoredBoundaries/WalkableFloor")
	if floor_body == null:
		_expect(false, "Missing-floor control has no floor collider")
		return
	floor_body.queue_free()
	await physics_frame
	var after := player.test_move(from, Vector3.DOWN * 1.0)
	var passed := before and not after
	_expect(passed, "Missing-floor negative control did not expose the floor gap")
	report["missing_floor_negative_control"] = {"floor_blocks_fall": before, "removed_floor_allows_fall": not after}


func _check_large_room_caps(scene: Node3D) -> void:
	var opened: PackedStringArray = scene.get_meta("open_socket_ids", PackedStringArray())
	_expect(opened.is_empty(), "Standalone large-room adapter left a connection open")
	for node_path in ["AuthoredBoundaries/WestWall", "AuthoredBoundaries/HallEndBoundary"]:
		_expect(scene.get_node_or_null(node_path) != null, "Standalone large-room adapter lacks cap " + node_path)
	report["large_room_caps_closed"] = {
		"west_cap": scene.get_node_or_null("AuthoredBoundaries/WestWall") != null,
		"hall_end_cap": scene.get_node_or_null("AuthoredBoundaries/HallEndBoundary") != null,
	}


func _floor_at(space: PhysicsDirectSpaceState3D, x: float, z: float, floor_y: float) -> bool:
	var query := PhysicsRayQueryParameters3D.create(Vector3(x, floor_y + 0.5, z), Vector3(x, floor_y - 0.15, z))
	query.collision_mask = 1
	return not space.intersect_ray(query).is_empty()


func _capsule_hits(space: PhysicsDirectSpaceState3D, center: Vector3, ignored: Array[String]) -> Array[String]:
	var shape := CapsuleShape3D.new()
	shape.radius = 0.3
	shape.height = 1.2
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, center)
	query.collision_mask = 1
	var names: Array[String] = []
	for result in space.intersect_shape(query, 64):
		var collider := result.get("collider") as Node
		if collider == null or collider.name in ignored:
			continue
		if collider.name.begins_with("ConnectorThreshold") or collider.name in ["WalkableFloor", "AuthoredFloor", "AuthoredPlanarRouteFloor"]:
			continue
		names.append(collider.name)
	return names


func _write_report() -> void:
	report["failures"] = failures
	var output_path := DEFAULT_OUTPUT
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--output="):
			output_path = argument.trim_prefix("--output=")
	var path := ProjectSettings.globalize_path(output_path)
	if FileAccess.file_exists(output_path):
		_fail("Refusing to overwrite connection controls report")
		return
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(output_path, FileAccess.WRITE)
	if file == null:
		_fail("Cannot write connection controls report")
		return
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("ISSUE166_CONNECTION_CONTROLS " + ("PASS" if failures.is_empty() else "FAIL"))


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE166_CONNECTION_CONTROLS: " + message)
