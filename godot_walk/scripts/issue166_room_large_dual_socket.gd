extends "res://scripts/issue164_room_large_connector.gd"

const WEST_SOCKET_CENTER := Vector3(-6.0, MODULE_FLOOR_Y, 0.0)
const WALL_X := -6.06
const WALL_HEIGHT := 3.2
const WALL_THICKNESS := 0.12

@export var open_hall_end := true
@export var open_west_back := true

var _candidate_player: CharacterBody3D
var _player_spawn := Vector3(-4.0, MODULE_FLOOR_Y + 0.6, 0.0)


func _ready() -> void:
	super._ready()
	if not open_hall_end:
		_close_hall_end()
	if open_west_back:
		_open_west_back()
	_set_dual_socket_contract()
	if _candidate_player != null:
		_player_spawn = _candidate_player.global_position


func _build_player() -> void:
	if include_player:
		super._build_player()
		_candidate_player = get_node_or_null("Player") as CharacterBody3D


func _reset_player() -> void:
	if _candidate_player == null:
		return
	_candidate_player.global_position = _player_spawn
	_candidate_player.velocity = Vector3.ZERO
	_candidate_player.reset_physics_interpolation()


func _close_hall_end() -> void:
	var boundaries := get_node_or_null("AuthoredBoundaries") as Node3D
	if boundaries == null:
		push_error("Large-room authored boundary root is missing")
		return
	for child_name in ["HallSocketNorthReturn", "HallSocketSouthReturn", "HallSocketHeader"]:
		var child := boundaries.get_node_or_null(child_name)
		if child != null:
			child.free()
	var socket := get_node_or_null("Socket_HallEnd_Authored")
	if socket != null:
		socket.free()
	ROOM_GEOMETRY.add_box(boundaries, "HallEndBoundary",
		Vector3(HALL_END_X, WALL_HEIGHT * 0.5, 0.0),
		Vector3(WALL_THICKNESS, WALL_HEIGHT, 3.0), materials.wallpaper, true, true)


func _open_west_back() -> void:
	var visuals := get_node_or_null("AuthoredVisuals") as Node3D
	var boundaries := get_node_or_null("AuthoredBoundaries") as Node3D
	if visuals == null or boundaries == null:
		push_error("Large-room shell is missing for the west-back socket")
		return
	var wall_visual := visuals.get_node_or_null("WestWallVisual")
	var wall_collision := boundaries.get_node_or_null("WestWall")
	if wall_visual == null or wall_collision == null:
		push_error("Large-room west wall cannot be adapted")
		return
	wall_visual.free()
	wall_collision.free()
	_add_west_returns(boundaries)
	var socket := Node3D.new()
	socket.name = "Socket_WestBack_Authored"
	socket.position = WEST_SOCKET_CENTER
	socket.set_meta("outward_normal", Vector3.LEFT)
	socket.set_meta("clear_width", SOCKET_WIDTH)
	socket.set_meta("clear_height", SOCKET_HEIGHT)
	socket.set_meta("approach_clearance_m", 1.2)
	add_child(socket)


func _add_west_returns(parent: Node3D) -> void:
	for side in [-1.0, 1.0]:
		var suffix := "Left" if side < 0.0 else "Right"
		ROOM_GEOMETRY.add_box(parent, "WestBackReturn_%s" % suffix,
			Vector3(WALL_X, WALL_HEIGHT * 0.5, side * 3.0),
			Vector3(WALL_THICKNESS, WALL_HEIGHT, 4.0), materials.wallpaper, true, true)
	ROOM_GEOMETRY.add_box(parent, "WestBackHeader",
		Vector3(WALL_X, (SOCKET_HEIGHT + WALL_HEIGHT) * 0.5, 0.0),
		Vector3(WALL_THICKNESS, WALL_HEIGHT - SOCKET_HEIGHT, SOCKET_WIDTH),
		materials.wallpaper, true, true)


func _set_dual_socket_contract() -> void:
	var opened := PackedStringArray()
	if open_hall_end:
		opened.append("hall_end")
	if open_west_back:
		opened.append("west_back")
	set_meta("room_id", "godot_source_textured_large_room_dual_socket_candidate_v1")
	set_meta("room_version", 1)
	set_meta("operator_approved", false)
	set_meta("generation_ready", false)
	set_meta("open_socket_ids", opened)
	set_meta("candidate_socket", {
		"id": "west_back",
		"floor_center": WEST_SOCKET_CENTER,
		"outward_normal": Vector3.LEFT,
		"clear_size": Vector2(SOCKET_WIDTH, SOCKET_HEIGHT),
		"approach_depth": 1.2,
		"open": open_west_back,
	})
	set_meta("rendered_envelope_bounds_xyz", AABB(
		Vector3(-6.12, -1.35, -5.12), Vector3(19.24, 3.3, 10.24)))
	set_meta("socket_policy", "west_back is authored for this comparison only; no source-video opening is claimed")
	set_meta("tested_connectors", PackedStringArray())
	set_meta("walk_route", PackedVector2Array([
		Vector2(-4.0, 0.0), Vector2(-4.0, 2.6), Vector2(0.0, 2.6),
		Vector2(4.0, 2.6), Vector2(4.0, 0.0), Vector2(9.0, 0.0), Vector2(12.0, 0.0),
	]))
