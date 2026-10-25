extends "res://scripts/hunyuan_psx_column_box.gd"

const LIBRARY_PRESET := preload("res://scripts/library_psx_preset.gd")
const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const BOUNDED_VISUAL := "res://evidence/2026-10-22-issue-160/bounded_hunyuan_visual.glb"
const ROOM_ID := "godot_later_bay_column_bounded_v1"
const ROOM_POLYGON_POINTS := [
	Vector2(-4.4, -1.2), Vector2(0.0, -1.2), Vector2(3.5, 1.2),
	Vector2(3.5, 5.6), Vector2(-0.3, 5.6), Vector2(-4.1, 3.7),
]
const C01_COLLISION_EXPANSION := PATCH_CLEARANCE * 2.0
const C02_MIN := Vector3(-1.0, FLOOR_Y, 4.025)
const C02_MAX := Vector3(-0.425, CEILING_Y, 4.825)
const EAST_SOCKET_Z := 3.1
const SOCKET_WIDTH := 2.0
const SOCKET_HEIGHT := 2.1

@export var connector_open := false
@export var include_player := true
@export var enable_environment := true
@export var apply_psx_preset := true


func _ready() -> void:
	variant_id = "four_sided_box"
	_set_design_contract()
	if enable_environment:
		_build_environment()
	_build_materials()
	_build_bounded_visual()
	_build_room_shell()
	_build_obstacles()
	if include_player:
		_build_player()
	if apply_psx_preset:
		LIBRARY_PRESET.new().configure(self)
	set_meta("room_id", ROOM_ID)
	set_meta("room_version", 1)
	set_meta("connector_open", connector_open)
	set_meta("visual_asset", BOUNDED_VISUAL)


func _set_design_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("generation_ready", false)
	set_meta("operator_approved", false)
	set_meta("walk_route", PackedVector2Array([
		Vector2(-3.5, 0.0), Vector2(-3.4, 2.6), Vector2(-1.8, 2.6),
		Vector2(2.4, 2.6), Vector2(2.4, 3.1), Vector2(2.4, 4.5),
	]))
	set_meta("walk_envelope", Rect2(-4.4, -1.2, 7.9, 6.8))
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["AuthoredFloor", "ConnectorThreshold"]))
	set_meta("boundary_probe_origin", Vector3(2.5, FLOOR_Y + 0.6, 3.1))
	set_meta("boundary_test_path", "AuthoredBoundaries/EastBoundary")
	set_meta("room_polygon_xz_authored", ROOM_POLYGON_POINTS)
	set_meta("authored_socket", {
		"id": "column_east_v1",
		"floor_center": Vector3(3.5, FLOOR_Y, EAST_SOCKET_Z),
		"outward_normal": Vector3.RIGHT,
		"clear_size": Vector2(SOCKET_WIDTH, SOCKET_HEIGHT),
		"approach_depth": 1.2,
		"open": connector_open,
	})
	set_meta("observed_openings", PackedStringArray())
	set_meta("tested_connectors", PackedStringArray())
	set_meta("authored_boundaries", PackedStringArray([
		"polygon floor", "polygon ceiling", "six perimeter closures", "C01 collision proxy",
		"C02 estimated authored prism and collider",
	]))


func _build_bounded_visual() -> void:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(ProjectSettings.globalize_path(BOUNDED_VISUAL), state) != OK:
		push_error("Missing bounded Hunyuan visual derivative: %s" % BOUNDED_VISUAL)
		get_tree().quit(2)
		return
	var visual := document.generate_scene(state) as Node3D
	if visual == null:
		push_error("Cannot instantiate bounded Hunyuan visual derivative")
		get_tree().quit(2)
		return
	visual.name = "BoundedHunyuanVisual"
	_apply_hunyuan_material(visual)
	add_child(visual)
	set_meta("hunyuan_visual_loaded", true)


func _build_room_shell() -> void:
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)
	ROOM_GEOMETRY.add_polygon_slab(self, "AuthoredFloor", PackedVector2Array(ROOM_POLYGON_POINTS),
		FLOOR_Y, _materials.floor, true)
	ROOM_GEOMETRY.add_polygon_slab(self, "AuthoredCeiling", PackedVector2Array(ROOM_POLYGON_POINTS),
		CEILING_Y, _materials.ceiling, false)
	_build_perimeter(boundaries)
	_build_safety_net()
	_add_socket_marker()


func _build_perimeter(parent: Node3D) -> void:
	var edge_names := ["SouthBoundary", "SoutheastBoundary", "EastBoundary",
		"NorthBoundary", "NorthwestBoundary", "WestBoundary"]
	var polygon := PackedVector2Array(ROOM_POLYGON_POINTS)
	for index in polygon.size():
		var start := polygon[index]
		var end := polygon[(index + 1) % polygon.size()]
		var edge := Node3D.new()
		edge.name = edge_names[index]
		parent.add_child(edge)
		if index == 2 and connector_open:
			_add_east_socket_walls(edge, start, end)
		else:
			ROOM_GEOMETRY.add_wall_segment(edge, "Wall", start, end,
				FLOOR_Y, CEILING_Y - FLOOR_Y, WALL_THICKNESS, _materials.wall)


func _add_east_socket_walls(parent: Node3D, start: Vector2, end: Vector2) -> void:
	var opening_start := EAST_SOCKET_Z - SOCKET_WIDTH * 0.5
	var opening_end := EAST_SOCKET_Z + SOCKET_WIDTH * 0.5
	var amount_start := (opening_start - start.y) / (end.y - start.y)
	var amount_end := (opening_end - start.y) / (end.y - start.y)
	ROOM_GEOMETRY.add_wall_segment(parent, "WallBeforeSocket", start,
		ROOM_GEOMETRY.interpolate(start, end, amount_start), FLOOR_Y,
		CEILING_Y - FLOOR_Y, WALL_THICKNESS, _materials.wall)
	ROOM_GEOMETRY.add_wall_segment(parent, "WallAfterSocket",
		ROOM_GEOMETRY.interpolate(start, end, amount_end), end,
		FLOOR_Y, CEILING_Y - FLOOR_Y, WALL_THICKNESS, _materials.wall)
	ROOM_GEOMETRY.add_box(parent, "SocketLintel",
		Vector3(3.5, FLOOR_Y + (CEILING_Y - FLOOR_Y + SOCKET_HEIGHT) * 0.5, EAST_SOCKET_Z),
		Vector3(WALL_THICKNESS, CEILING_Y - FLOOR_Y - SOCKET_HEIGHT, SOCKET_WIDTH),
		_materials.wall)


func _build_obstacles() -> void:
	var boundaries := get_node("AuthoredBoundaries") as Node3D
	_add_accepted_c01_visual(boundaries)
	_add_c01_collision(boundaries)
	var c02_center := (C02_MIN + C02_MAX) * 0.5
	ROOM_GEOMETRY.add_box(boundaries, "C02EstimatedPrism", c02_center,
		C02_MAX - C02_MIN, _materials.column)
	set_meta("C01_visual_bounds", [VISUAL_BOX_MIN, VISUAL_BOX_MAX])
	set_meta("C01_collision_bounds", [
		VISUAL_BOX_MIN - Vector3(C01_COLLISION_EXPANSION * 0.5, 0.0, C01_COLLISION_EXPANSION * 0.5),
		VISUAL_BOX_MAX + Vector3(C01_COLLISION_EXPANSION * 0.5, 0.0, C01_COLLISION_EXPANSION * 0.5),
	])
	set_meta("C02_estimated_bounds", [C02_MIN, C02_MAX])


func _add_accepted_c01_visual(parent: Node3D) -> void:
	var cover := Node3D.new()
	cover.name = "FourSidedColumnBox"
	parent.add_child(cover)
	var center := (VISUAL_BOX_MIN + VISUAL_BOX_MAX) * 0.5
	var size := VISUAL_BOX_MAX - VISUAL_BOX_MIN
	var backing := MeshInstance3D.new()
	backing.name = "ClosedPrism"
	backing.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = _flat_patch_material()
	backing.mesh = mesh
	cover.add_child(backing)
	_add_prism_faces(cover, center, size)


func _add_c01_collision(parent: Node3D) -> void:
	var center := (VISUAL_BOX_MIN + VISUAL_BOX_MAX) * 0.5
	var size := VISUAL_BOX_MAX - VISUAL_BOX_MIN
	var collision_size := size + Vector3(C01_COLLISION_EXPANSION, 0.0, C01_COLLISION_EXPANSION)
	ROOM_GEOMETRY.add_box(parent, "C01Collision", center, collision_size, null, false)


func _build_safety_net() -> void:
	var center := Vector3(-0.45, FLOOR_Y - 2.0, 2.2)
	ROOM_GEOMETRY.add_box(self, "SafetyNet", center, Vector3(12.0, 0.05, 12.0), null, false)


func _add_socket_marker() -> void:
	var socket := Node3D.new()
	socket.name = "Socket_East_Authored"
	socket.position = Vector3(3.5, FLOOR_Y, EAST_SOCKET_Z)
	socket.set_meta("outward_normal", Vector3.RIGHT)
	socket.set_meta("clear_width", SOCKET_WIDTH)
	socket.set_meta("clear_height", SOCKET_HEIGHT)
	add_child(socket)


func _build_player() -> void:
	var player := PLAYER_SCENE.instantiate()
	player.name = "Player"
	player.position = Vector3(-3.5, FLOOR_Y + 0.6, 0.0)
	add_child(player)
