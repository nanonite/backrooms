extends "res://scripts/issue160_pocket_room.gd"

const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const POCKET_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")

@export var additional_open_sockets := PackedStringArray()


func _ready() -> void:
	super._ready()
	PSX_PRESET.new().configure(self)
	_set_topology_metadata()


func _build_authored_room() -> void:
	super._build_authored_room()
	for socket_id: String in additional_open_sockets:
		if socket_id == "east":
			_open_east_socket()
		elif socket_id == "north":
			_open_north_socket()
		else:
			push_error("Unsupported #149 additional pocket socket: %s" % socket_id)


func _open_east_socket() -> void:
	_replace_boundary("east")
	_add_east_socket_parts()
	_add_topology_socket_marker("East", Vector3(6.0, FLOOR_Y, SOCKET_Z), Vector3.RIGHT)


func _add_east_socket_parts() -> void:
	var low := SOCKET_Z - CLEAR_WIDTH * 0.5
	var high := SOCKET_Z + CLEAR_WIDTH * 0.5
	var center_x := 6.06
	var bottom_z := -0.12
	var top_z := 13.92
	_add_wall_piece("EastVisualBeforeSocket", Vector3(center_x, FLOOR_Y + 1.2,
		(bottom_z + low) * 0.5), Vector3(WALL_THICKNESS, WALL_HEIGHT, low - bottom_z))
	_add_wall_piece("EastVisualAfterSocket", Vector3(center_x, FLOOR_Y + 1.2,
		(high + top_z) * 0.5), Vector3(WALL_THICKNESS, WALL_HEIGHT, top_z - high))
	_add_wall_piece("EastVisualSocketLintel", Vector3(center_x, FLOOR_Y + 2.25, SOCKET_Z),
		Vector3(WALL_THICKNESS, WALL_HEIGHT - CLEAR_HEIGHT, CLEAR_WIDTH))


func _open_north_socket() -> void:
	_replace_boundary("north")
	_add_north_socket_parts()
	_add_topology_socket_marker("North", Vector3(3.0, FLOOR_Y, 13.8), Vector3.BACK)


func _add_north_socket_parts() -> void:
	var low := 3.0 - CLEAR_WIDTH * 0.5
	var high := 3.0 + CLEAR_WIDTH * 0.5
	var center_z := 13.86
	_add_wall_piece("NorthVisualBeforeSocket", Vector3(low * 0.5, FLOOR_Y + 1.2,
		center_z), Vector3(low, WALL_HEIGHT, WALL_THICKNESS))
	_add_wall_piece("NorthVisualAfterSocket", Vector3((high + 6.0) * 0.5,
		FLOOR_Y + 1.2, center_z), Vector3(6.0 - high, WALL_HEIGHT, WALL_THICKNESS))
	_add_wall_piece("NorthVisualSocketLintel", Vector3(3.0, FLOOR_Y + 2.25, center_z),
		Vector3(CLEAR_WIDTH, WALL_HEIGHT - CLEAR_HEIGHT, WALL_THICKNESS))


func _replace_boundary(side: String) -> void:
	var group := get_node_or_null("AuthoredBoundaries/%sBoundary" % side.capitalize()) as Node3D
	var wall := group.get_node_or_null("Wall") if group != null else null
	var detail := get_node_or_null("AuthoredPocketVisualDetails/authored_room_boundary_%sVisual" % side)
	if wall == null or detail == null:
		push_error("Cannot replace #149 %s boundary visual/collision pair" % side)
		return
	wall.free()
	detail.free()


func _add_wall_piece(label: String, center: Vector3, size: Vector3) -> void:
	POCKET_GEOMETRY.add_box(self, label, center, size, _materials.wall)


func _add_topology_socket_marker(label: String, center: Vector3, normal: Vector3) -> void:
	var marker := Node3D.new()
	marker.name = "Socket_%s_Authored" % label
	marker.position = center
	marker.set_meta("outward_normal", normal)
	marker.set_meta("clear_width", CLEAR_WIDTH)
	marker.set_meta("clear_height", CLEAR_HEIGHT)
	add_child(marker)


func _set_topology_metadata() -> void:
	var open_sockets: Array[String] = ["west"]
	for socket_id: String in additional_open_sockets:
		open_sockets.append(socket_id)
	var topology := "pocket_pass_through" if open_sockets.size() == 2 else "pocket_three_way"
	set_meta("room_id", "godot_issue149_%s_v1" % topology)
	set_meta("room_version", 1)
	set_meta("generation_ready", false)
	set_meta("operator_approved", false)
	set_meta("topology_variant", topology)
	set_meta("open_socket_ids", PackedStringArray(open_sockets))
	set_meta("closed_unused_sockets", PackedStringArray(["south"] if open_sockets.size() == 3 else ["north", "south"]))
	set_meta("authored_sockets", _socket_contracts(open_sockets))
	set_meta("observed_openings", PackedStringArray())


func _socket_contracts(open_sockets: Array) -> Array[Dictionary]:
	var all_sockets := {
		"west": [Vector3(0.0, FLOOR_Y, 6.9), Vector3.LEFT],
		"east": [Vector3(6.0, FLOOR_Y, 6.9), Vector3.RIGHT],
		"north": [Vector3(3.0, FLOOR_Y, 13.8), Vector3.BACK],
	}
	var result: Array[Dictionary] = []
	for socket_id: String in open_sockets:
		var socket: Array = all_sockets[socket_id]
		result.append({
			"id": socket_id,
			"floor_center": socket[0],
			"outward_normal": socket[1],
			"clear_size": Vector2(CLEAR_WIDTH, CLEAR_HEIGHT),
			"floor_elevation": FLOOR_Y,
			"approach_clearance_m": 1.2,
			"compatibility_type": "level_doorway_2m_v1",
			"closure_behavior": "continuous visual wall and collider when not listed open",
		})
	return result
