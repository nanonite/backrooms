extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const PANORAMA_REFERENCE_PATH := "godot_walk/source_library/sources/video-ccf9722164a0bdc8/hunyuan/attempt-005/panorama/panorama.png"
const FLOOR_TEXTURE_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/concrete_floor.png"
const WINDOW_TEXTURE_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/textures/window_grid.png"
const ROOM_HALF_WIDTH := 8.0
const ROOM_HALF_DEPTH := 6.5
const ROOM_HEIGHT := 5.0
const SPAWN := Vector3(0.0, 0.6, 4.1)
const COLUMN_CENTERS := [
	Vector3(-5.6, ROOM_HEIGHT * 0.5, -1.5), Vector3(-1.8, ROOM_HEIGHT * 0.5, -1.5), Vector3(2.0, ROOM_HEIGHT * 0.5, -1.5),
	Vector3(-5.6, ROOM_HEIGHT * 0.5, 1.8), Vector3(-1.8, ROOM_HEIGHT * 0.5, 1.8), Vector3(2.0, ROOM_HEIGHT * 0.5, 1.8),
]

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	_set_candidate_metadata()
	_create_scene_groups()
	if not _build_environment() or not _build_materials():
		return
	_build_floor()
	_build_boundaries()
	_build_columns()
	_build_roof_grid()
	_build_floor_obstacles()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "industrial_hall_panorama_v3")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("panorama_reference_only", PANORAMA_REFERENCE_PATH)
	set_meta("source_frame", "frame_1097; decoded index 1096; PTS 36.533333 s")
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("walk_envelope", Rect2(-ROOM_HALF_WIDTH, -ROOM_HALF_DEPTH, ROOM_HALF_WIDTH * 2.0, ROOM_HALF_DEPTH * 2.0))
	set_meta("safe_spawn", SPAWN)


func _build_environment() -> bool:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.04)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.76, 0.75, 0.70)
	environment.ambient_light_energy = 0.75
	var world := WorldEnvironment.new()
	world.name = "PanoramaEnvironment"
	world.environment = environment
	add_child(world)
	var key_light := DirectionalLight3D.new()
	key_light.name = "OvercastIndustrialLight"
	key_light.rotation = Vector3(deg_to_rad(-52.0), deg_to_rad(24.0), 0.0)
	key_light.light_energy = 0.65
	add_child(key_light)
	return true


func _build_materials() -> bool:
	var floor_texture := _load_texture(FLOOR_TEXTURE_PATH)
	var window_texture := _load_texture(WINDOW_TEXTURE_PATH)
	if floor_texture == null or window_texture == null:
		return false
	materials.floor = _texture_material(floor_texture, Vector3(4.0, 1.0, 4.0))
	materials.wall = _solid_material(Color(0.43, 0.43, 0.40))
	materials.window = _texture_material(window_texture, Vector3(1.0, 1.0, 1.0))
	materials.roof = _solid_material(Color(0.34, 0.35, 0.33))
	materials.post = _solid_material(Color(0.55, 0.54, 0.50))
	materials.beam = _solid_material(Color(0.20, 0.22, 0.21))
	materials.trim = _solid_material(Color(0.28, 0.29, 0.28))
	materials.puddle = _solid_material(Color(0.16, 0.19, 0.20))
	return true


func _build_floor() -> void:
	var floor_center := Vector3(0.0, -0.12, 0.0)
	var floor_size := Vector3(ROOM_HALF_WIDTH * 2.0, 0.24, ROOM_HALF_DEPTH * 2.0)
	_add_box("FloorSurface", floor_center, floor_size, materials.floor, "AuthoredVisuals")
	_add_collision_box("WalkableFloor", floor_center, floor_size, "AuthoredBoundaries")


func _build_boundaries() -> void:
	_add_wall("WestBoundary", Vector3(-ROOM_HALF_WIDTH - 0.15, ROOM_HEIGHT * 0.5, 0.0), Vector3(0.3, ROOM_HEIGHT, ROOM_HALF_DEPTH * 2.0 + 0.3))
	_add_wall("EastBoundary", Vector3(ROOM_HALF_WIDTH + 0.15, ROOM_HEIGHT * 0.5, 0.0), Vector3(0.3, ROOM_HEIGHT, ROOM_HALF_DEPTH * 2.0 + 0.3))
	_add_wall("SouthBoundary", Vector3(0.0, ROOM_HEIGHT * 0.5, ROOM_HALF_DEPTH + 0.15), Vector3(ROOM_HALF_WIDTH * 2.0 + 0.3, ROOM_HEIGHT, 0.3))
	_add_wall("NorthBoundary", Vector3(0.0, ROOM_HEIGHT * 0.5, -ROOM_HALF_DEPTH - 0.15), Vector3(ROOM_HALF_WIDTH * 2.0 + 0.3, ROOM_HEIGHT, 0.3))
	_add_box("FarWindowReference", Vector3(0.0, 3.15, -ROOM_HALF_DEPTH + 0.012), Vector3(6.8, 1.65, 0.025), materials.window, "AuthoredVisuals")
	_add_box("WindowMullionLeft", Vector3(-2.35, 3.15, -ROOM_HALF_DEPTH - 0.02), Vector3(0.08, 1.72, 0.08), materials.trim, "AuthoredVisuals")
	_add_box("WindowMullionRight", Vector3(2.35, 3.15, -ROOM_HALF_DEPTH - 0.02), Vector3(0.08, 1.72, 0.08), materials.trim, "AuthoredVisuals")


func _build_columns() -> void:
	for index in COLUMN_CENTERS.size():
		var center: Vector3 = COLUMN_CENTERS[index]
		_add_box("SupportPostVisual_%02d" % index, center, Vector3(0.42, ROOM_HEIGHT, 0.42), materials.post, "AuthoredVisuals")
		_add_box("SupportPostBase_%02d" % index, Vector3(center.x, 0.34, center.z), Vector3(0.56, 0.68, 0.56), materials.trim, "AuthoredVisuals")
		_add_box("SupportPostCap_%02d" % index, Vector3(center.x, 4.42, center.z), Vector3(0.5, 0.28, 0.5), materials.trim, "AuthoredVisuals")
		_add_collision_box("SupportPostCollision_%02d" % index, center, Vector3(0.56, ROOM_HEIGHT, 0.56), "AuthoredObstacles")


func _build_roof_grid() -> void:
	_add_box("ClosedRoofUnderlay", Vector3(0.0, ROOM_HEIGHT - 0.28, 0.0), Vector3(ROOM_HALF_WIDTH * 2.0, 0.12, ROOM_HALF_DEPTH * 2.0), materials.roof, "AuthoredVisuals")
	for index in 7:
		var x := -7.0 + float(index) * 2.3
		_add_box("RoofLongBeam_%02d" % index, Vector3(x, ROOM_HEIGHT - 0.12, 0.0), Vector3(0.18, 0.2, ROOM_HALF_DEPTH * 2.0), materials.beam, "AuthoredVisuals")
	for index in 6:
		var z := -5.0 + float(index) * 2.0
		_add_box("RoofCrossBeam_%02d" % index, Vector3(0.0, ROOM_HEIGHT - 0.12, z), Vector3(ROOM_HALF_WIDTH * 2.0, 0.2, 0.18), materials.beam, "AuthoredVisuals")
	for index in 3:
		var z := -3.8 + float(index) * 3.4
		_add_box("RoofLightPanel_%02d" % index, Vector3(0.0, ROOM_HEIGHT - 0.18, z), Vector3(1.5, 0.04, 0.48), _solid_material(Color(0.72, 0.70, 0.61)), "AuthoredVisuals")


func _build_floor_obstacles() -> void:
	_add_box("BrokenSlabVisual", Vector3(-3.4, 0.08, -4.25), Vector3(1.8, 0.16, 0.85), materials.trim, "AuthoredVisuals")
	_add_collision_box("BrokenSlabObstacle", Vector3(-3.4, 0.12, -4.25), Vector3(1.8, 0.24, 0.85), "AuthoredObstacles")
	_add_box("PuddlePatchA", Vector3(4.4, 0.006, 3.2), Vector3(2.1, 0.012, 1.0), materials.puddle, "AuthoredVisuals")
	_add_box("PuddlePatchB", Vector3(-4.0, 0.006, 4.2), Vector3(1.6, 0.012, 0.62), materials.puddle, "AuthoredVisuals")


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(0.0, -3.1, 0.0), Vector3(ROOM_HALF_WIDTH * 2.0 + 2.0, 0.12, ROOM_HALF_DEPTH * 2.0 + 2.0), "SafetyNet")


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = SPAWN
	add_child(player)


func _apply_psx_profile() -> void:
	var compositor := Compositor.new()
	var effect = PSX_EFFECT.new()
	effect.pixel_size = 3
	effect.color_levels = 24
	compositor.compositor_effects = [effect]
	$PanoramaEnvironment.compositor = compositor
	PSX_PRESET.new().configure(self)
	set_meta("psx_profile_id", "library-psx-ursc-1.5-native-compositor")
	set_meta("operator_approved", false)


func _add_wall(label: String, center: Vector3, size: Vector3) -> void:
	_add_box(label + "Visual", center, size, materials.wall, "AuthoredVisuals")
	_add_collision_box(label, center, size, "AuthoredBoundaries")


func _add_box(label: String, center: Vector3, size: Vector3, material: Material, visual_parent_name: String) -> void:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	visual.mesh = mesh
	visual.material_override = material
	get_node(visual_parent_name).add_child(visual)


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


func _texture_material(texture: Texture2D, uv_scale: Vector3) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.uv1_scale = uv_scale
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _load_texture(resource_path: String) -> Texture2D:
	var image := Image.load_from_file(ProjectSettings.globalize_path(resource_path))
	if image == null or image.is_empty():
		push_error("Could not read candidate image resource: %s" % resource_path)
		return null
	return ImageTexture.create_from_image(image)


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
		player.get_node("Head").rotation = Vector3.ZERO
		print("Industrial hall candidate reset to safe spawn")
