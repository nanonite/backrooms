extends Node3D

## Isolated issue #281 connector-pair scene. Both rooms are instanced by
## reference; neither room, catalog entry or hash-pinned file is edited.
## A = chevron-corridor-v2-north-south-socket (yaw 90, north socket).
## B = accepted textured_large_room baseline hall_end via a test-only adapter.

const A_SCENE := preload("res://source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/room.tscn")
const B_SCENE := preload("res://evidence/2026-11-19-issue-281-connector-pair/test_only_hall_end_adapter.tscn")
const PLAYER_SCENE := preload("res://scenes/player.tscn")

const B_ORIGIN := Vector3(0.0, 0.0, 0.0)
const PLAYER_SPAWN := Vector3(16.0, 0.6, 0.0)
const PLAYER_YAW_DEGREES := 90.0

@export var a_origin: Vector3 = Vector3(23.06, 0.0, 0.0)
@export var a_yaw_degrees: int = 90
@export var a_socket_id: String = "north"

var player: CharacterBody3D


func _ready() -> void:
	_set_metadata()
	_add_rooms()
	_add_connector_floor()
	_spawn_player()
	set_meta("walkthrough_ready", true)


func _set_metadata() -> void:
	set_meta("room_id", "issue281_connector_pair_v1")
	set_meta("pair_status", "provisional_pair_test_pending_operator_review")
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("socket_test_status", "untested")
	set_meta("a_origin", a_origin)
	set_meta("a_yaw_degrees", a_yaw_degrees)
	set_meta("a_socket_id", a_socket_id)
	set_meta("b_origin", B_ORIGIN)
	set_meta("walk_floor_y", 0.0)
	set_meta("safe_spawn", PLAYER_SPAWN)


func _add_rooms() -> void:
	var large_room := B_SCENE.instantiate() as Node3D
	large_room.name = "LargeRoomHallEnd"
	large_room.position = B_ORIGIN
	add_child(large_room)
	var chevron := A_SCENE.instantiate() as Node3D
	chevron.name = "ChevronCorridorV2"
	chevron.position = a_origin
	chevron.rotation.y = deg_to_rad(float(a_yaw_degrees))
	add_child(chevron)
	var embedded := chevron.get_node_or_null("Player")
	if embedded != null:
		embedded.free()


func _add_connector_floor() -> void:
	var visuals := Node3D.new()
	visuals.name = "ConnectorVisuals"
	add_child(visuals)
	var boundaries := Node3D.new()
	boundaries.name = "ConnectorBoundaries"
	add_child(boundaries)
	var center := Vector3(13.02, -0.12, 0.0)
	var size := Vector3(0.24, 0.24, 2.0)
	var plate := MeshInstance3D.new()
	plate.name = "DoorwayThresholdVisual"
	plate.position = center + Vector3.UP * 0.128
	var plate_mesh := BoxMesh.new()
	plate_mesh.size = Vector3(size.x, 0.016, size.z)
	plate.mesh = plate_mesh
	plate.material_override = _trim_material()
	visuals.add_child(plate)
	var seam := StaticBody3D.new()
	seam.name = "DoorwayFloorSeam"
	seam.position = center
	boundaries.add_child(seam)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	seam.add_child(collision)


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = PLAYER_SPAWN
	player.rotation.y = deg_to_rad(PLAYER_YAW_DEGREES)
	add_child(player)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		_reset_player()


func _reset_player() -> void:
	player.global_position = PLAYER_SPAWN
	player.velocity = Vector3.ZERO
	player.rotation = Vector3(0.0, deg_to_rad(PLAYER_YAW_DEGREES), 0.0)
	player.get_node("Head").rotation = Vector3.ZERO


func get_connection_socket_world(reference: Array) -> Dictionary:
	if reference.size() != 2:
		return {}
	var room := get_node_or_null(String(reference[0])) as Node3D
	if room == null:
		return {}
	var socket: Dictionary = _find_socket(room, String(reference[1]))
	if socket.is_empty():
		return {}
	var local_center := _vector3_from(socket.get("local_floor_center", []))
	var local_normal := _vector3_from(socket.get("outward_normal", []))
	var world_center := room.to_global(local_center)
	var world_normal := (room.global_transform.basis * local_normal).normalized()
	var raw_size: Array = socket.get("clear_size_m", socket.get("clear_size", []))
	var size: Array = []
	if raw_size.size() == 2:
		size = [float(raw_size[0]), float(raw_size[1])]
	return {
		"id": String(reference[1]),
		"position": world_center,
		"normal": world_normal,
		"size": size,
		"compatibility_type": String(socket.get("compatibility_type", "")),
		"floor_y": world_center.y,
	}


func _find_socket(room: Node3D, socket_id: String) -> Dictionary:
	var single: Dictionary = room.get_meta("authored_socket", {})
	if not single.is_empty() and String(single.get("id", "")) == socket_id:
		return single
	for item in room.get_meta("authored_sockets", []):
		if item is Dictionary and String((item as Dictionary).get("id", "")) == socket_id:
			return item
	return {}


func _vector3_from(values: Array) -> Vector3:
	if values.size() != 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _trim_material() -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.28, 0.24, 0.19)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	return material
