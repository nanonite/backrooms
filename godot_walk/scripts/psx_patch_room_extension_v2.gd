extends Node3D

const WEST := -1.35
const EAST := 4.0
const SOUTH := -2.8
const NORTH := 3.4
const FLOOR_Y := -1.143
const CEILING_Y := 1.8
const WALL_THICKNESS := 0.16
const PATCH_PARTITION_X := 2.8
const PORTAL_SOUTH := -0.2
const PORTAL_NORTH := 2.6
const FLOOR_COLLISION_WEST := 0.45
const FLOOR_THICKNESS := 0.12

var wallpaper: StandardMaterial3D
var carpet: StandardMaterial3D
var ceiling: StandardMaterial3D
var wainscot: StandardMaterial3D
var walnut: StandardMaterial3D
var light_panel: StandardMaterial3D
var service_door: StandardMaterial3D
var brass: StandardMaterial3D


func _ready() -> void:
	_configure_walk_test()
	_create_materials()
	_build_shell()
	_build_extension_floor()
	_build_transition()
	_build_room_details()


func _configure_walk_test() -> void:
	var root := get_parent()
	root.set_meta("walk_route", PackedVector2Array([
		Vector2(-0.65, 2.9), Vector2(0.5, 2.9), Vector2(0.5, 1.7),
		Vector2(1.25, 1.7), Vector2(2.6, 1.7), Vector2(2.6, 0.2),
		Vector2(3.5, 0.2),
	]))
	root.set_meta("walk_envelope", Rect2(WEST, SOUTH, EAST - WEST, NORTH - SOUTH))
	root.set_meta("walk_floor_y", FLOOR_Y)
	root.set_meta("boundary_probe_origin", Vector3(3.5, -0.543, 0.2))
	root.set_meta("walk_floor_bodies", PackedStringArray([
		"GeneratedCollision", "AuthoredFloorExtension",
	]))
	root.set_meta("boundary_test_path", "AuthoredBoundaries/EastBoundary")


func _create_materials() -> void:
	wallpaper = _textured_material("wallpaper.png", Vector3(3.0, 1.8, 1.0))
	carpet = _textured_material("carpet.png", Vector3(4.0, 4.0, 1.0))
	ceiling = _textured_material("ceiling.png", Vector3(4.0, 4.0, 1.0))
	wainscot = _solid_material(Color(0.24, 0.32, 0.23))
	walnut = _solid_material(Color(0.31, 0.22, 0.12))
	light_panel = _solid_material(Color(0.82, 0.78, 0.57), true)
	service_door = _solid_material(Color(0.22, 0.3, 0.21))
	brass = _solid_material(Color(0.48, 0.38, 0.16))


func _build_shell() -> void:
	var wall_height := CEILING_Y - FLOOR_Y
	var middle_y := (CEILING_Y + FLOOR_Y) * 0.5
	_add_wall("WestBoundary", Vector3(WEST, middle_y, (SOUTH + NORTH) * 0.5),
		Vector3(WALL_THICKNESS, wall_height, NORTH - SOUTH))
	_add_wall("EastBoundary", Vector3(EAST, middle_y, (SOUTH + NORTH) * 0.5),
		Vector3(WALL_THICKNESS, wall_height, NORTH - SOUTH))
	_add_wall("NorthBoundary", Vector3((WEST + EAST) * 0.5, middle_y, NORTH),
		Vector3(EAST - WEST, wall_height, WALL_THICKNESS))
	_add_wall("SouthBoundary", Vector3((WEST + EAST) * 0.5, middle_y, SOUTH),
		Vector3(EAST - WEST, wall_height, WALL_THICKNESS))
	_add_visual_box("CeilingBackstop", Vector3((WEST + EAST) * 0.5, CEILING_Y + 0.035,
		(SOUTH + NORTH) * 0.5), Vector3(EAST - WEST, 0.07, NORTH - SOUTH), ceiling)


func _build_extension_floor() -> void:
	var collision_width := EAST - FLOOR_COLLISION_WEST
	var collision_size := Vector3(collision_width, FLOOR_THICKNESS, NORTH - SOUTH)
	var centre := Vector3((FLOOR_COLLISION_WEST + EAST) * 0.5,
		FLOOR_Y - FLOOR_THICKNESS * 0.5, (SOUTH + NORTH) * 0.5)
	var body := StaticBody3D.new()
	body.name = "AuthoredFloorExtension"
	body.position = centre
	add_child(body)
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(EAST - PATCH_PARTITION_X, FLOOR_THICKNESS, NORTH - SOUTH)
	mesh.mesh = box
	mesh.position.x = (PATCH_PARTITION_X + EAST) * 0.5 - centre.x
	mesh.material_override = carpet
	body.add_child(mesh)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = collision_size
	collision.shape = shape
	body.add_child(collision)
	_add_visual_box("PatchThreshold", Vector3(PATCH_PARTITION_X, FLOOR_Y + 0.012,
		(PORTAL_SOUTH + PORTAL_NORTH) * 0.5),
		Vector3(0.09, 0.018, PORTAL_NORTH - PORTAL_SOUTH - 0.12), walnut)


func _build_transition() -> void:
	var wall_height := CEILING_Y - FLOOR_Y
	var middle_y := (FLOOR_Y + CEILING_Y) * 0.5
	var south_depth := PORTAL_SOUTH - SOUTH
	var north_depth := NORTH - PORTAL_NORTH
	_add_wall("PatchPartitionSouth", Vector3(PATCH_PARTITION_X, middle_y,
		(SOUTH + PORTAL_SOUTH) * 0.5), Vector3(WALL_THICKNESS, wall_height, south_depth))
	_add_wall("PatchPartitionNorth", Vector3(PATCH_PARTITION_X, middle_y,
		(PORTAL_NORTH + NORTH) * 0.5), Vector3(WALL_THICKNESS, wall_height, north_depth))
	for index in range(2):
		var z := PORTAL_SOUTH if index == 0 else PORTAL_NORTH
		_add_wall("PatchPortalJamb%d" % index, Vector3(PATCH_PARTITION_X, middle_y, z),
			Vector3(WALL_THICKNESS, wall_height, 0.16), walnut)
	_add_wall("PatchPortalLintel", Vector3(PATCH_PARTITION_X, CEILING_Y - 0.12,
		(PORTAL_SOUTH + PORTAL_NORTH) * 0.5),
		Vector3(WALL_THICKNESS, 0.24, PORTAL_NORTH - PORTAL_SOUTH), walnut)


func _build_room_details() -> void:
	var wall_height := CEILING_Y - FLOOR_Y
	var middle_y := (CEILING_Y + FLOOR_Y) * 0.5
	_add_wainscot("West", Vector3(WEST + 0.105, middle_y, (SOUTH + NORTH) * 0.5),
		Vector3(0.05, wall_height, NORTH - SOUTH))
	_add_wainscot("East", Vector3(EAST - 0.105, middle_y, (SOUTH + NORTH) * 0.5),
		Vector3(0.05, wall_height, NORTH - SOUTH))
	_add_wainscot("South", Vector3((WEST + EAST) * 0.5, middle_y, SOUTH + 0.105),
		Vector3(EAST - WEST, wall_height, 0.05))
	_add_wainscot("North", Vector3((WEST + EAST) * 0.5, middle_y, NORTH - 0.105),
		Vector3(EAST - WEST, wall_height, 0.05))
	for index in range(2):
		var x := 2.1 + float(index) * 1.35
		_add_visual_box("CeilingLight%d" % index, Vector3(x, CEILING_Y - 0.055, 0.62),
			Vector3(0.78, 0.025, 0.28), light_panel)
	_build_east_end_door()


func _build_east_end_door() -> void:
	var door_z := 0.2
	var wall_face_x := EAST - WALL_THICKNESS * 0.5
	var frame_x := wall_face_x - 0.02
	var door_x := frame_x - 0.025
	var door_centre_y := FLOOR_Y + 1.1
	_add_visual_box("EastServiceDoorFrame",
		Vector3(frame_x, door_centre_y, door_z), Vector3(0.04, 1.0, 0.72), walnut)
	_add_visual_box("EastServiceDoor",
		Vector3(door_x, door_centre_y, door_z), Vector3(0.025, 0.82, 0.52), service_door)
	var detail_x := door_x - 0.017
	for panel_y in [door_centre_y - 0.2, door_centre_y + 0.2]:
		_add_service_door_panel(panel_y, detail_x, door_z)
	_add_visual_box("EastDoorHandlePlate", Vector3(detail_x, door_centre_y,
		door_z - 0.19), Vector3(0.018, 0.1, 0.06), brass)
	_add_visual_box("EastDoorHandle", Vector3(detail_x - 0.012, door_centre_y,
		door_z - 0.17), Vector3(0.025, 0.035, 0.08), walnut)


func _add_service_door_panel(panel_y: float, detail_x: float, door_z: float) -> void:
	var panel_id := int(panel_y * 100.0)
	_add_visual_box("EastDoorPanelTop%d" % panel_id,
		Vector3(detail_x, panel_y + 0.08, door_z), Vector3(0.012, 0.016, 0.38), walnut)
	_add_visual_box("EastDoorPanelBottom%d" % panel_id,
		Vector3(detail_x, panel_y - 0.08, door_z), Vector3(0.012, 0.016, 0.38), walnut)
	for side in [-1.0, 1.0]:
		_add_visual_box("EastDoorPanelSide%d_%d" % [panel_id, int(side)],
			Vector3(detail_x, panel_y, door_z + side * 0.215),
			Vector3(0.012, 0.16, 0.018), walnut)


func _add_wainscot(label: String, centre: Vector3, wall_size: Vector3) -> void:
	var height := 0.62
	var size := wall_size
	size.y = height
	var panel_centre := centre
	panel_centre.y = FLOOR_Y + height * 0.5
	_add_visual_box("%sWainscot" % label, panel_centre, size, wainscot)
	var rail_size := size
	rail_size.y = 0.045
	_add_visual_box("%sRail" % label, panel_centre + Vector3.UP * (height * 0.5),
		rail_size, walnut)


func _add_wall(label: String, centre: Vector3, size: Vector3,
		material: Material = null) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = centre
	add_child(body)
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.material_override = wallpaper if material == null else material
	body.add_child(mesh)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)


func _add_visual_box(label: String, centre: Vector3, size: Vector3,
		material: Material) -> void:
	var mesh := MeshInstance3D.new()
	mesh.name = label
	mesh.position = centre
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.material_override = material
	add_child(mesh)


func _textured_material(filename: String, uv_scale: Vector3) -> StandardMaterial3D:
	var texture := load("res://assets/psx_extension/textures/%s" % filename) as Texture2D
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.roughness = 1.0
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.uv1_scale = uv_scale
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _solid_material(color: Color, emissive: bool = false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	if emissive:
		material.emission_enabled = true
		material.emission = color
	return material
