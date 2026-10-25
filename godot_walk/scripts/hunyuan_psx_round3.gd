extends "res://scripts/hunyuan_psx_round1.gd"
class_name HunyuanPsxRound3

const ROUND_VARIANTS := ["preserve_hunyuan", "column_face_extrusion"]
const COLUMN_FACE_TEXTURE := "res://assets/psx_extension/textures/hunyuan_round3_column_front.png"
const COLUMN_FACE_WIDTH := 1.50
const PATCH_DEPTH := 0.025
const PATCH_CLEARANCE := 0.006
const VISUAL_COLUMN_Z_OFFSET := 0.62


func _ready() -> void:
	variant_id = _requested_variant()
	if not ROUND_VARIANTS.has(variant_id):
		push_error("Unknown Hunyuan round 3 variant: %s" % variant_id)
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
	if variant_id != "column_face_extrusion":
		return
	var image := Image.load_from_file(ProjectSettings.globalize_path(COLUMN_FACE_TEXTURE))
	if image == null or image.is_empty():
		set_meta("column_face_texture_loaded", false)
		push_error("Missing direct frame-0152 column-face crop: %s" % COLUMN_FACE_TEXTURE)
		return
	var texture := ImageTexture.create_from_image(image)
	var material := StandardMaterial3D.new()
	material.resource_name = "source_frame_0152_full_column_face"
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 1.0
	material.uv1_scale = Vector3.ONE
	_materials.column = material
	set_meta("column_face_texture_loaded", true)


func _build_authored_room() -> void:
	super._build_authored_room()
	if variant_id != "column_face_extrusion":
		return
	_add_column_face_extrusion()


func _add_column_face_extrusion() -> void:
	var parent := get_node_or_null("AuthoredBoundaries") as Node3D
	if parent == null:
		push_error("Column face variant has no authored boundary parent")
		return
	var east_face_x := COLUMN_CENTER.x + COLUMN_SIZE.x * 0.5
	var patch_center := Vector3(
		east_face_x + PATCH_DEPTH * 0.5,
		FLOOR_Y + COLUMN_SIZE.y * 0.5,
		COLUMN_CENTER.z + VISUAL_COLUMN_Z_OFFSET
	)
	var slab := MeshInstance3D.new()
	slab.name = "ColumnFaceExtrusionDepth"
	slab.position = patch_center
	var slab_mesh := BoxMesh.new()
	slab_mesh.size = Vector3(PATCH_DEPTH, COLUMN_SIZE.y, COLUMN_FACE_WIDTH)
	slab_mesh.material = _flat_patch_material()
	slab.mesh = slab_mesh
	parent.add_child(slab)
	var face := MeshInstance3D.new()
	face.name = "ColumnFaceFrame0152"
	face.position = patch_center + Vector3(PATCH_DEPTH * 0.5 + PATCH_CLEARANCE, 0.0, 0.0)
	var face_mesh := QuadMesh.new()
	face_mesh.size = Vector2(COLUMN_FACE_WIDTH, COLUMN_SIZE.y)
	face_mesh.material = _materials.column
	face.mesh = face_mesh
	face.rotation.y = PI * 0.5
	parent.add_child(face)


func _flat_patch_material() -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.resource_name = "column_face_extrusion_edge_fill"
	material.albedo_color = Color(0.72, 0.68, 0.49)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material
