extends Node3D

const WEST := -1.3
const EAST := 6.0
const SOUTH := -3.0
const NORTH := 3.4
const BOTTOM := -1.7
const TOP := 1.8
const THICKNESS := 0.16
const PARTITION_HEIGHT := 0.85
const PARTITION_Y := -1.14 + PARTITION_HEIGHT / 2.0

var wallpaper: StandardMaterial3D
var carpet: StandardMaterial3D
var ceiling: StandardMaterial3D
var walnut: StandardMaterial3D
var door_paint: StandardMaterial3D
var door_inset: StandardMaterial3D
var brass: StandardMaterial3D


func _ready() -> void:
	wallpaper = _textured_material("wallpaper.png", Vector3(3.0, 1.8, 1.0))
	carpet = _textured_material("carpet.png", Vector3(5.0, 5.0, 1.0))
	ceiling = _textured_material("ceiling.png", Vector3(4.0, 4.0, 1.0))
	walnut = _solid_material(Color(0.30, 0.205, 0.105))
	door_paint = _solid_material(Color(0.25, 0.34, 0.25))
	door_inset = _solid_material(Color(0.32, 0.40, 0.29))
	brass = _solid_material(Color(0.53, 0.39, 0.14), 0.35)
	_build_shell()
	_build_trim()
	_build_half_walls()
	_build_sealed_door()


func _build_shell() -> void:
	var width := EAST - WEST
	var length := NORTH - SOUTH
	var height := TOP - BOTTOM
	var middle := Vector3((WEST + EAST) * 0.5, (BOTTOM + TOP) * 0.5, (SOUTH + NORTH) * 0.5)
	_add_panel("WestWall", Vector3(WEST, middle.y, middle.z), Vector3(THICKNESS, height, length), wallpaper, true)
	_add_panel("NorthWall", Vector3(middle.x, middle.y, NORTH), Vector3(width, height, THICKNESS), wallpaper, true)
	_add_panel("EastBackstop", Vector3(EAST, middle.y, middle.z), Vector3(THICKNESS, height, length), wallpaper, true)
	_add_panel("SouthBackstop", Vector3(middle.x, middle.y, SOUTH), Vector3(width, height, THICKNESS), wallpaper, true)
	_add_panel("CarpetBackstop", Vector3(middle.x, BOTTOM, middle.z), Vector3(width, THICKNESS, length), carpet, false)
	_add_panel("CeilingBackstop", Vector3(middle.x, TOP, middle.z), Vector3(width, THICKNESS, length), ceiling, false)


func _build_trim() -> void:
	for wall in ["West", "North", "East", "South"]:
		_add_wall_trim(wall, -1.03, 0.18, walnut)
		_add_wall_trim(wall, -0.60, 0.055, walnut)
		_add_wall_trim(wall, 1.52, 0.10, walnut)


func _add_wall_trim(wall: String, y: float, height: float, material: Material) -> void:
	var centre: Vector3
	var size: Vector3
	if wall == "West":
		centre = Vector3(WEST + 0.105, y, (SOUTH + NORTH) * 0.5)
		size = Vector3(0.05, height, NORTH - SOUTH)
	elif wall == "North":
		centre = Vector3((WEST + EAST) * 0.5, y, NORTH - 0.105)
		size = Vector3(EAST - WEST, height, 0.05)
	elif wall == "East":
		centre = Vector3(EAST - 0.105, y, (SOUTH + NORTH) * 0.5)
		size = Vector3(0.05, height, NORTH - SOUTH)
	else:
		centre = Vector3((WEST + EAST) * 0.5, y, SOUTH + 0.105)
		size = Vector3(EAST - WEST, height, 0.05)
	_add_box("%sTrim_%s" % [wall, str(y)], centre, size, material)


func _build_half_walls() -> void:
	_add_half_wall("EastPartition", Vector3(1.25, PARTITION_Y, 2.325), Vector3(THICKNESS, PARTITION_HEIGHT, 2.15))
	_add_half_wall("SouthPartition", Vector3(-0.025, PARTITION_Y, 1.25), Vector3(2.55, PARTITION_HEIGHT, THICKNESS))
	_add_half_wall("ColumnGuard", Vector3(-0.75, PARTITION_Y, 1.8), Vector3(1.1, PARTITION_HEIGHT, THICKNESS))
	_add_half_wall("ColumnGuardSide", Vector3(-0.2, PARTITION_Y, 1.525), Vector3(THICKNESS, PARTITION_HEIGHT, 0.55))


func _add_half_wall(label: String, centre: Vector3, size: Vector3) -> void:
	_add_panel(label, centre, size, wallpaper, true)
	var cap_size := size + Vector3(0.14, 0.065, 0.14)
	cap_size.y = 0.065
	_add_box("%sWoodCap" % label, centre + Vector3.UP * (size.y * 0.5 + 0.0325), cap_size, walnut)


func _build_sealed_door() -> void:
	var centre := Vector3(2.5, -0.07, NORTH - 0.14)
	_add_box("SealedDoor", centre, Vector3(0.88, 2.12, 0.07), door_paint)
	for side in [-1.0, 1.0]:
		_add_box("DoorJamb_%s" % str(side), centre + Vector3(side * 0.51, 0.0, -0.025), Vector3(0.12, 2.28, 0.11), walnut)
	_add_box("DoorHeader", centre + Vector3(0.0, 1.19, -0.025), Vector3(1.14, 0.12, 0.11), walnut)
	for y in [-0.65, 0.23]:
		_add_box("DoorInset_%s" % str(y), centre + Vector3(0.0, y, -0.041), Vector3(0.54, 0.55, 0.018), door_inset)
	_add_door_knob(centre + Vector3(0.31, -0.10, -0.075))


func _add_door_knob(position: Vector3) -> void:
	var knob := MeshInstance3D.new()
	knob.name = "DoorKnob"
	var sphere := SphereMesh.new()
	sphere.radius = 0.045
	sphere.height = 0.09
	knob.mesh = sphere
	knob.position = position
	knob.material_override = brass
	add_child(knob)


func _add_panel(label: String, centre: Vector3, size: Vector3, material: Material, solid: bool) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = centre
	add_child(body)
	var box := BoxMesh.new()
	box.size = size
	var mesh := MeshInstance3D.new()
	mesh.mesh = box
	mesh.material_override = material
	body.add_child(mesh)
	if solid:
		var collision := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = size
		collision.shape = shape
		body.add_child(collision)


func _add_box(label: String, centre: Vector3, size: Vector3, material: Material) -> void:
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh.name = label
	mesh.mesh = box
	mesh.position = centre
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


func _solid_material(color: Color, metallic: float = 0.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	material.metallic = metallic
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material
