extends "res://evidence/2026-10-24-issue-163/issue163_room.gd"

const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const MODULE_FLOOR_Y := -1.27099049
const SOCKET_ID := "hall_end"
const SOCKET_CENTER := Vector3(13.06, MODULE_FLOOR_Y, 0.0)
const SOCKET_WIDTH := 2.0
const SOCKET_HEIGHT := 2.1
const HALL_END_X := 13.06
const HALL_WALL_HEIGHT := 3.2
const HALL_WALL_THICKNESS := 0.12

@export var include_player := false


func _ready() -> void:
	super._ready()
	_shift_room_to_library_floor()
	_replace_hall_end_with_socket()
	_remove_embedded_player()
	_rename_walkable_floor()
	_set_adapter_contract()


func _build_hunyuan_visual() -> void:
	set_meta("hunyuan_visual_only", false)
	set_meta("hunyuan_stage_status", "not_used_authored_source_video_room")
	set_meta("hunyuan_visual_loaded", false)


func _build_player() -> void:
	if include_player:
		super._build_player()


func _replace_hall_end_with_socket() -> void:
	var visuals := get_node_or_null("AuthoredVisuals")
	var boundaries := get_node_or_null("AuthoredBoundaries")
	if visuals == null or boundaries == null:
		push_error("Issue 163 room did not create its authored shell")
		return
	var original_visual := visuals.get_node_or_null("HallEndBoundaryVisual")
	var original_collision := boundaries.get_node_or_null("HallEndBoundary")
	if original_visual == null or original_collision == null:
		push_error("Issue 163 hallway end cap is missing")
		return
	original_visual.free()
	original_collision.free()
	var source_wall: Material = materials.wallpaper
	_add_socket_wall(boundaries, "HallSocketNorthReturn", -1.25, source_wall)
	_add_socket_wall(boundaries, "HallSocketSouthReturn", 1.25, source_wall)
	_add_header(boundaries, source_wall)
	var socket := Node3D.new()
	socket.name = "Socket_HallEnd_Authored"
	socket.position = SOCKET_CENTER
	socket.set_meta("outward_normal", Vector3.RIGHT)
	socket.set_meta("clear_width", SOCKET_WIDTH)
	socket.set_meta("clear_height", SOCKET_HEIGHT)
	socket.set_meta("approach_clearance_m", 1.2)
	add_child(socket)


func _shift_room_to_library_floor() -> void:
	for child: Node in get_children():
		if child is Node3D:
			(child as Node3D).position.y += MODULE_FLOOR_Y


func _add_socket_wall(parent: Node3D, label: String, center_z: float, material: Material) -> void:
	ROOM_GEOMETRY.add_box(parent, label,
		Vector3(HALL_END_X, HALL_WALL_HEIGHT * 0.5, center_z),
		Vector3(HALL_WALL_THICKNESS, HALL_WALL_HEIGHT, 0.5), material, true, true)


func _add_header(parent: Node3D, material: Material) -> void:
	ROOM_GEOMETRY.add_box(parent, "HallSocketHeader",
		Vector3(HALL_END_X, (SOCKET_HEIGHT + HALL_WALL_HEIGHT) * 0.5, 0.0),
		Vector3(HALL_WALL_THICKNESS, HALL_WALL_HEIGHT - SOCKET_HEIGHT, SOCKET_WIDTH),
		material, true, true)


func _remove_embedded_player() -> void:
	if not include_player:
		var player := get_node_or_null("Player")
		if player != null:
			player.free()


func _rename_walkable_floor() -> void:
	var floor_body := get_node_or_null("AuthoredBoundaries/WalkableFloor")
	if floor_body != null:
		floor_body.name = "AuthoredPlanarRouteFloor"


func _set_adapter_contract() -> void:
	set_meta("room_id", "godot_source_textured_large_room_hall_end_v1")
	set_meta("room_version", 1)
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("generation_ready", false)
	set_meta("open_socket_ids", PackedStringArray([SOCKET_ID]))
	set_meta("authored_socket", {
		"id": SOCKET_ID,
		"floor_center": SOCKET_CENTER,
		"outward_normal": Vector3.RIGHT,
		"clear_size": Vector2(SOCKET_WIDTH, SOCKET_HEIGHT),
		"approach_depth": 1.2,
		"open": true,
	})
	set_meta("walk_route", PackedVector2Array([
		Vector2(-4.0, 0.0), Vector2(-4.0, 2.6), Vector2(0.0, 2.6),
		Vector2(4.0, 2.6), Vector2(4.0, 0.0), Vector2(9.0, 0.0), Vector2(13.0, 0.0),
	]))
	set_meta("walk_envelope", Rect2(-6.0, -5.0, 19.0, 10.0))
	set_meta("walk_floor_y", MODULE_FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["AuthoredPlanarRouteFloor"]))
	set_meta("boundary_probe_origin", Vector3(4.0, MODULE_FLOOR_Y + 0.6, 3.0))
	set_meta("boundary_test_path", "AuthoredBoundaries/EastSouthBoundary")
	set_meta("source_video", "data/videos/room_large.mp4")
	set_meta("source_seed_frame", "room_large_frame_0013.png")
	set_meta("visual_provenance", "authored source-textured room baseline; no Hunyuan output")
	set_meta("observed_openings", PackedStringArray())
	set_meta("tested_connectors", PackedStringArray())
