class_name Issue183MapChecks
extends RefCounted

## Assembled-map physics checks: every direct edge passable both ways, every closed edge
## blocked, and a capsule/floor flood fill from the spawn that reaches every walkable
## cell and no void cell.

const PROBE := preload("res://scripts/shape_room_probe.gd")
const INSIDE_M := 1.0
const OUTSIDE_PROBE_M := 0.5
const FLOOD_STEP := 0.5


static func check_edges(space: PhysicsDirectSpaceState3D, assembly: Node3D) -> Dictionary:
	var result := {"direct_edges": 0, "direct_edges_checked": 0, "passed_forward": 0, "passed_reverse": 0,
		"closed_edges": 0, "closed_blocked": 0, "failures": [] as Array[String]}
	for edge: Dictionary in assembly.map.edges:
		var from_end := _end(assembly, String(edge.from))
		var to_end := _end(assembly, String(edge.to))
		var both_rooms: bool = assembly.has_room(String(edge.from).get_slice(":", 0)) and assembly.has_room(String(edge.to).get_slice(":", 0))
		if String(edge.connector) == "direct":
			result.direct_edges += 1
		if String(edge.connector) == "direct" and both_rooms:
			_check_direct(space, result, edge, from_end, to_end)
		else:
			_check_closed(space, result, edge, [from_end, to_end])
	return result


static func _end(assembly: Node3D, port_id: String) -> Dictionary:
	var spec: Variant = assembly.specs.get(port_id.get_slice(":", 0))
	if spec == null:
		return _module_end(assembly, port_id)
	for doorway: Dictionary in spec.doorways:
		if String(doorway.port_id) == port_id:
			return {"cell_id": port_id.get_slice(":", 0),
				"pos": Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1])),
				"normal": Vector2(float(doorway.normal[0]), float(doorway.normal[1])),
				"floor_y": PROBE.cell_floor_y(assembly.map, port_id.get_slice(":", 0))}
	return {}


## A module cell has no shape-room spec; its end of the joint is the map's own port record.
static func _module_end(assembly: Node3D, port_id: String) -> Dictionary:
	if not assembly.module_rooms.has(port_id.get_slice(":", 0)):
		return {}
	for cell: Dictionary in assembly.map.cells:
		for port: Dictionary in cell.required_ports:
			if String(port.port_id) == port_id:
				return {"cell_id": port_id.get_slice(":", 0),
					"pos": Vector2(float(port.pos_xz[0]), float(port.pos_xz[1])),
					"normal": Vector2(float(port.normal[0]), float(port.normal[1])),
					"floor_y": PROBE.cell_floor_y(assembly.map, port_id.get_slice(":", 0))}
	return {}


static func _check_direct(space: PhysicsDirectSpaceState3D, result: Dictionary, edge: Dictionary,
		from_end: Dictionary, to_end: Dictionary) -> void:
	var label := "%s -> %s" % [edge.from, edge.to]
	result.direct_edges_checked += 1
	if from_end.is_empty() and to_end.is_empty():
		result.failures.append("%s: neither room has a doorway record" % label)
		return
	if not from_end.is_empty() and not to_end.is_empty() and (from_end.pos != to_end.pos or from_end.normal != -to_end.normal):
		result.failures.append("%s: doorway positions or normals do not mirror" % label)
		return
	if from_end.is_empty():
		from_end = {"cell_id": String(edge.from).get_slice(":", 0), "pos": to_end.pos,
			"normal": -to_end.normal, "floor_y": to_end.floor_y}
	var inside_from: Vector2 = from_end.pos - from_end.normal * INSIDE_M
	var inside_to: Vector2 = from_end.pos + from_end.normal * INSIDE_M
	if String(edge.get("vertical", "level")) == "drop":
		_check_drop(space, result, edge, from_end, to_end, inside_from, inside_to)
		return
	var forward := _edge_sweep(space, edge, from_end, to_end, inside_from, inside_to)
	var reverse := _edge_sweep(space, edge, to_end, from_end, inside_to, inside_from)
	result.passed_forward += 1 if forward.passable else 0
	result.passed_reverse += 1 if reverse.passable else 0
	if not forward.passable:
		result.failures.append("%s forward: %s at %s" % [label, forward.reason, forward.at])
	if not reverse.passable:
		result.failures.append("%s reverse: %s at %s" % [label, reverse.reason, reverse.at])


static func _edge_sweep(space: PhysicsDirectSpaceState3D, edge: Dictionary, from_end: Dictionary,
		to_end: Dictionary, start: Vector2, finish: Vector2) -> Dictionary:
	var ramp: Dictionary = edge.get("ramp", {})
	if ramp.is_empty():
		return PROBE.sweep(space, start, finish, float(from_end.floor_y), float(to_end.floor_y))
	var lower_id := String(ramp.lower_cell_id)
	var lower_end: Dictionary = from_end if String(from_end.cell_id) == lower_id else to_end
	var upper_end: Dictionary = to_end if String(from_end.cell_id) == lower_id else from_end
	return PROBE.sweep_ramp(space, start, finish, lower_end.pos, -lower_end.normal,
		float(lower_end.floor_y), float(upper_end.floor_y), float(ramp.run_m), float(ramp.rise_m))


static func _check_drop(space: PhysicsDirectSpaceState3D, result: Dictionary, edge: Dictionary,
		from_end: Dictionary, to_end: Dictionary, inside_from: Vector2, inside_to: Vector2) -> void:
	var upper_id := String(edge.drop.upper_cell_id)
	var starts_upper: bool = String(from_end.cell_id) == upper_id
	var upper_end: Dictionary = from_end if starts_upper else to_end
	var lower_end: Dictionary = to_end if starts_upper else from_end
	var start: Vector2 = inside_from if starts_upper else inside_to
	var finish: Vector2 = inside_to if starts_upper else inside_from
	var travel := PROBE.sweep_drop(space, start, finish, float(upper_end.floor_y), float(lower_end.floor_y))
	if travel.passable:
		result.passed_forward += 1
	else:
		result.failures.append("%s upper-to-lower: %s at %s" % [edge.from, travel.reason, travel.at])


static func _check_closed(space: PhysicsDirectSpaceState3D, result: Dictionary, edge: Dictionary, ends: Array) -> void:
	for end: Dictionary in ends:
		if end.is_empty():
			continue
		result.closed_edges += 1
		var through := PROBE.sweep(space, end.pos - end.normal * INSIDE_M, end.pos + end.normal * OUTSIDE_PROBE_M,
			float(end.get("floor_y", 0.0)), float(end.get("floor_y", 0.0)))
		result.closed_blocked += 0 if through.passable else 1
		if through.passable:
			result.failures.append("%s -> %s: closed edge is passable" % [edge.from, edge.to])


static func check_flood(space: PhysicsDirectSpaceState3D, assembly: Node3D) -> Dictionary:
	var owners := {}
	var clear := {}
	for cell: Dictionary in assembly.map.cells:
		_sample_cell(space, cell, clear, owners)
	var diagonal_pairs := {}
	if String(assembly.map.get("generator_version", "")) in ["gmap-0.6.0", "gmap-0.6.1", "gmap-0.7.0", "gmap-0.8.0", "gmap-0.9.0", "gmap-0.10.0", "gmap-0.11.0", "gmap-0.12.0", "gmap-0.13.0"]:
		for edge: Dictionary in assembly.map.edges:
			if String(edge.get("kind", "")) == "diagonal":
				var cells := [String(edge.from).get_slice(":", 0), String(edge.to).get_slice(":", 0)]
				cells.sort()
				diagonal_pairs["%s|%s" % [cells[0], cells[1]]] = true
	var reached := _flood(clear, _key_of(assembly.spawn_position.x, assembly.spawn_position.z), owners, diagonal_pairs)
	return _flood_report(assembly, clear, owners, reached)


static func _key_of(x: float, z: float) -> Vector2i:
	return Vector2i(floori(x / FLOOD_STEP), floori(z / FLOOD_STEP))


static func _sample_cell(space: PhysicsDirectSpaceState3D, cell: Dictionary, clear: Dictionary, owners: Dictionary) -> void:
	var low := Vector2(float(cell.envelope_xz[0][0]), float(cell.envelope_xz[0][1]))
	var high := Vector2(float(cell.envelope_xz[2][0]), float(cell.envelope_xz[2][1]))
	var x := low.x + FLOOD_STEP / 2.0
	while x < high.x:
		var z := low.y + FLOOD_STEP / 2.0
		while z < high.y:
			if PROBE.clear_and_supported(space, x, z, float(cell.get("floor_y", 0.0))):
				var key := _key_of(x, z)
				clear[key] = true
				owners[key] = String(cell.cell_id)
			z += FLOOD_STEP
		x += FLOOD_STEP


static func _flood(clear: Dictionary, start: Vector2i, owners: Dictionary, diagonal_pairs: Dictionary) -> Dictionary:
	var visited := {}
	var pending: Array[Vector2i] = []
	if clear.has(start):
		pending.append(start)
	while not pending.is_empty():
		var current: Vector2i = pending.pop_back()
		if visited.has(current):
			continue
		visited[current] = true
		for step: Vector2i in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN,
			Vector2i(-1, -1), Vector2i(-1, 1), Vector2i(1, -1), Vector2i(1, 1)]:
			var next := current + step
			if not clear.has(next) or visited.has(next):
				continue
			if abs(step.x) == 1 and abs(step.y) == 1:
				var pair := [String(owners[current]), String(owners[next])]
				pair.sort()
				if not diagonal_pairs.has("%s|%s" % [pair[0], pair[1]]):
					continue
			pending.append(next)
	return visited


static func _expected_cells(assembly: Node3D) -> Dictionary:
	var expected := {assembly.origin_cell: true}
	var pending: Array[String] = [assembly.origin_cell]
	while not pending.is_empty():
		var current: String = pending.pop_back()
		for edge: Dictionary in assembly.map.edges:
			var other := ""
			if String(edge.from).get_slice(":", 0) == current:
				other = String(edge.to).get_slice(":", 0)
			elif String(edge.to).get_slice(":", 0) == current:
				other = String(edge.from).get_slice(":", 0)
			if other != "" and String(edge.connector) == "direct" and assembly.has_room(other) and not expected.has(other):
				expected[other] = true
				pending.append(other)
	return expected


static func _flood_report(assembly: Node3D, clear: Dictionary, owners: Dictionary, reached: Dictionary) -> Dictionary:
	var reached_cells := {}
	for key: Vector2i in reached:
		reached_cells[owners[key]] = reached_cells.get(owners[key], 0) + 1
	var expected := _expected_cells(assembly)
	var failures: Array[String] = []
	var void_ids: Array[String] = []
	for cell: Dictionary in assembly.map.cells:
		if String(cell.role) == "void":
			void_ids.append(String(cell.cell_id))
	for cell_id in expected:
		if not reached_cells.has(cell_id):
			failures.append("flood fill never reaches walkable cell %s" % cell_id)
	for cell_id in reached_cells:
		if not expected.has(cell_id):
			failures.append("flood fill reaches %s, which is %s" % [cell_id, "a void cell" if void_ids.has(cell_id) else "not expected"])
	var unreached_in_expected := 0
	var enclosed_in_modules := 0
	for key: Vector2i in clear:
		if expected.has(owners[key]) and not reached.has(key):
			# A library room's own props can wall off a pocket (#188); only generated rooms must be fully connected.
			if assembly.module_rooms.has(owners[key]):
				enclosed_in_modules += 1
			else:
				unreached_in_expected += 1
	if unreached_in_expected > 0:
		failures.append("%d clear samples inside reachable cells were not reached" % unreached_in_expected)
	return {"clear_samples": clear.size(), "reached_samples": reached.size(), "expected_cells": expected.size(),
		"reached_cells": reached_cells.size(), "void_cells_reached": void_ids.filter(func(id: String) -> bool: return reached_cells.has(id)).size(),
		"unreached_clear_samples_in_expected_cells": unreached_in_expected,
		"enclosed_clear_samples_in_module_cells": enclosed_in_modules, "failures": failures}
