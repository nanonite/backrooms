class_name Issue165RoomGeometry
extends RefCounted

const FLOOR_Y := 0.0
const CEILING_Y := 3.0
const WALL_THICKNESS := 0.16
const COLUMN_CENTER := Vector3(-2.5, 1.5, 0.0)
const COLUMN_SIZE := Vector3(0.9, 3.0, 0.9)


static func build(parent: Node3D, materials: Dictionary) -> void:
	var visuals := _child(parent, "AuthoredVisuals")
	var boundaries := _child(parent, "AuthoredBoundaries")
	_add_floors(visuals, boundaries, materials.floor)
	_add_ceilings(visuals, materials.ceiling)
	_add_boundary_shell(visuals, boundaries, materials.wallpaper)
	_add_column(visuals, boundaries, materials.column)
	_add_lights(visuals, materials.lamp)
	_add_safety_net(parent)


static func _add_floors(visuals: Node3D, boundaries: Node3D, material: Material) -> void:
	var floor_visual := Node3D.new()
	floor_visual.name = "WalkableFloorVisual"
	visuals.add_child(floor_visual)
	_add_box(floor_visual, "MainLegFloor", Vector3(-3.0, -0.025, 0.0), Vector3(6.0, 0.05, 4.0), material)
	_add_box(floor_visual, "TurnLegFloor", Vector3(2.0, -0.025, -2.5), Vector3(4.0, 0.05, 9.0), material)
	var floor_body := StaticBody3D.new()
	floor_body.name = "WalkableFloor"
	boundaries.add_child(floor_body)
	_add_collision(floor_body, "MainLegFloorShape", Vector3(-3.0, -0.06, 0.0), Vector3(6.0, 0.12, 4.0))
	_add_collision(floor_body, "TurnLegFloorShape", Vector3(2.0, -0.06, -2.5), Vector3(4.0, 0.12, 9.0))


static func _add_ceilings(visuals: Node3D, material: Material) -> void:
	var ceiling := Node3D.new()
	ceiling.name = "RenderedCeiling"
	visuals.add_child(ceiling)
	_add_box(ceiling, "MainLegCeiling", Vector3(-3.0, 3.025, 0.0), Vector3(6.0, 0.05, 4.0), material)
	_add_box(ceiling, "TurnLegCeiling", Vector3(2.0, 3.025, -2.5), Vector3(4.0, 0.05, 9.0), material)


static func _add_boundary_shell(visuals: Node3D, boundaries: Node3D, material: Material) -> void:
	_add_wall(visuals, boundaries, "Boundary_WestOuter", Vector3(-6.0, 1.5, 0.0), Vector3(0.16, 3.0, 4.16), material)
	_add_wall(visuals, boundaries, "Boundary_SouthMain", Vector3(-3.0, 1.5, -2.0), Vector3(6.16, 3.0, 0.16), material)
	_add_wall(visuals, boundaries, "Boundary_InnerElbow", Vector3(0.0, 1.5, -4.5), Vector3(0.16, 3.0, 5.16), material)
	_add_wall(visuals, boundaries, "Boundary_FarCap", Vector3(2.0, 1.5, -7.0), Vector3(4.16, 3.0, 0.16), material)
	_add_wall(visuals, boundaries, "Boundary_EastOuter", Vector3(4.0, 1.5, -2.5), Vector3(0.16, 3.0, 9.16), material)
	_add_wall(visuals, boundaries, "Boundary_NorthMain", Vector3(-1.0, 1.5, 2.0), Vector3(10.16, 3.0, 0.16), material)


static func _add_column(visuals: Node3D, boundaries: Node3D, material: Material) -> void:
	_add_box(visuals, "SourceObservedColumnVisual", COLUMN_CENTER, COLUMN_SIZE, material)
	var obstacle := StaticBody3D.new()
	obstacle.name = "SourceObservedColumnObstacle"
	obstacle.position = COLUMN_CENTER
	boundaries.add_child(obstacle)
	_add_collision(obstacle, "ColumnCapsuleBlocker", Vector3.ZERO, COLUMN_SIZE)


static func _add_lights(visuals: Node3D, material: Material) -> void:
	var positions := [Vector3(-4.5, 2.985, -0.4), Vector3(-1.5, 2.985, -0.4),
		Vector3(1.0, 2.985, -1.0), Vector3(3.0, 2.985, -3.0), Vector3(3.0, 2.985, -5.5)]
	for index in positions.size():
		_add_box(visuals, "CeilingLight_%02d" % index, positions[index], Vector3(0.9, 0.03, 0.42), material)


static func _add_safety_net(parent: Node3D) -> void:
	var safety := StaticBody3D.new()
	safety.name = "SafetyNet"
	safety.position = Vector3(-1.0, -4.0, -2.5)
	parent.add_child(safety)
	_add_collision(safety, "SafetyNetShape", Vector3.ZERO, Vector3(14.0, 0.1, 13.0))


static func _add_wall(visuals: Node3D, boundaries: Node3D, label: String,
		center: Vector3, size: Vector3, material: Material) -> void:
	_add_box(visuals, label + "Visual", center, size, material)
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	boundaries.add_child(body)
	_add_collision(body, "CollisionShape3D", Vector3.ZERO, size)


static func _add_box(parent: Node3D, label: String, center: Vector3, size: Vector3,
		material: Material) -> void:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	instance.mesh = mesh
	instance.material_override = material
	parent.add_child(instance)


static func _add_collision(parent: Node3D, label: String, center: Vector3, size: Vector3) -> void:
	var collision := CollisionShape3D.new()
	collision.name = label
	collision.position = center
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	parent.add_child(collision)


static func _child(parent: Node3D, label: String) -> Node3D:
	var child := Node3D.new()
	child.name = label
	parent.add_child(child)
	return child
