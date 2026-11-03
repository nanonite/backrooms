extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const TEXTURE_ROOT := "res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/textures/direct-source-crops-v1/"
const ROOM_HALF := 4.0
const WALL_HEIGHT := 2.8
const WALL_THICKNESS := 0.12
const SPAWN := Vector3(0.0, 0.6, 1.6)
const SPAWN_PITCH := deg_to_rad(7.0)
const DRESSER_CENTER := Vector3(0.0, 0.54, -3.30)
const DRESSER_SIZE := Vector3(2.30, 1.08, 0.64)

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	_set_candidate_contract()
	_create_groups()
	_build_environment()
	_build_materials()
	_build_room_shell()
	_build_dresser_scene()
	_spawn_player()
	_apply_psx_profile()
	set_meta("walkthrough_ready", true)
	print("Bill Viola single-room candidate ready; R resets to the safe spawn.")


func _set_candidate_contract() -> void:
	set_meta("room_id", "bill_viola_single_room_v1")
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("source_video", "data/videos/Bill Viola 'The Sleep of Reason' 1988.mp4")
	set_meta("source_frame", "frame_2731; index 2730; PTS 91.0 s")
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("safe_spawn", SPAWN)
	set_meta("safe_spawn_pitch_degrees", 7.0)
	set_meta("walk_envelope", Rect2(-ROOM_HALF, -ROOM_HALF, ROOM_HALF * 2.0, ROOM_HALF * 2.0))
	set_meta("rendered_envelope_bounds_xyz", AABB(Vector3(-4.12, -0.22, -4.12), Vector3(8.24, 3.16, 8.24)))
	set_meta("socket_contract", "No openings or sockets are authored; the candidate shell is closed.")
	set_meta("observed_openings", PackedStringArray())
	set_meta("tested_connectors", PackedStringArray())
	set_meta("psx_profile_id", "library-psx-ursc-1.5-native-compositor; pixel pass 3; 24 color levels")
	set_meta("walkable_polygon_xz", PackedVector2Array([
		Vector2(-ROOM_HALF, -ROOM_HALF), Vector2(ROOM_HALF, -ROOM_HALF),
		Vector2(ROOM_HALF, ROOM_HALF), Vector2(-ROOM_HALF, ROOM_HALF),
	]))


func _create_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _build_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.033, 0.03)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.78, 0.73, 0.63)
	environment.ambient_light_energy = 0.72
	var world := WorldEnvironment.new()
	world.name = "BillViolaRoomEnvironment"
	world.environment = environment
	add_child(world)
	var key_light := DirectionalLight3D.new()
	key_light.rotation = Vector3(deg_to_rad(-42.0), deg_to_rad(28.0), 0.0)
	key_light.light_energy = 0.35
	add_child(key_light)


func _build_materials() -> void:
	materials["wall"] = _solid_material(Color(0.63, 0.58, 0.49))
	materials["source_wall"] = _texture_material("plain_wall.png")
	materials["floor"] = _texture_material("dark_carpet.png")
	materials["wood"] = _solid_material(Color(0.12, 0.075, 0.042))
	materials["dresser_front"] = _texture_material("dresser_front.png")
	materials["tv"] = _solid_material(Color(0.035, 0.04, 0.045))
	materials["screen"] = _texture_material("television_screen.png")
	materials["baseboard"] = _solid_material(Color(0.82, 0.77, 0.67))


func _build_room_shell() -> void:
	_add_box_visual("SourceCarpetVisual", Vector3(0.0, -0.1, 0.0), Vector3(8.0, 0.2, 8.0), materials.floor)
	_add_box_collision("WalkableFloor", Vector3(0.0, -0.1, 0.0), Vector3(8.0, 0.2, 8.0), "AuthoredBoundaries")
	_add_wall("LeftBoundary", Vector3(-4.06, WALL_HEIGHT * 0.5, 0.0), Vector3(WALL_THICKNESS, WALL_HEIGHT, 8.12), materials.wall)
	_add_wall("RightBoundary", Vector3(4.06, WALL_HEIGHT * 0.5, 0.0), Vector3(WALL_THICKNESS, WALL_HEIGHT, 8.12), materials.wall)
	_add_wall("SourceFacingWall", Vector3(0.0, WALL_HEIGHT * 0.5, -4.06), Vector3(8.12, WALL_HEIGHT, WALL_THICKNESS), materials.source_wall)
	_add_wall("NearBoundary", Vector3(0.0, WALL_HEIGHT * 0.5, 4.06), Vector3(8.12, WALL_HEIGHT, WALL_THICKNESS), materials.wall)
	_add_box_visual("AuthoredContainmentCeiling", Vector3(0.0, 2.88, 0.0), Vector3(8.12, 0.16, 8.12), materials.wall)
	_add_box_collision("AuthoredCeilingBoundary", Vector3(0.0, 2.88, 0.0), Vector3(8.12, 0.16, 8.12), "AuthoredBoundaries")
	_add_baseboards()
	_add_safety_net()


func _add_baseboards() -> void:
	_add_box_visual("LeftSourceBaseboard", Vector3(-3.985, 0.065, 0.0), Vector3(0.035, 0.13, 7.96), materials.baseboard)
	_add_box_visual("RightSourceBaseboard", Vector3(3.985, 0.065, 0.0), Vector3(0.035, 0.13, 7.96), materials.baseboard)
	_add_box_visual("FarSourceBaseboard", Vector3(0.0, 0.065, -3.985), Vector3(7.96, 0.13, 0.035), materials.baseboard)
	_add_box_visual("NearAuthoredBaseboard", Vector3(0.0, 0.065, 3.985), Vector3(7.96, 0.13, 0.035), materials.baseboard)


func _add_wall(label: String, center: Vector3, size: Vector3, material: Material) -> void:
	_add_box_visual(label + "Visual", center, size, material)
	_add_box_collision(label, center, size, "AuthoredBoundaries")


func _build_dresser_scene() -> void:
	_add_box_visual("AuthoredDresserBody", DRESSER_CENTER, DRESSER_SIZE, materials.wood)
	_add_box_collision("DresserObstacle", DRESSER_CENTER, DRESSER_SIZE, "AuthoredObstacles")
	_add_dresser_front()
	_add_lamp(Vector3(-0.82, 1.08, -3.28))
	_add_television(Vector3(0.05, 1.34, -3.28))
	_add_vase_and_flowers()


func _add_dresser_front() -> void:
	var center := Vector3(DRESSER_CENTER.x, DRESSER_CENTER.y, DRESSER_CENTER.z + DRESSER_SIZE.z * 0.5 + 0.008)
	_add_plane("DirectSourceDresserFront", center, Vector2(2.28, 1.0), materials.dresser_front)


func _add_lamp(base: Vector3) -> void:
	_add_cylinder("LampBase", base + Vector3(0.0, 0.025, 0.0), 0.15, 0.05, Color(0.34, 0.28, 0.18), 8)
	_add_cylinder("LampStem", base + Vector3(0.0, 0.16, 0.0), 0.025, 0.24, Color(0.72, 0.61, 0.39), 6)
	_add_lamp_shade(base + Vector3(0.0, 0.34, 0.0))
	_add_glow(base + Vector3(0.0, 0.29, 0.0))


func _add_lamp_shade(center: Vector3) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.11
	mesh.bottom_radius = 0.21
	mesh.height = 0.25
	mesh.radial_segments = 7
	_add_mesh_visual("LampShade", mesh, center, _solid_material(Color(0.07, 0.065, 0.06)))


func _add_glow(center: Vector3) -> void:
	var bulb := SphereMesh.new()
	bulb.radius = 0.055
	bulb.height = 0.11
	_add_mesh_visual("LampBulb", bulb, center, _solid_material(Color(1.0, 0.77, 0.35)))
	var light := OmniLight3D.new()
	light.name = "LampLight"
	light.position = center
	light.light_color = Color(1.0, 0.73, 0.38)
	light.light_energy = 0.35
	light.omni_range = 2.2
	add_child(light)


func _add_television(center: Vector3) -> void:
	_add_box_visual("TelevisionCabinet", center, Vector3(0.52, 0.42, 0.36), materials.tv)
	_add_plane("DirectSourceTelevisionScreen", center + Vector3(0.0, 0.0, 0.184), Vector2(0.43, 0.34), materials.screen)


func _add_vase_and_flowers() -> void:
	var center := Vector3(0.82, 1.08, -3.30)
	_add_sphere("AuthoredCeramicVaseBody", center + Vector3(0.0, 0.16, 0.0),
		Vector3(0.15, 0.22, 0.13), Color(0.30, 0.35, 0.35))
	_add_cylinder("AuthoredCeramicVaseNeck", center + Vector3(0.0, 0.35, 0.0),
		0.07, 0.18, Color(0.34, 0.39, 0.38), 7)
	var flower_x := [-0.17, -0.10, -0.03, 0.06, 0.14, 0.20]
	for index in flower_x.size():
		_add_bouquet_stem(center, index, flower_x[index])


func _add_bouquet_stem(center: Vector3, index: int, offset_x: float) -> void:
	var height := 0.31 + float(index % 3) * 0.055
	var base := center + Vector3(offset_x * 0.35, 0.44, 0.0)
	_add_cylinder("FlowerStem_%02d" % index, base + Vector3(0.0, height * 0.5, 0.0),
		0.009, height, Color(0.31, 0.32, 0.20), 5)
	var leaf := base + Vector3(offset_x * 0.30, 0.20 + float(index % 2) * 0.11, 0.025)
	_add_sphere("FlowerLeaf_%02d" % index, leaf, Vector3(0.10, 0.045, 0.04),
		Color(0.31, 0.34, 0.22))
	var head := base + Vector3(offset_x, 0.44 + height, 0.0)
	_add_sphere("FlowerHead_%02d" % index, head, Vector3(0.095, 0.085, 0.085),
		Color(0.70, 0.62, 0.42))
	_add_sphere("FlowerCenter_%02d" % index, head + Vector3(0.0, -0.01, 0.04),
		Vector3(0.03, 0.03, 0.03), Color(0.27, 0.22, 0.12))


func _add_cylinder(label: String, center: Vector3, radius: float, height: float, color: Color, segments: int) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = segments
	_add_mesh_visual(label, mesh, center, _solid_material(color))


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = SPAWN
	player.get_node("Head").rotation.x = SPAWN_PITCH
	add_child(player)


func _apply_psx_profile() -> void:
	var compositor := Compositor.new()
	var effect := PSX_EFFECT.new()
	effect.pixel_size = 3
	effect.color_levels = 24
	effect.dither_strength = 1.0
	compositor.compositor_effects = [effect]
	$BillViolaRoomEnvironment.compositor = compositor
	PSX_PRESET.new().configure(self)
	set_meta("psx_applied", true)
	set_meta("psx_package", "URSC 1.5 subset / 8cd971d")


func _add_box_visual(label: String, center: Vector3, size: Vector3, material: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	_add_mesh_visual(label, mesh, center, material)


func _add_mesh_visual(label: String, mesh: Mesh, center: Vector3, material: Material) -> void:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = center
	instance.mesh = mesh
	instance.material_override = material
	$AuthoredVisuals.add_child(instance)


func _add_sphere(label: String, center: Vector3, scale: Vector3, color: Color) -> void:
	var mesh := SphereMesh.new()
	mesh.radius = 0.5
	mesh.height = 1.0
	mesh.radial_segments = 7
	mesh.rings = 4
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = center
	instance.scale = scale
	instance.mesh = mesh
	instance.material_override = _solid_material(color)
	$AuthoredVisuals.add_child(instance)


func _add_plane(label: String, center: Vector3, size: Vector2, material: Material) -> void:
	var mesh := PlaneMesh.new()
	mesh.size = size
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = center
	instance.rotation.x = PI * 0.5
	instance.mesh = mesh
	instance.material_override = material
	$AuthoredVisuals.add_child(instance)


func _add_box_collision(label: String, center: Vector3, size: Vector3, parent_name: String) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	var collision := CollisionShape3D.new()
	collision.name = "CollisionShape3D"
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	get_node(parent_name).add_child(body)


func _add_safety_net() -> void:
	_add_box_collision("SafetyNet", Vector3(0.0, -3.0, 0.0), Vector3(10.0, 0.1, 10.0), "SafetyNet")




func _texture_material(filename: String) -> StandardMaterial3D:
	var image := Image.load_from_file(ProjectSettings.globalize_path(TEXTURE_ROOT + filename))
	if image == null or image.is_empty():
		push_error("Could not load direct-source texture: " + filename)
		return _solid_material(Color.MAGENTA)
	var texture := ImageTexture.create_from_image(image)
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.roughness = 1.0
	return material


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		player.global_position = SPAWN
		player.velocity = Vector3.ZERO
		player.rotation = Vector3.ZERO
		player.get_node("Head").rotation = Vector3(SPAWN_PITCH, 0.0, 0.0)
		print("Bill Viola room reset to safe spawn")
