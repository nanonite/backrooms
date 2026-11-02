extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const FLOOR_TEXTURE_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/concrete_floor.png"
const WINDOW_TEXTURE_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/window_band.png"
const WALL_TEXTURE_PATH := "res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/textures/direct-source-crops-v1/painted_wall.png"
const HALF_WIDTH := 6.0
const HALF_DEPTH := 5.0
const WALL_HEIGHT := 4.2
const SPAWN := Vector3(0.0, 0.6, 3.8)
const ROCK_SEED := 16802
const ROCKS_PER_BANK := 12
const PEBBLE_COLUMNS := 21
const PEBBLE_ROWS := 16
const ROCK_BANKS := [
	Vector3(-4.0, 0.0, -3.15), Vector3(4.0, 0.0, -3.15),
	Vector3(-4.0, 0.0, 0.0), Vector3(4.0, 0.0, 0.0),
	Vector3(-4.0, 0.0, 3.15), Vector3(4.0, 0.0, 3.15),
]

var player: CharacterBody3D
var materials: Dictionary = {}
var rock_mesh: SphereMesh


func _ready() -> void:
	_set_candidate_metadata()
	_create_scene_groups()
	_build_environment()
	_build_materials()
	_build_floor()
	_build_boundaries()
	_build_roof()
	_build_brick_pier()
	_build_rock_field()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _set_candidate_metadata() -> void:
	set_meta("room_id", "debris_window_rock_room_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("source_frame", "frame_4560; index 4559; PTS 151.966667 s")
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("walk_envelope", Rect2(-HALF_WIDTH, -HALF_DEPTH, HALF_WIDTH * 2.0, HALF_DEPTH * 2.0))
	set_meta("safe_spawn", SPAWN)
	set_meta("panorama_reference_only", "attempt-006/panorama/panorama.png")
	set_meta("visible_rock_count", ROCKS_PER_BANK * ROCK_BANKS.size() + PEBBLE_COLUMNS * PEBBLE_ROWS + 1)


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _build_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.04)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.76, 0.75, 0.70)
	environment.ambient_light_energy = 0.75
	var world := WorldEnvironment.new()
	world.name = "RockRoomEnvironment"
	world.environment = environment
	add_child(world)
	var key_light := DirectionalLight3D.new()
	key_light.name = "HighWindowOvercastLight"
	key_light.rotation = Vector3(deg_to_rad(-50.0), deg_to_rad(32.0), 0.0)
	key_light.light_energy = 0.62
	add_child(key_light)


func _build_materials() -> void:
	materials["floor"] = _solid_material(Color(0.34, 0.33, 0.31))
	materials["wall"] = _texture_material(_load_texture(WALL_TEXTURE_PATH), Vector3(2.0, 1.0, 2.0))
	materials["window"] = _texture_material(_load_texture(WINDOW_TEXTURE_PATH), Vector3.ONE)
	materials["ceiling"] = _solid_material(Color(0.43, 0.42, 0.38))
	materials["beam"] = _solid_material(Color(0.27, 0.28, 0.27))
	materials["trim"] = _solid_material(Color(0.24, 0.25, 0.23))
	materials["brick"] = _solid_material(Color(0.46, 0.42, 0.37))
	materials["rock_palette"] = _rock_materials()
	rock_mesh = SphereMesh.new()
	rock_mesh.radius = 0.5
	rock_mesh.height = 1.0
	rock_mesh.radial_segments = 7
	rock_mesh.rings = 4


func _rock_materials() -> Array[StandardMaterial3D]:
	var colors := [Color(0.32, 0.30, 0.27), Color(0.43, 0.40, 0.35), Color(0.25, 0.27, 0.26), Color(0.49, 0.45, 0.39)]
	var palette: Array[StandardMaterial3D] = []
	for color: Color in colors:
		palette.append(_solid_material(color))
	return palette


func _build_floor() -> void:
	var center := Vector3(0.0, -0.12, 0.0)
	var size := Vector3(HALF_WIDTH * 2.0, 0.24, HALF_DEPTH * 2.0)
	_add_box("ConcreteFloorVisual", center, size, materials["floor"], "AuthoredVisuals")
	_add_collision_box("WalkableFloor", center, size, "AuthoredBoundaries")


func _build_boundaries() -> void:
	_add_wall("WestBoundary", Vector3(-HALF_WIDTH - 0.15, WALL_HEIGHT * 0.5, 0.0), Vector3(0.3, WALL_HEIGHT, HALF_DEPTH * 2.0 + 0.3))
	_add_wall("EastBoundary", Vector3(HALF_WIDTH + 0.15, WALL_HEIGHT * 0.5, 0.0), Vector3(0.3, WALL_HEIGHT, HALF_DEPTH * 2.0 + 0.3))
	_add_wall("SouthBoundary", Vector3(0.0, WALL_HEIGHT * 0.5, HALF_DEPTH + 0.15), Vector3(HALF_WIDTH * 2.0 + 0.3, WALL_HEIGHT, 0.3))
	_add_wall("NorthBoundary", Vector3(0.0, WALL_HEIGHT * 0.5, -HALF_DEPTH - 0.15), Vector3(HALF_WIDTH * 2.0 + 0.3, WALL_HEIGHT, 0.3))
	_build_window_band()


func _build_window_band() -> void:
	_add_box("EastWindowReference", Vector3(HALF_WIDTH - 0.035, 3.12, 0.0), Vector3(0.045, 1.48, 7.8), materials["window"], "AuthoredVisuals")
	_add_box("WindowSill", Vector3(HALF_WIDTH - 0.09, 2.34, 0.0), Vector3(0.16, 0.12, 8.15), materials["trim"], "AuthoredVisuals")
	_add_box("WindowHeader", Vector3(HALF_WIDTH - 0.09, 3.91, 0.0), Vector3(0.16, 0.12, 8.15), materials["trim"], "AuthoredVisuals")
	for index in 6:
		var z := -3.25 + float(index) * 1.3
		_add_box("WindowMullion_%02d" % index, Vector3(HALF_WIDTH - 0.07, 3.12, z), Vector3(0.12, 1.55, 0.075), materials["trim"], "AuthoredVisuals")


func _build_roof() -> void:
	_add_box("ClosedCeilingUnderlay", Vector3(0.0, 4.0, 0.0), Vector3(HALF_WIDTH * 2.0 + 0.3, 0.16, HALF_DEPTH * 2.0 + 0.3), materials["ceiling"], "AuthoredVisuals")
	for index in 4:
		var x := -4.5 + float(index) * 3.0
		_add_box("CeilingBeamLong_%02d" % index, Vector3(x, 3.82, 0.0), Vector3(0.18, 0.28, HALF_DEPTH * 2.0), materials["beam"], "AuthoredVisuals")
	for index in 3:
		var z := -3.2 + float(index) * 3.2
		_add_box("CeilingBeamCross_%02d" % index, Vector3(0.0, 3.84, z), Vector3(HALF_WIDTH * 2.0, 0.24, 0.16), materials["beam"], "AuthoredVisuals")


func _build_brick_pier() -> void:
	var center := Vector3(-5.2, WALL_HEIGHT * 0.5, -3.2)
	_add_box("SourceObservedBrickPier", center, Vector3(0.62, WALL_HEIGHT, 0.68), materials["brick"], "AuthoredVisuals")
	_add_collision_box("BrickPierCollision", center, Vector3(0.68, WALL_HEIGHT, 0.74), "AuthoredObstacles")


func _build_rock_field() -> void:
	var random := RandomNumberGenerator.new()
	random.seed = ROCK_SEED
	var rock_index := 0
	for bank: Vector3 in ROCK_BANKS:
		for _stone in ROCKS_PER_BANK:
			var angle := random.randf_range(0.0, TAU)
			var radius := random.randf_range(0.0, 0.82)
			var center := Vector3(bank.x + cos(angle) * radius, 0.0, bank.z + sin(angle) * radius)
			var size := Vector3(random.randf_range(0.62, 1.3), random.randf_range(0.38, 0.9), random.randf_range(0.58, 1.25))
			_add_rock("Stone_%03d" % rock_index, center, size, random.randi_range(0, 3), true, random)
			rock_index += 1
	_add_rock("PathsideBoulder", Vector3(2.1, 0.0, -0.6), Vector3(1.32, 0.84, 1.2), 1, true, random)
	_add_gravel_field(random)


func _add_rock(label: String, floor_center: Vector3, size: Vector3, palette_index: int, collidable: bool, random: RandomNumberGenerator) -> void:
	var center := floor_center + Vector3(0.0, size.y * 0.5, 0.0)
	var visual := MeshInstance3D.new()
	visual.name = label + "Visual"
	visual.position = center
	visual.scale = size
	visual.rotation = Vector3(random.randf_range(-0.12, 0.12), random.randf_range(-PI, PI), random.randf_range(-0.12, 0.12))
	visual.mesh = rock_mesh
	visual.material_override = materials["rock_palette"][palette_index]
	get_node("AuthoredVisuals").add_child(visual)
	if collidable:
		_add_rock_collision(label + "Collision", center, size)


func _add_rock_collision(label: String, center: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	get_node("AuthoredObstacles").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = Vector3(size.x * 0.78, size.y * 0.72, size.z * 0.78)
	collision.shape = shape
	collision.position.y = -size.y * 0.08
	body.add_child(collision)


func _add_gravel_field(random: RandomNumberGenerator) -> void:
	var index := 0
	for column in PEBBLE_COLUMNS:
		for row in PEBBLE_ROWS:
			var x := lerpf(-5.35, 5.35, float(column) / float(PEBBLE_COLUMNS - 1))
			var z := lerpf(-4.35, 4.35, float(row) / float(PEBBLE_ROWS - 1))
			var center := Vector3(x + random.randf_range(-0.25, 0.25), 0.0, z + random.randf_range(-0.25, 0.25))
			var size := Vector3(random.randf_range(0.25, 0.56), random.randf_range(0.1, 0.24), random.randf_range(0.25, 0.56))
			_add_rock("Gravel_%03d" % index, center, size, random.randi_range(0, 3), false, random)
			index += 1


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(0.0, -3.0, 0.0), Vector3(HALF_WIDTH * 2.0 + 2.0, 0.12, HALF_DEPTH * 2.0 + 2.0), "SafetyNet")


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
	$RockRoomEnvironment.compositor = compositor
	PSX_PRESET.new().configure(self)
	set_meta("psx_profile_id", "library-psx-ursc-1.5-native-compositor")


func _add_wall(label: String, center: Vector3, size: Vector3) -> void:
	_add_box(label + "Visual", center, size, materials["wall"], "AuthoredVisuals")
	_add_collision_box(label, center, size, "AuthoredBoundaries")


func _add_box(label: String, center: Vector3, size: Vector3, material: Material, parent_name: String) -> void:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	visual.mesh = mesh
	visual.material_override = material
	get_node(parent_name).add_child(visual)


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
		print("Debris-window rock room reset to safe spawn")
