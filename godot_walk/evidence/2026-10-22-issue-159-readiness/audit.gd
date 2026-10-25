extends SceneTree

const OUTPUT := "res://evidence/2026-10-22-issue-159-readiness"
const GRID := preload("res://scripts/walkable_area_grid.gd")
var scene: Node3D
var player: CharacterBody3D


func _initialize() -> void:
	call_deferred("_audit")


func _audit() -> void:
	scene = load("res://scenes/library_column_room.tscn").instantiate()
	root.add_child(scene)
	player = scene.get_node("Player")
	player.set_physics_process(false)
	player.set_process(false)
	for tick in 3:
		await physics_frame
	var report := _measure()
	report["collisions"] = _collisions()
	report["point_probes"] = _probes()
	report["source_geometry"] = _geometry()
	report["registration_accepted"] = scene.get_meta("registration_accepted")
	report["scale_calibrated"] = scene.get_meta("scale_calibrated")
	_save("audit.json", report)
	print("READINESS_AUDIT_COMPLETE")
	quit()


func _measure() -> Dictionary:
	var space := player.get_world_3d().direct_space_state
	var capsule: CapsuleShape3D = player.get_node("CollisionShape3D").shape
	var excluded: Array[RID] = [player.get_rid()]
	var query := GRID._capsule_query(capsule, player.collision_mask, excluded)
	var floor_names := PackedStringArray(["AuthoredFloor"])
	var floor_y: float = scene.get_meta("walk_floor_y")
	var cells := GRID._sample_grid(space, query, player.collision_mask, excluded,
		scene.get_meta("walk_envelope"), floor_y, GRID._floor_name_set(floor_names))
	var coordinates: Array = []
	for cell: Vector2i in cells:
		coordinates.append([cell.x, cell.y])
	_save("capsule_clear_cells.json", coordinates)
	return {"capsule": {"radius": capsule.radius, "height": capsule.height},
		"floor_y": floor_y, "grid_step": GRID.GRID_STEP_M,
		"measurement": GRID.measure(space, capsule, player.collision_mask,
			player.get_rid(), scene.get_meta("walk_envelope"), floor_y,
			floor_names, Vector2(player.position.x, player.position.z))}


func _collisions() -> Array:
	var records: Array = []
	for shape: CollisionShape3D in scene.find_children("*", "CollisionShape3D", true, false):
		if shape.get_parent() == player:
			continue
		var record := {"path": str(scene.get_path_to(shape)),
			"center": _coordinates(shape.global_position), "type": shape.shape.get_class()}
		if shape.shape is BoxShape3D:
			record["size"] = _coordinates(shape.shape.size)
		records.append(record)
	return records


func _probes() -> Array:
	var records: Array = []
	var space := player.get_world_3d().direct_space_state
	var excluded: Array[RID] = [player.get_rid()]
	var query := GRID._capsule_query(player.get_node("CollisionShape3D").shape, 1, excluded)
	for point: Vector2 in [Vector2(-0.7, 4.45), Vector2(-2, 3.2), Vector2(0, 5.6), Vector2(5, 4.7)]:
		query.transform.origin = Vector3(point.x, -0.65099049, point.y)
		var hits: Array = []
		for hit: Dictionary in space.intersect_shape(query):
			hits.append(str(hit.collider.name))
		var ray := PhysicsRayQueryParameters3D.create(Vector3(point.x, -0.9, point.y),
			Vector3(point.x, -1.5, point.y), 1, excluded)
		var floor_hit := space.intersect_ray(ray)
		records.append({"xz": [point.x, point.y], "standing_capsule_hits": hits,
			"floor": str(floor_hit.collider.name) if not floor_hit.is_empty() else null})
	return records


func _geometry() -> Dictionary:
	var slice := {}
	var bounds: AABB
	var initialized := false
	var count := 0
	for mesh: MeshInstance3D in scene.get_node("HunyuanVisualOnly").find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for vertex in vertices:
				var world: Vector3 = mesh.global_transform * vertex
				bounds = bounds.expand(world) if initialized else AABB(world, Vector3.ZERO)
				initialized = true
				count += 1
				if absf(world.y) <= 0.1:
					var point := Vector2(snappedf(world.x, 0.025), snappedf(world.z, 0.025))
					slice[point] = true
	var points: Array = []
	for point: Vector2 in slice:
		points.append([point.x, point.y])
	_save("midheight_visual_slice.json", points)
	return {"vertex_entries": count, "world_bounds_min": _coordinates(bounds.position),
		"world_bounds_max": _coordinates(bounds.end), "midheight_slice_y": [-0.1, 0.1],
		"slice_quantization": 0.025, "slice_points": points.size(),
		"bounds_are_walkable": false}


func _save(filename: String, document: Variant) -> void:
	var file := FileAccess.open(OUTPUT.path_join(filename), FileAccess.WRITE)
	if file == null:
		push_error("Cannot write audit evidence: " + filename)
		quit(2)
		return
	file.store_string(JSON.stringify(document, "\t") + "\n")


func _coordinates(vector: Vector3) -> Array:
	return [vector.x, vector.y, vector.z]
