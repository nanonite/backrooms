extends "res://scripts/hunyuan_psx_round3.gd"

const BOX_VARIANTS := ["preserve_hunyuan", "four_sided_box"]
const VISUAL_BOX_MIN := Vector3(0.06, FLOOR_Y, 0.30)
const VISUAL_BOX_MAX := Vector3(0.78, CEILING_Y, 1.80)


func _ready() -> void:
	variant_id = _requested_variant()
	if not BOX_VARIANTS.has(variant_id):
		push_error("Unknown Hunyuan column-box variant: %s" % variant_id)
		get_tree().quit(2)
		return
	_set_design_contract()
	_build_environment()
	_build_materials()
	_build_visual_source()
	_build_authored_room()
	_build_player()


func _build_materials() -> void:
	var requested := variant_id
	if requested == "four_sided_box":
		variant_id = "column_face_extrusion"
	super._build_materials()
	variant_id = requested


func _build_authored_room() -> void:
	super._build_authored_room()
	if variant_id != "four_sided_box":
		return
	var cover := Node3D.new()
	cover.name = "FourSidedColumnBox"
	get_node("AuthoredBoundaries").add_child(cover)
	var center := (VISUAL_BOX_MIN + VISUAL_BOX_MAX) * 0.5
	var size := VISUAL_BOX_MAX - VISUAL_BOX_MIN
	var backing := MeshInstance3D.new()
	backing.name = "ClosedPrism"
	backing.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = _flat_patch_material()
	backing.mesh = mesh
	cover.add_child(backing)
	_add_prism_faces(cover, center, size)


func _add_prism_faces(parent: Node3D, center: Vector3, size: Vector3) -> void:
	var clearance := PATCH_CLEARANCE
	_add_source_face(parent, "EastSourceFace", center + Vector3(size.x * 0.5 + clearance, 0, 0),
		Vector2(size.z, size.y), PI * 0.5)
	_add_source_face(parent, "WestSourceFace", center - Vector3(size.x * 0.5 + clearance, 0, 0),
		Vector2(size.z, size.y), -PI * 0.5)
	_add_source_face(parent, "NorthSourceFace", center + Vector3(0, 0, size.z * 0.5 + clearance),
		Vector2(size.x, size.y), 0)
	_add_source_face(parent, "SouthSourceFace", center - Vector3(0, 0, size.z * 0.5 + clearance),
		Vector2(size.x, size.y), PI)


func _add_source_face(parent: Node3D, label: String, center: Vector3,
		size: Vector2, yaw: float) -> void:
	var face := MeshInstance3D.new()
	face.name = label
	face.position = center
	face.rotation.y = yaw
	var mesh := QuadMesh.new()
	mesh.size = size
	mesh.material = _materials.column
	face.mesh = mesh
	parent.add_child(face)
