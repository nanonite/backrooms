class_name Issue183RoomChecks
extends RefCounted

## Per-room physics checks for generated shape rooms: floor support inside the polygon
## and none outside, walls block the capsule, open doorways are clear, closed ones blocked.

const PROBE := preload("res://scripts/shape_room_probe.gd")
const BUILDER := preload("res://scripts/shape_room_builder.gd")
const RASTER_STEP := 0.5
const WALL_INSET := 0.08
const APPROACH_DEPTH := 0.5
const DOOR_MARGIN := 0.4
const VERTEX_MARGIN := 1.0


static func check_all(space: PhysicsDirectSpaceState3D, assembly: Node3D) -> Dictionary:
	var failures: Array[String] = []
	var rooms: Array[Dictionary] = []
	var ids: Array = assembly.specs.keys()
	ids.sort()
	for cell_id in ids:
		var result := check_room(space, assembly, assembly.specs[cell_id])
		rooms.append(result)
		failures.append_array(result.failures)
	return {"rooms": rooms, "failures": failures}


static func check_room(space: PhysicsDirectSpaceState3D, assembly: Node3D, spec: Dictionary) -> Dictionary:
	var ring: Array[Vector2] = BUILDER.ring_of(spec)
	var result := {"cell_id": String(spec.cell_id), "failures": [] as Array[String]}
	result.merge(_floor_counts(space, spec, ring))
	result.merge(_wall_counts(space, spec, ring))
	result.merge(_doorway_counts(space, spec, _expected_kinds(assembly, spec)))
	_collect_failures(result)
	return result


static func _expected_kinds(assembly: Node3D, spec: Dictionary) -> Dictionary:
	var kinds := {}
	for doorway: Dictionary in spec.doorways:
		var open: bool = String(doorway.kind) == "open" and assembly.specs.has(String(doorway.to_cell_id))
		kinds[String(doorway.port_id)] = "open" if open else "closed_visible"
	return kinds


static func _floor_counts(space: PhysicsDirectSpaceState3D, spec: Dictionary, ring: Array[Vector2]) -> Dictionary:
	var low := Vector2(float(spec.envelope_xz[0][0]), float(spec.envelope_xz[0][1]))
	var high := Vector2(float(spec.envelope_xz[2][0]), float(spec.envelope_xz[2][1]))
	var counts := {"floor_inside": 0, "floor_inside_supported": 0, "floor_outside": 0, "floor_outside_supported": 0}
	var x := low.x + RASTER_STEP / 2.0
	while x < high.x:
		var z := low.y + RASTER_STEP / 2.0
		while z < high.y:
			var supported := PROBE.floor_supported(space, x, z)
			var key := "floor_inside" if PROBE.inside_polygon(Vector2(x, z), ring) else "floor_outside"
			counts[key] += 1
			counts[key + "_supported"] += 1 if supported else 0
			z += RASTER_STEP
		x += RASTER_STEP
	return counts


static func _wall_counts(space: PhysicsDirectSpaceState3D, spec: Dictionary, ring: Array[Vector2]) -> Dictionary:
	var counts := {"wall_samples": 0, "wall_blocked": 0, "approach_samples": 0, "approach_clear": 0}
	for index in ring.size():
		var start := ring[index]
		var finish := ring[(index + 1) % ring.size()]
		var direction := (finish - start).normalized()
		var inward := Vector2(-direction.y, direction.x)
		var length := start.distance_to(finish)
		var distance := RASTER_STEP / 2.0
		while distance < length:
			if not _near_doorway(start, direction, distance, spec):
				_sample_wall(space, counts, start + direction * distance, inward, distance, length)
			distance += RASTER_STEP
	return counts


static func _sample_wall(space: PhysicsDirectSpaceState3D, counts: Dictionary, point: Vector2,
		inward: Vector2, distance: float, length: float) -> void:
	var wall_point := point + inward * WALL_INSET
	counts.wall_samples += 1
	counts.wall_blocked += 0 if PROBE.blockers(space, wall_point.x, wall_point.y).is_empty() else 1
	if distance < VERTEX_MARGIN or distance > length - VERTEX_MARGIN:
		return
	var approach := point + inward * APPROACH_DEPTH
	counts.approach_samples += 1
	counts.approach_clear += 1 if PROBE.clear_and_supported(space, approach.x, approach.y) else 0


static func _near_doorway(start: Vector2, direction: Vector2, distance: float, spec: Dictionary) -> bool:
	var point := start + direction * distance
	for doorway: Dictionary in spec.doorways:
		var centre := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		if absf((point - centre).dot(direction)) < 1.0 + DOOR_MARGIN and absf((point - centre).dot(Vector2(-direction.y, direction.x))) < 0.5:
			return true
	return false


static func _doorway_counts(space: PhysicsDirectSpaceState3D, spec: Dictionary, kinds: Dictionary) -> Dictionary:
	var counts := {"open_doorways": 0, "open_clear": 0, "closed_doorways": 0, "closed_blocked": 0}
	for doorway: Dictionary in spec.doorways:
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		var centre := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		if kinds[String(doorway.port_id)] == "open":
			var through := PROBE.sweep(space, centre - normal * APPROACH_DEPTH, centre + normal * APPROACH_DEPTH)
			counts.open_doorways += 1
			counts.open_clear += 1 if through.passable else 0
		else:
			counts.closed_doorways += 1
			counts.closed_blocked += 0 if PROBE.blockers(space, centre.x, centre.y).is_empty() else 1
	return counts


static func _collect_failures(result: Dictionary) -> void:
	var failures: Array[String] = result.failures
	var cell := String(result.cell_id)
	if result.floor_inside_supported != result.floor_inside:
		failures.append("%s: floor missing at %d of %d polygon samples" % [cell, result.floor_inside - result.floor_inside_supported, result.floor_inside])
	if result.floor_outside_supported != 0:
		failures.append("%s: floor present at %d samples outside the polygon" % [cell, result.floor_outside_supported])
	if result.wall_blocked != result.wall_samples:
		failures.append("%s: capsule passes %d wall samples" % [cell, result.wall_samples - result.wall_blocked])
	if result.approach_clear != result.approach_samples:
		failures.append("%s: %d wall approach samples are not clear and supported" % [cell, result.approach_samples - result.approach_clear])
	if result.open_clear != result.open_doorways:
		failures.append("%s: an open doorway is not clear" % cell)
	if result.closed_blocked != result.closed_doorways:
		failures.append("%s: a closed doorway does not block the capsule" % cell)
