extends SceneTree

const SCENE_PATH := "res://scenes/issue165_corridor_corner_transfer.tscn"
const GRID_STEP := 0.2

var failures: Array[String] = []
var output_path := "res://evidence/2026-10-25-issue-165/mechanics/transfer_room_runtime.json"


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_path = argument.trim_prefix("--out=")
	call_deferred("_run")


func _run() -> void:
	var packed := load(SCENE_PATH) as PackedScene
	_expect(packed != null, "Transfer scene did not load")
	if packed == null:
		quit(1)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	await physics_frame
	var player := room.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null and room.get_meta("walkthrough_ready", false), "Player or ready state is missing")
	if player == null:
		quit(1)
		return
	_check_contract(room, player)
	await physics_frame
	var space := player.get_world_3d().direct_space_state
	var perimeter := _check_boundary_perimeter(room, player, space)
	var grid := _measure_spawn_connected_space(room, player, space)
	var obstacle: Dictionary = await _check_column_and_negative_control(room, player, space)
	var envelope := _check_render_containment(room)
	_write_report(room, grid, perimeter, envelope, obstacle)
	quit(0 if failures.is_empty() else 1)


func _check_contract(room: Node3D, player: CharacterBody3D) -> void:
	_expect(room.get_meta("registration_accepted") == false, "Registration flag changed")
	_expect(room.get_meta("scale_calibrated") == false, "Scale flag changed")
	_expect(room.get_meta("operator_approved") == false, "New room was promoted before review")
	_expect(room.get_meta("source_video") == "data/videos/corridor_corner.mp4", "Source video identity changed")
	_expect(room.get_node_or_null("AuthoredBoundaries/WalkableFloor") != null, "Separate floor collision is missing")
	_expect(room.get_meta("tested_connectors", PackedStringArray()).is_empty(), "No connector test is declared")
	var before := player.global_position
	player.global_position = Vector3(1000.0, 1000.0, 1000.0)
	player.velocity = Vector3(3.0, 4.0, -2.0)
	room.call("_reset_player")
	_expect(player.global_position.distance_to(before) < 0.001, "Safe reset did not restore spawn")
	_expect(player.velocity.length() < 0.001, "Safe reset did not clear velocity")


func _check_column_and_negative_control(room: Node3D, player: CharacterBody3D,
		space: PhysicsDirectSpaceState3D) -> Dictionary:
	var visual := room.get_node_or_null("AuthoredVisuals/SourceObservedColumnVisual") as MeshInstance3D
	var body := room.get_node_or_null("AuthoredBoundaries/SourceObservedColumnObstacle") as StaticBody3D
	_expect(visual != null and body != null, "Observed column needs separate visible and collision assets")
	if visual == null or body == null:
		return {"positive_blocked": false, "negative_open": false, "approach_clear": []}
	var mesh := visual.mesh as BoxMesh
	var collision := body.get_node_or_null("ColumnCapsuleBlocker") as CollisionShape3D
	_expect(mesh != null and collision != null and mesh.size == collision.shape.size,
		"Column visual and authored collider dimensions differ")
	var center := _capsule_blockers(space, player, Vector3(-2.5, 0.64, 0.0))
	var positive_blocked := center.has("SourceObservedColumnObstacle")
	_expect(positive_blocked, "Full capsule query did not hit the column obstacle")
	var sides := [Vector3(-2.5, 0.64, 1.15), Vector3(-2.5, 0.64, -1.15),
		Vector3(-1.15, 0.64, 0.0), Vector3(-3.85, 0.64, 0.0)]
	var clear_sides := []
	for position in sides:
		var blockers := _capsule_blockers(space, player, position)
		clear_sides.append(blockers.is_empty() and _floor_supported(space, position.x, position.z))
	for side_clear in clear_sides:
		_expect(side_clear, "An approachable column face lacks clear supported space")
	body.queue_free()
	await physics_frame
	var negative_open := not _capsule_blockers(space, player, Vector3(-2.5, 0.64, 0.0)).has("SourceObservedColumnObstacle")
	_expect(negative_open, "Removing the column collider did not disable its blocking effect")
	return {"positive_blocked": positive_blocked, "negative_open": negative_open,
		"approach_clear": clear_sides}


func _check_boundary_perimeter(room: Node3D, player: CharacterBody3D,
		space: PhysicsDirectSpaceState3D) -> Array[Dictionary]:
	var probes := [
		{"id": "west", "body": "Boundary_WestOuter", "wall": Vector3(-6.0, 0.64, 0.0), "approach": Vector3(-5.55, 0.64, 0.0)},
		{"id": "south_main", "body": "Boundary_SouthMain", "wall": Vector3(-3.0, 0.64, -2.0), "approach": Vector3(-3.0, 0.64, -1.55)},
		{"id": "inner_elbow", "body": "Boundary_InnerElbow", "wall": Vector3(0.0, 0.64, -4.5), "approach": Vector3(0.45, 0.64, -4.5)},
		{"id": "far_cap", "body": "Boundary_FarCap", "wall": Vector3(2.0, 0.64, -7.0), "approach": Vector3(2.0, 0.64, -6.55)},
		{"id": "east", "body": "Boundary_EastOuter", "wall": Vector3(4.0, 0.64, -2.5), "approach": Vector3(3.55, 0.64, -2.5)},
		{"id": "north", "body": "Boundary_NorthMain", "wall": Vector3(-1.0, 0.64, 2.0), "approach": Vector3(-1.0, 0.64, 1.55)},
	]
	var results: Array[Dictionary] = []
	for probe: Dictionary in probes:
		results.append(_check_one_boundary(room, player, space, probe))
	return results


func _check_one_boundary(room: Node3D, player: CharacterBody3D,
		space: PhysicsDirectSpaceState3D, probe: Dictionary) -> Dictionary:
	var visual := room.get_node_or_null("AuthoredVisuals/%sVisual" % probe.body) as MeshInstance3D
	var blocks_capsule := _capsule_blockers(space, player, probe.wall).has(probe.body)
	var approach_clear := _capsule_blockers(space, player, probe.approach).is_empty()
	var floor_supported := _floor_supported(space, probe.approach.x, probe.approach.z)
	_expect(visual != null, "Boundary lacks a matching visible wall: %s" % probe.body)
	_expect(blocks_capsule, "Boundary does not block a full capsule: %s" % probe.body)
	_expect(approach_clear and floor_supported, "Boundary approach is not clear and supported: %s" % probe.body)
	return {"id": probe.id, "body": probe.body, "visual_present": visual != null,
		"full_capsule_blocked_at_wall": blocks_capsule,
		"approach_capsule_clear": approach_clear, "approach_floor_supported": floor_supported}


func _measure_spawn_connected_space(room: Node3D, player: CharacterBody3D,
		space: PhysicsDirectSpaceState3D) -> Dictionary:
	var polygon: PackedVector2Array = room.get_meta("walkable_polygon_xz")
	var min_x := -6.0
	var max_x := 4.0
	var min_z := -7.0
	var max_z := 2.0
	var clear := {}
	for ix in range(int((max_x - min_x) / GRID_STEP) + 1):
		for iz in range(int((max_z - min_z) / GRID_STEP) + 1):
			_add_clear_sample(clear, polygon, player, space, min_x + ix * GRID_STEP, min_z + iz * GRID_STEP)
	var start := Vector2i(roundi((player.position.x - min_x) / GRID_STEP), roundi((player.position.z - min_z) / GRID_STEP))
	var connected := _flood(clear, start)
	var area := float(connected.size()) * GRID_STEP * GRID_STEP
	_expect(area > 1.0, "Spawn-connected capsule-clear footprint is empty")
	return {"method": "0.2-unit capsule and floor-ray grid; 4-neighbor flood from spawn", "resolution": GRID_STEP,
		"spawn_connected_samples": connected.size(), "spawn_connected_area_estimate": area,
		"clear_supported_samples": clear.size()}


func _add_clear_sample(clear: Dictionary, polygon: PackedVector2Array, player: CharacterBody3D,
		space: PhysicsDirectSpaceState3D, x: float, z: float) -> void:
	if not _inside_polygon(Vector2(x, z), polygon):
		return
	if not _capsule_blockers(space, player, Vector3(x, 0.64, z)).is_empty():
		return
	if _floor_supported(space, x, z):
		var ix := roundi((x + 6.0) / GRID_STEP)
		var iz := roundi((z + 7.0) / GRID_STEP)
		clear[Vector2i(ix, iz)] = true


func _flood(clear: Dictionary, start: Vector2i) -> Array[Vector2i]:
	var visited: Array[Vector2i] = []
	if not clear.has(start):
		return visited
	var pending: Array[Vector2i] = [start]
	var directions := [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]
	while not pending.is_empty():
		var current: Vector2i = pending.pop_back()
		if visited.has(current):
			continue
		visited.append(current)
		for direction in directions:
			var next: Vector2i = current + direction
			if clear.has(next) and not visited.has(next):
				pending.append(next)
	return visited


func _inside_polygon(point: Vector2, polygon: PackedVector2Array) -> bool:
	var inside := false
	var previous := polygon.size() - 1
	for index in polygon.size():
		var a := polygon[index]
		var b := polygon[previous]
		if (a.y > point.y) != (b.y > point.y):
			var crossing_x := (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x
			if point.x < crossing_x:
				inside = not inside
		previous = index
	return inside


func _capsule_blockers(space: PhysicsDirectSpaceState3D, player: CharacterBody3D,
		center: Vector3) -> Array[String]:
	var shape := CapsuleShape3D.new()
	shape.radius = 0.3
	shape.height = 1.2
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, center)
	query.exclude = [player.get_rid()]
	query.collision_mask = 1
	var names: Array[String] = []
	for result in space.intersect_shape(query, 32):
		var collider := result.get("collider") as Node
		if collider != null and collider.name != "WalkableFloor":
			names.append(collider.name)
	return names


func _floor_supported(space: PhysicsDirectSpaceState3D, x: float, z: float) -> bool:
	var query := PhysicsRayQueryParameters3D.create(Vector3(x, 0.45, z), Vector3(x, -0.12, z))
	query.collision_mask = 1
	var result := space.intersect_ray(query)
	return not result.is_empty() and (result.collider as Node).name == "WalkableFloor"


func _check_render_containment(room: Node3D) -> Dictionary:
	var bounds: AABB = room.get_meta("rendered_envelope_bounds_xyz")
	var failures_found: Array[String] = []
	var meshes := room.find_children("*", "MeshInstance3D", true, false)
	for instance: MeshInstance3D in meshes:
		_check_mesh_bounds(instance, bounds, failures_found)
	_expect(failures_found.is_empty(), "Rendered mesh escaped the declared AABB: %s" % str(failures_found))
	return {"bounds_min": bounds.position, "bounds_size": bounds.size,
		"mesh_count": meshes.size(), "escaped_meshes": failures_found,
		"background_geometry_count": 0}


func _check_mesh_bounds(instance: MeshInstance3D, bounds: AABB, failures_found: Array[String]) -> void:
	if instance.mesh == null:
		failures_found.append(instance.name + ":missing_mesh")
		return
	var local := instance.mesh.get_aabb()
	for x in [local.position.x, local.end.x]:
		for y in [local.position.y, local.end.y]:
			for z in [local.position.z, local.end.z]:
				var world_point := instance.global_transform * Vector3(x, y, z)
				if not bounds.has_point(world_point):
					failures_found.append(instance.name)
					return


func _write_report(room: Node3D, grid: Dictionary, perimeter: Array[Dictionary],
		envelope: Dictionary, obstacle: Dictionary) -> void:
	var report := {"scene": SCENE_PATH, "walkable_grid": grid, "perimeter_checks": perimeter,
		"render_containment": envelope,
		"column_obstacle": obstacle, "registration_accepted": room.get_meta("registration_accepted"),
		"scale_calibrated": room.get_meta("scale_calibrated"), "failures": failures}
	var absolute_path := ProjectSettings.globalize_path(output_path)
	if FileAccess.file_exists(output_path) or FileAccess.file_exists(absolute_path):
		_fail("Refusing to overwrite runtime report: " + output_path)
		return
	DirAccess.make_dir_recursive_absolute(absolute_path.get_base_dir())
	var file := FileAccess.open(absolute_path, FileAccess.WRITE)
	if file == null:
		_fail("Cannot write runtime report: " + output_path)
		return
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("ISSUE165_TRANSFER_ROOM: ", "PASS" if failures.is_empty() else "FAIL")


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE165_TRANSFER_ROOM: " + message)
