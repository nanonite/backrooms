class_name Issue190DiagonalChecks
extends RefCounted

## Checks for the 45-degree walls of a gmap-0.4.0 map (#190):
##  - capsule push: a capsule pushed into every diagonal wall from inside is stopped (no clipping);
##  - floor: dense ray samples (every 0.1 m, so exactly on the 0.5 m lines where triangulation edges run)
##    find the floor everywhere inside the outline, diagonals included (no slit);
##  - joint coverage: the wall collision boxes cover the whole wall band around every diagonal joint
##    (an unmitred joint would leave a gap);
##  - coplanar faces: no vertical face of a diagonal wall shares a plane, with the same facing and a
##    positive overlap, with a vertical face of any other wall, header, trim or library box.
## Edge traversal, floor support and the flood fill are covered by the #183 checks.

const PROBE := preload("res://scripts/shape_room_probe.gd")
const BUILDER := preload("res://scripts/shape_room_builder.gd")
const DIAGONAL := preload("res://scripts/shape_room_diagonal.gd")
const PUSH_FRACTIONS := [0.3, 0.5, 0.7]
const LINK_PUSH_FRACTIONS := [0.1, 0.3, 0.5, 0.7, 0.9]
const PUSH_START_M := 1.0
const PUSH_TRAVEL_M := 1.6
const STOPPED_DEPTH_M := 0.40  # a stopped capsule centre stays at least this far inside the outline
const JOINT_RADIUS_M := 0.45
const SAMPLE_STEP_M := 0.03
const FACE_EPS := 0.0005
const FLOOR_STEP_M := 0.1
const FLOOR_EDGE_SKIP_M := 0.2  # the wall band (0.16 m) is inside the outline: a ray there hits the wall


## `with_floor` false skips the dense floor samples (the negative controls do not need them).
static func check(assembly: Node3D, with_floor: bool = true) -> Dictionary:
	var result := {"diagonal_edges": 0, "push_samples": 0, "push_stopped": 0, "floor_samples": 0, "floor_missing": 0, "module_overhang_samples": 0, "joint_samples": 0,
		"joint_uncovered": 0, "coplanar_faces": 0, "failures": [] as Array[String]}
	for cell_id: String in assembly.rooms:
		var spec: Dictionary = assembly.specs[cell_id]
		if not DIAGONAL.is_chamfered(spec):
			continue
		var ring: Array[Vector2] = BUILDER.ring_of(spec)
		_push(assembly, cell_id, ring, result)
		if with_floor:
			_floor(assembly, cell_id, ring, spec, result)
		_joints(assembly.rooms[cell_id], cell_id, ring, spec, result)
	for conflict: String in coplanar(assembly):
		result.coplanar_faces += 1
		result.failures.append("Diagonal wall face is coplanar: " + conflict)
	return result


static func _floor(assembly: Node3D, cell_id: String, ring: Array[Vector2], spec: Dictionary, result: Dictionary) -> void:
	var space := assembly.get_world_3d().direct_space_state
	var low := Vector2(float(spec.envelope_xz[0][0]), float(spec.envelope_xz[0][1]))
	var high := Vector2(float(spec.envelope_xz[2][0]), float(spec.envelope_xz[2][1]))
	for i in range(int(round((high.x - low.x) / FLOOR_STEP_M)) + 1):
		for j in range(int(round((high.y - low.y) / FLOOR_STEP_M)) + 1):
			var point := low + Vector2(i, j) * FLOOR_STEP_M
			if not PROBE.inside_polygon(point, ring) or _wall_distance(point, ring) < FLOOR_EDGE_SKIP_M:
				continue
			result.floor_samples += 1
			if not PROBE.floor_supported(space, point.x, point.y):
				if _under_module_wall(assembly, space, point):
					result.module_overhang_samples += 1  # a library wall overhangs this room by up to 0.3 m (#188)
					continue
				result.floor_missing += 1
				if result.floor_missing <= 3:
					result.failures.append("%s: no floor at (%.4f, %.4f) inside the outline" % [cell_id, point.x, point.y])


## The ray down at `point` is stopped by a box of a placed library room, not by a gap in the floor.
static func _under_module_wall(assembly: Node3D, space: PhysicsDirectSpaceState3D, point: Vector2) -> bool:
	var query := PhysicsRayQueryParameters3D.create(Vector3(point.x, 0.45, point.y), Vector3(point.x, -0.12, point.y))
	var hit := space.intersect_ray(query)
	if hit.is_empty():
		return false
	for room in assembly.module_rooms.values():
		if room.is_ancestor_of(hit.collider as Node):
			return true
	return false


static func _wall_distance(point: Vector2, ring: Array[Vector2]) -> float:
	var nearest := INF
	for index in ring.size():
		var closest := Geometry2D.get_closest_point_to_segment(point, ring[index], ring[(index + 1) % ring.size()])
		nearest = minf(nearest, point.distance_to(closest))
	return nearest


static func _push(assembly: Node3D, cell_id: String, ring: Array[Vector2], result: Dictionary) -> void:
	var space := assembly.get_world_3d().direct_space_state
	for index in ring.size():
		var start := ring[index]
		var direction := (ring[(index + 1) % ring.size()] - start).normalized()
		if not DIAGONAL.is_diagonal(direction):
			continue
		result.diagonal_edges += 1
		var inward := Vector2(-direction.y, direction.x)
		var length := start.distance_to(ring[(index + 1) % ring.size()])
		var fractions: Array = LINK_PUSH_FRACTIONS if _has_diagonal_doorway(assembly.specs[cell_id]) else PUSH_FRACTIONS
		for fraction: float in fractions:
			var on_wall := start + direction * (length * fraction)
			if _has_diagonal_doorway(assembly.specs[cell_id]) and _near_doorway(on_wall, direction, assembly.specs[cell_id]):
				continue  # an opening is not a solid wall to push against.
			var from := on_wall + inward * PUSH_START_M
			result.push_samples += 1
			if not PROBE.blockers(space, from.x, from.y).is_empty() or not PROBE.floor_supported(space, from.x, from.y):
				result.failures.append("%s edge %d: push start %s is not clear floor" % [cell_id, index, from])
				continue
			var depth := _pushed_depth(assembly, from, -inward, on_wall, inward)
			if depth >= STOPPED_DEPTH_M:
				result.push_stopped += 1
			else:
				result.failures.append("%s edge %d: a capsule pushed into the wall reached %.2f m of the outline (stop >= %.2f)" % [
					cell_id, index, depth, STOPPED_DEPTH_M])


static func _near_doorway(point: Vector2, direction: Vector2, spec: Dictionary) -> bool:
	for doorway: Dictionary in spec.doorways:
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		if absf(normal.dot(direction)) > 0.001:
			continue
		var center := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		if absf((point - center).dot(direction)) < float(doorway.width_m) / 2.0 + PROBE.RADIUS:
			return true
	return false


static func _has_diagonal_doorway(spec: Dictionary) -> bool:
	return spec.doorways.any(func(doorway: Dictionary) -> bool:
		return absf(absf(float(doorway.normal[0])) - absf(float(doorway.normal[1]))) < 0.001)


## How far inside the wall line the capsule centre ends after being pushed `PUSH_TRAVEL_M` toward it.
static func _pushed_depth(assembly: Node3D, from: Vector2, toward: Vector2, on_wall: Vector2, inward: Vector2) -> float:
	var body := CharacterBody3D.new()
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = PROBE.RADIUS
	capsule.height = PROBE.HEIGHT
	shape.shape = capsule
	body.add_child(shape)
	assembly.add_child(body)
	body.global_position = Vector3(from.x, PROBE.CENTER_Y, from.y)
	body.move_and_collide(Vector3(toward.x, 0.0, toward.y) * PUSH_TRAVEL_M)
	var at := Vector2(body.global_position.x, body.global_position.z)
	assembly.remove_child(body)
	body.free()
	return (at - on_wall).dot(inward)


## Samples of the wall band (inside the outline, closer than the wall thickness to it) around each
## vertex that touches a diagonal edge must lie inside at least one wall collision box.
static func _joints(room: Node3D, cell_id: String, ring: Array[Vector2], spec: Dictionary, result: Dictionary) -> void:
	var boxes := _wall_shapes(room)
	for index in ring.size():
		var touches: bool = DIAGONAL.is_diagonal((ring[(index + 1) % ring.size()] - ring[index]).normalized()) \
			or DIAGONAL.is_diagonal((ring[index] - ring[(index - 1 + ring.size()) % ring.size()]).normalized())
		if not touches:
			continue
		var vertex := ring[index]
		var x := -JOINT_RADIUS_M
		while x <= JOINT_RADIUS_M:
			var z := -JOINT_RADIUS_M
			while z <= JOINT_RADIUS_M:
				var point := vertex + Vector2(x, z)
				if point.distance_to(vertex) <= JOINT_RADIUS_M and _in_wall_band(point, ring):
					if _inside_open_doorway_band(point, spec):
						z += SAMPLE_STEP_M
						continue
					result.joint_samples += 1
					if not _covered(point, boxes):
						result.joint_uncovered += 1
						if result.joint_uncovered <= 3:
							result.failures.append("%s: wall band at %s near vertex %d is not covered by a wall box" % [cell_id, point, index])
				z += SAMPLE_STEP_M
			x += SAMPLE_STEP_M


static func _inside_open_doorway_band(point: Vector2, spec: Dictionary) -> bool:
	for doorway: Dictionary in spec.doorways:
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		if absf(absf(normal.x) - absf(normal.y)) > 0.001:
			continue
		var center := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		var offset := point - center
		var tangent := Vector2(-normal.y, normal.x)
		if absf(offset.dot(tangent)) < float(doorway.width_m) / 2.0 and absf(offset.dot(normal)) < BUILDER.WALL_THICKNESS:
			return true
	return false


static func _in_wall_band(point: Vector2, ring: Array[Vector2]) -> bool:
	if not PROBE.inside_polygon(point, ring):
		return false
	var nearest := _wall_distance(point, ring)
	return nearest < BUILDER.WALL_THICKNESS - 0.005 and nearest > 0.005


static func _wall_shapes(room: Node3D) -> Array[Dictionary]:
	var boxes: Array[Dictionary] = []
	for body in room.get_node("AuthoredBoundaries").get_children():
		if not String(body.name).begins_with("Wall_"):
			continue
		for child in body.get_children():
			if child is CollisionShape3D and (child as CollisionShape3D).shape is BoxShape3D:
				boxes.append({"inverse": (child as CollisionShape3D).global_transform.affine_inverse(),
					"half": ((child as CollisionShape3D).shape as BoxShape3D).size / 2.0})
	return boxes


static func _covered(point: Vector2, boxes: Array[Dictionary]) -> bool:
	for box: Dictionary in boxes:
		var local: Vector3 = box.inverse * Vector3(point.x, 1.0, point.y)
		if absf(local.x) <= box.half.x + 0.0001 and absf(local.y) <= box.half.y and absf(local.z) <= box.half.z + 0.0001:
			return true
	return false


## Names of vertical-face coplanar conflicts that involve a diagonal (turned) box: same plane, same
## facing, positive overlap along the plane and in height. Wall, header and trim boxes of every
## shape room and every box of a placed library room are compared.
static func coplanar(assembly: Node3D) -> Array[String]:
	var boxes := _oriented_boxes(assembly)
	var found: Array[String] = []
	for i in boxes.size():
		for j in range(i + 1, boxes.size()):
			var a: Dictionary = boxes[i]
			var b: Dictionary = boxes[j]
			if not (a.turned or b.turned) or a.center.distance_to(b.center) > a.radius + b.radius:
				continue
			for face_a: Dictionary in _vertical_faces(a):
				for face_b: Dictionary in _vertical_faces(b):
					if _same_plane_overlap(face_a, face_b):
						found.append("%s and %s (plane %.3f)" % [a.name, b.name, face_a.offset])
	return found


static func _oriented_boxes(assembly: Node3D) -> Array[Dictionary]:
	var boxes: Array[Dictionary] = []
	for cell_id: String in assembly.rooms:
		for node in _meshes(assembly.rooms[cell_id].get_node("AuthoredVisuals")):
			var label := String(node.name)
			if label.begins_with("Wall_") or label.begins_with("Header_") or label.begins_with("Trim"):
				boxes.append(_oriented(cell_id, node))
	for cell_id: String in assembly.module_rooms:
		for node in _meshes(assembly.module_rooms[cell_id]):
			boxes.append(_oriented(cell_id, node))
	return boxes


static func _oriented(cell_id: String, node: MeshInstance3D) -> Dictionary:
	var half := (node.mesh as BoxMesh).size / 2.0
	var basis := node.global_transform.basis.orthonormalized()
	return {"name": "%s/%s" % [cell_id, node.name], "center": node.global_position, "half": half, "basis": basis,
		"radius": half.length(), "turned": absf(sin(2.0 * node.global_rotation.y)) > 0.001}


static func _meshes(node: Node) -> Array[MeshInstance3D]:
	var found: Array[MeshInstance3D] = []
	for child in node.get_children():
		if child is MeshInstance3D and (child as MeshInstance3D).mesh is BoxMesh:
			found.append(child)
		found.append_array(_meshes(child))
	return found


## The four vertical faces of a box: outward normal, plane offset, and the extent along the plane.
static func _vertical_faces(box: Dictionary) -> Array[Dictionary]:
	var faces: Array[Dictionary] = []
	var basis: Basis = box.basis
	for axis in [0, 2]:
		var other: int = 2 if axis == 0 else 0
		for face_sign in [-1.0, 1.0]:
			var normal: Vector3 = basis[axis] * face_sign
			faces.append({"normal": normal, "offset": normal.dot(box.center) + box.half[axis],
				"y_low": box.center.y - box.half.y, "y_high": box.center.y + box.half.y,
				"center": box.center, "half_other": box.half[other]})
	return faces


static func _same_plane_overlap(a: Dictionary, b: Dictionary) -> bool:
	if (a.normal as Vector3).dot(b.normal) < 0.9999 or absf(a.offset - b.offset) > FACE_EPS:
		return false
	var tangent := Vector3(-a.normal.z, 0.0, a.normal.x)
	var a_mid: float = (a.center as Vector3).dot(tangent)
	var b_mid: float = (b.center as Vector3).dot(tangent)
	var low := maxf(a_mid - a.half_other, b_mid - b.half_other)
	var high := minf(a_mid + a.half_other, b_mid + b.half_other)
	var y_low := maxf(a.y_low, b.y_low)
	var y_high := minf(a.y_high, b.y_high)
	return high - low > FACE_EPS and y_high - y_low > FACE_EPS
