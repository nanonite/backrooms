extends Node3D

# Visual-only depth revision of slot-canyon-courtyard-v1. Every collidable body,
# the declared footprint, spawn, panorama, seed crops, camera/PSX settings and
# reset behaviour are copied from the accepted baseline. The RELIEF_* arrays
# below add non-colliding visual meshes only; they introduce no collider.

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

# VISUAL ONLY. name, center x/y/z, size x/y/z, material key, tilt degrees around Y.
# Uneven heights and small tilts break the flat wall silhouette in elevation;
# no corresponding StaticBody3D or CollisionShape3D is created for any entry.
const RELIEF_FINS := [
	["WestReliefA", -3.92, 2.10, -8.10, 0.16, 4.20, 1.10, "wall_dark", -3.0],
	["WestReliefB", -3.90, 2.55, -6.40, 0.18, 5.10, 1.35, "wall_dark", 2.0],
	["WestReliefC", -3.91, 1.80, -4.55, 0.15, 3.60, 0.95, "wall_warm", -4.0],
	["WestReliefD", -3.90, 2.95, -2.60, 0.17, 5.90, 1.40, "wall_dark", 3.0],
	["WestReliefE", -3.92, 2.20, -0.70, 0.15, 4.40, 1.05, "wall_warm", -2.0],
	["LowerEastReliefA", 3.90, 2.40, -8.20, 0.16, 4.80, 1.20, "wall_dark", 2.5],
	["LowerEastReliefB", 3.91, 1.95, -5.90, 0.15, 3.90, 0.90, "wall_warm", -3.0],
	["LowerEastReliefC", 3.90, 3.10, -3.10, 0.17, 6.20, 1.30, "wall_dark", 4.0],
	["BendSouthReliefA", 6.20, 2.30, 2.10, 1.20, 4.60, 0.16, "wall_warm", -2.0],
	["BendSouthReliefB", 9.30, 2.75, 2.10, 1.40, 5.50, 0.17, "wall_warm", 3.0],
	["NorthReliefA", -1.60, 2.20, 7.90, 1.10, 4.40, 0.16, "wall_warm", 2.0],
	["NorthReliefB", 1.60, 2.90, 7.90, 1.30, 5.80, 0.17, "wall_dark", -3.0],
	["NorthReliefC", 5.40, 2.10, 7.90, 1.00, 4.20, 0.15, "wall_warm", 4.0],
	["FarEastReliefA", 10.90, 2.65, 3.90, 0.16, 5.30, 1.25, "wall_warm", -3.0],
	["FarEastReliefB", 10.91, 2.00, 6.40, 0.15, 4.00, 1.00, "wall_warm", 2.0],
]

# VISUAL ONLY overhead ledges: name, center, size, material key.
# All sit above the capsule top (Y > 1.2) so they cannot affect walking.
const RELIEF_LEDGES := [
	["WestLedgeA", -3.55, 4.90, -5.20, 0.85, 0.22, 2.10, "strata"],
	["WestLedgeB", -3.60, 5.70, -1.30, 0.75, 0.20, 1.70, "strata"],
	["EastLedgeA", 3.55, 5.10, -6.40, 0.80, 0.22, 1.90, "strata"],
	["NorthLedgeA", 2.40, 5.40, 7.55, 2.10, 0.20, 0.85, "strata"],
	["BendLedgeA", 10.55, 5.20, 4.90, 0.80, 0.20, 1.60, "strata"],
]

# VISUAL ONLY chipped caps on the three existing boulders.
const RELIEF_ROCK_CAPS := [
	["BoulderARelief", -1.95, 0.68, -2.85, 0.70, 0.22, 0.55, "rock", 12.0],
	["BoulderBRelief", 2.35, 0.58, 0.62, 0.62, 0.20, 0.70, "rock", -9.0],
	["BoulderCRelief", 6.70, 0.72, 4.50, 0.85, 0.24, 0.50, "rock", 7.0],
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
	_build_visual_relief()
	_build_safety_net()
	_spawn_player()
	_apply_psx_profile()


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "slot_canyon_courtyard_v2")
	set_meta("baseline_room_id", "slot_canyon_courtyard_v1")
	set_meta("variant_of", "slot-canyon-courtyard-v1")
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
	set_meta("visual_relief_visual_only", true)
	set_meta("visual_relief_node_count", RELIEF_FINS.size() + RELIEF_LEDGES.size() + RELIEF_ROCK_CAPS.size())


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


func _build_visual_relief() -> void:
	for fin: Array in RELIEF_FINS:
		var center := Vector3(fin[1], fin[2], fin[3])
		var size := Vector3(fin[4], fin[5], fin[6])
		var material: Material = materials.wall_warm if fin[7] == "wall_warm" else materials.wall_dark
		var visual := _add_box(fin[0], center, size, material, "AuthoredVisuals")
		visual.rotation.y = deg_to_rad(float(fin[8]))
	for ledge: Array in RELIEF_LEDGES:
		_add_box(ledge[0], Vector3(ledge[1], ledge[2], ledge[3]), Vector3(ledge[4], ledge[5], ledge[6]), materials.strata, "AuthoredVisuals")
	for cap: Array in RELIEF_ROCK_CAPS:
		var visual := _add_box(cap[0], Vector3(cap[1], cap[2], cap[3]), Vector3(cap[4], cap[5], cap[6]), materials.rock, "AuthoredVisuals")
		visual.rotation.y = deg_to_rad(float(cap[7]))


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


func _add_box(label: String, center: Vector3, size: Vector3, material: Material, visual_parent_name: String) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	visual.mesh = mesh
	visual.material_override = material
	get_node(visual_parent_name).add_child(visual)
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
		print("Slot canyon courtyard v2 reset to safe spawn")
