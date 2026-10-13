extends RefCounted

const GRID_STEP_M := 0.1
const FLOOR_NORMAL_MIN_Y := 0.7
const FLOOR_HEIGHT_TOLERANCE_M := 0.15
const NEIGHBORS := [Vector2i.RIGHT, Vector2i.LEFT, Vector2i.DOWN, Vector2i.UP]


static func measure(space: PhysicsDirectSpaceState3D, capsule: Shape3D,
		collision_mask: int, excluded_rid: RID, envelope: Rect2, floor_y: float,
		floor_names: PackedStringArray, start: Vector2) -> Dictionary:
	var excluded: Array[RID] = [excluded_rid]
	var allowed_floors := _floor_name_set(floor_names)
	var shape_query := _capsule_query(capsule, collision_mask, excluded)
	var walkable := _sample_grid(space, shape_query, collision_mask, excluded,
		envelope, floor_y, allowed_floors)
	var connected := _connected_count(walkable, start)
	var connected_count: int = connected.center_samples
	var area := float(connected_count) * GRID_STEP_M * GRID_STEP_M
	return {
		"grid_step_m": GRID_STEP_M,
		"walkable_center_samples": walkable.size(),
		"spawn_connected_center_samples": connected_count,
		"spawn_sample_offset_m": connected.seed_offset_m,
		"spawn_connected_area_estimate_m2": snappedf(area, 0.001),
		"method": "10 cm capsule grid, 2 cm floor clearance, floor rays, 4-neighbor connectivity",
	}


static func _floor_name_set(floor_names: PackedStringArray) -> Dictionary:
	var names := {}
	for floor_name in floor_names:
		names[floor_name] = true
	return names


static func _capsule_query(capsule: Shape3D, collision_mask: int,
		excluded: Array[RID]) -> PhysicsShapeQueryParameters3D:
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = capsule
	query.collision_mask = collision_mask
	query.exclude = excluded
	query.margin = 0.0
	return query


static func _sample_grid(space: PhysicsDirectSpaceState3D,
		shape_query: PhysicsShapeQueryParameters3D, collision_mask: int,
		excluded: Array[RID], envelope: Rect2, floor_y: float,
		allowed_floors: Dictionary) -> Dictionary:
	var walkable := {}
	var first_x := ceili(envelope.position.x / GRID_STEP_M)
	var last_x := floori(envelope.end.x / GRID_STEP_M)
	var first_z := ceili(envelope.position.y / GRID_STEP_M)
	var last_z := floori(envelope.end.y / GRID_STEP_M)
	for grid_x in range(first_x, last_x + 1):
		for grid_z in range(first_z, last_z + 1):
			var cell := Vector2i(grid_x, grid_z)
			var centre := Vector3(grid_x * GRID_STEP_M, floor_y + 0.6,
				grid_z * GRID_STEP_M)
			if _is_walkable(space, shape_query, collision_mask, excluded,
					centre, floor_y, allowed_floors):
				walkable[cell] = true
	return walkable


static func _is_walkable(space: PhysicsDirectSpaceState3D,
		shape_query: PhysicsShapeQueryParameters3D, collision_mask: int,
		excluded: Array[RID], centre: Vector3, floor_y: float,
		allowed_floors: Dictionary) -> bool:
	var from := Vector3(centre.x, floor_y + 0.5, centre.z)
	var to := Vector3(centre.x, floor_y - 0.2, centre.z)
	var ray := PhysicsRayQueryParameters3D.create(from, to, collision_mask, excluded)
	var hit := space.intersect_ray(ray)
	if not _is_allowed_floor_hit(hit, floor_y, allowed_floors):
		return false
	shape_query.transform = Transform3D(Basis.IDENTITY, centre + Vector3.UP * 0.02)
	return space.intersect_shape(shape_query, 1).is_empty()


static func _is_allowed_floor_hit(hit: Dictionary, floor_y: float,
		allowed_floors: Dictionary) -> bool:
	if hit.is_empty():
		return false
	var body := hit.get("collider") as CollisionObject3D
	var normal: Vector3 = hit.get("normal", Vector3.ZERO)
	var point: Vector3 = hit.get("position", Vector3.ZERO)
	return (
		body != null
		and allowed_floors.has(str(body.name))
		and normal.y >= FLOOR_NORMAL_MIN_Y
		and absf(point.y - floor_y) <= FLOOR_HEIGHT_TOLERANCE_M
	)


static func _connected_count(walkable: Dictionary, start: Vector2) -> Dictionary:
	var seed := _nearest_walkable_cell(walkable, start)
	if not seed.found:
		return {"center_samples": 0, "seed_offset_m": seed.distance_m}
	var visited := {seed.cell: true}
	var queue: Array[Vector2i] = [seed.cell]
	var cursor := 0
	while cursor < queue.size():
		var cell := queue[cursor]
		cursor += 1
		for offset in NEIGHBORS:
			var neighbor: Vector2i = cell + offset
			if walkable.has(neighbor) and not visited.has(neighbor):
				visited[neighbor] = true
				queue.append(neighbor)
	return {"center_samples": queue.size(), "seed_offset_m": seed.distance_m}


static func _nearest_walkable_cell(walkable: Dictionary, start: Vector2) -> Dictionary:
	if walkable.is_empty():
		return {"found": false, "cell": Vector2i.ZERO, "distance_m": -1.0}
	var best_cell := Vector2i.ZERO
	var best_distance := INF
	for value in walkable:
		var cell: Vector2i = value
		var centre := Vector2(cell.x, cell.y) * GRID_STEP_M
		var distance := centre.distance_to(start)
		if distance < best_distance:
			best_cell = cell
			best_distance = distance
	return {"found": best_distance <= 0.25, "cell": best_cell, "distance_m": best_distance}
