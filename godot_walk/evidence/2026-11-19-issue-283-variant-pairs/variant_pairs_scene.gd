extends Node3D

## Isolated issue #283 variant-pair assembly. Both rooms are instanced by
## reference from the accepted source library; neither room, catalog entry nor
## hash-pinned file is edited. Every placement value is exported so the one
## assembly can be reused for all four corridor-to-corridor pairs and for the
## negative controls.

const CHEVRON_175_SCENE := preload("res://source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/room.tscn")
const NESTED_LIGHT_173_SCENE := preload("res://source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/room.tscn")
const CHEVRON_176_SCENE := preload("res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/room.tscn")
const CHEVRON_CROSS_177_SCENE := preload("res://source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v2-north-south-socket/room.tscn")
const PLAYER_SCENE := preload("res://scenes/player.tscn")

@export var pair_id: String = "p1_chevron175_south__chevron176_north"
@export var from_room_key: String = "chevron_175"
@export var to_room_key: String = "chevron_176"
@export var from_socket_id: String = "south"
@export var to_socket_id: String = "north"
@export var from_origin: Vector3 = Vector3(0.0, 0.0, 0.0)
@export var to_origin: Vector3 = Vector3(0.0, 0.0, 20.0)
@export var from_yaw_degrees: int = 0
@export var to_yaw_degrees: int = 0
@export var player_spawn: Vector3 = Vector3(0.0, 0.6, 4.0)
@export var player_yaw_degrees: int = 180

var player: CharacterBody3D


func _ready() -> void:
	_set_metadata()
	_add_rooms()
	_add_floor_seam()
	_spawn_player()
	set_meta("walkthrough_ready", true)


func _set_metadata() -> void:
	set_meta("room_id", "issue283_variant_pair_v1")
	set_meta("pair_id", pair_id)
	set_meta("pair_status", "provisional_pair_test_pending_operator_review")
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("socket_test_status", "untested")
	set_meta("layout_eligible", false)
	set_meta("from_room_key", from_room_key)
	set_meta("to_room_key", to_room_key)
	set_meta("from_socket_id", from_socket_id)
	set_meta("to_socket_id", to_socket_id)
	set_meta("from_origin", from_origin)
	set_meta("to_origin", to_origin)
	set_meta("from_yaw_degrees", from_yaw_degrees)
	set_meta("to_yaw_degrees", to_yaw_degrees)
	set_meta("walk_floor_y", 0.0)
	set_meta("safe_spawn", player_spawn)


func _scene_for(room_key: String) -> PackedScene:
	match room_key:
		"chevron_175":
			return CHEVRON_175_SCENE
		"nested_light_173":
			return NESTED_LIGHT_173_SCENE
		"chevron_176":
			return CHEVRON_176_SCENE
		"chevron_cross_177":
			return CHEVRON_CROSS_177_SCENE
	return null


func _add_rooms() -> void:
	var from_scene := _scene_for(from_room_key)
	var to_scene := _scene_for(to_room_key)
	if from_scene == null or to_scene == null:
		push_error("issue283: unknown room key")
		return
	var from_room := from_scene.instantiate() as Node3D
	from_room.name = "FromRoom"
	from_room.position = from_origin
	from_room.rotation.y = deg_to_rad(float(from_yaw_degrees))
	add_child(from_room)
	_free_embedded_player(from_room)
	var to_room := to_scene.instantiate() as Node3D
	to_room.name = "ToRoom"
	to_room.position = to_origin
	to_room.rotation.y = deg_to_rad(float(to_yaw_degrees))
	add_child(to_room)
	_free_embedded_player(to_room)


func _free_embedded_player(room: Node3D) -> void:
	var embedded := room.get_node_or_null("Player")
	if embedded != null:
		embedded.free()


func _add_floor_seam() -> void:
	var socket := get_connection_socket_world(["FromRoom", from_socket_id])
	if socket.is_empty():
		push_error("issue283: cannot locate from-socket for floor seam")
		return
	var center: Vector3 = socket["position"]
	var boundaries := Node3D.new()
	boundaries.name = "ConnectorBoundaries"
	add_child(boundaries)
	var seam := StaticBody3D.new()
	seam.name = "ConnectorFloorSeam"
	seam.position = Vector3(center.x, -0.12, center.z)
	boundaries.add_child(seam)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = Vector3(2.0, 0.24, 0.4)
	collision.shape = shape
	seam.add_child(collision)


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = player_spawn
	player.rotation.y = deg_to_rad(float(player_yaw_degrees))
	add_child(player)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		_reset_player()


func _reset_player() -> void:
	player.global_position = player_spawn
	player.velocity = Vector3.ZERO
	player.rotation = Vector3(0.0, deg_to_rad(float(player_yaw_degrees)), 0.0)
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
