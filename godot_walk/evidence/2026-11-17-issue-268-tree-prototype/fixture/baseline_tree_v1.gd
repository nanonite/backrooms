extends Node3D

# Baseline for issue 268: the *current* one-tree representation scheme from the
# accepted snow-garden-courtyard-v2 room -- solid six-sided trunk cylinder, four
# small branch cylinders, two thin textured canopy boxes and a separate trunk box
# collision. Geometry is simplified to one tree in the same isolated fixture, but
# the representation scheme is unchanged. Uncalibrated authored design units.
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const TEXTURE_ROOT := "res://evidence/2026-11-17-issue-268-tree-prototype/fixture/textures/"
const TRUNK_HEIGHT := 5.6
const TRUNK_RADIUS := 0.24
const GROUND_SIZE := Vector3(14.0, 0.24, 14.0)
const SPAWN := Vector3(0.0, 0.6, 4.5)

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	set_meta("fixture_id", "issue_268_baseline_tree_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("trunk_representation", "solid_cylinder")
	set_meta("canopy_representation", "two_thin_textured_boxes")
	_create_groups()
	if not _build_materials():
		return
	_build_floor()
	_build_tree()
	_build_safety_net()
	_spawn_player()


func _create_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredCanopy", "TreeCollision", "AuthoredBoundaries", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _build_materials() -> bool:
	var canopy := _load_texture(TEXTURE_ROOT + "branch_canopy.png")
	if canopy == null:
		return false
	materials.trunk = _solid_material(Color(0.21, 0.25, 0.32))
	materials.branch = _solid_material(Color(0.24, 0.28, 0.35))
	materials.ground = _solid_material(Color(0.62, 0.68, 0.74))
	materials.ground_shade = _solid_material(Color(0.54, 0.61, 0.68))
	materials.canopy = _texture_material(canopy)
	return true


func _build_floor() -> void:
	_add_box("InspectionFloorVisual", Vector3(0.0, -0.12, 0.0), GROUND_SIZE, materials.ground, "AuthoredVisuals")
	_add_box("FloorAccent", Vector3(0.0, -0.115, 0.0), Vector3(3.0, 0.02, 14.0), materials.ground_shade, "AuthoredVisuals")
	_add_collision_box("WalkableFloor", Vector3(0.0, -0.12, 0.0), GROUND_SIZE, "AuthoredBoundaries")


func _build_tree() -> void:
	var trunk_center := Vector3(0.0, TRUNK_HEIGHT / 2.0, 0.0)
	_add_cylinder("BaselineTrunk", trunk_center, TRUNK_RADIUS, TRUNK_HEIGHT, materials.trunk, 6)
	for index in 4:
		var angle := TAU * float(index) / 4.0
		var tilt := deg_to_rad(36.0 + float(index % 2) * 8.0)
		var length := 1.3 + float(index % 3) * 0.4
		var direction := Vector3(sin(tilt) * cos(angle), cos(tilt), sin(tilt) * sin(angle))
		var center := Vector3(0.0, TRUNK_HEIGHT * 0.74, 0.0) + direction * (length * 0.5)
		var rotation := Vector3(tilt * sin(angle), 0.0, -tilt * cos(angle))
		_add_cylinder("BaselineBranch%d" % index, center, 0.045, length, materials.branch, 4, rotation)
	for index in 2:
		var angle := TAU * float(index) / 2.0
		var center := Vector3(cos(angle) * 0.55, TRUNK_HEIGHT - 0.8 - float(index) * 0.5, sin(angle) * 0.55)
		_add_box("BaselinePanel%d" % index, center, Vector3(1.25, 0.85, 0.06),
			materials.canopy, "AuthoredCanopy", Vector3(0.0, angle, 0.0))
	var body := StaticBody3D.new()
	body.name = "TrunkCollision"
	body.position = trunk_center
	get_node("TreeCollision").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = Vector3(TRUNK_RADIUS * 2.0, TRUNK_HEIGHT, TRUNK_RADIUS * 2.0)
	collision.shape = shape
	body.add_child(collision)


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(0.0, -3.1, 0.0), Vector3(16.0, 0.12, 16.0), "SafetyNet")


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = SPAWN
	add_child(player)


func _add_box(label: String, center: Vector3, size: Vector3, material: Material,
		parent_name: String, rotation := Vector3.ZERO) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	return _add_mesh(label, center, mesh, material, parent_name, rotation)


func _add_cylinder(label: String, center: Vector3, radius: float, height: float,
		material: Material, segments: int, rotation := Vector3.ZERO) -> MeshInstance3D:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = segments
	mesh.rings = 1
	return _add_mesh(label, center, mesh, material, "AuthoredVisuals", rotation)


func _add_mesh(label: String, center: Vector3, mesh: Mesh, material: Material,
		parent_name: String, rotation := Vector3.ZERO) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	visual.rotation = rotation
	visual.mesh = mesh
	visual.material_override = material
	get_node(parent_name).add_child(visual)
	return visual


func _add_collision_box(label: String, center: Vector3, size: Vector3, parent_name: String) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	get_node(parent_name).add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)


func _texture_material(texture: Texture2D) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _load_texture(resource_path: String) -> Texture2D:
	var image := Image.load_from_file(ProjectSettings.globalize_path(resource_path))
	if image == null or image.is_empty():
		push_error("Could not read fixture texture: %s" % resource_path)
		return null
	return ImageTexture.create_from_image(image)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		player.global_position = SPAWN
		player.velocity = Vector3.ZERO
		player.rotation = Vector3.ZERO
		player.get_node("Head").rotation = Vector3.ZERO
		print("Issue 268 baseline tree reset to safe spawn")
