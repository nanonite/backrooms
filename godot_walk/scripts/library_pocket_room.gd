extends "res://scripts/hunyuan_psx_round1.gd"

const LIBRARY_PRESET := preload("res://scripts/library_psx_preset.gd")
const POCKET_ROOT := "res://evidence/2026-10-21-issue-148/early-pocket/generated/"


func _ready() -> void:
	_set_design_contract()
	_build_environment()
	_build_materials()
	_build_visual_source()
	_build_authored_room()
	_build_player()
	LIBRARY_PRESET.new().configure(self)
	set_meta("room_id", "godot_authored_early_pocket_v1")


func _build_materials() -> void:
	super._build_materials()
	for material: StandardMaterial3D in _materials.values():
		material.cull_mode = BaseMaterial3D.CULL_DISABLED


func _set_design_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("walk_route", PackedVector2Array([
		Vector2(0.8, 0.8), Vector2(5.2, 0.8),
		Vector2(5.2, 6.9), Vector2(5.2, 13.0),
		Vector2(0.8, 13.0), Vector2(0.8, 6.9)]))
	set_meta("walk_envelope", Rect2(0, 0, 6.0, 13.8))
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["AuthoredPlanarRouteFloor"]))
	set_meta("boundary_probe_origin", Vector3(3, FLOOR_Y + 0.6, 6.9))
	set_meta("boundary_test_path", "AuthoredBoundaries/authored_room_boundary_east")


func _build_visual_source() -> void:
	var visual := _load_original_glb("early_pocket_visual.glb")
	if visual == null:
		push_error("Missing protected early-pocket visual GLB")
		get_tree().quit(2)
		return
	visual.name = "AuthoredPocketVisual"
	add_child(visual)
	for instance in visual.find_children("*", "MeshInstance3D", true, false):
		var center_y: float = instance.mesh.get_aabb().get_center().y
		instance.mesh = _textured_plane(instance.mesh)
		instance.material_override = _materials.floor if center_y < 0 else _materials.ceiling
	_add_report_visuals()


func _add_report_visuals() -> void:
	var report_path := POCKET_ROOT + "early_pocket_scene_report.json"
	var report: Variant = JSON.parse_string(FileAccess.get_file_as_string(report_path))
	if not report is Dictionary:
		push_error("Invalid early-pocket authored surface report")
		get_tree().quit(2)
		return
	var trim := _solid_material(Color(0.37, 0.34, 0.23))
	var lamp := _solid_material(Color(1.0, 0.97, 0.76))
	for surface: Dictionary in report.visual.authored_visual_surfaces:
		var label: String = surface.name
		if label.contains("wallpaper") or label in ["authored_carpet_visual", "authored_ceiling_visual"]:
			continue
		var material: Material = _materials.wall
		if label.contains("grid"):
			material = trim
		elif label.contains("light"):
			material = lamp
		_add_box(label + "Visual", _vector(surface.center_world_m),
			_vector(surface.size_m), material, self, true, false)


func _build_authored_room() -> void:
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)
	var source := _load_original_glb("early_pocket_collision.glb")
	if source == null:
		push_error("Missing protected early-pocket collision GLB")
		get_tree().quit(2)
		return
	add_child(source)
	for instance in source.find_children("*", "MeshInstance3D", true, false):
		_add_imported_collision(instance, boundaries)
	source.free()


func _add_imported_collision(instance: MeshInstance3D, parent: Node3D) -> void:
	var body := StaticBody3D.new()
	body.name = instance.name
	parent.add_child(body)
	body.global_transform = instance.global_transform
	var collision := CollisionShape3D.new()
	collision.name = "CollisionShape3D"
	var shape := instance.mesh.create_trimesh_shape()
	if shape == null:
		push_error("Cannot create original collision triangles for %s" % instance.name)
		get_tree().quit(2)
		return
	shape.backface_collision = true
	collision.shape = shape
	body.add_child(collision)


func _build_player() -> void:
	var player := PLAYER_SCENE.instantiate()
	player.name = "Player"
	player.position = Vector3(0.8, FLOOR_Y + 0.6, 0.8)
	add_child(player)


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _vector(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])


func _load_original_glb(filename: String) -> Node3D:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(POCKET_ROOT + filename, state) != OK:
		return null
	return document.generate_scene(state) as Node3D


func _textured_plane(source: ArrayMesh) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	for surface in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var coordinates := PackedVector2Array()
		for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
			coordinates.append(Vector2(vertex.x, vertex.z) * 0.25)
		arrays[Mesh.ARRAY_TEX_UV] = coordinates
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
