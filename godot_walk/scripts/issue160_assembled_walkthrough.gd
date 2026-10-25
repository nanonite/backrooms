extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const COLUMN_SCENE := preload("res://scenes/issue160_column_connector.tscn")
const POCKET_SCENE := preload("res://scenes/issue160_pocket_connector.tscn")
const LIBRARY_PRESET := preload("res://scripts/library_psx_preset.gd")
const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const FLOOR_Y := -1.27099049
const COLUMN_TO_POCKET := Vector3(3.5, 0.0, -3.8)

@export var add_player := true
@export var apply_psx_preset := true


func _ready() -> void:
	_set_assembly_contract()
	var column := COLUMN_SCENE.instantiate()
	column.name = "ColumnRoom"
	column.position = Vector3.ZERO
	column.include_player = false
	column.enable_environment = true
	column.apply_psx_preset = false
	add_child(column)
	var pocket := POCKET_SCENE.instantiate()
	pocket.name = "PocketRoom"
	pocket.position = COLUMN_TO_POCKET
	pocket.include_player = false
	pocket.enable_environment = false
	pocket.apply_psx_preset = false
	add_child(pocket)
	_add_boundary_group()
	_add_authored_transition()
	if add_player:
		_build_player()
	if apply_psx_preset:
		LIBRARY_PRESET.new().configure(self)


func _set_assembly_contract() -> void:
	set_meta("room_id", "issue160_column_to_pocket_authored_assembly_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("generation_ready", false)
	set_meta("operator_approved", false)
	set_meta("walk_route", PackedVector2Array([
		Vector2(-3.5, 0.0), Vector2(-3.4, 2.6), Vector2(-1.8, 2.6),
		Vector2(2.4, 2.6), Vector2(2.4, 3.1), Vector2(4.3, 3.1),
		Vector2(8.7, 3.1), Vector2(8.7, 9.2), Vector2(4.3, 9.2),
		Vector2(4.3, 3.1), Vector2(2.4, 3.1), Vector2(-3.5, 0.0),
	]))
	set_meta("walk_envelope", Rect2(-4.4, -3.8, 13.9, 13.8))
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray([
		"AuthoredFloor", "AuthoredPlanarRouteFloor", "ConnectorThreshold",
	]))
	set_meta("boundary_probe_origin", Vector3(2.5, FLOOR_Y + 0.6, 3.1))
	set_meta("boundary_test_path", "PocketRoom/AuthoredBoundaries/EastBoundary")
	set_meta("observed_openings", PackedStringArray())
	set_meta("authored_connection", {
		"id": "column_east__pocket_west_v1",
		"status": "authored_not_source_observed",
		"column_socket_local": Vector3(3.5, FLOOR_Y, 3.1),
		"pocket_socket_local": Vector3(0.0, FLOOR_Y, 6.9),
		"pocket_transform": COLUMN_TO_POCKET,
		"world_center": Vector3(3.5, FLOOR_Y, 3.1),
		"clear_size": Vector2(2.0, 2.1),
		"approach_depth": 1.2,
	})
	set_meta("tested_connectors", PackedStringArray(["column_east__pocket_west_v1"]))


func _add_boundary_group() -> void:
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)


func _add_authored_transition() -> void:
	var trim := StandardMaterial3D.new()
	trim.albedo_color = Color(0.37, 0.34, 0.23)
	trim.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var floor_texture := load("res://assets/psx_extension/textures/floor_source_video.png") as Texture2D
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_texture = floor_texture
	floor_material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	floor_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	floor_material.uv1_scale = Vector3(4.0, 4.0, 1.0)
	ROOM_GEOMETRY.add_box(self, "ConnectorThreshold",
		Vector3(3.5, FLOOR_Y - 0.06, 3.1), Vector3(0.24, 0.12, 2.0),
		floor_material)
	ROOM_GEOMETRY.add_box(self, "ConnectorJambNorth",
		Vector3(3.5, FLOOR_Y + 1.05, 2.1), Vector3(0.18, 2.1, 0.12), trim, true, false)
	ROOM_GEOMETRY.add_box(self, "ConnectorJambSouth",
		Vector3(3.5, FLOOR_Y + 1.05, 4.1), Vector3(0.18, 2.1, 0.12), trim, true, false)
	ROOM_GEOMETRY.add_box(self, "ConnectorHeader",
		Vector3(3.5, FLOOR_Y + 2.1, 3.1), Vector3(0.18, 0.12, 2.0), trim, true, false)


func _build_player() -> void:
	var player := PLAYER_SCENE.instantiate()
	player.name = "Player"
	player.position = Vector3(-3.5, FLOOR_Y + 0.6, 0.0)
	add_child(player)
