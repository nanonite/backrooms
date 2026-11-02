extends "res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/room.gd"

@export var connector_open := false
@export var spawn_embedded_player := true

const SOCKET_HALF_WIDTH := 1.2
const SOCKET_CLEAR_HEIGHT := 2.2


func _set_candidate_metadata() -> void:
	super._set_candidate_metadata()
	set_meta("room_id", "industrial_hall_panorama_v4_south_socket")
	set_meta("candidate_status", "connector_adapter_pending_review")
	set_meta("operator_approved", false)
	set_meta("authored_socket", _socket_declaration())
	set_meta("connector_open_ids", ["south"] if connector_open else [])


func _build_boundaries() -> void:
	_add_wall("WestBoundary", Vector3(-ROOM_HALF_WIDTH - 0.15, ROOM_HEIGHT * 0.5, 0.0), Vector3(0.3, ROOM_HEIGHT, ROOM_HALF_DEPTH * 2.0 + 0.3))
	_add_wall("EastBoundary", Vector3(ROOM_HALF_WIDTH + 0.15, ROOM_HEIGHT * 0.5, 0.0), Vector3(0.3, ROOM_HEIGHT, ROOM_HALF_DEPTH * 2.0 + 0.3))
	_add_wall("NorthBoundary", Vector3(0.0, ROOM_HEIGHT * 0.5, -ROOM_HALF_DEPTH - 0.15), Vector3(ROOM_HALF_WIDTH * 2.0 + 0.3, ROOM_HEIGHT, 0.3))
	if connector_open:
		_build_south_opening()
	else:
		_add_wall("SouthBoundary", Vector3(0.0, ROOM_HEIGHT * 0.5, ROOM_HALF_DEPTH + 0.15), Vector3(ROOM_HALF_WIDTH * 2.0 + 0.3, ROOM_HEIGHT, 0.3))
	_add_box("FarWindowReference", Vector3(0.0, 3.15, -ROOM_HALF_DEPTH + 0.012), Vector3(6.8, 1.65, 0.025), materials.window, "AuthoredVisuals")
	_add_box("WindowMullionLeft", Vector3(-2.35, 3.15, -ROOM_HALF_DEPTH - 0.02), Vector3(0.08, 1.72, 0.08), materials.trim, "AuthoredVisuals")
	_add_box("WindowMullionRight", Vector3(2.35, 3.15, -ROOM_HALF_DEPTH - 0.02), Vector3(0.08, 1.72, 0.08), materials.trim, "AuthoredVisuals")


func _build_south_opening() -> void:
	var wall_z := ROOM_HALF_DEPTH + 0.15
	var side_width := ROOM_HALF_WIDTH - SOCKET_HALF_WIDTH + 0.15
	var side_center := (ROOM_HALF_WIDTH + SOCKET_HALF_WIDTH + 0.15) * 0.5
	_add_wall("SouthBoundaryWest", Vector3(-side_center, ROOM_HEIGHT * 0.5, wall_z), Vector3(side_width, ROOM_HEIGHT, 0.3))
	_add_wall("SouthBoundaryEast", Vector3(side_center, ROOM_HEIGHT * 0.5, wall_z), Vector3(side_width, ROOM_HEIGHT, 0.3))
	var header_height := ROOM_HEIGHT - SOCKET_CLEAR_HEIGHT
	_add_wall("SouthSocketHeader", Vector3(0.0, SOCKET_CLEAR_HEIGHT + header_height * 0.5, wall_z), Vector3(SOCKET_HALF_WIDTH * 2.0, header_height, 0.3))


func _socket_declaration() -> Dictionary:
	return {
		"id": "south",
		"local_floor_center": [0.0, 0.0, ROOM_HALF_DEPTH],
		"outward_normal": [0.0, 0.0, 1.0],
		"clear_size": [SOCKET_HALF_WIDTH * 2.0, SOCKET_CLEAR_HEIGHT],
		"approach_clearance": 1.2,
		"compatibility_type": "level_doorway_2m_v1",
		"closure_behavior": "Closed wall and matching collider when connector_open is false.",
	}


func _spawn_player() -> void:
	if spawn_embedded_player:
		super._spawn_player()


func _unhandled_key_input(event: InputEvent) -> void:
	if player != null:
		super._unhandled_key_input(event)
