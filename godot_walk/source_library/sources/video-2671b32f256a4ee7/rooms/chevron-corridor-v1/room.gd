extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const PANORAMA_PATH := "res://source_library/sources/video-2671b32f256a4ee7/hunyuan/attempt-001-retry-001/panorama/panorama.png"
const FLOOR_TEXTURE_PATH := "res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v1/textures/carpet_floor.png"
const WALL_TEXTURE_PATH := "res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v1/textures/chevron_wall.png"
const CEILING_TEXTURE_PATH := "res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v1/textures/ceiling_grid.png"
const ROOM_HALF_WIDTH := 8.0
const ROOM_HALF_DEPTH := 10.0
const ROOM_HEIGHT := 4.2
const PARTITION_HEIGHT := 3.4
const SPAWN := Vector3(0.0, 0.6, 8.4)
const PARTITIONS := [
	{"center": Vector3(-4.5, PARTITION_HEIGHT * 0.5, 5.0), "size": Vector3(0.3, PARTITION_HEIGHT, 4.0)},
	{"center": Vector3(4.5, PARTITION_HEIGHT * 0.5, 2.0), "size": Vector3(0.3, PARTITION_HEIGHT, 4.0)},
	{"center": Vector3(-4.5, PARTITION_HEIGHT * 0.5, -2.0), "size": Vector3(0.3, PARTITION_HEIGHT, 4.0)},
	{"center": Vector3(4.5, PARTITION_HEIGHT * 0.5, -6.0), "size": Vector3(0.3, PARTITION_HEIGHT, 4.0)},
]
const LIGHT_Z := [-6.0, -2.0, 2.0, 6.0]

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	_set_candidate_metadata()
	_create_scene_groups()
	if not _build_environment() or not _build_materials():
		return
	_build_floor()
	_build_boundaries()
	_build_partitions()
	_build_ceiling()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "chevron_corridor_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("panorama_visual_only", true)
	set_meta("source_frame", "frame_0096; decoded index 95; PTS 3.958333 s")
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("walk_envelope", Rect2(-ROOM_HALF_WIDTH, -ROOM_HALF_DEPTH, ROOM_HALF_WIDTH * 2.0, ROOM_HALF_DEPTH * 2.0))
	set_meta("safe_spawn", SPAWN)


func _build_environment() -> bool:
	var panorama := _load_texture(PANORAMA_PATH)
	if panorama == null:
		return false
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.86, 0.84, 0.64)
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
	key_light.name = "CeilingDaylight"
	key_light.rotation = Vector3(deg_to_rad(-55.0), deg_to_rad(24.0), 0.0)
	key_light.light_energy = 0.85
	add_child(key_light)
	return true


func _build_materials() -> bool:
	var floor_texture := _load_texture(FLOOR_TEXTURE_PATH)
	var wall_texture := _load_texture(WALL_TEXTURE_PATH)
	var ceiling_texture := _load_texture(CEILING_TEXTURE_PATH)
	if floor_texture == null or wall_texture == null or ceiling_texture == null:
		return false
	materials.floor = _texture_material(floor_texture, Vector3(5.0, 1.0, 6.0))
	materials.wall = _texture_material(wall_texture, Vector3(2.0, 1.0, 1.0))
	materials.ceiling = _texture_material(ceiling_texture, Vector3(3.0, 1.0, 4.0))
	materials.baseboard = _solid_material(Color(0.90, 0.89, 0.78))
	materials.grid_rib = _solid_material(Color(0.62, 0.59, 0.42))
	materials.light_panel = _solid_material(Color(1.0, 0.99, 0.92))
	materials.far_panel = _solid_material(Color(0.96, 0.94, 0.80))
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
	_add_box("FarLightPanel", Vector3(0.0, 2.4, -ROOM_HALF_DEPTH + 0.012), Vector3(1.6, 2.0, 0.025), materials.far_panel, "AuthoredVisuals")


func _build_partitions() -> void:
	for index in PARTITIONS.size():
		var partition: Dictionary = PARTITIONS[index]
		var center: Vector3 = partition["center"]
		var size: Vector3 = partition["size"]
		_add_box("PartitionWall_%02d" % index, center, size, materials.wall, "AuthoredVisuals")
		var base_center := Vector3(center.x, 0.11, center.z)
		_add_box("PartitionBase_%02d" % index, base_center, Vector3(size.x + 0.04, 0.22, size.z + 0.04), materials.baseboard, "AuthoredVisuals")
		_add_collision_box("PartitionCollision_%02d" % index, center, size, "AuthoredObstacles")


func _build_ceiling() -> void:
	_add_box("GridCeiling", Vector3(0.0, ROOM_HEIGHT + 0.08, 0.0), Vector3(ROOM_HALF_WIDTH * 2.0, 0.16, ROOM_HALF_DEPTH * 2.0), materials.ceiling, "AuthoredVisuals")
	for index in 10:
		var z := -9.0 + float(index) * 2.0
		_add_box("CeilingRibX_%02d" % index, Vector3(0.0, ROOM_HEIGHT - 0.02, z), Vector3(ROOM_HALF_WIDTH * 2.0, 0.08, 0.08), materials.grid_rib, "AuthoredVisuals")
	for index in 8:
		var x := -7.0 + float(index) * 2.0
		_add_box("CeilingRibZ_%02d" % index, Vector3(x, ROOM_HEIGHT - 0.02, 0.0), Vector3(0.08, 0.08, ROOM_HALF_DEPTH * 2.0), materials.grid_rib, "AuthoredVisuals")
	for index in LIGHT_Z.size():
		var z: float = LIGHT_Z[index]
		_add_box("FluorescentPanel_%02d" % index, Vector3(0.0, ROOM_HEIGHT - 0.06, z), Vector3(2.2, 0.05, 0.85), materials.light_panel, "AuthoredVisuals")


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
		print("Chevron corridor candidate reset to safe spawn")
