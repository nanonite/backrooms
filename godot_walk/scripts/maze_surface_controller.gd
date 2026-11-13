class_name MazeSurfaceController
extends RefCounted

## Runtime wear and surface-variant application for the M8 follower edits (#238).
##
## The committed map and the instanced room are not rebuilt.  ``tag_room``
## records the palette, variants and wear the room was built with; an override
## then clones only the affected mesh materials, replaces the albedo with the
## registry variant and updates the floor collider's surface metadata.  Every
## other room, mesh and layer keeps its state.
##
## Variants are validated against the same palette registry the map names.  A
## variant only moves forward along clean -> worn -> damaged.

const VARIANT_ORDER := ["clean", "worn", "damaged"]
const SURFACES := ["floor", "wall", "ceiling", "trim"]
const MIN_WEAR := 0
const MAX_WEAR := 2
const REGISTRY_PATHS := {
	"0.2.0": "res://room_catalog/material_palettes/palettes-0.2.0.json",
	"0.3.0": "res://room_catalog/material_palettes/palettes-0.3.0.json",
}

static var _registries: Dictionary = {}
static var _textures: Dictionary = {}


static func tag_room(room: Node3D, spec: Dictionary) -> void:
	var materials: Variant = spec.get("materials")
	if room == null or not materials is Dictionary:
		return
	if not materials.has("palette_id") or not materials.has("variants"):
		return
	room.set_meta("maze_surface_tagged", true)
	room.set_meta("maze_surface_palette_id", String(materials["palette_id"]))
	room.set_meta("maze_surface_registry_version", String(materials.get("registry_version", "0.2.0")))
	room.set_meta("maze_surface_variants", (materials["variants"] as Dictionary).duplicate(true))
	room.set_meta("maze_surface_wear", int(materials.get("wear", 0)))


static func tagged(room: Node3D) -> bool:
	return room != null and room.has_meta("maze_surface_tagged")


static func wear(room: Node3D) -> int:
	if not tagged(room):
		return 0
	return int(room.get_meta("maze_surface_wear", 0))


static func variants(room: Node3D) -> Dictionary:
	if not tagged(room):
		return {}
	return (room.get_meta("maze_surface_variants", {}) as Dictionary).duplicate(true)


static func apply_override(room: Node3D, override: Dictionary) -> bool:
	if not tagged(room):
		return false
	var current_wear := wear(room)
	var current_variants := variants(room)
	var next_wear := current_wear
	if override.has("wear"):
		var wear_value: Variant = override["wear"]
		if typeof(wear_value) != TYPE_INT:
			return false
		next_wear = int(wear_value)
		if next_wear < MIN_WEAR or next_wear > MAX_WEAR:
			return false
	var next_variants := current_variants.duplicate(true)
	if override.has("surface_variant"):
		var record: Variant = override["surface_variant"]
		if not record is Dictionary:
			return false
		for surface: String in record:
			if not SURFACES.has(surface):
				return false
			next_variants[surface] = String(record[surface])
	var palette := _palette_for_room(room)
	if palette.is_empty():
		return false
	for surface: String in SURFACES:
		var variant := String(next_variants.get(surface, ""))
		if not VARIANT_ORDER.has(variant):
			return false
		if not _surface_field(palette, surface).get("variants", {}).has(variant):
			return false
	for surface: String in SURFACES:
		var variant := String(next_variants[surface])
		if variant == String(current_variants.get(surface, "")):
			continue
		if not _apply_surface(room, palette, surface, variant):
			return false
	room.set_meta("maze_surface_wear", next_wear)
	room.set_meta("maze_surface_variants", next_variants.duplicate(true))
	_update_floor_body(room, next_variants, next_wear)
	return true


static func palette_for_cell(cell: Dictionary) -> Dictionary:
	var record: Variant = cell.get("palette")
	if not record is Dictionary:
		return {}
	var palette_id := String(record.get("palette_id", ""))
	var version := String(record.get("registry_version", "0.2.0"))
	var registry := _registry(version)
	for palette: Dictionary in registry.get("palettes", []):
		if String(palette.get("palette_id", "")) == palette_id:
			return palette
	return {}


static func next_variant(current: String, palette: Dictionary, surface: String) -> String:
	var field := _surface_field(palette, surface)
	if field.is_empty():
		return ""
	var position := VARIANT_ORDER.find(current)
	if position < 0 or position + 1 >= VARIANT_ORDER.size():
		return ""
	var candidate: String = VARIANT_ORDER[position + 1]
	return candidate if (field.get("variants", {}) as Dictionary).has(candidate) else ""


static func escalatable_surfaces(variants: Dictionary, palette: Dictionary) -> Array:
	var result: Array = []
	if palette.is_empty():
		return result
	for surface: String in SURFACES:
		if not next_variant(String(variants.get(surface, "")), palette, surface).is_empty():
			result.append(surface)
	return result


static func surface_of(node: Node) -> String:
	var name := String(node.name)
	if name.begins_with("Trim"):
		return "trim"
	if name.begins_with("Wall") or name.begins_with("Header_"):
		return "wall"
	if name.begins_with("Floor") or name.begins_with("SeamStrip_"):
		return "floor"
	if name.begins_with("Ceiling"):
		return "ceiling"
	return ""


static func _palette_for_room(room: Node3D) -> Dictionary:
	var palette_id := String(room.get_meta("maze_surface_palette_id", ""))
	var version := String(room.get_meta("maze_surface_registry_version", "0.2.0"))
	var registry := _registry(version)
	for palette: Dictionary in registry.get("palettes", []):
		if String(palette.get("palette_id", "")) == palette_id:
			return palette
	return {}


static func _surface_field(palette: Dictionary, surface: String) -> Dictionary:
	var surfaces: Variant = palette.get("surfaces")
	if not surfaces is Dictionary:
		return {}
	var field: Variant = surfaces.get(surface)
	return field if field is Dictionary else {}


static func _apply_surface(room: Node3D, palette: Dictionary, surface: String,
		variant: String) -> bool:
	var field := _surface_field(palette, surface)
	var variant_record: Variant = (field.get("variants", {}) as Dictionary).get(variant)
	if not variant_record is Dictionary:
		return false
	for node: Node in room.find_children("*", "MeshInstance3D", true, false):
		if surface_of(node) != surface:
			continue
		var mesh := node as MeshInstance3D
		var template := mesh.material_override as StandardMaterial3D
		if template == null:
			return false
		var material := _variant_material(template, variant_record)
		if material == null:
			return false
		mesh.material_override = material
	return true


static func _variant_material(template: StandardMaterial3D,
		entry: Dictionary) -> StandardMaterial3D:
	var material := template.duplicate() as StandardMaterial3D
	if material == null:
		return null
	if entry.has("texture"):
		var path := String(entry["texture"])
		var texture := _texture(path)
		if texture == null:
			return null
		material.albedo_texture = texture
		material.albedo_color = Color.WHITE
		material.set_meta("source_path", path)
		return material
	if entry.has("color"):
		var values: Array = entry["color"]
		material.albedo_texture = null
		material.albedo_color = Color(float(values[0]), float(values[1]), float(values[2]))
		material.set_meta("source_path", "")
		return material
	return null


static func _texture(path: String) -> Texture2D:
	if _textures.has(path):
		return _textures[path] as Texture2D
	var image := Image.load_from_file(ProjectSettings.globalize_path(path))
	if image == null:
		push_error("Missing surface variant texture: %s" % path)
		return null
	var texture := ImageTexture.create_from_image(image)
	_textures[path] = texture
	return texture


static func _update_floor_body(room: Node3D, variants: Dictionary, wear: int) -> void:
	var body := room.find_child("WalkableFloor", true, false) as StaticBody3D
	if body == null or not body.has_meta("surface_acoustic"):
		return
	body.set_meta("surface_wear", wear)
	body.set_meta("surface_variant", String(variants.get("floor", "clean")))


static func _registry(version: String) -> Dictionary:
	if _registries.has(version):
		return _registries[version] as Dictionary
	if not REGISTRY_PATHS.has(version):
		return {}
	var parsed: Variant = JSON.parse_string(
		FileAccess.get_file_as_string(String(REGISTRY_PATHS[version]))
	)
	if not parsed is Dictionary:
		return {}
	_registries[version] = parsed
	return parsed
