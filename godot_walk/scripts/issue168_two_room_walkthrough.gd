extends Node3D

const HALL_ADAPTER := preload("res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v4-south-socket/room.tscn")
const ROCK_ADAPTER := preload("res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v2-north-socket/room.tscn")
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const HALL_SPAWN := Vector3(0.0, 0.6, 4.1)
const ROCK_ROOM_ORIGIN := Vector3(0.0, 0.0, 11.5)
const SOCKET_WIDTH := 2.4
const SOCKET_HEIGHT := 2.2
const SOCKET_Z := 6.5
const FLOOR_Y := 0.0

var player: CharacterBody3D


func _ready() -> void:
	_set_candidate_metadata()
	_add_room_adapters()
	_add_connector_groups()
	_build_shared_door_frame()
	_spawn_player()
	set_meta("walkthrough_ready", true)


func _set_candidate_metadata() -> void:
	set_meta("room_id", "issue168_two_room_walkthrough_v1")
	set_meta("candidate_status", "pending_operator_review")
	set_meta("operator_approved", false)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("safe_spawn", HALL_SPAWN)
	set_meta("source_video_connectivity_established", false)
	set_meta("candidate_connections", [_connection_record()])
	set_meta("rendered_envelope_bounds_xyz", AABB(Vector3(-8.3, -0.3, -6.8), Vector3(16.6, 5.4, 23.6)))


func _add_room_adapters() -> void:
	var hall := HALL_ADAPTER.instantiate() as Node3D
	hall.name = "IndustrialHall"
	hall.set("connector_open", true)
	hall.set("spawn_embedded_player", false)
	add_child(hall)
	var rocks := ROCK_ADAPTER.instantiate() as Node3D
	rocks.name = "DebrisWindowRockRoom"
	rocks.position = ROCK_ROOM_ORIGIN
	rocks.set("connector_open", true)
	rocks.set("spawn_embedded_player", false)
	add_child(rocks)


func _add_connector_groups() -> void:
	var visuals := Node3D.new()
	visuals.name = "AuthoredConnectorVisuals"
	add_child(visuals)
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredConnectorBoundaries"
	add_child(boundaries)
	_add_bridge_floor(visuals, boundaries)


func _add_bridge_floor(visuals: Node3D, boundaries: Node3D) -> void:
	var size := Vector3(SOCKET_WIDTH, 0.24, 0.22)
	var center := Vector3(0.0, -0.12, SOCKET_Z)
	_add_box(visuals, "DoorwayThresholdVisual", center + Vector3.UP * 0.128, Vector3(size.x, 0.016, size.z), _trim_material())
	_add_collision_box(boundaries, "DoorwayFloorSeam", center, size)


func _build_shared_door_frame() -> void:
	var visuals := get_node("AuthoredConnectorVisuals") as Node3D
	var trim := _trim_material()
	for side in [-1.0, 1.0]:
		var jamb_position := Vector3(side * 1.17, SOCKET_HEIGHT * 0.5, SOCKET_Z)
		_add_box(visuals, "SharedDoorJamb_%s" % str(side), jamb_position, Vector3(0.06, SOCKET_HEIGHT, 0.62), trim)
	_add_box(visuals, "SharedDoorHeader", Vector3(0.0, SOCKET_HEIGHT + 0.04, SOCKET_Z), Vector3(SOCKET_WIDTH + 0.12, 0.08, 0.62), trim)


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = HALL_SPAWN
	player.rotation.y = PI
	add_child(player)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		_reset_player()


func _reset_player() -> void:
	player.global_position = HALL_SPAWN
	player.velocity = Vector3.ZERO
	player.rotation = Vector3(0.0, PI, 0.0)
	player.get_node("Head").rotation = Vector3.ZERO


func get_connection_socket_world(reference: Array) -> Dictionary:
	if reference.size() != 2:
		return {}
	var room := get_node_or_null(String(reference[0])) as Node3D
	if room == null:
		return {}
	var socket: Dictionary = room.get_meta("authored_socket", {})
	if socket.get("id") != reference[1]:
		return {}
	var local_center := _vector3_from_array(socket.get("local_floor_center", []))
	var local_normal := _vector3_from_array(socket.get("outward_normal", []))
	return {
		"position": room.to_global(local_center),
		"normal": room.global_transform.basis * local_normal,
		"size": socket.get("clear_size", []),
		"approach_clearance": socket.get("approach_clearance", 0.0),
		"floor_y": room.to_global(local_center).y,
	}


func _connection_record() -> Dictionary:
	return {
		"id": "industrial_hall_south__rock_room_north_v1",
		"from": ["IndustrialHall", "south"],
		"to": ["DebrisWindowRockRoom", "north"],
		"origin": "explicit_authored_game_connection; source video does not establish continuity",
		"status": "provisional_pending_operator_review",
	}


func _vector3_from_array(values: Array) -> Vector3:
	if values.size() != 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _trim_material() -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.28, 0.24, 0.19)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	return material


func _add_box(parent: Node3D, label: String, center: Vector3, size: Vector3, material: Material) -> void:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = label
	mesh_instance.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh_instance.mesh = mesh
	mesh_instance.material_override = material
	parent.add_child(mesh_instance)


func _add_collision_box(parent: Node3D, label: String, center: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	parent.add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
