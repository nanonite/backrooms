class_name Issue193DiagonalLinkChecks
extends RefCounted

## Runtime checks for 0.6.0 authored diagonal links. Metadata validation is separate.

const MAP_CHECKS := preload("res://scripts/issue183_map_checks.gd")
const PROBE := preload("res://scripts/shape_room_probe.gd")
const LATERAL_OFFSETS := [-0.65, 0.0, 0.65]
const INSIDE_M := 1.0
const ALIGN_TOLERANCE := 0.01
const HEADER_DEPTH := 0.16
const TRIM_DEPTH := 0.2


static func check(assembly: Node3D) -> Dictionary:
	var result := {"links": 0, "diagonal_edges": 0, "lane_sweeps": 0, "lane_sweeps_passed": 0,
		"passage_wall_colliders": 0, "frames_checked": 0, "failures": [] as Array[String]}
	if not (String(assembly.map.get("generator_version", "")) in ["gmap-0.6.0", "gmap-0.6.1", "gmap-0.7.0", "gmap-0.8.0"]):
		return result
	for cell: Dictionary in assembly.map.cells:
		if not cell.has("diagonal_passage"):
			continue
		result.links += 1
		_check_passage(assembly, String(cell.cell_id), result)
	for edge: Dictionary in assembly.map.edges:
		if String(edge.get("kind", "")) == "diagonal":
			result.diagonal_edges += 1
			_check_edge(assembly, edge, result)
	_check_frames(assembly, result)
	if result.diagonal_edges != result.links * 2:
		result.failures.append("each diagonal passage must have two authored edges")
	return result


static func _check_passage(assembly: Node3D, cell_id: String, result: Dictionary) -> void:
	if not assembly.specs.has(cell_id) or not assembly.rooms.has(cell_id):
		result.failures.append("%s: passage room was not built" % cell_id)
		return
	var spec: Dictionary = assembly.specs[cell_id]
	if spec.doorways.size() != 2 or spec.doorways.any(func(d: Dictionary) -> bool:
		return absf(float(d.normal[0])) < 0.5 or absf(float(d.normal[1])) < 0.5):
		result.failures.append("%s: passage needs two 45-degree openings" % cell_id)
	var boundaries: Node3D = assembly.rooms[cell_id].get_node("AuthoredBoundaries")
	for body in boundaries.find_children("Wall_*", "StaticBody3D", true, false):
		if body.get_child_count() > 0:
			result.passage_wall_colliders += 1
	if result.passage_wall_colliders < 2:
		result.failures.append("%s: passage side walls have no collision" % cell_id)


static func _check_edge(assembly: Node3D, edge: Dictionary, result: Dictionary) -> void:
	var from_end := MAP_CHECKS._end(assembly, String(edge.from))
	var to_end := MAP_CHECKS._end(assembly, String(edge.to))
	if from_end.is_empty() or to_end.is_empty():
		result.failures.append("%s -> %s: diagonal endpoint has no runtime doorway" % [edge.from, edge.to])
		return
	var normal: Vector2 = from_end.normal
	var tangent := Vector2(-normal.y, normal.x)
	for offset: float in LATERAL_OFFSETS:
		var start: Vector2 = from_end.pos - normal * INSIDE_M + tangent * offset
		var finish: Vector2 = to_end.pos - to_end.normal * INSIDE_M + tangent * offset
		for pair in [[start, finish], [finish, start]]:
			result.lane_sweeps += 1
			var travel := PROBE.sweep(assembly.get_world_3d().direct_space_state, pair[0], pair[1])
			if travel.passable:
				result.lane_sweeps_passed += 1
			else:
				result.failures.append("%s -> %s lateral %.2f: %s" % [edge.from, edge.to, offset, travel.reason])


## Every 45-degree doorway of a room (the passage itself builds none) needs its header and trim, laid along the
## face: the box's local X runs along the wall (perpendicular to the doorway normal), the box sits on the inward
## side of the doorway line, and the header spans the opening's height up to the ceiling. #193 shipped headers
## and trim unrotated on chamfer faces because the spec did not carry the flag that selected the rotation.
static func _check_frames(assembly: Node3D, result: Dictionary) -> void:
	for cell_id: String in assembly.specs:
		var spec: Dictionary = assembly.specs[cell_id]
		if spec.has("diagonal_passage") or not assembly.rooms.has(cell_id):
			continue
		var room: Node3D = assembly.rooms[cell_id]
		for doorway: Dictionary in spec.doorways:
			var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
			if absf(normal.x) < 0.5 or absf(normal.y) < 0.5:
				continue
			result.frames_checked += 1
			var port := String(doorway.port_id).replace(":", "_")  # Godot node names cannot hold ":"
			var door := room.to_global(Vector3(float(doorway.pos_xz[0]), 0.0, float(doorway.pos_xz[1])))
			var visuals: Node3D = room.get_node("AuthoredVisuals")
			var door_height := float(doorway.height_m)
			var ceiling := float(spec.ceiling_height_m)
			var width := float(doorway.width_m)
			_check_box(visuals, "Header_" + port + "Visual", door, normal, Vector2(door_height, ceiling), HEADER_DEPTH, width, result)
			for label: String in ["TrimJambLow_", "TrimJambHigh_", "TrimLintel_"]:
				_check_box(visuals, label + port, door, normal, Vector2.ZERO, TRIM_DEPTH, 0.0, result)


static func _check_box(visuals: Node3D, label: String, door: Vector3, normal: Vector2, vertical: Vector2,
		depth: float, min_along: float, result: Dictionary) -> void:
	var box := visuals.find_child(label, true, false) as MeshInstance3D
	if box == null or not box.mesh is BoxMesh:
		result.failures.append("%s: diagonal doorway has no %s" % [visuals.get_parent().name, label])
		return
	var size: Vector3 = (box.mesh as BoxMesh).size
	var along := Vector2(box.global_transform.basis.x.x, box.global_transform.basis.x.z).normalized()
	var across := Vector2(box.global_transform.basis.z.x, box.global_transform.basis.z.z).normalized()
	var inward := (Vector2(box.global_position.x - door.x, box.global_position.z - door.z)).dot(-normal)
	if absf(along.dot(normal)) > ALIGN_TOLERANCE or absf(across.cross(normal)) > ALIGN_TOLERANCE:
		result.failures.append("%s: %s is not aligned with the 45-degree face (long axis %s, normal %s)" % [
			visuals.get_parent().name, label, along, normal])
	if absf(inward - depth / 2.0) > 0.05 and not label.begins_with("TrimJamb") and not label.begins_with("TrimLintel"):
		result.failures.append("%s: %s sits %.2f m inside the doorway line, expected about %.2f" % [
			visuals.get_parent().name, label, inward, depth / 2.0])
	if size.x < min_along - ALIGN_TOLERANCE:
		result.failures.append("%s: %s is %.2f m along the face, narrower than the opening" % [visuals.get_parent().name, label, size.x])
	if vertical != Vector2.ZERO:
		var bottom := box.global_position.y - size.y / 2.0
		var top := box.global_position.y + size.y / 2.0
		if absf(bottom - vertical.x) > ALIGN_TOLERANCE or absf(top - vertical.y) > ALIGN_TOLERANCE:
			result.failures.append("%s: %s spans y %.2f-%.2f, expected %.2f-%.2f" % [
				visuals.get_parent().name, label, bottom, top, vertical.x, vertical.y])
