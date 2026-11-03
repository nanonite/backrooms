extends RefCounted

## Palette checks for shape-room-0.5.0 rooms (#192): each built room's wall, floor, ceiling, trim and
## lamp materials must be the ones its spec names (texture resource path or albedo colour).

const COLOR_TOLERANCE := 0.002


static func check(assembly: Node3D, specs: Dictionary) -> Dictionary:
	var result := {"rooms": 0, "surfaces": 0, "mismatches": 0, "palettes": {}, "failures": []}
	for cell_id: String in specs:
		var spec: Dictionary = specs[cell_id]
		if not spec.materials.has("palette_id") or not assembly.rooms.has(cell_id):
			continue
		result.rooms += 1
		var palettes: Dictionary = result.palettes
		palettes[spec.materials.palette_id] = int(palettes.get(spec.materials.palette_id, 0)) + 1
		_check_room(assembly.rooms[cell_id], spec, result)
	return result


static func _check_room(room: Node3D, spec: Dictionary, result: Dictionary) -> void:
	var visuals := room.get_node("AuthoredVisuals") as Node3D
	var wanted: Dictionary = spec.materials
	# [name, meshes, expected, must exist]; a surface is a Dictionary, trim and lamp a colour Array.
	var groups := [
		["floor", _meshes(visuals.get_node("WalkableFloorVisual"), ""), wanted.floor, true],
		["ceiling", _meshes(visuals.get_node("RenderedCeiling"), ""), wanted.ceiling, true],
		["wall", _meshes(visuals, "Wall_"), wanted.wall, true],
		["header", _meshes(visuals, "Header_"), wanted.wall, false],
		["trim", _meshes(visuals, "Trim"), wanted.trim_color, false],
		["lamp", _meshes(visuals.get_node("CeilingLamps"), ""), wanted.lamp_color, true],
	]
	for group: Array in groups:
		var meshes: Array = group[1]
		if meshes.is_empty() and group[3]:
			_report(result, "%s: no %s meshes found" % [spec.cell_id, group[0]])
		for mesh: MeshInstance3D in meshes:
			result.surfaces += 1
			if not material_matches(mesh.material_override, group[2]):
				_report(result, "%s: %s %s does not match palette %s" % [spec.cell_id, group[0], mesh.name, wanted.palette_id])


## `expected` is a palette surface ({texture, tile_m} or {color}) or a bare colour [r, g, b].
static func material_matches(material: Material, expected: Variant) -> bool:
	if expected is Array:
		return _colour_matches(material, expected)
	var surface: Dictionary = expected
	var standard := material as StandardMaterial3D
	if standard == null:
		return false
	if surface.has("texture"):
		return standard.albedo_texture != null and String(standard.get_meta("source_path", "")) == String(surface.texture)
	return standard.albedo_texture == null and _colour_matches(material, surface.color)


static func _meshes(parent: Node, prefix: String) -> Array:
	var found: Array = []
	for child in parent.get_children():
		if child is MeshInstance3D and String(child.name).begins_with(prefix):
			found.append(child)
	return found


static func _colour_matches(material: Material, rgb: Array) -> bool:
	var standard := material as StandardMaterial3D
	if standard == null:
		return false
	var color := standard.albedo_color
	return absf(color.r - float(rgb[0])) < COLOR_TOLERANCE and absf(color.g - float(rgb[1])) < COLOR_TOLERANCE and absf(color.b - float(rgb[2])) < COLOR_TOLERANCE


static func _report(result: Dictionary, message: String) -> void:
	result.mismatches += 1
	result.failures.append(message)
