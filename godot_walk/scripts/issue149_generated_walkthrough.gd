extends Node3D

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const ROOM_GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const FLOOR_Y := -1.27099049
const HASH_FAILURE := "#149 catalog or runtime dependency hash mismatch"

var _spawn_position := Vector3(-3.5, FLOOR_Y + 0.6, 0.0)
var _player: CharacterBody3D
var _layout: Dictionary = {}
var _catalog: Dictionary = {}
var _modules_by_id: Dictionary = {}
var _instances_by_id: Dictionary = {}


func _ready() -> void:
	_set_unaccepted_contract()
	call_deferred("_build_walkthrough")


func _build_walkthrough() -> void:
	var layout_path := _layout_argument()
	if not _load_layout(layout_path):
		get_tree().quit(2)
		return
	if not _load_catalog_snapshot():
		get_tree().quit(2)
		return
	if not _verify_runtime_dependencies():
		get_tree().quit(2)
		return
	_index_modules()
	if not _instantiate_modules():
		get_tree().quit(2)
		return
	if not _validate_connections():
		get_tree().quit(2)
		return
	_add_connection_transitions()
	_build_player()
	PSX_PRESET.new().configure(self)
	set_meta("walkthrough_ready", true)
	print("ISSUE149_WALKTHROUGH_READY seed=%d placements=%d catalog=%s" % [
		_layout.seed, _layout.placements.size(), _layout.catalog_sha256
	])


func _layout_argument() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--layout="):
			return argument.trim_prefix("--layout=")
	return "res://evidence/2026-10-22-issue-149/layout_seed_149.json"


func _load_layout(path: String) -> bool:
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if not parsed is Dictionary or parsed.get("schema_version") != 1:
		push_error("Invalid #149 layout JSON: %s" % path)
		return false
	if not _verify_layout_file_hash(path):
		push_error("Serialized #149 layout file hash is invalid: %s" % path)
		return false
	_layout = parsed
	var snapshot_path: String = _layout.get("catalog_snapshot_path", "")
	if snapshot_path.is_empty() or FileAccess.get_sha256(snapshot_path) != _layout.get("catalog_sha256"):
		push_error(HASH_FAILURE)
		return false
	return true


func _verify_layout_file_hash(path: String) -> bool:
	var expected := FileAccess.get_file_as_string(path + ".sha256").strip_edges().split(" ")[0]
	return expected.length() == 64 and FileAccess.get_sha256(path) == expected


func _load_catalog_snapshot() -> bool:
	var path: String = _layout.catalog_snapshot_path
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary or parsed.get("engine") != "Godot 4.6.3":
		push_error("Invalid #149 Godot module catalog snapshot")
		return false
	_catalog = parsed
	for module: Dictionary in _catalog.get("modules", []):
		_modules_by_id[module.id] = module
	return true


func _verify_runtime_dependencies() -> bool:
	for dependency: Dictionary in _catalog.get("runtime_dependencies", []):
		var resource_path := "res://" + String(dependency.path).trim_prefix("godot_walk/")
		if FileAccess.get_sha256(resource_path) != dependency.sha256:
			push_error("Runtime dependency hash mismatch: %s" % dependency.path)
			return false
	return true


func _index_modules() -> void:
	set_meta("walkthrough_ready", false)
	set_meta("layout_id", _layout.layout_id)
	set_meta("layout_seed", _layout.seed)
	set_meta("catalog_sha256", _layout.catalog_sha256)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("generation_ready", false)
	set_meta("operator_approved", false)
	set_meta("observed_openings", PackedStringArray())
	set_meta("candidate_connections", _layout.connections)
	set_meta("walk_floor_y", FLOOR_Y)
	set_meta("walk_floor_bodies", PackedStringArray(["AuthoredFloor", "AuthoredPlanarRouteFloor", "ConnectorThreshold"]))
	var envelope: Array = _layout.walk_envelope
	set_meta("walk_envelope", Rect2(envelope[0], envelope[1], envelope[2], envelope[3]))
	set_meta("walk_route", _route_points(_layout.walk_route_xz))
	set_meta("boundary_probe_origin", Vector3(-3.5, FLOOR_Y + 0.6, 0.0))
	set_meta("boundary_test_path", "R000/AuthoredBoundaries/WestBoundary")
	var boundaries := Node3D.new()
	boundaries.name = "AuthoredBoundaries"
	add_child(boundaries)


func _route_points(values: Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for point: Array in values:
		result.append(Vector2(point[0], point[1]))
	return result


func _instantiate_modules() -> bool:
	for placement: Dictionary in _layout.placements:
		var room := _instantiate_module(placement)
		if room == null:
			return false
		room.name = placement.instance_id
		room.position = _vector3(placement.transform.position)
		room.rotation.y = deg_to_rad(placement.transform.yaw_degrees)
		room.set_meta("layout_module_id", placement.module_id)
		room.set_meta("layout_instance_id", placement.instance_id)
		add_child(room)
		_instances_by_id[placement.instance_id] = room
		if not _module_sockets_match(room, placement):
			return false
	return true


func _instantiate_module(placement: Dictionary) -> Node3D:
	var module: Dictionary = _modules_by_id.get(placement.module_id, {})
	if module.is_empty() or module.scene != placement.scene:
		push_error("Layout references an unregistered module: %s" % placement.module_id)
		return null
	var expected_hash := _scene_hash(module)
	if expected_hash.is_empty() or expected_hash != placement.scene_sha256:
		push_error("Layout scene hash is stale for %s" % placement.module_id)
		return null
	var packed := load(module.scene) as PackedScene
	if packed == null:
		push_error("Cannot load room scene: %s" % module.scene)
		return null
	return packed.instantiate() as Node3D


func _scene_hash(module: Dictionary) -> String:
	var scene_file := "godot_walk/" + String(module.scene).trim_prefix("res://")
	for item: Dictionary in module.dependency_hashes:
		if item.path == scene_file:
			return item.sha256
	return ""


func _module_sockets_match(room: Node3D, placement: Dictionary) -> bool:
	var actual := _actual_open_socket_ids(room, placement)
	var expected: Array = Array(placement.open_sockets)
	actual.sort()
	expected.sort()
	if actual != expected:
		push_error("Scene socket openings differ from layout for %s: %s vs %s" % [
			placement.instance_id, str(actual), str(expected)
	])
		return false
	return true


func _actual_open_socket_ids(room: Node3D, placement: Dictionary) -> Array[String]:
	if room.has_meta("open_socket_ids"):
		var socket_ids: PackedStringArray = room.get_meta("open_socket_ids")
		var result: Array[String] = []
		for socket_id: String in socket_ids:
			result.append(socket_id)
		return result
	var socket: Dictionary = room.get_meta("authored_socket", {})
	if not socket.get("open", false):
		return []
	var module: Dictionary = _modules_by_id[placement.module_id]
	return [module.sockets[0].id]


func _validate_connections() -> bool:
	for connection: Dictionary in _layout.connections:
		var left := _socket_world(connection.from)
		var right := _socket_world(connection.to)
		if left.is_empty() or right.is_empty():
			return false
		var left_position: Vector3 = left.position
		var right_position: Vector3 = right.position
		var left_normal: Vector3 = left.normal
		var right_normal: Vector3 = right.normal
		if left_position.distance_to(right_position) > 0.001:
			push_error("Socket centers do not align: %s" % connection.id)
			return false
		if left_normal.dot(right_normal) > -0.999:
			push_error("Socket normals do not oppose: %s" % connection.id)
			return false
		if left.size != right.size or absf(left.floor_y - right.floor_y) > 0.001:
			push_error("Socket clearances or floor elevations differ: %s" % connection.id)
			return false
	return true


func _socket_world(endpoint: Dictionary) -> Dictionary:
	var placement := _placement(endpoint.instance_id)
	var module: Dictionary = _modules_by_id.get(placement.module_id, {})
	var socket: Dictionary = _socket_config(module, endpoint.socket_id)
	var room: Node3D = _instances_by_id.get(endpoint.instance_id)
	if socket.is_empty() or room == null:
		push_error("Missing socket endpoint: %s/%s" % [endpoint.instance_id, endpoint.socket_id])
		return {}
	return {
		"position": room.global_transform * _vector3(socket.local_floor_center),
		"normal": room.global_basis * _vector3(socket.outward_normal),
		"size": socket.clear_size_m,
		"floor_y": socket.floor_elevation_m + room.position.y,
	}


func get_connection_socket_world(endpoint: Dictionary) -> Dictionary:
	return _socket_world(endpoint)


func _placement(instance_id: String) -> Dictionary:
	for placement: Dictionary in _layout.placements:
		if placement.instance_id == instance_id:
			return placement
	return {}


func _socket_config(module: Dictionary, socket_id: String) -> Dictionary:
	for socket: Dictionary in module.get("sockets", []):
		if socket.id == socket_id:
			return socket
	return {}


func _add_connection_transitions() -> void:
	var trim := StandardMaterial3D.new()
	trim.albedo_color = Color(0.37, 0.34, 0.23)
	trim.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_texture = load("res://assets/psx_extension/textures/floor_source_video.png")
	floor_material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	floor_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	for index in _layout.connections.size():
		_add_transition(index, _layout.connections[index], trim, floor_material)


func _add_transition(index: int, connection: Dictionary, trim: Material, floor_material: Material) -> void:
	var socket := _socket_world(connection.from)
	var center: Vector3 = socket.position
	var size: Array = socket.size
	var threshold_size := Vector3(0.24, 0.12, size[0]) if absf(socket.normal.x) > 0.9 else Vector3(size[0], 0.12, 0.24)
	ROOM_GEOMETRY.add_box(self, "ConnectorThreshold_%03d" % index,
		Vector3(center.x, center.y - 0.06, center.z), threshold_size, floor_material)
	_add_door_frame(index, center, socket.normal, size, trim)


func _add_door_frame(index: int, center: Vector3, normal: Vector3, size: Array, material: Material) -> void:
	var depth := 0.08
	var height: float = float(size[1])
	var half_width: float = float(size[0]) * 0.5
	if absf(normal.x) > 0.9:
		for side in [-1.0, 1.0]:
			ROOM_GEOMETRY.add_box(self, "Portal_%03d_Jamb_%s" % [index, str(side)],
				center + Vector3(0.0, height * 0.5, side * half_width),
				Vector3(depth, height, depth), material, true, false)
		ROOM_GEOMETRY.add_box(self, "Portal_%03d_Header" % index,
			center + Vector3(0.0, height, 0.0), Vector3(depth, depth, size[0]), material, true, false)
		return
	for side in [-1.0, 1.0]:
		ROOM_GEOMETRY.add_box(self, "Portal_%03d_Jamb_%s" % [index, str(side)],
			center + Vector3(side * half_width, height * 0.5, 0.0),
			Vector3(depth, height, depth), material, true, false)
	ROOM_GEOMETRY.add_box(self, "Portal_%03d_Header" % index,
		center + Vector3(0.0, height, 0.0), Vector3(size[0], depth, depth), material, true, false)


func _build_player() -> void:
	var spawn: Dictionary = _layout.spawn
	_spawn_position = _vector3(spawn.local_position)
	_player = PLAYER_SCENE.instantiate() as CharacterBody3D
	_player.name = "Player"
	_player.position = _spawn_position
	add_child(_player)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		_reset_player()


func _reset_player() -> void:
	if _player == null:
		return
	_player.velocity = Vector3.ZERO
	_player.global_position = global_transform * _spawn_position
	_player.reset_physics_interpolation()


func _vector3(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])


func _set_unaccepted_contract() -> void:
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("generation_ready", false)
	set_meta("operator_approved", false)
	set_meta("observed_openings", PackedStringArray())
	set_meta("tested_connectors", PackedStringArray())
