extends "res://source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v1/room.gd"

## Authored two-socket through variant of the accepted #175 room.
## The accepted standalone room is untouched; both openings declared here are
## operator-approved but UNTESTED, so this variant stays out of automatic layout.

const SOCKET_HALF_WIDTH := 1.0
const SOCKET_CLEAR_HEIGHT := 2.1
const SOCKET_FLOOR_Y := 0.0
const SOCKET_APPROACH_M := 1.2
const SOCKET_COMPATIBILITY := "level_doorway_2m_v1"
const WALL_THICKNESS := 0.3


func _set_candidate_metadata() -> void:
	super._set_candidate_metadata()
	set_meta("room_id", "chevron_corridor_v2_north_south_socket")
	set_meta("candidate_status", "socket_variant_pending_operator_review")
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("variant_of", "chevron_corridor_v1")
	set_meta("authored_sockets", [_north_socket(), _south_socket()])
	set_meta("connector_open_ids", ["north", "south"])
	set_meta("socket_test_status", "untested")


func _build_boundaries() -> void:
	_add_wall("WestBoundary", Vector3(-ROOM_HALF_WIDTH - 0.15, ROOM_HEIGHT * 0.5, 0.0), Vector3(WALL_THICKNESS, ROOM_HEIGHT, ROOM_HALF_DEPTH * 2.0 + WALL_THICKNESS))
	_add_wall("EastBoundary", Vector3(ROOM_HALF_WIDTH + 0.15, ROOM_HEIGHT * 0.5, 0.0), Vector3(WALL_THICKNESS, ROOM_HEIGHT, ROOM_HALF_DEPTH * 2.0 + WALL_THICKNESS))
	_build_opening("North", -ROOM_HALF_DEPTH - 0.15)
	_build_opening("South", ROOM_HALF_DEPTH + 0.15)


func _build_opening(label: String, wall_z: float) -> void:
	var side_width := ROOM_HALF_WIDTH - SOCKET_HALF_WIDTH + WALL_THICKNESS * 0.5
	var side_center := (ROOM_HALF_WIDTH + SOCKET_HALF_WIDTH + WALL_THICKNESS * 0.5) * 0.5
	_add_wall(label + "BoundaryWest", Vector3(-side_center, ROOM_HEIGHT * 0.5, wall_z), Vector3(side_width, ROOM_HEIGHT, WALL_THICKNESS))
	_add_wall(label + "BoundaryEast", Vector3(side_center, ROOM_HEIGHT * 0.5, wall_z), Vector3(side_width, ROOM_HEIGHT, WALL_THICKNESS))
	var header_height := ROOM_HEIGHT - SOCKET_CLEAR_HEIGHT
	_add_wall(label + "SocketHeader", Vector3(0.0, SOCKET_CLEAR_HEIGHT + header_height * 0.5, wall_z), Vector3(SOCKET_HALF_WIDTH * 2.0, header_height, WALL_THICKNESS))


func _build_baseboards() -> void:
	var inner_x := ROOM_HALF_WIDTH - 0.02
	var inner_z := ROOM_HALF_DEPTH - 0.02
	_add_box("BaseboardWest", Vector3(-inner_x, 0.12, 0.0), Vector3(0.08, 0.24, ROOM_HALF_DEPTH * 2.0), materials.baseboard, "AuthoredVisuals")
	_add_box("BaseboardEast", Vector3(inner_x, 0.12, 0.0), Vector3(0.08, 0.24, ROOM_HALF_DEPTH * 2.0), materials.baseboard, "AuthoredVisuals")
	var side_width := ROOM_HALF_WIDTH - SOCKET_HALF_WIDTH
	var side_center := (ROOM_HALF_WIDTH + SOCKET_HALF_WIDTH) * 0.5
	for label in ["South", "North"]:
		var z := inner_z if label == "South" else -inner_z
		_add_box("Baseboard" + label + "West", Vector3(-side_center, 0.12, z), Vector3(side_width, 0.24, 0.08), materials.baseboard, "AuthoredVisuals")
		_add_box("Baseboard" + label + "East", Vector3(side_center, 0.12, z), Vector3(side_width, 0.24, 0.08), materials.baseboard, "AuthoredVisuals")


func _north_socket() -> Dictionary:
	return _socket("north", Vector3(0.0, SOCKET_FLOOR_Y, -ROOM_HALF_DEPTH), Vector3(0.0, 0.0, -1.0))


func _south_socket() -> Dictionary:
	return _socket("south", Vector3(0.0, SOCKET_FLOOR_Y, ROOM_HALF_DEPTH), Vector3(0.0, 0.0, 1.0))


func _socket(id: String, center: Vector3, normal: Vector3) -> Dictionary:
	return {
		"id": id,
		"local_floor_center": [center.x, center.y, center.z],
		"outward_normal": [normal.x, normal.y, normal.z],
		"clear_size_m": [SOCKET_HALF_WIDTH * 2.0, SOCKET_CLEAR_HEIGHT],
		"floor_elevation_m": SOCKET_FLOOR_Y,
		"approach_clearance_m": SOCKET_APPROACH_M,
		"compatibility_type": SOCKET_COMPATIBILITY,
		"circulation_role": "through",
		"test_status": "untested",
		"closure_behavior": "Open visual doorway and matching collider returns/header; no source-video connectivity is claimed.",
	}
