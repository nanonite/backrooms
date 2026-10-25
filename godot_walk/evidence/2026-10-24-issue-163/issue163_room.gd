extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const TEXTURE_ROOT := "res://evidence/2026-10-24-issue-163/source_textures/"
const HUNYUAN_VISUAL := "res://evidence/2026-10-24-issue-163/worldgen/hunyuan_layers.glb"
const FLOOR_Y := 0.0
const CEILING_Y := 3.2
const ROOM_WEST := -6.0
const ROOM_EAST := 6.0
const ROOM_SOUTH := -5.0
const ROOM_NORTH := 5.0
const HALL_END := 13.0
const COLUMN_CENTER := Vector3(-2.0, CEILING_Y * 0.5, 0.0)
const COLUMN_SIZE := Vector3(1.4, CEILING_Y, 1.4)

var materials: Dictionary = {}
var hunyuan_visual: Node3D


func _ready() -> void:
	_set_contract()
	_build_environment()
	_build_materials()
	_build_hunyuan_visual()
	_build_authored_room()
	_build_player()
	PSX_PRESET.new().configure(self)
	# The preset defaults to unapproved; preserve this room's operator decision.
	set_meta("operator_approved", true)
	set_meta("room_id", "room_large_video_psx_v1")


func _set_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("walk_route", PackedVector2Array([
		Vector2(-4.0, 0.0), Vector2(-4.0, 2.6), Vector2(0.0, 2.6),
		Vector2(4.0, 2.6), Vector2(4.0, 0.0), Vector2(9.0, 0.0),
	]))
	set_meta("walk_envelope", Rect2(-6.0, -5.0, 19.0, 10.0))
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
	set_meta("boundary_probe_origin", Vector3(4.0, 0.6, 3.0))
	set_meta("boundary_test_path", "AuthoredBoundaries/EastSouthBoundary")
	set_meta("hunyuan_visual_only", true)
	set_meta("hunyuan_stage_status", "blocked_vram_before_panorama")
	set_meta("source_video", "data/videos/room_large.mp4")
	set_meta("source_seed_frame", "room_large_frame_0013.png")


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
	compositor.compositor_effects = [effect]
	world.environment = environment
	world.compositor = compositor
	add_child(world)
	var light := DirectionalLight3D.new()
	light.name = "KeyLight"
	light.rotation = Vector3(deg_to_rad(-48.0), deg_to_rad(35.0), 0.0)
	light.light_energy = 0.65
	add_child(light)


func _build_materials() -> void:
	materials.wallpaper = _textured_material("wallpaper.png", Vector3(5.0, 3.0, 1.0))
	materials.floor = _textured_material("floor.png", Vector3.ONE)
	materials.ceiling = _textured_material("ceiling.png", Vector3.ONE)
	materials.ceiling.cull_mode = BaseMaterial3D.CULL_DISABLED
	materials.column = _textured_material("column_face.png", Vector3(1.5, 3.0, 1.0))
	materials.trim = _solid_material(Color(0.77, 0.73, 0.58))
	materials.lamp = _solid_material(Color(1.0, 0.97, 0.78))


func _build_hunyuan_visual() -> void:
	if not ResourceLoader.exists(HUNYUAN_VISUAL):
		set_meta("hunyuan_visual_loaded", false)
		return
	var packed := load(HUNYUAN_VISUAL) as PackedScene
	if packed == null:
		push_error("Cannot import SceneGen visual GLB: %s" % HUNYUAN_VISUAL)
		return
	hunyuan_visual = packed.instantiate()
	hunyuan_visual.name = "HunyuanGeneratedVisualOnly"
	add_child(hunyuan_visual)
	for instance in hunyuan_visual.find_children("*", "MeshInstance3D", true, false):
		var material := StandardMaterial3D.new()
		material.vertex_color_use_as_albedo = true
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		(instance as MeshInstance3D).material_override = material
	set_meta("hunyuan_visual_loaded", true)
	set_meta("hunyuan_transform", "identity; scale and registration unaccepted")


func _build_authored_room() -> void:
	var visuals := Node3D.new()
	visuals.name = "AuthoredVisuals"
	add_child(visuals)
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)
	_add_walkable_floor(visuals, boundaries)
	_add_shell(visuals, boundaries)
	_add_box("SingleColumnVisual", COLUMN_CENTER, COLUMN_SIZE, materials.column, visuals, null, false)
	_add_box("ColumnObstacle", COLUMN_CENTER, COLUMN_SIZE, null, null, boundaries, true)
	_add_ceiling(visuals)
	_add_safety_net()


func _add_shell(visuals: Node3D, boundaries: Node3D) -> void:
	var mid_y := CEILING_Y * 0.5
	var wall_h := CEILING_Y
	_add_box("WestWall", Vector3(ROOM_WEST - 0.06, mid_y, 0.0), Vector3(0.12, wall_h, 10.0), materials.wallpaper, visuals, boundaries, true)
	_add_box("SouthWall", Vector3(0.0, mid_y, ROOM_NORTH + 0.06), Vector3(12.0, wall_h, 0.12), materials.wallpaper, visuals, boundaries, true)
	_add_box("NorthWall", Vector3(0.0, mid_y, ROOM_SOUTH - 0.06), Vector3(12.0, wall_h, 0.12), materials.wallpaper, visuals, boundaries, true)
	_add_box("EastSouthBoundary", Vector3(ROOM_EAST + 0.06, mid_y, 3.25), Vector3(0.12, wall_h, 3.5), materials.wallpaper, visuals, boundaries, true)
	_add_box("EastNorthBoundary", Vector3(ROOM_EAST + 0.06, mid_y, -3.25), Vector3(0.12, wall_h, 3.5), materials.wallpaper, visuals, boundaries, true)
	_add_box("PassageHeader", Vector3(ROOM_EAST + 0.06, 2.9, 0.0), Vector3(0.12, 0.6, 3.0), materials.trim, visuals, boundaries, true)
	_add_box("HallWestWall", Vector3(9.5, mid_y, -1.56), Vector3(7.0, wall_h, 0.12), materials.wallpaper, visuals, boundaries, true)
	_add_box("HallEastWall", Vector3(9.5, mid_y, 1.56), Vector3(7.0, wall_h, 0.12), materials.wallpaper, visuals, boundaries, true)
	_add_box("HallEndBoundary", Vector3(HALL_END + 0.06, mid_y, 0.0), Vector3(0.12, wall_h, 3.0), materials.wallpaper, visuals, boundaries, true)


func _add_ceiling(visuals: Node3D) -> void:
	var ceiling := MeshInstance3D.new()
	ceiling.name = "RoomAndHallCeiling"
	ceiling.mesh = _l_surface_mesh(CEILING_Y, true)
	ceiling.material_override = materials.ceiling
	visuals.add_child(ceiling)
	for x in [-3.5, 1.0, 4.0]:
		_add_box("CeilingLight_%s" % str(x), Vector3(x, CEILING_Y - 0.035, -1.0), Vector3(1.2, 0.025, 0.55), materials.lamp, visuals, null, false)
	_add_box("HallCeilingLight", Vector3(9.5, CEILING_Y - 0.035, 0.0), Vector3(1.2, 0.025, 0.55), materials.lamp, visuals, null, false)


func _add_walkable_floor(visuals: Node3D, boundaries: Node3D) -> void:
	var floor_visual := MeshInstance3D.new()
	floor_visual.name = "ContinuousWalkableFloorVisual"
	floor_visual.mesh = _l_surface_mesh(FLOOR_Y + 0.001, false)
	floor_visual.material_override = materials.floor
	visuals.add_child(floor_visual)
	var body := StaticBody3D.new()
	body.name = "WalkableFloor"
	boundaries.add_child(body)
	_add_floor_shape(body, "MainFloorShape", Vector3(0.0, -0.06, 0.0), Vector3(12.0, 0.12, 10.0))
	_add_floor_shape(body, "HallFloorShape", Vector3(9.5, -0.06, 0.0), Vector3(7.0, 0.12, 3.0))


func _add_floor_shape(body: StaticBody3D, label: String, center: Vector3, size: Vector3) -> void:
	var collision := CollisionShape3D.new()
	collision.name = label
	collision.position = center
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)


func _l_surface_mesh(height: float, reverse_winding: bool) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var rectangles := [Rect2(ROOM_WEST, ROOM_SOUTH, 12.0, 10.0), Rect2(ROOM_EAST, -1.5, 7.0, 3.0)]
	for rectangle: Rect2 in rectangles:
		_append_surface_rect(rectangle, height, reverse_winding, vertices, normals, uvs)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


func _append_surface_rect(rectangle: Rect2, height: float, reverse_winding: bool, vertices: PackedVector3Array, normals: PackedVector3Array, uvs: PackedVector2Array) -> void:
	var left := rectangle.position.x
	var right := rectangle.end.x
	var back := rectangle.position.y
	var front := rectangle.end.y
	var points := [Vector3(left, height, back), Vector3(left, height, front), Vector3(right, height, front), Vector3(right, height, back)]
	var indices := [0, 1, 2, 0, 2, 3]
	if reverse_winding:
		indices = [0, 2, 1, 0, 3, 2]
	for index: int in indices:
		var point: Vector3 = points[index]
		vertices.append(point)
		normals.append(Vector3.DOWN if reverse_winding else Vector3.UP)
		uvs.append(Vector2(point.x, point.z) * 0.5)


func _add_safety_net() -> void:
	var body := StaticBody3D.new()
	body.name = "SafetyNet"
	body.position = Vector3(3.5, -4.0, 0.0)
	add_child(body)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(23.0, 0.1, 12.0)
	collision.shape = shape
	body.add_child(collision)


func _add_box(label: String, center: Vector3, size: Vector3, material: Material, visual_parent: Node3D, collision_parent: Node3D, collidable: bool) -> void:
	if visual_parent != null and material != null:
		var instance := MeshInstance3D.new()
		instance.name = label + "Visual"
		instance.position = center
		var mesh := BoxMesh.new()
		mesh.size = size
		instance.mesh = mesh
		instance.material_override = material
		visual_parent.add_child(instance)
	if collidable and collision_parent != null:
		var body := StaticBody3D.new()
		body.name = label
		body.position = center
		collision_parent.add_child(body)
		var collision := CollisionShape3D.new()
		collision.name = "CollisionShape3D"
		var shape := BoxShape3D.new()
		shape.size = size
		collision.shape = shape
		body.add_child(collision)


func _build_player() -> void:
	var player := PLAYER_SCENE.instantiate()
	player.name = "Player"
	player.position = Vector3(-4.0, FLOOR_Y + 0.6, 0.0)
	add_child(player)


func _textured_material(filename: String, uv_scale: Vector3) -> StandardMaterial3D:
	var image := Image.new()
	var image_path := ProjectSettings.globalize_path(TEXTURE_ROOT + filename)
	if image.load(image_path) != OK:
		push_error("Missing direct-source material texture: %s" % filename)
		return StandardMaterial3D.new()
	var texture := ImageTexture.create_from_image(image)
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.uv1_scale = uv_scale
	return material


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material
