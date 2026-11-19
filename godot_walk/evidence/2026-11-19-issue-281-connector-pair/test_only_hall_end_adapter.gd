extends "res://evidence/2026-10-24-issue-163/issue163_room.gd"

## Test-only adapter for issue #281 connector-pair testing.
##
## Opens the accepted baseline's hall_end socket at floor 0.0 WITHOUT shifting
## the room to the library floor (-1.27099049) used by issue #164. No library
## file, room scene, script or catalog entry is edited; this is a new file that
## extends the accepted baseline by reference.

const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const SOCKET_ID := "hall_end"
const SOCKET_CENTER := Vector3(13.06, 0.0, 0.0)
const SOCKET_WIDTH := 2.0
const SOCKET_HEIGHT := 2.1
const HALL_END_X := 13.06
const HALL_WALL_HEIGHT := 3.2
const HALL_WALL_THICKNESS := 0.12

@export var include_player := false


func _ready() -> void:
	super._ready()
	_replace_hall_end_with_socket()
	_set_adapter_contract()


func _build_player() -> void:
	if include_player:
		super._build_player()


func _replace_hall_end_with_socket() -> void:
	var visuals := get_node_or_null("AuthoredVisuals")
	var boundaries := get_node_or_null("AuthoredBoundaries")
	if visuals == null or boundaries == null:
		push_error("Issue #281 adapter: baseline authored shell is missing")
		return
	var original_visual := visuals.get_node_or_null("HallEndBoundaryVisual")
	var original_collision := boundaries.get_node_or_null("HallEndBoundary")
	if original_visual == null or original_collision == null:
		push_error("Issue #281 adapter: baseline hall end cap is missing")
		return
	original_visual.free()
	original_collision.free()
	var source_wall: Material = materials.wallpaper
	ROOM_GEOMETRY.add_box(boundaries, "HallSocketNorthReturn",
		Vector3(HALL_END_X, HALL_WALL_HEIGHT * 0.5, -1.25),
		Vector3(HALL_WALL_THICKNESS, HALL_WALL_HEIGHT, 0.5), source_wall, true, true)
	ROOM_GEOMETRY.add_box(boundaries, "HallSocketSouthReturn",
		Vector3(HALL_END_X, HALL_WALL_HEIGHT * 0.5, 1.25),
		Vector3(HALL_WALL_THICKNESS, HALL_WALL_HEIGHT, 0.5), source_wall, true, true)
	ROOM_GEOMETRY.add_box(boundaries, "HallSocketHeader",
		Vector3(HALL_END_X, (SOCKET_HEIGHT + HALL_WALL_HEIGHT) * 0.5, 0.0),
		Vector3(HALL_WALL_THICKNESS, HALL_WALL_HEIGHT - SOCKET_HEIGHT, SOCKET_WIDTH),
		source_wall, true, true)
	var socket := Node3D.new()
	socket.name = "Socket_HallEnd_Authored"
	socket.position = SOCKET_CENTER
	socket.set_meta("outward_normal", Vector3.RIGHT)
	socket.set_meta("clear_width", SOCKET_WIDTH)
	socket.set_meta("clear_height", SOCKET_HEIGHT)
	socket.set_meta("approach_clearance_m", 1.2)
	add_child(socket)


func _set_adapter_contract() -> void:
	set_meta("room_id", "godot_source_textured_large_room_v1__test_only_hall_end_adapter")
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("pair_test_only", true)
	set_meta("open_socket_ids", PackedStringArray([SOCKET_ID]))
	set_meta("authored_socket", {
		"id": SOCKET_ID,
		"local_floor_center": [13.06, 0.0, 0.0],
		"outward_normal": [1.0, 0.0, 0.0],
		"clear_size_m": [SOCKET_WIDTH, SOCKET_HEIGHT],
		"floor_elevation_m": 0.0,
		"approach_clearance_m": 1.2,
		"compatibility_type": "level_doorway_2m_v1",
		"test_status": "untested",
		"closure_behavior": "Open only in this test-only adapter; the accepted baseline wall and collider are untouched.",
	})
	set_meta("walk_floor_y", 0.0)
	set_meta("walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
