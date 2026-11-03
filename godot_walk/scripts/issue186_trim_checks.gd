class_name Issue186TrimChecks
extends RefCounted

## Trim/wall coplanarity check (#186). Every visual box is axis-aligned, so each face
## is a plane on one axis with a normal sign. Two faces z-fight when they lie in the
## same plane, face the same way and overlap with positive area. A trim box (jamb or
## lintel) is tested against every wall and header box of the assembled map, which
## covers the walls of the adjacent cell at a shared doorway and the perpendicular wall
## at a corner doorway. Opposite-facing coplanar contacts (a jamb pressed against a wall
## end, the lintel under a header) are back to back: one face is always inside solid
## geometry, so they cannot flicker and are only counted. Likewise a face on the floor plane
## (y = 0) that faces down is the underside of a box standing on the floor: no camera sees
## it, so a library room's wall (#188) standing next to a jamb there is only counted.

const EPS := 0.0005
const OLD_TRIM_SHIFT := 0.06


static func check(assembly: Node3D) -> Dictionary:
	var boxes := collect(assembly)
	var result := conflicts(boxes.trim, boxes.solid)
	result["trim_boxes"] = boxes.trim.size()
	result["solid_boxes"] = boxes.solid.size()
	result["degenerate_trim_boxes"] = 0
	result["degenerate_conflicts"] = 0
	for trim: Dictionary in boxes.trim:
		if trim.degenerate:
			result.degenerate_trim_boxes += 1
	for conflict: Dictionary in result.same_facing:
		if conflict.degenerate:
			result.degenerate_conflicts += 1
	return result


static func collect(assembly: Node3D) -> Dictionary:
	var trim: Array[Dictionary] = []
	var solid: Array[Dictionary] = []
	for cell_id: String in assembly.rooms:
		var room: Node3D = assembly.rooms[cell_id]
		var spec: Dictionary = assembly.specs[cell_id]
		var degenerate: Array = spec.get("degenerate_port_ids", [])
		var visuals := room.get_node("AuthoredVisuals")
		for node in _meshes(visuals):
			var label := String(node.name)
			var box := {"name": "%s/%s" % [cell_id, label], "center": node.global_position,
				"size": (node.mesh as BoxMesh).size, "degenerate": false}
			if label.begins_with("Trim"):
				for port: String in degenerate:
					# Node names cannot hold ':', so "c03:p1" is stored as "c03_p1".
					if label.ends_with("_" + port.replace(":", "_")):
						box["degenerate"] = true
				trim.append(box)
			elif label.begins_with("Wall_") or label.begins_with("Header_"):
				solid.append(box)
	var module_boxes := collect_module_boxes(assembly)
	solid.append_array(module_boxes)  # #188: trim against a library room's boxes too
	return {"trim": trim, "solid": solid, "module": module_boxes}


## Every BoxMesh of every placed library module as an axis-aligned world box. The module is
## turned by quarter turns only, so the absolute basis gives the exact world extents.
static func collect_module_boxes(assembly: Node3D) -> Array[Dictionary]:
	var boxes: Array[Dictionary] = []
	if not "module_rooms" in assembly:
		return boxes
	for cell_id: String in assembly.module_rooms:
		for node in _meshes(assembly.module_rooms[cell_id]):
			var extent := _world_extent(node.global_transform.basis, (node.mesh as BoxMesh).size)
			boxes.append({"name": "%s/%s" % [cell_id, node.name], "center": node.global_position,
				"size": extent, "degenerate": false})
	return boxes


## Extents of a box of `size` turned by `basis` (exact for the quarter turns used here).
static func _world_extent(basis: Basis, size: Vector3) -> Vector3:
	var axes := [basis.x, basis.y, basis.z]
	var extent := Vector3.ZERO
	for source in 3:
		for target in 3:
			extent[target] += absf(axes[source][target]) * size[source]
	return extent


static func _meshes(node: Node) -> Array[MeshInstance3D]:
	var found: Array[MeshInstance3D] = []
	for child in node.get_children():
		if child is MeshInstance3D and (child as MeshInstance3D).mesh is BoxMesh:
			found.append(child)
		found.append_array(_meshes(child))
	return found


static func conflicts(trim: Array[Dictionary], solid: Array[Dictionary]) -> Dictionary:
	var same_facing: Array[Dictionary] = []
	var back_to_back := 0
	var floor_undersides := 0
	var pairs := 0
	for t: Dictionary in trim:
		for w: Dictionary in solid:
			if not _touching(t, w):
				continue
			pairs += 1
			for axis in 3:
				for t_sign in [-1, 1]:
					for w_sign in [-1, 1]:
						if absf(_plane(t, axis, t_sign) - _plane(w, axis, w_sign)) > EPS or not _overlap(t, w, axis):
							continue
						if t_sign == w_sign and axis == 1 and t_sign == -1 and absf(_plane(t, axis, t_sign)) <= EPS:
							floor_undersides += 1
						elif t_sign == w_sign:
							same_facing.append({"trim": t.name, "other": w.name, "axis": axis, "sign": t_sign,
								"plane": _plane(t, axis, t_sign), "degenerate": t.degenerate})
						else:
							back_to_back += 1
	return {"pairs_checked": pairs, "same_facing": same_facing, "same_facing_count": same_facing.size(),
		"back_to_back_contacts": back_to_back, "floor_underside_contacts": floor_undersides}


## The first real jamb moved outward onto the wall, as the pre-fix trim was built, must
## be reported; so must a trim box that shares a full face plane with a wall.
static func negative_controls(assembly: Node3D) -> Dictionary:
	var boxes := collect(assembly)
	var result := {"old_outside_trim_detected": false, "shared_plane_detected": false}
	for trim: Dictionary in boxes.trim:
		if not String(trim.name).contains("TrimJamb"):
			continue
		var thin := 0 if trim.size.x < trim.size.z else 2
		for direction in [-1.0, 1.0]:
			var moved: Dictionary = trim.duplicate()
			var offset := Vector3.ZERO
			offset[thin] = direction * OLD_TRIM_SHIFT
			moved["center"] = trim.center + offset
			if conflicts([moved], boxes.solid).same_facing_count > 0:
				result.old_outside_trim_detected = true
		if result.old_outside_trim_detected:
			break
	if not boxes.solid.is_empty():
		var wall: Dictionary = boxes.solid[0]
		var shared := {"name": "synthetic", "center": wall.center, "size": wall.size * Vector3(0.5, 0.5, 1.0), "degenerate": false}
		result.shared_plane_detected = conflicts([shared], [wall]).same_facing_count > 0
	return result


static func _plane(box: Dictionary, axis: int, face_sign: int) -> float:
	return box.center[axis] + face_sign * box.size[axis] / 2.0


## Positive overlap of the two faces' extents on both axes other than `axis`.
static func _overlap(a: Dictionary, b: Dictionary, axis: int) -> bool:
	for other in 3:
		if other == axis:
			continue
		var low := maxf(a.center[other] - a.size[other] / 2.0, b.center[other] - b.size[other] / 2.0)
		var high := minf(a.center[other] + a.size[other] / 2.0, b.center[other] + b.size[other] / 2.0)
		if high - low <= EPS:
			return false
	return true


static func _touching(a: Dictionary, b: Dictionary) -> bool:
	for axis in 3:
		if absf(a.center[axis] - b.center[axis]) > (a.size[axis] + b.size[axis]) / 2.0 + EPS:
			return false
	return true
