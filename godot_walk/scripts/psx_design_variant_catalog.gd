extends RefCounted

const SCHEMA_VERSION := 1
const VARIANT_PATHS := {
	"v2_control": "res://design_variants/v2_control.json",
	"door_flush": "res://design_variants/door_flush.json",
	"door_removed": "res://design_variants/door_removed.json",
	"wall_endcap": "res://design_variants/wall_endcap.json",
	"north_wall_smooth": "res://design_variants/north_wall_smooth.json",
	"north_wall_source_texture": "res://design_variants/north_wall_source_texture.json",
	"clean_ceiling": "res://design_variants/clean_ceiling.json",
	"source_texture_cleanup": "res://design_variants/source_texture_cleanup.json",
	"source_floor_single_column": "res://design_variants/source_floor_single_column.json",
	"source_floor_ceiling_single_column": "res://design_variants/source_floor_ceiling_single_column.json",
}
const EXPECTED_PARENTS := {
	"v2_control": "corridor_psx_room_v2",
	"door_flush": "v2_control",
	"door_removed": "v2_control",
	"wall_endcap": "v2_control",
	"north_wall_smooth": "door_flush",
	"north_wall_source_texture": "north_wall_smooth",
	"clean_ceiling": "door_flush",
	"source_texture_cleanup": "door_flush",
	"source_floor_single_column": "door_flush",
	"source_floor_ceiling_single_column": "door_flush",
}
const EXPECTED_COLLISION_BOUNDS := {
	"west": -1.35,
	"east": 4.0,
	"south": -2.8,
	"north": 3.4,
	"wall_thickness": 0.16,
	"floor_y": -1.143,
	"ceiling_y": 1.8,
	"floor_west": 0.45,
	"floor_thickness": 0.12,
	"partition_x": 2.8,
	"portal_south": -0.2,
	"portal_north": 2.6,
}
const EXPECTED_MATERIAL_IDS := {
	"wall": "wallpaper_v2",
	"floor": "carpet_v2",
	"ceiling": "ceiling_v2",
	"wainscot": "olive_wainscot_v2",
	"trim": "walnut_trim_v2",
	"light": "warm_emissive_v2",
	"door": "service_green_v2",
	"hardware": "brass_v2",
}
const ALLOWED_DOOR_POLICIES := [
	"as_built", "flush_to_wall_face", "omit", "wall_endcap",
]
const ALLOWED_SURFACE_TREATMENTS := [
	"none", "north_wall_paneling", "north_wall_source_texture",
	"lowered_ceiling_grid", "source_texture_room_shell",
	"source_floor_single_column", "source_floor_ceiling_single_column",
]
const ALLOWED_COLUMN_FACE_TREATMENTS := ["preserve_native_splat", "source_video_wrap"]
const ALLOWED_JUNCTION_TREATMENTS := ["inherit_v2", "source_ceiling_perimeter_trim"]


static func variant_ids() -> PackedStringArray:
	return PackedStringArray(VARIANT_PATHS.keys())


static func load_variant(variant_id: String) -> Dictionary:
	if not VARIANT_PATHS.has(variant_id):
		push_error("Unknown PSX design variant: %s" % variant_id)
		return {}
	var path: String = VARIANT_PATHS[variant_id]
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("Cannot open PSX design variant %s: %s" % [variant_id, path])
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("PSX design variant is not a JSON object: %s" % path)
		return {}
	var spec: Dictionary = parsed
	var error := validate_variant(spec, variant_id)
	if not error.is_empty():
		push_error("Invalid PSX design variant %s: %s" % [variant_id, error])
		return {}
	return spec


static func validate_variant(spec: Dictionary, expected_id: String) -> String:
	if int(spec.get("schema_version", -1)) != SCHEMA_VERSION:
		return "unsupported schema_version"
	if not _valid_identity(spec, expected_id):
		return "identity, parent, or source_type does not match the catalog"
	var design: Variant = spec.get("design", null)
	if typeof(design) != TYPE_DICTIONARY:
		return "design must be an object"
	var design_error := _validate_design(design)
	if not design_error.is_empty():
		return design_error
	return ""


static func _valid_identity(spec: Dictionary, expected_id: String) -> bool:
	if not EXPECTED_PARENTS.has(expected_id):
		return false
	return (
		str(spec.get("candidate_id", "")) == expected_id
		and str(spec.get("parent_candidate_id", "")) == EXPECTED_PARENTS[expected_id]
		and str(spec.get("source_type", "")) == "gaussian_splat"
		and not str(spec.get("change_summary", "")).strip_edges().is_empty()
		and not str(spec.get("hypothesis", "")).strip_edges().is_empty()
	)


static func _validate_design(design: Dictionary) -> String:
	if str(design.get("layout", "")) != "room_v2":
		return "layout must inherit room_v2"
	if str(design.get("transition", "")) != "framed_portal_v2":
		return "transition must inherit framed_portal_v2"
	if not ALLOWED_DOOR_POLICIES.has(str(design.get("doorway_policy", ""))):
		return "doorway_policy is outside the supported enum"
	if not ALLOWED_COLUMN_FACE_TREATMENTS.has(str(design.get("column_face_treatment", ""))):
		return "column_face_treatment is outside the supported enum"
	if not ALLOWED_JUNCTION_TREATMENTS.has(str(design.get("junction_treatment", ""))):
		return "junction_treatment is outside the supported enum"
	if not _matches_material_ids(design.get("materials", null)):
		return "material IDs must remain on the v2 palette"
	if not ALLOWED_SURFACE_TREATMENTS.has(str(design.get("surface_treatment", "none"))):
		return "surface_treatment is outside the supported enum"
	return _validate_collision(design.get("collision", null))


static func _validate_collision(value: Variant) -> String:
	if typeof(value) != TYPE_DICTIONARY:
		return "collision must be an object"
	var collision: Dictionary = value
	if str(collision.get("policy", "")) != "inherit_v2_locked":
		return "collision policy must inherit locked v2 extents"
	var bounds: Variant = collision.get("bounds_m", null)
	if typeof(bounds) != TYPE_DICTIONARY:
		return "collision.bounds_m must be an object"
	for key: String in EXPECTED_COLLISION_BOUNDS:
		if not _same_number(bounds, key, EXPECTED_COLLISION_BOUNDS[key]):
			return "collision bound %s differs from the v2 contract" % key
	return ""


static func _same_number(values: Dictionary, key: String, expected: float) -> bool:
	var value: Variant = values.get(key, null)
	if typeof(value) != TYPE_FLOAT and typeof(value) != TYPE_INT:
		return false
	return is_equal_approx(float(value), expected)


static func _matches_material_ids(value: Variant) -> bool:
	if typeof(value) != TYPE_DICTIONARY:
		return false
	var materials: Dictionary = value
	if materials.size() != EXPECTED_MATERIAL_IDS.size():
		return false
	for key: String in EXPECTED_MATERIAL_IDS:
		if str(materials.get(key, "")) != EXPECTED_MATERIAL_IDS[key]:
			return false
	return true
