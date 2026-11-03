class_name ShapeRoomMaterials
extends RefCounted

## PSX materials for shape rooms (room_catalog/MATERIAL_LANGUAGE.md): nearest-filtered, unshaded.
## A spec with `materials.palette_id` (shape-room-0.5.0, #192) names each of wall, floor and ceiling as a
## texture (+ tile_m) or a solid colour; an older spec gets the kit default (olive trim, warm pale lamps).

const DARK_PANEL := Color(0.03, 0.03, 0.03)
const WALL_TILE_M := 1.5
const FLOOR_TILE_M := 4.0
const CEILING_TILE_M := 4.0


static func make(spec: Dictionary) -> Dictionary:
	var source: Dictionary = spec.materials
	var tiles := {"wallpaper": WALL_TILE_M, "floor": FLOOR_TILE_M, "ceiling": CEILING_TILE_M}
	var materials := {
		"trim": _solid(_color(source.trim_color)),
		"lamp": _solid(_color(source.lamp_color)),
		"dark": _solid(DARK_PANEL),
		"_scaled": {},
		"_tiles": tiles,
		"_palette_id": String(source.get("palette_id", "")),
	}
	if source.has("palette_id"):
		for pair: Array in [["wallpaper", "wall"], ["floor", "floor"], ["ceiling", "ceiling"]]:
			var surface: Dictionary = source[pair[1]]
			materials[pair[0]] = _surface(surface)
			tiles[pair[0]] = float(surface.get("tile_m", tiles[pair[0]]))
	else:
		materials["wallpaper"] = _textured(String(source.wallpaper_texture))
		materials["floor"] = _textured(String(source.floor_texture))
		materials["ceiling"] = _textured(String(source.ceiling_texture))
	return materials


static func scaled(materials: Dictionary, key: String, size_u: float, size_v: float) -> Material:
	var tile := tile_m(materials, key)
	var cache: Dictionary = materials["_scaled"]
	var cache_key := "%s_%.3f_%.3f" % [key, size_u / tile, size_v / tile]
	if not cache.has(cache_key):
		var material := _copy(materials[key])
		material.uv1_scale = Vector3(size_u / tile, size_v / tile, 1.0)
		cache[cache_key] = material
	return cache[cache_key]


## Unscaled-UV material for a mesh whose UVs are already metres / tile (polygon floors and ceilings,
## #190), double-sided so a triangle wound the wrong way still shows. Same texel density as `scaled`.
static func planar(materials: Dictionary, key: String) -> Material:
	var cache: Dictionary = materials["_scaled"]
	var cache_key := "%s_planar" % key
	if not cache.has(cache_key):
		var material := _copy(materials[key])
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		cache[cache_key] = material
	return cache[cache_key]


static func tile_m(materials: Dictionary, key: String) -> float:
	return float(materials["_tiles"][key])


## A texture's resource path, or "" for a solid colour: the headless palette check reads it back.
static func source_path(material: Material) -> String:
	return String(material.get_meta("source_path", ""))


static func _copy(base: StandardMaterial3D) -> StandardMaterial3D:
	var material := base.duplicate() as StandardMaterial3D
	if base.has_meta("source_path"):
		material.set_meta("source_path", base.get_meta("source_path"))
	return material


static func _surface(surface: Dictionary) -> StandardMaterial3D:
	if surface.has("texture"):
		return _textured(String(surface.texture))
	return _solid(_color(surface.color))


static func _color(values: Array) -> Color:
	return Color(float(values[0]), float(values[1]), float(values[2]))


static func _textured(path: String) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	var image := Image.load_from_file(ProjectSettings.globalize_path(path))
	if image == null:
		push_error("Missing kit texture: %s" % path)
		return material
	material.albedo_texture = ImageTexture.create_from_image(image)
	material.set_meta("source_path", path)
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.roughness = 1.0
	return material


static func _solid(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	return material
