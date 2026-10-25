extends SceneTree

const FLOOR_Y := -1.27099049
var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_verify")


func _verify() -> void:
	var capture_script := load("res://scripts/capture_issue160.gd") as Script
	_expect(capture_script != null, "Capture script does not parse")
	var column := _load_room("res://scenes/issue160_bounded_column_room.tscn")
	await physics_frame
	_verify_module_flags(column)
	_verify_column_obstacles(column)
	column.queue_free()
	await process_frame
	await _verify_openings_and_seam()
	for failure in failures:
		printerr(failure)
	print("ISSUE160_ROOM_CONTRACT: ", "PASS" if failures.is_empty() else "FAIL")
	quit(0 if failures.is_empty() else 1)


func _load_room(path: String) -> Node3D:
	var packed := load(path) as PackedScene
	if packed == null:
		_expect(false, "Cannot load scene %s" % path)
		return Node3D.new()
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	return room


func _verify_module_flags(room: Node3D) -> void:
	_expect(not room.get_meta("registration_accepted", true), "Registration flag changed")
	_expect(not room.get_meta("scale_calibrated", true), "Scale calibration flag changed")
	_expect(not room.get_meta("generation_ready", true), "Module was promoted without review")
	_expect(not room.get_meta("operator_approved", true), "Operator approval was inferred")


func _verify_column_obstacles(room: Node3D) -> void:
	var face := room.get_node("AuthoredBoundaries/FourSidedColumnBox/EastSourceFace") as MeshInstance3D
	var face_material := face.mesh.material as StandardMaterial3D
	_expect(face.mesh.size.is_equal_approx(Vector2(1.5, 2.4)), "Accepted C01 face size changed")
	_expect(is_equal_approx(face.position.x, 0.78 + 0.006), "Accepted C01 face offset changed")
	_expect(face_material != null and face_material.uv1_scale == Vector3.ONE,
		"Accepted C01 texture or UV treatment changed")
	var c01 := room.get_node("AuthoredBoundaries/C01Collision/CollisionShape3D") as CollisionShape3D
	var c01_shape := c01.shape as BoxShape3D
	_expect(c01_shape != null and c01_shape.size.is_equal_approx(Vector3(0.732, 2.4, 1.512)),
		"C01 collision no longer fits the accepted visual prism")
	var c02 := room.get_node("AuthoredBoundaries/C02EstimatedPrism/CollisionShape3D") as CollisionShape3D
	var c02_shape := c02.shape as BoxShape3D
	_expect(c02_shape != null and c02_shape.size.is_equal_approx(Vector3(0.575, 2.4, 0.8)),
		"C02 authored prism and collider disagree")
	var player := room.get_node("Player") as CharacterBody3D
	var space := room.get_world_3d().direct_space_state
	_check_four_sides(space, player, "C01Collision", Vector3(0.42, FLOOR_Y + 1.2, 1.05))
	_check_four_sides(space, player, "C02EstimatedPrism", Vector3(-0.7125, FLOOR_Y + 1.2, 4.425))
	var visual := room.get_node("BoundedHunyuanVisual")
	_expect(visual.find_children("*", "MeshInstance3D", true, false).size() == 2,
		"Bounded Hunyuan derivative did not load both source layers")


func _check_four_sides(space: PhysicsDirectSpaceState3D, player: CharacterBody3D,
		target_name: String, center: Vector3) -> void:
	for direction in [Vector3.RIGHT, Vector3.LEFT, Vector3.FORWARD, Vector3.BACK]:
		var approach_distance := 0.7 if target_name == "C02EstimatedPrism" \
			and direction == Vector3.BACK else 2.0
		var query := PhysicsRayQueryParameters3D.create(center + direction * approach_distance,
			center - direction * 2.0)
		query.exclude = [player.get_rid()]
		var hit := space.intersect_ray(query)
		_expect(not hit.is_empty() and hit.collider.name == target_name,
			"%s is not collidable from side %s; hit=%s" % [
				target_name, direction, hit.get("collider", "none")
			])


func _verify_openings_and_seam() -> void:
	var assembly := _load_room("res://scenes/issue160_assembled_walkthrough.tscn")
	await physics_frame
	var column := assembly.get_node("ColumnRoom") as Node3D
	var pocket := assembly.get_node("PocketRoom") as Node3D
	_expect(assembly.get_meta("observed_openings").is_empty(),
		"Authored sockets were incorrectly labeled as source-observed openings")
	_expect(assembly.get_meta("tested_connectors").has("column_east__pocket_west_v1"),
		"Mechanically tested connector is missing its separate catalog ID")
	var column_socket: Dictionary = column.get_meta("authored_socket")
	var pocket_socket: Dictionary = pocket.get_meta("authored_socket")
	var column_world: Vector3 = column.global_transform * column_socket.floor_center
	var pocket_world: Vector3 = pocket.global_transform * pocket_socket.floor_center
	var column_normal: Vector3 = column.global_basis * column_socket.outward_normal
	var pocket_normal: Vector3 = pocket.global_basis * pocket_socket.outward_normal
	_expect(column_world.distance_to(pocket_world) < 0.001, "Authored socket centers do not align")
	_expect(column_normal.dot(pocket_normal) < -0.999, "Socket normals do not oppose")
	_expect(column_socket.clear_size == pocket_socket.clear_size, "Socket clear sizes differ")
	var player := assembly.get_node("Player") as CharacterBody3D
	var space := assembly.get_world_3d().direct_space_state
	var center := Vector3(3.5, FLOOR_Y + 0.62, 3.1)
	var capsule: Shape3D = player.get_node("CollisionShape3D").shape
	var capsule_query := PhysicsShapeQueryParameters3D.new()
	capsule_query.shape = capsule
	capsule_query.transform = Transform3D(Basis.IDENTITY, center)
	capsule_query.collision_mask = player.collision_mask
	capsule_query.exclude = [player.get_rid()]
	capsule_query.margin = 0.0
	_expect(space.intersect_shape(capsule_query, 1).is_empty(), "Capsule does not clear the connector")
	_check_connector_ray(space, player, center, Vector3(1.0, 0.0, 0.0), "opening")
	_check_connector_ray(space, player, center + Vector3(0.0, -0.2, 0.0),
		Vector3(1.0, 0.0, 0.0), "threshold")
	_check_floor(space, player, Vector3(3.38, FLOOR_Y + 0.8, 3.1))
	_check_floor(space, player, Vector3(3.5, FLOOR_Y + 0.8, 3.1))
	_check_floor(space, player, Vector3(3.62, FLOOR_Y + 0.8, 3.1))
	var lintel_ray := PhysicsRayQueryParameters3D.create(
		Vector3(2.8, FLOOR_Y + 2.25, 3.1), Vector3(4.2, FLOOR_Y + 2.25, 3.1))
	lintel_ray.exclude = [player.get_rid()]
	_expect(not space.intersect_ray(lintel_ray).is_empty(), "Connector lintels leave a ceiling leak")
	var boundary_ray := PhysicsRayQueryParameters3D.create(
		Vector3(2.8, FLOOR_Y + 1.0, 1.85), Vector3(4.2, FLOOR_Y + 1.0, 1.85))
	boundary_ray.exclude = [player.get_rid()]
	_expect(not space.intersect_ray(boundary_ray).is_empty(), "Connector jambs leave a side seam")


func _check_connector_ray(space: PhysicsDirectSpaceState3D, player: CharacterBody3D,
		center: Vector3, direction: Vector3, label: String) -> void:
	var ray := PhysicsRayQueryParameters3D.create(center - direction * 0.7,
		center + direction * 0.7)
	ray.exclude = [player.get_rid()]
	_expect(space.intersect_ray(ray).is_empty(), "Connector has an unexpected %s obstruction" % label)


func _check_floor(space: PhysicsDirectSpaceState3D, player: CharacterBody3D, start: Vector3) -> void:
	var ray := PhysicsRayQueryParameters3D.create(start, start - Vector3.UP * 1.2)
	ray.exclude = [player.get_rid()]
	var hit := space.intersect_ray(ray)
	_expect(not hit.is_empty() and hit.normal.y > 0.7
		and absf(hit.position.y - FLOOR_Y) < 0.03,
		"Connector floor transition has a gap or step at %s" % start)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
