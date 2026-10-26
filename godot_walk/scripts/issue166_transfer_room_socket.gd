extends "res://scripts/issue165_transfer_room.gd"

const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const SOCKET_CENTER := Vector3(-6.0, 0.0, 0.0)
const SOCKET_WIDTH := 2.0
const SOCKET_HEIGHT := 2.1
const WALL_X := -5.92
const WALL_HEIGHT := 3.0
const WALL_THICKNESS := 0.16

@export var socket_open := true
@export var include_player := false


func _ready() -> void:
	super._ready()
	if socket_open:
		_open_west_socket()
	_set_socket_contract()


func _build_player() -> void:
	if include_player:
		super._build_player()


func _open_west_socket() -> void:
	var visuals := get_node_or_null("AuthoredVisuals") as Node3D
	var boundaries := get_node_or_null("AuthoredBoundaries") as Node3D
	if visuals == null or boundaries == null:
		push_error("Transfer-room shell is missing for the west socket")
		return
	var wall_visual := visuals.get_node_or_null("Boundary_WestOuterVisual")
	var wall_collision := boundaries.get_node_or_null("Boundary_WestOuter")
	if wall_visual == null or wall_collision == null:
		push_error("Transfer-room west boundary cannot be adapted")
		return
	wall_visual.free()
	wall_collision.free()
	for side in [-1.0, 1.0]:
		var suffix := "Left" if side < 0.0 else "Right"
		ROOM_GEOMETRY.add_box(boundaries, "WestSocketReturn_%s" % suffix,
			Vector3(WALL_X, WALL_HEIGHT * 0.5, side * 1.54),
			Vector3(WALL_THICKNESS, WALL_HEIGHT, 1.08), materials.wallpaper, true, true)
	ROOM_GEOMETRY.add_box(boundaries, "WestSocketHeader",
		Vector3(WALL_X, (SOCKET_HEIGHT + WALL_HEIGHT) * 0.5, 0.0),
		Vector3(WALL_THICKNESS, WALL_HEIGHT - SOCKET_HEIGHT, SOCKET_WIDTH),
		materials.wallpaper, true, true)
	var socket := Node3D.new()
	socket.name = "Socket_West_Authored"
	socket.position = SOCKET_CENTER
	socket.set_meta("outward_normal", Vector3.LEFT)
	socket.set_meta("clear_width", SOCKET_WIDTH)
	socket.set_meta("clear_height", SOCKET_HEIGHT)
	socket.set_meta("approach_clearance_m", 1.2)
	add_child(socket)


func _set_socket_contract() -> void:
	set_meta("room_id", "godot_corridor_corner_socket_candidate_v1")
	set_meta("room_version", 1)
	set_meta("operator_approved", false)
	set_meta("generation_ready", false)
	set_meta("open_socket_ids", PackedStringArray(["west"]) if socket_open else PackedStringArray())
	set_meta("candidate_socket", {
		"id": "west",
		"floor_center": SOCKET_CENTER,
		"outward_normal": Vector3.LEFT,
		"clear_size": Vector2(SOCKET_WIDTH, SOCKET_HEIGHT),
		"approach_depth": 1.2,
		"open": socket_open,
	})
	set_meta("socket_contract", "west is an authored gameplay socket; the footage does not establish this connection")
	set_meta("tested_connectors", PackedStringArray())
