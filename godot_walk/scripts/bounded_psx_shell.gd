extends Node3D

const WALL_SHADER := preload("res://scripts/psx/bounded_wall.gdshader")
const WEST := -1.3
const EAST := 6.0
const SOUTH := -3.0
const NORTH := 3.4
const BOTTOM := -1.7
const TOP := 1.8
const THICKNESS := 0.16
const PARTITION_HEIGHT := 0.85
const PARTITION_Y := -1.14 + PARTITION_HEIGHT / 2.0


func _ready() -> void:
	var width := EAST - WEST
	var length := NORTH - SOUTH
	var height := TOP - BOTTOM
	var middle := Vector3((WEST + EAST) / 2.0, (BOTTOM + TOP) / 2.0, (SOUTH + NORTH) / 2.0)
	_add_panel("West", Vector3(WEST, middle.y, middle.z), Vector3(THICKNESS, height, length), 0, true)
	_add_panel("North", Vector3(middle.x, middle.y, NORTH), Vector3(width, height, THICKNESS), 0, true)
	_add_panel("East", Vector3(EAST, middle.y, middle.z), Vector3(THICKNESS, height, length), 0, true)
	_add_panel("South", Vector3(middle.x, middle.y, SOUTH), Vector3(width, height, THICKNESS), 0, true)
	_add_panel("FloorBackstop", Vector3(middle.x, BOTTOM, middle.z), Vector3(width, THICKNESS, length), 1, false)
	_add_panel("CeilingBackstop", Vector3(middle.x, TOP, middle.z), Vector3(width, THICKNESS, length), 2, false)
	_add_panel("EastPartition", Vector3(1.25, PARTITION_Y, 2.325), Vector3(THICKNESS, PARTITION_HEIGHT, 2.15), 0, true)
	_add_panel("SouthPartition", Vector3(-0.025, PARTITION_Y, 1.25), Vector3(2.55, PARTITION_HEIGHT, THICKNESS), 0, true)
	_add_panel("ColumnGuard", Vector3(-0.75, PARTITION_Y, 1.8), Vector3(1.1, PARTITION_HEIGHT, THICKNESS), 0, true)
	_add_panel("ColumnGuardSide", Vector3(-0.2, PARTITION_Y, 1.525), Vector3(THICKNESS, PARTITION_HEIGHT, 0.55), 0, true)


func _add_panel(label: String, centre: Vector3, size: Vector3, surface: int, solid: bool) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = centre
	add_child(body)
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	var material := ShaderMaterial.new()
	material.shader = WALL_SHADER
	material.set_shader_parameter("surface_kind", surface)
	mesh.material_override = material
	body.add_child(mesh)
	if solid:
		var shape := CollisionShape3D.new()
		var box_shape := BoxShape3D.new()
		box_shape.size = size
		shape.shape = box_shape
		body.add_child(shape)
