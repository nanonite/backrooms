class_name Issue199SurfaceChecks
extends RefCounted

## Surface checks for shape-room-0.9.0 (#199): every generated floor collider must
## carry the palette's acoustic tag, and every declared acoustic tag must resolve.

const ACOUSTIC_TAGS := ["carpet", "concrete", "tile", "plaster", "metal", "wood", "debris"]


static func check(assembly: Node3D, specs: Dictionary) -> Dictionary:
	var result := {"rooms": 0, "floor_colliders": 0, "resolved_floors": 0,
		"surface_tags": 0, "failures": [] as Array[String]}
	for cell_id: String in specs:
		var spec: Dictionary = specs[cell_id]
		if not spec.materials.has("acoustic"):
			continue
		result.rooms += 1
		var expected: Dictionary = spec.materials.acoustic
		for surface: String in expected:
			result.surface_tags += 1
			if not ACOUSTIC_TAGS.has(String(expected[surface])):
				_report(result, "%s: unknown %s acoustic tag %s" % [cell_id, surface, expected[surface]])
		var room: Node3D = assembly.rooms[cell_id]
		var bodies := room.find_children("WalkableFloor", "StaticBody3D", true, false)
		if bodies.is_empty():
			_report(result, "%s: no WalkableFloor collider" % cell_id)
			continue
		for body_node: Node in bodies:
			var body := body_node as StaticBody3D
			result.floor_colliders += 1
			var tag := String(body.get_meta("surface_acoustic", ""))
			if tag.is_empty():
				_report(result, "%s: floor collider has no surface_acoustic" % cell_id)
				continue
			if not ACOUSTIC_TAGS.has(tag):
				_report(result, "%s: floor collider has unknown acoustic tag %s" % [cell_id, tag])
				continue
			result.resolved_floors += 1
			if tag != String(expected.floor):
				_report(result, "%s: floor tag %s does not match palette %s" % [cell_id, tag, expected.floor])
	return result


static func _report(result: Dictionary, message: String) -> void:
	result.failures.append(message)
