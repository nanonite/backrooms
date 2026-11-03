class_name Issue188ModuleChecks
extends RefCounted

## Checks for library modules placed as leaf cells in a gmap-0.3.0 map (#188):
##  - the placed socket lands on its port (position within the landing clearance, normal,
##    floor height) and the instanced scene reports the socket open;
##  - the doorway aperture holds no collider (parent wall + library wall double-up must not
##    block it) and the floor is supported on both sides of the joint;
##  - a parent shape-room wall never shares its wall plane (the plane across the joint), with the
##    same facing, with a library-room box: the 2 cm landing clearance exists to prevent exactly
##    that, and a control that undoes the clearance must be detected. Coplanar faces on the
##    other axes are the reveal / lintel faces where the two rooms' openings meet (#189): the
##    parent doorway is cut MODULE_JOINT_RECESS larger than the library opening, so there must
##    be none (`reveal_coplanar_faces` is 0), and a control that rebuilds the old geometry must
##    be detected.
## Edge traversal both ways is covered by Issue183MapChecks, which treats module cells as rooms.

const PROBE := preload("res://scripts/shape_room_probe.gd")
const TRIM := preload("res://scripts/issue186_trim_checks.gd")
const DOORWAYS := preload("res://scripts/doorway_sizes.gd")
const LANDING_TOLERANCE_M := 0.05
const APERTURE_DEPTH_M := 0.9
const APERTURE_INSET_M := 0.05
const FLOOR_PROBE_M := 0.3
const CLEARANCE_M := 0.02


static func check(space: PhysicsDirectSpaceState3D, assembly: Node3D) -> Dictionary:
	var result := {"module_cells": 0, "sockets_landed": 0, "sockets_open": 0, "apertures_clear": 0,
		"floors_supported": 0, "joints": [] as Array[Dictionary], "failures": [] as Array[String]}
	var ids: Array = assembly.module_rooms.keys()
	ids.sort()
	for cell_id: String in ids:
		result.module_cells += 1
		var joint := _check_module(space, assembly, cell_id, result.failures)
		result.sockets_landed += 1 if joint.landed else 0
		result.sockets_open += 1 if joint.open else 0
		result.apertures_clear += 1 if joint.aperture_clear else 0
		result.floors_supported += 1 if joint.floors_supported else 0
		result.joints.append(joint)
	var coplanar := joint_coplanar(assembly, 0.0)
	var wall_plane := wall_plane_conflicts(assembly, coplanar)
	result["wall_coplanar_conflicts"] = wall_plane.size()
	result["reveal_coplanar_faces"] = coplanar.size() - wall_plane.size()
	for conflict: Dictionary in wall_plane:
		result.failures.append("Module box %s shares wall plane %.3f (axis %d) with room box %s" % [
			conflict.trim, conflict.plane, conflict.axis, conflict.other])
	# #189: the reveal and lintel faces where the two openings meet must not share a plane
	# either; the parent doorway is cut larger than the library's (MODULE_JOINT_RECESS).
	for conflict: Dictionary in coplanar:
		if not wall_plane.has(conflict):
			result.failures.append("Module box %s shares face plane %.3f (axis %d, sign %d) with room box %s" % [
				conflict.trim, conflict.plane, conflict.axis, conflict.sign, conflict.other])
	# Control: without the clearance (module pushed back onto the parent wall) the same check must fire.
	var control := wall_plane_conflicts(assembly, joint_coplanar(assembly, CLEARANCE_M))
	# Informational: a room whose wall straddles its footprint edge (the column) has nothing to
	# collide in that plane, so the control only fires for the rooms whose wall stands outside it.
	result["clearance_control_conflicts"] = control.size()
	return result


## Conflicts on the axis across the joint (x for east / west joints, z otherwise).
static func wall_plane_conflicts(assembly: Node3D, conflicts: Array) -> Array[Dictionary]:
	var kept: Array[Dictionary] = []
	for conflict: Dictionary in conflicts:
		var port := _port_of(assembly, String(conflict.trim).get_slice("/", 0))
		if port.is_empty():
			continue
		if int(conflict.axis) == (0 if absf(port.normal.x) > 0.5 else 2):
			kept.append(conflict)
	return kept


static func _check_module(space: PhysicsDirectSpaceState3D, assembly: Node3D, cell_id: String,
		failures: Array[String]) -> Dictionary:
	var info: Dictionary = assembly.module_info[cell_id]
	var room: Node3D = assembly.module_rooms[cell_id]
	var port := _port_of(assembly, cell_id)
	var joint := {"cell_id": cell_id, "module_id": String(info.placement.module_id), "landed": false, "open": false,
		"aperture_clear": false, "floors_supported": false, "landing_miss_m": -1.0}
	if port.is_empty() or info.socket.is_empty():
		failures.append("%s: module has no port or socket record" % cell_id)
		return joint
	var local_centre := _vec3(info.socket.local_floor_center)
	var local_normal := _vec3(info.socket.outward_normal)
	var world_centre := room.to_global(local_centre)
	var world_normal := (room.global_transform.basis * local_normal).normalized()
	var miss := Vector2(world_centre.x, world_centre.z).distance_to(port.pos)
	joint["landing_miss_m"] = miss
	var normal_ok := Vector2(world_normal.x, world_normal.z).distance_to(port.normal) < 0.001
	joint["landed"] = miss <= LANDING_TOLERANCE_M and normal_ok and absf(world_centre.y) < 0.001
	if not joint.landed:
		failures.append("%s: socket %s lands %.3f m from its port (normal ok: %s, floor y %.3f)" % [
			cell_id, info.placement.socket_id, miss, str(normal_ok), world_centre.y])
	joint["open"] = _reports_open(room, String(info.placement.socket_id))
	if not joint.open:
		failures.append("%s: instanced scene does not report socket %s open" % [cell_id, info.placement.socket_id])
	var size := DOORWAYS.size_of({"compatibility_type": String(port.compatibility_type)})
	joint["aperture_clear"] = _aperture_clear(space, port, size, cell_id, failures)
	joint["floors_supported"] = _floors_supported(space, port, cell_id, failures)
	return joint


static func _port_of(assembly: Node3D, cell_id: String) -> Dictionary:
	for cell: Dictionary in assembly.map.cells:
		if String(cell.cell_id) == cell_id and not cell.required_ports.is_empty():
			var port: Dictionary = cell.required_ports[0]
			return {"pos": Vector2(float(port.pos_xz[0]), float(port.pos_xz[1])),
				"normal": Vector2(float(port.normal[0]), float(port.normal[1])),
				"compatibility_type": String(port.compatibility_type)}
	return {}


static func _reports_open(room: Node3D, socket_id: String) -> bool:
	if room.has_meta("connector_open_ids"):
		return socket_id in room.get_meta("connector_open_ids")
	return room.has_meta("connector_open") and bool(room.get_meta("connector_open"))


## A box as wide as the opening (less a 5 cm reveal each side), from 10 cm above the floor to
## 10 cm under the lintel and 0.9 m deep across the joint, must touch no collider at all
## (floors excepted): parent wall, library wall and both headers all stay out of it.
static func _aperture_clear(space: PhysicsDirectSpaceState3D, port: Dictionary, size: Vector2,
		cell_id: String, failures: Array[String]) -> bool:
	var shape := BoxShape3D.new()
	var across := size.x - 2.0 * APERTURE_INSET_M
	var height := size.y - 0.2
	var on_x_wall: bool = absf(port.normal.x) > 0.5
	shape.size = Vector3(APERTURE_DEPTH_M, height, across) if on_x_wall else Vector3(across, height, APERTURE_DEPTH_M)
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, Vector3(port.pos.x, 0.1 + height / 2.0, port.pos.y))
	query.collision_mask = 1
	var hits: Array[String] = []
	for hit in space.intersect_shape(query, 32):
		var collider := hit.get("collider") as Node
		if collider != null and not PROBE.is_floor_body(collider):
			hits.append("%s/%s" % [collider.get_parent().name, collider.name])
	if not hits.is_empty():
		failures.append("%s: doorway aperture is obstructed by %s" % [cell_id, ", ".join(hits)])
	return hits.is_empty()


static func _floors_supported(space: PhysicsDirectSpaceState3D, port: Dictionary, cell_id: String,
		failures: Array[String]) -> bool:
	var supported := true
	for distance: float in [-FLOOR_PROBE_M, 0.0, FLOOR_PROBE_M]:
		var point: Vector2 = port.pos + port.normal * distance
		if not PROBE.floor_supported(space, point.x, point.y):
			supported = false
			failures.append("%s: no floor support %.1f m from the port along its normal" % [cell_id, distance])
	return supported


## Wall and header boxes of the shape rooms against the library rooms' boxes: same plane,
## same facing, positive overlap. `press` slides each module box that far toward its
## parent (the control that undoes the landing clearance).
static func joint_coplanar(assembly: Node3D, press: float) -> Array:
	var boxes := TRIM.collect(assembly)
	var rooms: Array[Dictionary] = []
	for box: Dictionary in boxes.solid:
		if _is_module_name(assembly, String(box.name)):
			continue
		rooms.append(box)
	var moved: Array[Dictionary] = []
	for box: Dictionary in boxes.module:
		var shifted: Dictionary = box.duplicate()
		var cell_id := String(box.name).get_slice("/", 0)
		shifted["center"] = box.center + _toward_parent(assembly, cell_id) * press
		moved.append(shifted)
	return TRIM.conflicts(moved, rooms).same_facing


static func _is_module_name(assembly: Node3D, box_name: String) -> bool:
	return assembly.module_rooms.has(box_name.get_slice("/", 0))


static func _toward_parent(assembly: Node3D, cell_id: String) -> Vector3:
	var port := _port_of(assembly, cell_id)
	if port.is_empty():
		return Vector3.ZERO
	return Vector3(port.normal.x, 0.0, port.normal.y)


static func _vec3(values: Array) -> Vector3:
	return Vector3(float(values[0]), float(values[1]), float(values[2]))
