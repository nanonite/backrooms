extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const PANORAMA_PATH := "res://source_library/sources/video-d92fc1fa764aa3a2/hunyuan/attempt-001-retry-001/panorama/panorama.png"
const TEXTURE_ROOT := "res://source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v1/textures/"
const WALL_HEIGHT := 2.4
const TREE_HEIGHT := 6.2
const SPAWN := Vector3(0.0, 0.6, 6.0)

# name, center x/y/z, size x/y/z
const WALL_SEGMENTS := [
	["SouthWall", 0.0, 1.2, -8.15, 20.3, 2.4, 0.3],
	["NorthWall", 0.0, 1.2, 8.15, 20.3, 2.4, 0.3],
	["WestWall", -10.15, 1.2, 0.0, 0.3, 2.4, 16.3],
	["EastWall", 10.15, 1.2, 0.0, 0.3, 2.4, 16.3],
]

# name, x, z
const TREE_POSITIONS := [
	["Tree00", -7.2, -5.4],
	["Tree01", -3.6, -5.6],
	["Tree02", 3.6, -5.6],
	["Tree03", 7.2, -5.4],
	["Tree04", -7.2, 0.8],
	["Tree05", -3.8, 2.0],
	["Tree06", 3.8, 2.0],
	["Tree07", 7.2, 0.8],
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
	_build_trees()
	_build_stone_bench()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "snow_garden_courtyard_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("panorama_visual_only", true)
	set_meta("source_frame", "frame_4347; decoded index 4346; PTS 145.011533 s")
	set_meta("footprint", "authored orthogonal rectangle, uncalibrated design units")
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("walk_envelope", Rect2(-10.0, -8.0, 20.0, 16.0))
	set_meta("safe_spawn", SPAWN)


func _build_environment() -> bool:
	var panorama := _load_texture(PANORAMA_PATH)
	if panorama == null:
		return false
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.62, 0.72, 0.92)
	environment.ambient_light_energy = 0.9
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
	key_light.name = "WinterSunlight"
	key_light.light_color = Color(0.85, 0.91, 1.0)
	key_light.rotation = Vector3(deg_to_rad(-72.0), deg_to_rad(24.0), 0.0)
	key_light.light_energy = 1.0
	add_child(key_light)
	return true


func _build_materials() -> bool:
	var stone := _load_texture(TEXTURE_ROOT + "stone_figure.png")
	var branches := _load_texture(TEXTURE_ROOT + "branch_canopy.png")
	if stone == null or branches == null:
		return false
	materials.snow = _solid_material(Color(0.78, 0.84, 0.92))
	materials.hedge = _solid_material(Color(0.18, 0.26, 0.24))
	materials.trunk = _solid_material(Color(0.20, 0.24, 0.31))
	materials.stone = _texture_material(stone, Vector3(1.0, 1.0, 1.0))
	materials.branches = _texture_material(branches, Vector3(1.0, 1.0, 1.0))
	return true


func _build_floor() -> void:
	_add_box("WalkableFloorVisual", Vector3(0.0, -0.12, 0.0), Vector3(20.0, 0.24, 16.0), materials.snow, "AuthoredVisuals")
	_add_collision_box("WalkableFloor", Vector3(0.0, -0.12, 0.0), Vector3(20.0, 0.24, 16.0), "AuthoredBoundaries")


func _build_boundaries() -> void:
	for segment: Array in WALL_SEGMENTS:
		var center := Vector3(segment[1], segment[2], segment[3])
		var size := Vector3(segment[4], segment[5], segment[6])
		_add_box("%sVisual" % segment[0], center, size, materials.hedge, "AuthoredVisuals")
		_add_collision_box(segment[0], center, size, "AuthoredBoundaries")


func _build_trees() -> void:
	for tree: Array in TREE_POSITIONS:
		var name: String = tree[0]
		var tree_x: float = tree[1]
		var tree_z: float = tree[2]
		var trunk_center := Vector3(tree_x, TREE_HEIGHT / 2.0, tree_z)
		var trunk_size := Vector3(0.42, TREE_HEIGHT, 0.42)
		_add_box("%sTrunk" % name, trunk_center, trunk_size, materials.trunk, "AuthoredVisuals")
		_add_box("%sCanopyX" % name, Vector3(tree_x, 5.2, tree_z), Vector3(2.6, 2.0, 0.10), materials.branches, "AuthoredVisuals")
		_add_box("%sCanopyZ" % name, Vector3(tree_x, 5.2, tree_z), Vector3(0.10, 2.0, 2.6), materials.branches, "AuthoredVisuals")
		_add_collision_box("%sCollision" % name, trunk_center, trunk_size, "AuthoredObstacles")


func _build_stone_bench() -> void:
	_add_box("BenchPlinth", Vector3(0.0, 0.18, 0.0), Vector3(3.4, 0.36, 1.6), materials.stone, "AuthoredVisuals")
	_add_box("BenchSeat", Vector3(0.0, 0.55, 0.0), Vector3(3.0, 0.22, 1.2), materials.stone, "AuthoredVisuals")
	_add_box("BenchBack", Vector3(0.0, 1.15, -0.5), Vector3(3.0, 1.0, 0.25), materials.stone, "AuthoredVisuals")
	_add_collision_box("StoneBenchCollision", Vector3(0.0, 0.75, -0.1), Vector3(3.4, 1.5, 1.8), "AuthoredObstacles")


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(0.0, -3.1, 0.0), Vector3(22.0, 0.12, 18.0), "SafetyNet")


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
		print("Snow garden courtyard candidate reset to safe spawn")
