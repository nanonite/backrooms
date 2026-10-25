extends "res://scripts/hunyuan_psx_round1.gd"
class_name HunyuanPsxRound2

const ROUND_VARIANTS := ["preserve_hunyuan", "column_box_source_face"]
const COLUMN_FACE_TEXTURE := "res://assets/psx_extension/textures/column_face_frame_0152.png"


func _ready() -> void:
	variant_id = _requested_variant()
	if not ROUND_VARIANTS.has(variant_id):
		push_error("Unknown Hunyuan round 2 variant: %s" % variant_id)
		get_tree().quit(2)
		return
	_set_design_contract()
	_build_environment()
	_build_materials()
	_build_visual_source()
	_build_authored_room()
	_build_player()


func _build_materials() -> void:
	super._build_materials()
	if variant_id != "column_box_source_face":
		return
	var texture := load(COLUMN_FACE_TEXTURE) as Texture2D
	if texture == null:
		push_error("Missing frame-0152 column face crop: %s" % COLUMN_FACE_TEXTURE)
		return
	var material := StandardMaterial3D.new()
	material.resource_name = "column_face_frame_0152"
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.roughness = 1.0
	material.uv1_scale = Vector3.ONE
	_materials.column = material


func _build_authored_room() -> void:
	super._build_authored_room()
	if variant_id != "column_box_source_face":
		return
	var boundaries := get_node_or_null("AuthoredBoundaries") as Node3D
	if boundaries == null:
		push_error("Column box variant has no authored boundary parent")
		return
	_add_box("ColumnBoxSourceFace", COLUMN_CENTER, COLUMN_SIZE,
		_materials.column, boundaries, true, false)
