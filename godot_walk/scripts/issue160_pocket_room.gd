extends "res://scripts/hunyuan_psx_round1.gd"

const LIBRARY_PRESET := preload("res://scripts/library_psx_preset.gd")
const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const POCKET_ROOT := "res://evidence/2026-10-21-issue-148/early-pocket/generated/"
const CLEAR_WIDTH := 2.0
const CLEAR_HEIGHT := 2.1
const SOCKET_Z := 6.9
const WALL_HEIGHT := 2.4

@export var connector_open := false
@export var include_player := true
@export var enable_environment := true
@export var apply_psx_preset := true


func _ready() -> void:
	_set_design_contract()
	if enable_environment:
		_build_environment()
	_build_materials()
	for material: StandardMaterial3D in _materials.values():
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
	_build_visual_source()
	_build_authored_room()
	if include_player:
		_build_player()
	if apply_psx_preset:
		LIBRARY_PRESET.new().configure(self)
	set_meta("room_id", "godot_authored_early_pocket_connector_v1")
	set_meta("room_version", 1)
	set_meta("connector_open", connector_open)
	set_meta("visual_source", POCKET_ROOT + "early_pocket_visual.glb")
	set_meta("collision_source_reference", POCKET_ROOT + "early_pocket_collision.glb")


func _set_design_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("generation_ready", false)
	set_meta("operator_approved", false)
	set_meta("walk_route", PackedVector2Array([
		Vector2(0.8, 0.8), Vector2(5.2, 0.8), Vector2(5.2, 6.9),
		Vector2(5.2, 13.0), Vector2(0.8, 13.0), Vector2(0.8, 6.9),
	]))
	set_meta("walk_envelope", Rect2(0.0, 0.0, 6.0, 13.8))
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["AuthoredPlanarRouteFloor", "ConnectorThreshold"]))
	set_meta("boundary_probe_origin", Vector3(3.0, FLOOR_Y + 0.6, 6.9))
	set_meta("boundary_test_path", "AuthoredBoundaries/WestBoundary")
	set_meta("authored_socket", {
		"id": "pocket_west_v1",
		"floor_center": Vector3(0.0, FLOOR_Y, SOCKET_Z),
		"outward_normal": Vector3.LEFT,
		"clear_size": Vector2(CLEAR_WIDTH, CLEAR_HEIGHT),
		"approach_depth": 1.2,
		"open": connector_open,
	})
	set_meta("observed_openings", PackedStringArray())
	set_meta("tested_connectors", PackedStringArray())
	set_meta("authored_boundaries", PackedStringArray([
		"report-derived box floor, ceiling and perimeter", "paired west socket opening when enabled",
	]))


func _build_visual_source() -> void:
	var visual := _load_original_glb("early_pocket_visual.glb")
	if visual == null:
		push_error("Missing protected early-pocket visual GLB")
		get_tree().quit(2)
		return
	visual.name = "AuthoredPocketVisual"
	add_child(visual)
	for instance in visual.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := instance as MeshInstance3D
		var center_y := mesh_instance.mesh.get_aabb().get_center().y
		mesh_instance.mesh = _textured_plane(mesh_instance.mesh as ArrayMesh)
		mesh_instance.material_override = _materials.floor if center_y < 0.0 else _materials.ceiling
	_build_report_visuals()


func _build_report_visuals() -> void:
	var report: Variant = JSON.parse_string(FileAccess.get_file_as_string(
		POCKET_ROOT + "early_pocket_scene_report.json"))
	if not report is Dictionary:
		push_error("Invalid early-pocket authored surface report")
		get_tree().quit(2)
		return
	var visuals := Node3D.new()
	visuals.name = "AuthoredPocketVisualDetails"
	add_child(visuals)
	var trim := _solid_material(Color(0.37, 0.34, 0.23))
	var lamp := _solid_material(Color(1.0, 0.97, 0.76))
	for surface: Dictionary in report.visual.authored_visual_surfaces:
		var label: String = surface.name
		if label.contains("wallpaper") or label in ["authored_carpet_visual", "authored_ceiling_visual"]:
			continue
		var material: Material = _materials.wall
		if label.contains("grid"):
			material = trim
		elif label.contains("light"):
			material = lamp
		if connector_open and label == "authored_room_boundary_west":
			_add_west_socket_visual(visuals, material)
		else:
			_add_box(label + "Visual", _vector(surface.center_world_m),
				_vector(surface.size_m), material, visuals, true, false)


func _add_west_socket_visual(parent: Node3D, material: Material) -> void:
	var low_z := SOCKET_Z - CLEAR_WIDTH * 0.5
	var high_z := SOCKET_Z + CLEAR_WIDTH * 0.5
	_add_box("WestVisualBeforeSocket", Vector3(-0.06, FLOOR_Y + WALL_HEIGHT * 0.5,
		(-0.12 + low_z) * 0.5), Vector3(WALL_THICKNESS, WALL_HEIGHT, low_z + 0.12),
		material, parent, true, false)
	_add_box("WestVisualAfterSocket", Vector3(-0.06, FLOOR_Y + WALL_HEIGHT * 0.5,
		(high_z + 13.92) * 0.5), Vector3(WALL_THICKNESS, WALL_HEIGHT, 13.92 - high_z),
		material, parent, true, false)
	_add_box("WestVisualSocketLintel", Vector3(-0.06,
		FLOOR_Y + (WALL_HEIGHT + CLEAR_HEIGHT) * 0.5, SOCKET_Z),
		Vector3(WALL_THICKNESS, WALL_HEIGHT - CLEAR_HEIGHT, CLEAR_WIDTH),
		material, parent, true, false)


func _build_authored_room() -> void:
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)
	ROOM_GEOMETRY.add_box(self, "AuthoredPlanarRouteFloor",
		Vector3(3.0, FLOOR_Y - 0.06, 6.9), Vector3(6.0, 0.12, 13.8), null, false)
	ROOM_GEOMETRY.add_box(self, "AuthoredCeilingCollision",
		Vector3(3.0, CEILING_Y + 0.06, 6.9), Vector3(6.0, 0.12, 13.8), null, false)
	_add_pocket_boundaries(boundaries)
	ROOM_GEOMETRY.add_box(self, "SafetyNet", Vector3(3.0, FLOOR_Y - 2.0, 6.9),
		Vector3(8.0, 0.05, 16.0), null, false)
	_add_socket_marker()


func _add_pocket_boundaries(parent: Node3D) -> void:
	_add_boundary_group(parent, "WestBoundary", Vector3(-0.06, FLOOR_Y + 1.2, 6.9),
		Vector3(WALL_THICKNESS, WALL_HEIGHT, 14.04), true)
	_add_boundary_group(parent, "EastBoundary", Vector3(6.06, FLOOR_Y + 1.2, 6.9),
		Vector3(WALL_THICKNESS, WALL_HEIGHT, 14.04), false)
	_add_boundary_group(parent, "SouthBoundary", Vector3(3.0, FLOOR_Y + 1.2, -0.06),
		Vector3(6.0, WALL_HEIGHT, WALL_THICKNESS), false)
	_add_boundary_group(parent, "NorthBoundary", Vector3(3.0, FLOOR_Y + 1.2, 13.86),
		Vector3(6.0, WALL_HEIGHT, WALL_THICKNESS), false)


func _add_boundary_group(parent: Node3D, label: String, center: Vector3,
		size: Vector3, west_socket: bool) -> void:
	var group := Node3D.new()
	group.name = label
	parent.add_child(group)
	if west_socket and connector_open:
		_add_west_socket_collision(group)
	else:
		ROOM_GEOMETRY.add_box(group, "Wall", center, size, null, false)


func _add_west_socket_collision(parent: Node3D) -> void:
	var low_z := SOCKET_Z - CLEAR_WIDTH * 0.5
	var high_z := SOCKET_Z + CLEAR_WIDTH * 0.5
	ROOM_GEOMETRY.add_box(parent, "WallBeforeSocket",
		Vector3(-0.06, FLOOR_Y + WALL_HEIGHT * 0.5, (-0.12 + low_z) * 0.5),
		Vector3(WALL_THICKNESS, WALL_HEIGHT, low_z + 0.12), null, false)
	ROOM_GEOMETRY.add_box(parent, "WallAfterSocket",
		Vector3(-0.06, FLOOR_Y + WALL_HEIGHT * 0.5, (high_z + 13.92) * 0.5),
		Vector3(WALL_THICKNESS, WALL_HEIGHT, 13.92 - high_z), null, false)
	ROOM_GEOMETRY.add_box(parent, "SocketLintel",
		Vector3(-0.06, FLOOR_Y + (WALL_HEIGHT + CLEAR_HEIGHT) * 0.5, SOCKET_Z),
		Vector3(WALL_THICKNESS, WALL_HEIGHT - CLEAR_HEIGHT, CLEAR_WIDTH), null, false)


func _add_socket_marker() -> void:
	var socket := Node3D.new()
	socket.name = "Socket_West_Authored"
	socket.position = Vector3(0.0, FLOOR_Y, SOCKET_Z)
	socket.set_meta("outward_normal", Vector3.LEFT)
	socket.set_meta("clear_width", CLEAR_WIDTH)
	socket.set_meta("clear_height", CLEAR_HEIGHT)
	add_child(socket)


func _build_player() -> void:
	var player := PLAYER_SCENE.instantiate()
	player.name = "Player"
	player.position = Vector3(0.8, FLOOR_Y + 0.6, 0.8)
	add_child(player)


func _load_original_glb(filename: String) -> Node3D:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	if document.append_from_file(POCKET_ROOT + filename, state) != OK:
		return null
	return document.generate_scene(state) as Node3D


func _textured_plane(source: ArrayMesh) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	for surface in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var coordinates := PackedVector2Array()
		for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
			coordinates.append(Vector2(vertex.x, vertex.z) * 0.25)
		arrays[Mesh.ARRAY_TEX_UV] = coordinates
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _vector(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])
