extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const PANORAMA_PATH := "res://source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-002/panorama/panorama.png"
const FLOOR_TEXTURE_PATH := "res://source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/textures/carpet_floor.png"
const WALL_TEXTURE_PATH := "res://source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/textures/wood_wall.png"
const WINDOW_TEXTURE_PATH := "res://source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/textures/sash_window.png"
const CEILING_TEXTURE_PATH := "res://source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/textures/ceiling_slats.png"
const CHAIR_TEXTURE_PATH := "res://source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/textures/chair_reference.png"
const ROOM_HALF_WIDTH := 7.0
const ROOM_HALF_DEPTH := 9.0
const ROOM_HEIGHT := 4.6
const SPAWN := Vector3(0.0, 0.6, 6.6)
const WINDOW_CENTERS_Z := [-5.5, 0.0, 5.5]
const CHAIR_CENTERS := [Vector3(4.8, 0.0, -6.0), Vector3(6.0, 0.0, -6.0)]

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	_set_candidate_metadata()
	_create_scene_groups()
	if not _build_environment() or not _build_materials():
		return
	_build_floor()
	_build_boundaries()
	_build_windows()
	_build_ceiling()
	_build_chairs()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "wooden_verdure_hall_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("panorama_visual_only", true)
	set_meta("source_frame", "frame_3357; decoded index 3356; PTS 139.973167 s")
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
	environment.ambient_light_color = Color(0.82, 0.80, 0.72)
	environment.ambient_light_energy = 0.8
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
	key_light.name = "WindowDaylight"
	key_light.rotation = Vector3(deg_to_rad(-48.0), deg_to_rad(32.0), 0.0)
	key_light.light_energy = 0.9
	add_child(key_light)
	return true


func _build_materials() -> bool:
	var floor_texture := _load_texture(FLOOR_TEXTURE_PATH)
	var wall_texture := _load_texture(WALL_TEXTURE_PATH)
	var window_texture := _load_texture(WINDOW_TEXTURE_PATH)
	var ceiling_texture := _load_texture(CEILING_TEXTURE_PATH)
	var chair_texture := _load_texture(CHAIR_TEXTURE_PATH)
	if floor_texture == null or wall_texture == null or window_texture == null or ceiling_texture == null or chair_texture == null:
		return false
	materials.floor = _texture_material(floor_texture, Vector3(5.0, 1.0, 6.0))
	materials.wall = _texture_material(wall_texture, Vector3(3.0, 1.4, 1.0))
	materials.window = _texture_material(window_texture, Vector3(1.0, 1.0, 1.0))
	materials.ceiling = _texture_material(ceiling_texture, Vector3(3.0, 1.0, 4.0))
	materials.chair = _texture_material(chair_texture, Vector3(1.0, 1.0, 1.0))
	materials.frame = _solid_material(Color(0.09, 0.08, 0.07))
	materials.rib = _solid_material(Color(0.30, 0.18, 0.10))
	materials.far_panel = _solid_material(Color(0.86, 0.84, 0.72))
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
	_add_box("FarLightPanel", Vector3(0.0, 2.6, -ROOM_HALF_DEPTH + 0.012), Vector3(1.4, 1.9, 0.025), materials.far_panel, "AuthoredVisuals")


func _build_windows() -> void:
	for side in [-1.0, 1.0]:
		for index in WINDOW_CENTERS_Z.size():
			var z: float = WINDOW_CENTERS_Z[index]
			var x: float = side * (ROOM_HALF_WIDTH - 0.02)
			var label := "%s_%02d" % ["West" if side < 0.0 else "East", index]
			_add_box("WindowPanel" + label, Vector3(x, 2.35, z), Vector3(0.03, 1.8, 2.4), materials.window, "AuthoredVisuals")
			_add_box("WindowTop" + label, Vector3(x - side * 0.01, 3.28, z), Vector3(0.08, 0.1, 2.55), materials.frame, "AuthoredVisuals")
			_add_box("WindowSill" + label, Vector3(x - side * 0.01, 1.42, z), Vector3(0.14, 0.1, 2.55), materials.frame, "AuthoredVisuals")
			_add_box("WindowMullionA" + label, Vector3(x - side * 0.02, 2.35, z - 0.8), Vector3(0.07, 1.85, 0.07), materials.frame, "AuthoredVisuals")
			_add_box("WindowMullionB" + label, Vector3(x - side * 0.02, 2.35, z + 0.8), Vector3(0.07, 1.85, 0.07), materials.frame, "AuthoredVisuals")
			_add_box("WindowCrossbar" + label, Vector3(x - side * 0.02, 2.35, z), Vector3(0.07, 0.07, 2.42), materials.frame, "AuthoredVisuals")


func _build_ceiling() -> void:
	_add_box("SlatCeiling", Vector3(0.0, ROOM_HEIGHT + 0.08, 0.0), Vector3(ROOM_HALF_WIDTH * 2.0, 0.16, ROOM_HALF_DEPTH * 2.0), materials.ceiling, "AuthoredVisuals")
	for index in 9:
		var z := -8.0 + float(index) * 2.0
		_add_box("CeilingRib_%02d" % index, Vector3(0.0, ROOM_HEIGHT - 0.04, z), Vector3(ROOM_HALF_WIDTH * 2.0, 0.12, 0.18), materials.rib, "AuthoredVisuals")


func _build_chairs() -> void:
	for index in CHAIR_CENTERS.size():
		var center: Vector3 = CHAIR_CENTERS[index]
		_add_box("ChairSeat_%02d" % index, center + Vector3(0.0, 0.46, 0.0), Vector3(0.62, 0.08, 0.58), materials.chair, "AuthoredVisuals")
		_add_box("ChairBack_%02d" % index, center + Vector3(0.0, 0.82, -0.25), Vector3(0.62, 0.66, 0.07), materials.chair, "AuthoredVisuals")
		_add_box("ChairLegs_%02d" % index, center + Vector3(0.0, 0.22, 0.0), Vector3(0.52, 0.44, 0.48), materials.rib, "AuthoredVisuals")
		_add_collision_box("ChairCollision_%02d" % index, center + Vector3(0.0, 0.45, 0.0), Vector3(0.62, 0.9, 0.58), "AuthoredObstacles")


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
		print("Wooden verdure hall candidate reset to safe spawn")
