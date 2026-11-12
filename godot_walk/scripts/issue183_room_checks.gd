class_name Issue183RoomChecks
extends RefCounted

## Per-room physics checks for generated shape rooms: floor support inside the polygon
## and none outside, walls block the capsule, open doorways are clear, closed ones blocked.

const PROBE := preload("res://scripts/shape_room_probe.gd")
const BUILDER := preload("res://scripts/shape_room_builder.gd")
const DOORWAYS := preload("res://scripts/doorway_sizes.gd")
const RASTER_STEP := 0.5
const WALL_INSET := 0.08
const APPROACH_DEPTH := 0.5
const DOOR_MARGIN := 0.4
const VERTEX_MARGIN := 1.0
## A sample this close to the outline lies on a wall line: a 45-degree edge runs through raster
## sample centres (#190), where "inside" and "supported" are both ambiguous, so it is not judged.
const BOUNDARY_SKIP := 0.05
## A wall approach sample nearer than this to another wall (the thin end of a wedge) is not judged.
const OTHER_WALL_SKIP := 0.51


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
	var floor_y := PROBE.cell_floor_y(assembly.map, String(spec.cell_id))
	var result := {"cell_id": String(spec.cell_id), "failures": [] as Array[String]}
	result.merge(_floor_counts(space, spec, ring, assembly, floor_y))
	result.merge(_wall_counts(space, assembly, spec, ring, floor_y))
	result.merge(_doorway_counts(space, assembly, spec, _expected_kinds(assembly, spec), floor_y))
	_collect_failures(result)
	return result


static func _expected_kinds(assembly: Node3D, spec: Dictionary) -> Dictionary:
	var kinds := {}
	for doorway: Dictionary in spec.doorways:
		var open: bool = String(doorway.kind) == "open" and assembly.has_room(String(doorway.to_cell_id))
		kinds[String(doorway.port_id)] = "open" if open else "closed_visible"
	return kinds


static func _floor_counts(space: PhysicsDirectSpaceState3D, spec: Dictionary, ring: Array[Vector2], assembly: Node3D, floor_y: float) -> Dictionary:
	var low := Vector2(float(spec.envelope_xz[0][0]), float(spec.envelope_xz[0][1]))
	var high := Vector2(float(spec.envelope_xz[2][0]), float(spec.envelope_xz[2][1]))
	var counts := {"floor_inside": 0, "floor_inside_supported": 0, "floor_outside": 0, "floor_outside_supported": 0,
		"floor_outside_connector_supported": 0}
	var x := low.x + RASTER_STEP / 2.0
	while x < high.x:
		var z := low.y + RASTER_STEP / 2.0
		while z < high.y:
			if _boundary_distance(Vector2(x, z), ring) < BOUNDARY_SKIP:
				z += RASTER_STEP
				continue
			var supported := PROBE.floor_supported(space, x, z, floor_y)
			var key := "floor_inside" if PROBE.inside_polygon(Vector2(x, z), ring) else "floor_outside"
			counts[key] += 1
			counts[key + "_supported"] += 1 if supported else 0
			if key == "floor_outside" and supported and _inside_connected_diagonal_neighbor(Vector2(x, z), String(spec.cell_id), assembly):
				counts.floor_outside_connector_supported += 1
			z += RASTER_STEP
		x += RASTER_STEP
	return counts


static func _inside_connected_diagonal_neighbor(point: Vector2, cell_id: String, assembly: Node3D) -> bool:
	for edge: Dictionary in assembly.map.edges:
		if String(edge.get("kind", "")) != "diagonal":
			continue
		var from_cell := String(edge.from).get_slice(":", 0)
		var to_cell := String(edge.to).get_slice(":", 0)
		var other := to_cell if from_cell == cell_id else from_cell if to_cell == cell_id else ""
		if other == "" or not assembly.specs.has(other):
			continue
		if PROBE.inside_polygon(point, BUILDER.ring_of(assembly.specs[other])):
			return true
	return false


static func _boundary_distance(point: Vector2, ring: Array[Vector2]) -> float:
	var nearest := INF
	for index in ring.size():
		var closest := Geometry2D.get_closest_point_to_segment(point, ring[index], ring[(index + 1) % ring.size()])
		nearest = minf(nearest, point.distance_to(closest))
	return nearest


static func _wall_counts(space: PhysicsDirectSpaceState3D, assembly: Node3D, spec: Dictionary,
		ring: Array[Vector2], floor_y: float) -> Dictionary:
	var counts := {"wall_samples": 0, "wall_blocked": 0, "approach_samples": 0, "approach_clear": 0}
	var chamfered: bool = spec.has("chamfers") or spec.has("diagonal_passage")
	var current: bool = ["shape-room-0.4.0", "shape-room-0.5.0", "shape-room-0.6.0", "shape-room-0.7.0", "shape-room-0.8.0", "shape-room-0.9.0", "shape-room-0.10.0"].has(String(spec.generator_version))
	for index in ring.size():
		var start := ring[index]
		var finish := ring[(index + 1) % ring.size()]
		var direction := (finish - start).normalized()
		var inward := Vector2(-direction.y, direction.x)
		var length := start.distance_to(finish)
		var module_edge := _edge_has_module_joint(assembly, spec, start, direction, inward, length, current)
		var distance := RASTER_STEP / 2.0
		while distance < length:
			if not _near_doorway(start, direction, distance, spec):
				var crowded: bool = chamfered and _near_other_edge(start + direction * distance + inward * APPROACH_DEPTH, ring, index)
				_sample_wall(space, counts, start + direction * distance, inward, distance, length, floor_y, module_edge or crowded)
			distance += RASTER_STEP
	return counts


## A library module's wall stands just outside its footprint, so it overhangs this room's
## wall at a module joint (a few centimetres to 0.3 m inside): the 0.5 m approach probe
## would touch it. Wall blocking is still checked there; only the approach probe is skipped.
static func _edge_has_module_joint(assembly: Node3D, spec: Dictionary, start: Vector2, direction: Vector2,
		inward: Vector2, length: float, any_along: bool = false) -> bool:
	for doorway: Dictionary in spec.doorways:
		if not assembly.module_rooms.has(String(doorway.to_cell_id)):
			continue
		var offset := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1])) - start
		var along := offset.dot(direction)
		# shape-room-0.4.0 (#190): any wall on the joint's line may sit under the library wall's overhang
		var in_line: bool = any_along and absf(direction.dot(Vector2(float(doorway.normal[0]), float(doorway.normal[1])))) < 0.001
		if absf(offset.dot(inward)) < 0.001 and ((along > -0.001 and along < length + 0.001) or in_line):
			return true
	return false


static func _sample_wall(space: PhysicsDirectSpaceState3D, counts: Dictionary, point: Vector2,
		inward: Vector2, distance: float, length: float, floor_y: float, module_edge: bool = false) -> void:
	var wall_point := point + inward * WALL_INSET
	counts.wall_samples += 1
	counts.wall_blocked += 0 if PROBE.blockers(space, wall_point.x, wall_point.y, floor_y).is_empty() else 1
	if module_edge or distance < VERTEX_MARGIN or distance > length - VERTEX_MARGIN:
		return
	var approach := point + inward * APPROACH_DEPTH
	counts.approach_samples += 1
	counts.approach_clear += 1 if PROBE.clear_and_supported(space, approach.x, approach.y, floor_y) else 0


static func _near_other_edge(point: Vector2, ring: Array[Vector2], own: int) -> bool:
	for index in ring.size():
		if index == own:
			continue
		var closest := Geometry2D.get_closest_point_to_segment(point, ring[index], ring[(index + 1) % ring.size()])
		if point.distance_to(closest) < OTHER_WALL_SKIP:
			return true
	return false


static func _near_doorway(start: Vector2, direction: Vector2, distance: float, spec: Dictionary) -> bool:
	var point := start + direction * distance
	for doorway: Dictionary in spec.doorways:
		var centre := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		var half := DOORWAYS.size_of(doorway).x / 2.0
		if absf((point - centre).dot(direction)) < half + DOOR_MARGIN and absf((point - centre).dot(Vector2(-direction.y, direction.x))) < 0.5:
			return true
	return false


static func _doorway_counts(space: PhysicsDirectSpaceState3D, assembly: Node3D, spec: Dictionary, kinds: Dictionary, floor_y: float) -> Dictionary:
	var counts := {"open_doorways": 0, "open_clear": 0, "open_failures": [] as Array[String], "closed_doorways": 0, "closed_blocked": 0}
	for doorway: Dictionary in spec.doorways:
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		var centre := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		var drop := _drop_for_port(assembly.map, String(doorway.port_id))
		if not drop.is_empty() and String(spec.cell_id) == String(drop.lower_cell_id):
			counts.closed_doorways += 1
			counts.closed_blocked += 0 if PROBE.blockers(space, centre.x, centre.y, floor_y).is_empty() else 1
			continue
		if kinds[String(doorway.port_id)] == "open":
			var destination_y := PROBE.cell_floor_y(assembly.map, String(doorway.to_cell_id))
			var start := centre - normal * APPROACH_DEPTH
			var finish := centre + normal * APPROACH_DEPTH
			var ramp := _ramp_for_port(assembly.map, String(doorway.port_id))
			var through := PROBE.sweep(space, start, finish, floor_y, destination_y)
			if not drop.is_empty():
				through = PROBE.sweep_drop(space, start, finish, floor_y, destination_y)
			elif not ramp.is_empty():
				var lower := _port_record(assembly.map, String(ramp.lower_port_id))
				through = PROBE.sweep_ramp(space, start, finish, lower.pos, -lower.normal,
					float(lower.floor_y), float(ramp.upper_floor_y), float(ramp.run_m), float(ramp.rise_m))
			counts.open_doorways += 1
			counts.open_clear += 1 if through.passable else 0
			if not through.passable:
				counts.open_failures.append("%s: %s at %s" % [doorway.port_id, through.reason, through.at])
		else:
			counts.closed_doorways += 1
			counts.closed_blocked += 0 if PROBE.blockers(space, centre.x, centre.y, floor_y).is_empty() else 1
	return counts


static func _ramp_for_port(map_data: Dictionary, port_id: String) -> Dictionary:
	for edge: Dictionary in map_data.edges:
		if port_id not in [String(edge.from), String(edge.to)] or not edge.has("ramp"):
			continue
		var lower_id := String(edge.ramp.lower_cell_id)
		var lower_port := String(edge.from) if String(edge.from).get_slice(":", 0) == lower_id else String(edge.to)
		return {"lower_port_id": lower_port, "upper_floor_y": PROBE.cell_floor_y(map_data, String(edge.ramp.upper_cell_id)),
			"run_m": float(edge.ramp.run_m), "rise_m": float(edge.ramp.rise_m)}
	return {}


static func _drop_for_port(map_data: Dictionary, port_id: String) -> Dictionary:
	for edge: Dictionary in map_data.edges:
		if port_id in [String(edge.from), String(edge.to)] and edge.has("drop"):
			return edge.drop
	return {}


static func _port_record(map_data: Dictionary, port_id: String) -> Dictionary:
	var cell_id := port_id.get_slice(":", 0)
	for cell: Dictionary in map_data.cells:
		if String(cell.cell_id) != cell_id:
			continue
		for port: Dictionary in cell.required_ports:
			if String(port.port_id) == port_id:
				return {"pos": Vector2(float(port.pos_xz[0]), float(port.pos_xz[1])),
					"normal": Vector2(float(port.normal[0]), float(port.normal[1])),
					"floor_y": float(cell.get("floor_y", 0.0))}
	return {}


static func _collect_failures(result: Dictionary) -> void:
	var failures: Array[String] = result.failures
	var cell := String(result.cell_id)
	if result.floor_inside_supported != result.floor_inside:
		failures.append("%s: floor missing at %d of %d polygon samples" % [cell, result.floor_inside - result.floor_inside_supported, result.floor_inside])
	var illegal_outside: int = result.floor_outside_supported - result.floor_outside_connector_supported
	if illegal_outside != 0:
		failures.append("%s: floor present at %d samples outside the polygon and unconnected" % [cell, illegal_outside])
	if result.wall_blocked != result.wall_samples:
		failures.append("%s: capsule passes %d wall samples" % [cell, result.wall_samples - result.wall_blocked])
	if result.approach_clear != result.approach_samples:
		failures.append("%s: %d wall approach samples are not clear and supported" % [cell, result.approach_samples - result.approach_clear])
	if result.open_clear != result.open_doorways:
		failures.append_array(result.open_failures)
	if result.closed_blocked != result.closed_doorways:
		failures.append("%s: a closed doorway does not block the capsule" % cell)
