class_name Issue201ElevationChecks
extends RefCounted

## Physics and graph checks for gmap-0.10.0 elevation (#201): level and ramp
## edges both ways, drops only from upper to lower, riser coverage, and
## coplanarity of the new sill, ledge, ramp and riser boxes.

const PROBE := preload("res://scripts/shape_room_probe.gd")
const TRIM := preload("res://scripts/issue186_trim_checks.gd")
const CAPSULE_RADIUS := 0.3
const CAPSULE_HEIGHT := 1.2
const CAPSULE_CENTER := 0.6
const STEP_M := 0.2
const EPS := 0.001


static func cell_index(map_data: Dictionary) -> Dictionary:
	var result := {}
	for cell: Dictionary in map_data.cells:
		result[String(cell.cell_id)] = cell
	return result


static func floor_of(cell: Dictionary) -> float:
	return float(cell.get("floor_y", 0.0))


static func edge_cells(edge: Dictionary) -> Array[String]:
	return [String(edge.from).get_slice(":", 0), String(edge.to).get_slice(":", 0)]


static func port_end(assembly: Node3D, port_id: String) -> Dictionary:
	var cell_id := port_id.get_slice(":", 0)
	for cell: Dictionary in assembly.map.cells:
		if String(cell.cell_id) != cell_id:
			continue
		for port: Dictionary in cell.required_ports:
			if String(port.port_id) == port_id:
				return {"pos": Vector2(float(port.pos_xz[0]), float(port.pos_xz[1])),
					"normal": Vector2(float(port.normal[0]), float(port.normal[1])),
					"cell_id": cell_id}
	return {}


static func check_graph(assembly: Node3D) -> Dictionary:
	return _flood_report(assembly, assembly.origin_cell, "directed flood from spawn")


static func check_strong(assembly: Node3D) -> Dictionary:
	var failures: Array[String] = []
	var cells := cell_index(assembly.map)
	for cell_id: String in cells:
		if String(cells[cell_id].role) == "void" or not assembly.has_room(cell_id):
			continue
		var reached := _reachable(assembly, cell_id)
		for other: String in cells:
			if String(cells[other].role) == "void" or not assembly.has_room(other):
				continue
			if not reached.has(other):
				failures.append("%s cannot reach %s" % [cell_id, other])
				break
	return {"failures": failures}


static func _flood_report(assembly: Node3D, start: String, label: String) -> Dictionary:
	var reached := _reachable(assembly, start)
	var expected := {}
	for cell: Dictionary in assembly.map.cells:
		if String(cell.role) != "void" and assembly.has_room(String(cell.cell_id)):
			expected[String(cell.cell_id)] = true
	var failures: Array[String] = []
	for cell_id: String in expected:
		if not reached.has(cell_id):
			failures.append("%s never reaches %s" % [label, cell_id])
	return {"expected_cells": expected.size(), "reached_cells": reached.size(), "failures": failures}


static func _reachable(assembly: Node3D, start: String) -> Dictionary:
	var cells := cell_index(assembly.map)
	var reached := {start: true}
	var pending: Array[String] = [start]
	while not pending.is_empty():
		var current: String = pending.pop_back()
		for edge: Dictionary in assembly.map.edges:
			if String(edge.connector) != "direct":
				continue
			var ends := edge_cells(edge)
			var other := ""
			if ends[0] == current:
				other = ends[1]
			elif ends[1] == current:
				other = ends[0]
			if other.is_empty() or not cells.has(other) or reached.has(other):
				continue
			if String(edge.get("vertical", "level")) == "drop":
				var drop: Dictionary = edge.get("drop", {})
				if String(drop.get("upper_cell_id", "")) != current:
					continue
			reached[other] = true
			pending.append(other)
	return reached


static func check_edges(space: PhysicsDirectSpaceState3D, assembly: Node3D) -> Dictionary:
	var result := {"level_edges": 0, "level_passed": 0, "ramp_edges": 0, "ramp_passed": 0,
		"drop_edges": 0, "failures": [] as Array[String]}
	for edge: Dictionary in assembly.map.edges:
		if String(edge.connector) != "direct":
			continue
		var vertical := String(edge.get("vertical", "level"))
		if vertical == "drop":
			result.drop_edges += 1
			continue
		var forward := _traverse(space, assembly, edge, false)
		var reverse := _traverse(space, assembly, edge, true)
		if vertical == "ramp":
			result.ramp_edges += 1
			if forward.passable and reverse.passable:
				result.ramp_passed += 1
			else:
				result.failures.append("%s -> %s ramp forward=%s reverse=%s" % [
					edge.from, edge.to, _reason(forward), _reason(reverse)])
		else:
			result.level_edges += 1
			if forward.passable and reverse.passable:
				result.level_passed += 1
			else:
				result.failures.append("%s -> %s level forward=%s reverse=%s" % [
					edge.from, edge.to, _reason(forward), _reason(reverse)])
	return result


static func _reason(result: Dictionary) -> String:
	return "pass" if result.passable else String(result.reason)


static func _traverse(space: PhysicsDirectSpaceState3D, assembly: Node3D, edge: Dictionary, reverse: bool) -> Dictionary:
	var ends: Array = [port_end(assembly, String(edge.from)), port_end(assembly, String(edge.to))]
	if reverse:
		ends.reverse()
	if ends[0].is_empty() or ends[1].is_empty():
		return {"passable": false, "reason": "missing port record"}
	var cells := cell_index(assembly.map)
	var from_cell := String(ends[0].cell_id)
	var to_cell := String(ends[1].cell_id)
	var from_floor := floor_of(cells[from_cell])
	var to_floor := floor_of(cells[to_cell])
	if String(edge.get("vertical", "level")) == "ramp":
		return _traverse_ramp(space, edge, ends, from_floor, to_floor, cells)
	var start: Vector2 = ends[0].pos - ends[0].normal * 0.9
	var finish: Vector2 = ends[1].pos - ends[1].normal * 0.9
	return _sweep_lanes(space, start, finish, from_floor, to_floor, 2.0)


static func _traverse_ramp(space: PhysicsDirectSpaceState3D, edge: Dictionary, ends: Array,
		from_floor: float, to_floor: float, cells: Dictionary) -> Dictionary:
	var ramp: Dictionary = edge.get("ramp", {})
	var lower_id := String(ramp.get("lower_cell_id", ""))
	var upper_id := String(ramp.get("upper_cell_id", ""))
	if not cells.has(lower_id) or not cells.has(upper_id):
		return {"passable": false, "reason": "ramp cells missing"}
	var upper_floor := floor_of(cells[upper_id])
	var lower_floor := floor_of(cells[lower_id])
	var lower_end: Dictionary = ends[0] if String(ends[0].cell_id) == lower_id else ends[1]
	var upper_end: Dictionary = ends[1] if String(ends[1].cell_id) == upper_id else ends[0]
	var direction: Vector2 = -lower_end.normal
	var run := float(ramp.get("run_m", 3.25))
	var rise := upper_floor - lower_floor
	var width := float(ramp.get("width_m", 2.2))
	var start: Vector2 = lower_end.pos + direction * 0.16
	var finish: Vector2 = start + direction * run
	var lanes: Array[float] = [0.0]
	if width > 1.4:
		lanes = [-width / 2.0 + 0.55, 0.0, width / 2.0 - 0.55]
	var upper_inside: Vector2 = upper_end.pos - upper_end.normal * 0.9
	for lane: float in lanes:
		var lateral := Vector2(-direction.y, direction.x) * lane
		var points: Array[Dictionary] = []
		points.append({"pos": upper_inside + lateral, "floor": upper_floor})
		var steps := int(ceil(run / STEP_M))
		for step in steps + 1:
			var distance := run * float(step) / float(steps)
			points.append({"pos": start + direction * distance + lateral,
				"floor": upper_floor - rise * float(step) / float(steps)})
		points.append({"pos": start + direction * (run + 0.8) + lateral, "floor": lower_floor})
		for point: Dictionary in points:
			var y := float(point.floor) + CAPSULE_CENTER
			var hits := _blockers_at(space, point.pos.x, point.pos.y, y)
			if not hits.is_empty():
				return {"passable": false, "reason": "ramp blocked by %s at %s" % [hits[0], point.pos]}
			if not _supported(space, point.pos, y):
				return {"passable": false, "reason": "ramp has no support at %s" % point.pos}
	return {"passable": true}


static func _sweep_lanes(space: PhysicsDirectSpaceState3D, start: Vector2, finish: Vector2,
		from_floor: float, to_floor: float, width: float) -> Dictionary:
	var direction := (finish - start).normalized()
	var lateral := Vector2(-direction.y, direction.x)
	var lanes: Array[float] = [0.0]
	if width > 1.4:
		lanes = [-width / 2.0 + 0.55, 0.0, width / 2.0 - 0.55]
	for lane: float in lanes:
		var steps := int(ceil(start.distance_to(finish) / STEP_M))
		for step in steps + 1:
			var point := start.lerp(finish, float(step) / float(steps)) + lateral * lane
			var t := float(step) / float(steps)
			var y := lerpf(from_floor, to_floor, t) + CAPSULE_CENTER
			var hits := _blockers_at(space, point.x, point.y, y)
			if not hits.is_empty():
				return {"passable": false, "reason": "blocked by %s at %s" % [hits[0], point]}
			if not _supported(space, point, y):
				return {"passable": false, "reason": "no support"}
	return {"passable": true}


static func _blockers_at(space: PhysicsDirectSpaceState3D, x: float, z: float, center_y: float) -> Array[String]:
	var shape := CapsuleShape3D.new()
	shape.radius = CAPSULE_RADIUS
	shape.height = CAPSULE_HEIGHT
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, Vector3(x, center_y + 0.05, z))
	query.collision_mask = 1
	var names: Array[String] = []
	for result in space.intersect_shape(query, 32):
		var collider := result.get("collider") as Node
		if collider != null and not PROBE.is_floor_body(collider):
			names.append(collider.name)
	return names


static func _supported(space: PhysicsDirectSpaceState3D, point: Vector2, center_y: float) -> bool:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(point.x, center_y + 0.45, point.y), Vector3(point.x, center_y - 0.7, point.y))
	query.collision_mask = 1
	return not space.intersect_ray(query).is_empty()


static func drop_edges(assembly: Node3D) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for edge: Dictionary in assembly.map.edges:
		if String(edge.connector) == "direct" and String(edge.get("vertical", "")) == "drop":
			result.append(edge)
	return result


static func riser_expectations(assembly: Node3D) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var cells: Array[Dictionary] = []
	for cell: Dictionary in assembly.map.cells:
		if String(cell.role) != "void" and assembly.has_room(String(cell.cell_id)):
			cells.append(cell)
	for left_index in cells.size():
		for right_index in range(left_index + 1, cells.size()):
			var left: Dictionary = cells[left_index]
			var right: Dictionary = cells[right_index]
			var shared := shared_boundary(left, right)
			if shared.is_empty():
				continue
			var left_floor := floor_of(left)
			var right_floor := floor_of(right)
			if absf(left_floor - right_floor) <= EPS:
				continue
			var upper: Dictionary = left if left_floor > right_floor else right
			var lower: Dictionary = right if upper == left else left
			result.append({"upper": String(upper.cell_id), "lower": String(lower.cell_id),
				"bottom": minf(left_floor, right_floor), "top": maxf(left_floor, right_floor),
				"shared": shared})
	return result


static func shared_boundary(left: Dictionary, right: Dictionary) -> Dictionary:
	var left_rect := envelope_rect(left)
	var right_rect := envelope_rect(right)
	if absf(left_rect.end.x - right_rect.position.x) <= EPS:
		return {"axis": "x", "boundary": left_rect.end.x,
			"low": maxf(left_rect.position.y, right_rect.position.y),
			"high": minf(left_rect.end.y, right_rect.end.y), "left_is_low": true} if minf(left_rect.end.y, right_rect.end.y) - maxf(left_rect.position.y, right_rect.position.y) > 0.0001 else {}
	if absf(left_rect.position.x - right_rect.end.x) <= EPS:
		return {"axis": "x", "boundary": left_rect.position.x,
			"low": maxf(left_rect.position.y, right_rect.position.y),
			"high": minf(left_rect.end.y, right_rect.end.y), "left_is_low": false} if minf(left_rect.end.y, right_rect.end.y) - maxf(left_rect.position.y, right_rect.position.y) > 0.0001 else {}
	if absf(left_rect.end.y - right_rect.position.y) <= EPS:
		return {"axis": "z", "boundary": left_rect.end.y,
			"low": maxf(left_rect.position.x, right_rect.position.x),
			"high": minf(left_rect.end.x, right_rect.end.x), "left_is_low": true} if minf(left_rect.end.x, right_rect.end.x) - maxf(left_rect.position.x, right_rect.position.x) > 0.0001 else {}
	if absf(left_rect.position.y - right_rect.end.y) <= EPS:
		return {"axis": "z", "boundary": left_rect.position.y,
			"low": maxf(left_rect.position.x, right_rect.position.x),
			"high": minf(left_rect.end.x, right_rect.end.x), "left_is_low": false} if minf(left_rect.end.x, right_rect.end.x) - maxf(left_rect.position.x, right_rect.position.x) > 0.0001 else {}
	return {}


static func envelope_rect(cell: Dictionary) -> Rect2:
	var points: Array = cell.envelope_xz
	var minimum := Vector2(float(points[0][0]), float(points[0][1]))
	var maximum := minimum
	for point: Array in points:
		minimum.x = minf(minimum.x, float(point[0]))
		minimum.y = minf(minimum.y, float(point[1]))
		maximum.x = maxf(maximum.x, float(point[0]))
		maximum.y = maxf(maximum.y, float(point[1]))
	return Rect2(minimum, maximum - minimum)


static func check_risers(assembly: Node3D) -> Dictionary:
	var result := {"expected": 0, "present": 0, "covered_samples": 0, "samples": 0,
		"failures": [] as Array[String]}
	var host := assembly.get_node_or_null("Risers")
	for expectation: Dictionary in riser_expectations(assembly):
		result.expected += 1
		var name := "WallRiser_%s_%s" % [expectation.upper, expectation.lower]
		var body := host.get_node_or_null(name) as StaticBody3D if host != null else null
		if body == null or body.get_child_count() == 0:
			result.failures.append("missing riser %s" % name)
			continue
		result.present += 1
		var samples := _riser_samples(expectation)
		result.samples += samples.size()
		for sample: Dictionary in samples:
			result.covered_samples += 1 if _riser_ray_blocked(assembly, sample) else 0
	if result.covered_samples != result.samples:
		result.failures.append("%d of %d riser samples are open" % [result.samples - result.covered_samples, result.samples])
	return result


static func _riser_samples(expectation: Dictionary) -> Array[Dictionary]:
	var shared: Dictionary = expectation.shared
	var samples: Array[Dictionary] = []
	var low := float(shared.low)
	var high := float(shared.high)
	var y := (float(expectation.bottom) + float(expectation.top)) / 2.0
	var distance := 0.15
	while distance < high - low:
		samples.append({"axis": String(shared.axis), "boundary": float(shared.boundary),
			"along": low + distance, "y": y})
		distance += 0.3
	return samples


static func _riser_ray_blocked(assembly: Node3D, sample: Dictionary) -> bool:
	var space := assembly.get_world_3d().direct_space_state
	var half := 0.35
	var from := Vector3.ZERO
	var to := Vector3.ZERO
	if String(sample.axis) == "x":
		from = Vector3(float(sample.boundary) + half, float(sample.y), float(sample.along))
		to = Vector3(float(sample.boundary) - half, float(sample.y), float(sample.along))
	else:
		from = Vector3(float(sample.along), float(sample.y), float(sample.boundary) + half)
		to = Vector3(float(sample.along), float(sample.y), float(sample.boundary) - half)
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collision_mask = 1
	var hit := space.intersect_ray(query)
	return not hit.is_empty()


static func check_coplanar(assembly: Node3D) -> Dictionary:
	var all_boxes := _collect_boxes(assembly)
	var elevated: Array[Dictionary] = []
	for box: Dictionary in all_boxes:
		var label := String(box.name)
		if label.contains("/WallSill_") or label.contains("/TrimLedge_") or label.contains("/RampStep_") or label.begins_with("WallRiser_"):
			elevated.append(box)
	var same_facing: Array[Dictionary] = []
	for box: Dictionary in elevated:
		var others: Array[Dictionary] = []
		for other: Dictionary in all_boxes:
			if String(other.name) != String(box.name):
				others.append(other)
		var conflicts := TRIM.conflicts([box], others)
		same_facing.append_array(conflicts.same_facing)
	return {"elevation_boxes": elevated.size(), "same_facing_count": same_facing.size(),
		"conflicts": same_facing, "failures": [] as Array[String]}


static func _collect_boxes(assembly: Node3D) -> Array[Dictionary]:
	var boxes: Array[Dictionary] = []
	for cell_id: String in assembly.rooms:
		var room: Node3D = assembly.rooms[cell_id]
		for node in room.find_children("*", "MeshInstance3D", true, false):
			var mesh := (node as MeshInstance3D).mesh
			if not mesh is BoxMesh:
				continue
			var turned := absf(sin(2.0 * node.global_rotation.y)) > 0.001
			boxes.append({"name": "%s/%s" % [cell_id, node.name], "center": node.global_position,
				"size": TRIM._world_extent(node.global_transform.basis, (mesh as BoxMesh).size) if turned else (mesh as BoxMesh).size,
				"rotated": turned, "degenerate": false})
	var host := assembly.get_node_or_null("Risers")
	if host != null:
		for node in host.find_children("*", "MeshInstance3D", true, false):
			var mesh := (node as MeshInstance3D).mesh
			if mesh is BoxMesh:
				boxes.append({"name": String(node.name), "center": node.global_position,
					"size": (mesh as BoxMesh).size, "rotated": false, "degenerate": false})
	return boxes
