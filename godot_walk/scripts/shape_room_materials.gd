class_name ShapeRoomMaterials
extends RefCounted

## Kit-default PSX materials for shape rooms (room_catalog/MATERIAL_LANGUAGE.md):
## nearest-filtered, unshaded, olive trim and warm pale lamps.

const DARK_PANEL := Color(0.03, 0.03, 0.03)
const WALL_TILE_M := 1.5
const FLOOR_TILE_M := 4.0
const CEILING_TILE_M := 4.0


static func make(spec: Dictionary) -> Dictionary:
	var source: Dictionary = spec.materials
	return {
		"wallpaper": _textured(String(source.wallpaper_texture)),
		"floor": _textured(String(source.floor_texture)),
		"ceiling": _textured(String(source.ceiling_texture)),
		"trim": _solid(_color(source.trim_color)),
		"lamp": _solid(_color(source.lamp_color)),
		"dark": _solid(DARK_PANEL),
		"_scaled": {},
	}


static func scaled(materials: Dictionary, key: String, size_u: float, size_v: float) -> Material:
	var tile := WALL_TILE_M if key == "wallpaper" else FLOOR_TILE_M
	var cache: Dictionary = materials["_scaled"]
	var cache_key := "%s_%.3f_%.3f" % [key, size_u / tile, size_v / tile]
	if not cache.has(cache_key):
		var material := (materials[key] as StandardMaterial3D).duplicate() as StandardMaterial3D
		material.uv1_scale = Vector3(size_u / tile, size_v / tile, 1.0)
		cache[cache_key] = material
	return cache[cache_key]


## Unscaled-UV material for a mesh whose UVs are already metres / tile (polygon floors and ceilings,
## #190), double-sided so a triangle wound the wrong way still shows. Same texel density as `scaled`.
static func planar(materials: Dictionary, key: String) -> Material:
	var cache: Dictionary = materials["_scaled"]
	var cache_key := "%s_planar" % key
	if not cache.has(cache_key):
		var material := (materials[key] as StandardMaterial3D).duplicate() as StandardMaterial3D
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		cache[cache_key] = material
	return cache[cache_key]


static func tile_m(key: String) -> float:
	return WALL_TILE_M if key == "wallpaper" else (CEILING_TILE_M if key == "ceiling" else FLOOR_TILE_M)


static func _color(values: Array) -> Color:
	return Color(float(values[0]), float(values[1]), float(values[2]))


static func _textured(path: String) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	var image := Image.load_from_file(ProjectSettings.globalize_path(path))
	if image == null:
		push_error("Missing kit texture: %s" % path)
		return material
	material.albedo_texture = ImageTexture.create_from_image(image)
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
