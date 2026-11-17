extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const PANORAMA_PATH := "res://source_library/sources/video-22909eb734e4d8e2/hunyuan/attempt-001/panorama/panorama.png"
const TEXTURE_ROOT := "res://source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/textures/"
const WALL_HEIGHT := 7.0
const SPAWN := Vector3(0.0, 0.6, -7.0)

# name, center x/y/z, size x/y/z, use warm strata crop
const WALL_SEGMENTS := [
	["SouthWall", 0.0, 3.5, -10.15, 8.3, 7.0, 0.3, false],
	["LowerEastWall", 4.15, 3.5, -4.0, 0.3, 7.0, 12.3, false],
	["BendSouthWall", 7.5, 3.5, 1.85, 7.3, 7.0, 0.3, true],
	["FarEastWall", 11.15, 3.5, 5.0, 0.3, 7.0, 6.3, true],
	["NorthWall", 3.5, 3.5, 8.15, 15.3, 7.0, 0.3, true],
	["WestWall", -4.15, 3.5, -1.0, 0.3, 7.0, 18.3, false],
]

# name, center x/y/z, size x/y/z
const FLOOR_SEGMENTS := [
	["MainFloor", 0.0, -0.12, -1.0, 8.0, 0.24, 18.0],
	["BendFloor", 7.5, -0.12, 5.0, 7.0, 0.24, 6.0],
]

# name, center x/y/z, size x/y/z
const ROCK_OBSTACLES := [
	["BoulderA", -1.8, 0.30, -3.0, 1.0, 0.60, 0.9],
	["BoulderB", 2.2, 0.25, 0.5, 0.9, 0.50, 1.1],
	["BoulderC", 6.5, 0.32, 4.6, 1.2, 0.65, 0.8],
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
	_build_rocks()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "slot_canyon_courtyard_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("panorama_visual_only", true)
	set_meta("source_frame", "frame_1363; decoded index 1362; PTS 45.4454 s")
	set_meta("footprint", "authored L-shaped orthogonal courtyard, uncalibrated design units")
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["MainFloorCollision", "BendFloorCollision"]))
	set_meta("walk_envelope", Rect2(-4.0, -10.0, 15.0, 18.0))
	set_meta("safe_spawn", SPAWN)


func _build_environment() -> bool:
	var panorama := _load_texture(PANORAMA_PATH)
	if panorama == null:
		return false
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.58, 0.40, 0.31)
	environment.ambient_light_energy = 0.85
	var sky_material := PanoramaSkyMaterial.new()
	sky_material.panorama = panorama
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	var world := WorldEnvironment.new()
	world.name = "PanoramaEnvironment"
	world.environment = environment
	add_child(world)
	var key_light := DirectionalLight3D.new()
	key_light.name = "SlotSunlight"
	key_light.light_color = Color(1.0, 0.74, 0.45)
	key_light.rotation = Vector3(deg_to_rad(-78.0), deg_to_rad(18.0), 0.0)
	key_light.light_energy = 1.1
	add_child(key_light)
	return true


func _build_materials() -> bool:
	var dark_wall := _load_texture(TEXTURE_ROOT + "wall_strata_dark.png")
	var warm_wall := _load_texture(TEXTURE_ROOT + "wall_strata_warm.png")
	var floor_texture := _load_texture(TEXTURE_ROOT + "sandy_floor.png")
	var glow_texture := _load_texture(TEXTURE_ROOT + "slot_glow.png")
	var rock_texture := _load_texture(TEXTURE_ROOT + "rock_rubble.png")
	if dark_wall == null or warm_wall == null or floor_texture == null or glow_texture == null or rock_texture == null:
		return false
	materials.wall_dark = _texture_material(dark_wall, Vector3(2.2, 1.5, 2.2))
	materials.wall_warm = _texture_material(warm_wall, Vector3(2.2, 1.5, 2.2))
	materials.floor = _texture_material(floor_texture, Vector3(3.0, 1.0, 3.0))
	materials.glow = _texture_material(glow_texture, Vector3(1.0, 1.0, 1.0))
	materials.rock = _texture_material(rock_texture, Vector3(1.0, 1.0, 1.0))
	materials.strata = _solid_material(Color(0.34, 0.16, 0.10))
	return true


func _build_floor() -> void:
	for segment: Array in FLOOR_SEGMENTS:
		var center := Vector3(segment[1], segment[2], segment[3])
		var size := Vector3(segment[4], segment[5], segment[6])
		_add_box("%sVisual" % segment[0], center, size, materials.floor, "AuthoredVisuals")
		_add_collision_box("%sCollision" % segment[0], center, size, "AuthoredBoundaries")


func _build_boundaries() -> void:
	for segment: Array in WALL_SEGMENTS:
		var center := Vector3(segment[1], segment[2], segment[3])
		var size := Vector3(segment[4], segment[5], segment[6])
		var material: Material = materials.wall_warm if segment[7] else materials.wall_dark
		_add_box("%sVisual" % segment[0], center, size, material, "AuthoredVisuals")
		_add_collision_box(segment[0], center, size, "AuthoredBoundaries")
	_add_box("FarLightStreak", Vector3(0.0, 5.6, 7.82), Vector3(2.4, 2.4, 0.04), materials.glow, "AuthoredVisuals")


func _build_rocks() -> void:
	for rock: Array in ROCK_OBSTACLES:
		var center := Vector3(rock[1], rock[2], rock[3])
		var size := Vector3(rock[4], rock[5], rock[6])
		_add_box("%sVisual" % rock[0], center, size, materials.rock, "AuthoredVisuals")
		_add_collision_box("%sCollision" % rock[0], center, size, "AuthoredObstacles")
	_add_box("LooseGravelShelf", Vector3(7.8, 0.03, 6.2), Vector3(1.8, 0.06, 1.0), materials.strata, "AuthoredVisuals")


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(3.5, -3.1, -1.0), Vector3(17.0, 0.12, 20.0), "SafetyNet")


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
		print("Slot canyon courtyard candidate reset to safe spawn")
