extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const GEOMETRY := preload("res://scripts/issue165_room_geometry.gd")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const TEXTURE_ROOT := "res://evidence/2026-10-25-issue-165/source_textures/"
const SPAWN := Vector3(-5.0, 0.6, 0.0)
const SPAWN_YAW := -PI * 0.5

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	_set_adaptation_contract()
	_build_environment()
	_build_materials()
	GEOMETRY.build(self, materials)
	_build_player()
	PSX_PRESET.new().configure(self)
	set_meta("walkthrough_ready", true)
	set_meta("operator_approved", false)
	set_meta("room_id", "issue165_corridor_corner_l_room_v1")


func _set_adaptation_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("source_video", "data/videos/corridor_corner.mp4")
	set_meta("source_seed_frame", "frame_0001.png")
	set_meta("source_context", "synthetic L-turn/corridor context; unregistered")
	set_meta("walk_envelope", Rect2(-6.0, -7.0, 10.0, 9.0))
	set_meta("walkable_polygon_xz", PackedVector2Array([
		Vector2(-6.0, -2.0), Vector2(0.0, -2.0), Vector2(0.0, -7.0),
		Vector2(4.0, -7.0), Vector2(4.0, 2.0), Vector2(-6.0, 2.0),
	]))
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("walk_route", PackedVector2Array([
		Vector2(-5.0, 0.0), Vector2(-4.0, 1.15), Vector2(-1.0, 1.15),
		Vector2(0.8, 0.5), Vector2(2.0, -2.8), Vector2(2.0, -5.8),
	]))
	set_meta("boundary_probe_origin", Vector3(-5.0, 0.6, 0.0))
	set_meta("boundary_test_path", "AuthoredBoundaries/Boundary_EastOuter")
	set_meta("boundary_test_rect_is_conservative_aabb", true)
	set_meta("rendered_envelope_bounds_xyz", AABB(Vector3(-6.08, -0.08, -7.08), Vector3(10.16, 3.16, 9.16)))
	set_meta("background_geometry", PackedStringArray())
	set_meta("socket_contract", "No socket or connector is authored; every perimeter is closed.")
	set_meta("tested_connectors", PackedStringArray())


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.035)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.88, 0.86, 0.78)
	environment.ambient_light_energy = 0.8
	var compositor := Compositor.new()
	var effect = PSX_EFFECT.new()
	effect.pixel_size = 3
	effect.color_levels = 24
	effect.dither_strength = 1.0
	compositor.compositor_effects = [effect]
	world.environment = environment
	world.compositor = compositor
	add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation = Vector3(deg_to_rad(-48.0), deg_to_rad(35.0), 0.0)
	light.light_energy = 0.65
	add_child(light)


func _build_materials() -> void:
	materials.wallpaper = _source_material("wallpaper_source_frame_0001.png", Vector3(4.0, 3.0, 1.0))
	materials.floor = _source_material("floor_source_frame_0001.png", Vector3.ONE)
	materials.ceiling = _source_material("ceiling_source_frame_0001.png", Vector3.ONE)
	materials.column = _source_material("column_source_frame_0001.png", Vector3(1.0, 3.0, 1.0))
	materials.lamp = _solid_material(Color(1.0, 0.97, 0.76))


func _source_material(filename: String, uv_scale: Vector3) -> StandardMaterial3D:
	var path := ProjectSettings.globalize_path(TEXTURE_ROOT + filename)
	var image := Image.new()
	if image.load(path) != OK:
		push_error("Missing direct-source crop: %s" % path)
		return StandardMaterial3D.new()
	var material := StandardMaterial3D.new()
	material.albedo_texture = ImageTexture.create_from_image(image)
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.roughness = 1.0
	material.uv1_scale = uv_scale
	return material


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _build_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = SPAWN
	player.rotation.y = SPAWN_YAW
	add_child(player)


func _reset_player() -> void:
	if player == null:
		return
	player.global_position = SPAWN
	player.rotation = Vector3(0.0, SPAWN_YAW, 0.0)
	player.velocity = Vector3.ZERO
	player.get_node("Head").rotation = Vector3.ZERO


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		_reset_player()
