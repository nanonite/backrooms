extends Node3D
class_name HunyuanPsxRound1

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const HUNYUAN_SCENE_PATH := "res://evidence/2026-10-20-issue-147/hunyuan_layers.glb"
const PSX_EFFECT_SCRIPT := preload("res://scripts/psx/psx_post_effect.gd")
const FLOOR_Y := -1.27099049
const CEILING_Y := FLOOR_Y + 2.4
const WEST := -5.4
const EAST := 4.5
const SOUTH := -5.0
const NORTH := 8.8
const WALL_THICKNESS := 0.12
const COLUMN_CENTER := Vector3(-0.44746488, -0.07099044, 0.32348078)
const COLUMN_SIZE := Vector3(1.8587826, 2.4, 2.3700817)
const VARIANTS := ["preserve_hunyuan", "source_surface_cleanup"]

@export_enum("preserve_hunyuan", "source_surface_cleanup") var variant_id := "preserve_hunyuan"

var _materials: Dictionary = {}


func _ready() -> void:
	variant_id = _requested_variant()
	if not VARIANTS.has(variant_id):
		push_error("Unknown Hunyuan round variant: %s" % variant_id)
		get_tree().quit(2)
		return
	_set_design_contract()
	_build_environment()
	_build_materials()
	_build_visual_source()
	_build_authored_room()
	_build_player()


func _requested_variant() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--variant="):
			return argument.get_slice("=", 1)
	return variant_id


func _set_design_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("variant_id", variant_id)
	set_meta("walk_route", PackedVector2Array([
		Vector2(-4.4, -4.0), Vector2(3.5, -4.0),
		Vector2(3.5, 7.8), Vector2(-4.4, 7.8),
	]))
	set_meta("walk_envelope", Rect2(WEST, SOUTH, EAST - WEST, NORTH - SOUTH))
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["AuthoredFloor"]))
	set_meta("boundary_probe_origin", Vector3(3.3, FLOOR_Y + 0.6, 1.9))
	set_meta("boundary_test_path", "AuthoredBoundaries/EastBoundary")


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.035)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.88, 0.86, 0.78)
	environment.ambient_light_energy = 0.8
	var compositor := Compositor.new()
	var effect := PSX_EFFECT_SCRIPT.new()
	effect.pixel_size = 3
	effect.color_levels = 24
	compositor.compositor_effects = [effect]
	world.environment = environment
	world.compositor = compositor
	add_child(world)
	var key_light := DirectionalLight3D.new()
	key_light.rotation = Vector3(deg_to_rad(-48.0), deg_to_rad(35.0), 0.0)
	key_light.light_energy = 0.65
	add_child(key_light)


func _build_materials() -> void:
	_materials.floor = _material("floor", "floor_source_video.png")
	_materials.wall = _material("wall", "wallpaper_source_video.png")
	_materials.ceiling = _material("ceiling", "ceiling_source_video.png")
	_materials.column = _material("column", "column_source_video.png")


func _build_visual_source() -> void:
	var packed := load(HUNYUAN_SCENE_PATH) as PackedScene
	if packed == null:
		push_error("Cannot load issue-147 Hunyuan visual GLB: %s" % HUNYUAN_SCENE_PATH)
		return
	var visual := packed.instantiate()
	visual.name = "HunyuanVisualOnly"
	var quaternion := Quaternion(0.6511913, 0.27745163, 0.27848938, -0.64916414)
	visual.transform = Transform3D(
		Basis(quaternion).scaled(Vector3.ONE * 1.5582858),
		Vector3(2.9209783, -0.205319, 3.703508)
	)
	_apply_hunyuan_material(visual)
	add_child(visual)
	set_meta("hunyuan_visual_loaded", true)


func _build_authored_room() -> void:
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)
	_add_box("AuthoredFloor", Vector3((WEST + EAST) * 0.5, FLOOR_Y - 0.06,
		(SOUTH + NORTH) * 0.5), Vector3(EAST - WEST, 0.12, NORTH - SOUTH),
		_materials.floor, self, true)
	_add_boundaries(boundaries)
	_add_box("ColumnObstacle", COLUMN_CENTER, COLUMN_SIZE, null, boundaries, false)
	if variant_id == "source_surface_cleanup":
		_add_surface_cleanup(boundaries)
	var net := StaticBody3D.new()
	net.name = "SafetyNet"
	net.position = Vector3((WEST + EAST) * 0.5, FLOOR_Y - 2.0, (SOUTH + NORTH) * 0.5)
	add_child(net)
	var net_shape := CollisionShape3D.new()
	net_shape.name = "CollisionShape3D"
	var net_box := BoxShape3D.new()
	net_box.size = Vector3(EAST - WEST + 2.0, 0.05, NORTH - SOUTH + 2.0)
	net_shape.shape = net_box
	net.add_child(net_shape)


func _add_boundaries(parent: Node3D) -> void:
	var center_y := (FLOOR_Y + CEILING_Y) * 0.5
	var wall_height := CEILING_Y - FLOOR_Y
	_add_box("WestBoundary", Vector3(WEST - WALL_THICKNESS * 0.5,
		center_y, (SOUTH + NORTH) * 0.5),
		Vector3(WALL_THICKNESS, wall_height, NORTH - SOUTH), null, parent, false)
	_add_box("EastBoundary", Vector3(EAST + WALL_THICKNESS * 0.5,
		center_y, (SOUTH + NORTH) * 0.5),
		Vector3(WALL_THICKNESS, wall_height, NORTH - SOUTH), null, parent, false)
	_add_box("SouthBoundary", Vector3((WEST + EAST) * 0.5,
		center_y, SOUTH - WALL_THICKNESS * 0.5),
		Vector3(EAST - WEST, wall_height, WALL_THICKNESS), null, parent, false)
	_add_box("NorthBoundary", Vector3((WEST + EAST) * 0.5,
		center_y, NORTH + WALL_THICKNESS * 0.5),
		Vector3(EAST - WEST, wall_height, WALL_THICKNESS), null, parent, false)


func _add_surface_cleanup(parent: Node3D) -> void:
	var center_y := (FLOOR_Y + CEILING_Y) * 0.5
	var wall_height := CEILING_Y - FLOOR_Y
	_add_box("SourceWestWall", Vector3(WEST + 0.025, center_y, (SOUTH + NORTH) * 0.5),
		Vector3(0.05, wall_height, NORTH - SOUTH), _materials.wall, parent, true, false)
	_add_box("SourceEastWall", Vector3(EAST - 0.025, center_y, (SOUTH + NORTH) * 0.5),
		Vector3(0.05, wall_height, NORTH - SOUTH), _materials.wall, parent, true, false)
	_add_box("SourceSouthWall", Vector3((WEST + EAST) * 0.5, center_y, SOUTH + 0.025),
		Vector3(EAST - WEST, wall_height, 0.05), _materials.wall, parent, true, false)
	_add_box("SourceNorthWall", Vector3((WEST + EAST) * 0.5, center_y, NORTH - 0.025),
		Vector3(EAST - WEST, wall_height, 0.05), _materials.wall, parent, true, false)
	_add_box("SourceCeiling", Vector3((WEST + EAST) * 0.5, CEILING_Y - 0.025,
		(SOUTH + NORTH) * 0.5), Vector3(EAST - WEST, 0.05, NORTH - SOUTH),
		_materials.ceiling, parent, true, false)
	_add_box("SourceColumnCover", COLUMN_CENTER, COLUMN_SIZE, _materials.column, parent, true, false)


func _build_player() -> void:
	var player := PLAYER_SCENE.instantiate()
	player.name = "Player"
	player.position = Vector3(-4.4, FLOOR_Y + 0.6, -4.0)
	add_child(player)


func _material(material_id: String, filename: String) -> StandardMaterial3D:
	var texture_path := "res://assets/psx_extension/textures/%s" % filename
	var texture := load(texture_path) as Texture2D
	if texture == null:
		push_error("Missing source-video PSX texture: %s" % texture_path)
	var material := StandardMaterial3D.new()
	material.resource_name = material_id
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.uv1_scale = Vector3(4.0, 4.0, 1.0)
	return material


func _apply_hunyuan_material(instance: Node) -> void:
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	for child in instance.find_children("*", "MeshInstance3D", true, false):
		(child as MeshInstance3D).material_override = material


func _add_box(label: String, center: Vector3, size: Vector3,
		material: Material, parent: Node3D, visible: bool,
		collidable: bool = true) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	parent.add_child(body)
	if collidable:
		var collision := CollisionShape3D.new()
		collision.name = "CollisionShape3D"
		var shape := BoxShape3D.new()
		shape.size = size
		collision.shape = shape
		body.add_child(collision)
	if visible:
		var mesh := MeshInstance3D.new()
		mesh.name = "%sVisual" % label
		var box := BoxMesh.new()
		box.size = size
		mesh.mesh = box
		mesh.material_override = material
		body.add_child(mesh)
