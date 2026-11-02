extends "res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/room.gd"

@export var connector_open := false
@export var spawn_embedded_player := true

const SOCKET_HALF_WIDTH := 1.2
const SOCKET_CLEAR_HEIGHT := 2.2


func _set_candidate_metadata() -> void:
	super._set_candidate_metadata()
	set_meta("room_id", "debris_window_rock_room_v2_north_socket")
	set_meta("candidate_status", "connector_adapter_pending_review")
	set_meta("operator_approved", false)
	set_meta("authored_socket", _socket_declaration())
	set_meta("connector_open_ids", ["north"] if connector_open else [])


func _build_boundaries() -> void:
	_add_wall("WestBoundary", Vector3(-HALF_WIDTH - 0.15, WALL_HEIGHT * 0.5, 0.0), Vector3(0.3, WALL_HEIGHT, HALF_DEPTH * 2.0 + 0.3))
	_add_wall("EastBoundary", Vector3(HALF_WIDTH + 0.15, WALL_HEIGHT * 0.5, 0.0), Vector3(0.3, WALL_HEIGHT, HALF_DEPTH * 2.0 + 0.3))
	_add_wall("SouthBoundary", Vector3(0.0, WALL_HEIGHT * 0.5, HALF_DEPTH + 0.15), Vector3(HALF_WIDTH * 2.0 + 0.3, WALL_HEIGHT, 0.3))
	if connector_open:
		_build_north_opening()
	else:
		_add_wall("NorthBoundary", Vector3(0.0, WALL_HEIGHT * 0.5, -HALF_DEPTH - 0.15), Vector3(HALF_WIDTH * 2.0 + 0.3, WALL_HEIGHT, 0.3))
	_build_window_band()


func _build_north_opening() -> void:
	var wall_z := -HALF_DEPTH - 0.15
	var side_width := HALF_WIDTH - SOCKET_HALF_WIDTH + 0.15
	var side_center := (HALF_WIDTH + SOCKET_HALF_WIDTH + 0.15) * 0.5
	_add_wall("NorthBoundaryWest", Vector3(-side_center, WALL_HEIGHT * 0.5, wall_z), Vector3(side_width, WALL_HEIGHT, 0.3))
	_add_wall("NorthBoundaryEast", Vector3(side_center, WALL_HEIGHT * 0.5, wall_z), Vector3(side_width, WALL_HEIGHT, 0.3))
	var header_height := WALL_HEIGHT - SOCKET_CLEAR_HEIGHT
	_add_wall("NorthSocketHeader", Vector3(0.0, SOCKET_CLEAR_HEIGHT + header_height * 0.5, wall_z), Vector3(SOCKET_HALF_WIDTH * 2.0, header_height, 0.3))


func _socket_declaration() -> Dictionary:
	return {
		"id": "north",
		"local_floor_center": [0.0, 0.0, -HALF_DEPTH],
		"outward_normal": [0.0, 0.0, -1.0],
		"clear_size": [SOCKET_HALF_WIDTH * 2.0, SOCKET_CLEAR_HEIGHT],
		"approach_clearance": 1.2,
		"compatibility_type": "level_doorway_2m_v1",
		"closure_behavior": "Closed wall and matching collider when connector_open is false.",
	}


func _build_environment() -> void:
	if spawn_embedded_player:
		super._build_environment()


func _apply_psx_profile() -> void:
	if spawn_embedded_player:
		super._apply_psx_profile()
		return
	PSX_PRESET.new().configure(self)
	set_meta("psx_profile_id", "library-psx-ursc-1.5-native-compositor")


func _spawn_player() -> void:
	if spawn_embedded_player:
		super._spawn_player()


func _unhandled_key_input(event: InputEvent) -> void:
	if player != null:
		super._unhandled_key_input(event)
