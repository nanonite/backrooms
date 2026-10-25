extends "res://scripts/issue149_generated_walkthrough.gd"

const STREAMER := preload("res://scripts/issue156_bounded_streamer.gd")
const GEOMETRY := preload("res://scripts/issue160_room_geometry.gd")
const EVIDENCE_LAYOUT := "res://evidence/2026-10-23-issue-156/layout_seed_149.json"
const MAX_RESIDENT_MODULES := 4
const MAX_CACHED_MODULE_TYPES := 4

var _streamer: Node
var _connection_geometry: Node3D
var _cached_rooms_by_module: Dictionary = {}
var _room_cache_order: Array[String] = []


func _exit_tree() -> void:
	for room: Node3D in _cached_rooms_by_module.values():
		room.free()
	_cached_rooms_by_module.clear()
	_room_cache_order.clear()


func _layout_argument() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--layout="):
			return argument.trim_prefix("--layout=")
	return EVIDENCE_LAYOUT


func _instantiate_modules() -> bool:
	if not _streaming_settings_valid():
		push_error("#156 layout requests unsupported streaming bounds")
		return false
	for placement: Dictionary in _layout.placements:
		var module: Dictionary = _modules_by_id.get(placement.module_id, {})
		if module.is_empty() or module.scene != placement.scene:
			push_error("#156 layout references an unregistered module: %s" % placement.module_id)
			return false
		if _scene_hash(module) != placement.scene_sha256:
			push_error("#156 scene hash is stale for %s" % placement.module_id)
			return false
		if not _layout_sockets_match(module, placement):
			return false
	return true


func _streaming_settings_valid() -> bool:
	var settings: Dictionary = _layout.settings.get("streaming", {})
	return settings.get("mode") == "bounded_graph_window" \
		and settings.get("graph_radius") == 1 \
		and settings.get("max_resident_modules") == MAX_RESIDENT_MODULES \
		and settings.get("retain_backtracking") == true


func _layout_sockets_match(module: Dictionary, placement: Dictionary) -> bool:
	var expected: Array[String] = []
	for socket: Dictionary in module.sockets:
		expected.append(socket.id)
	var actual: Array = placement.open_sockets.duplicate()
	expected.sort()
	actual.sort()
	if actual == expected:
		return true
	push_error("#156 layout socket list differs from catalog for %s" % placement.instance_id)
	return false


func _socket_world(endpoint: Dictionary) -> Dictionary:
	var placement := _placement(endpoint.instance_id)
	var module: Dictionary = _modules_by_id.get(placement.get("module_id", ""), {})
	var socket: Dictionary = _socket_config(module, endpoint.socket_id)
	if placement.is_empty() or socket.is_empty():
		push_error("Missing #156 socket endpoint: %s/%s" % [endpoint.instance_id, endpoint.socket_id])
		return {}
	var transform: Dictionary = placement.transform
	var origin := _vector3(transform.position)
	var local := Transform3D(Basis(Vector3.UP, deg_to_rad(float(transform.yaw_degrees))), origin)
	var world := global_transform * local
	return {
		"position": world * _vector3(socket.local_floor_center),
		"normal": world.basis * _vector3(socket.outward_normal),
		"size": socket.clear_size_m,
		"floor_y": (world * _vector3(socket.local_floor_center)).y,
	}


func _add_connection_transitions() -> void:
	return


func _build_player() -> void:
	super._build_player()
	_streamer = STREAMER.new()
	_streamer.name = "BoundedLayoutStreamer"
	add_child(_streamer)
	var settings: Dictionary = _layout.settings.streaming
	if not _streamer.configure(self, settings.graph_radius, settings.max_resident_modules):
		push_error("#156 bounded streamer configuration is invalid")
		get_tree().quit(2)
		return
	if not _streamer.refresh(true):
		push_error("#156 could not load the initial room window")
		get_tree().quit(2)


func _reset_player() -> void:
	super._reset_player()
	if _streamer != null:
		_streamer.refresh(true)


func streaming_layout() -> Dictionary:
	return _layout


func streaming_placement(instance_id: String) -> Dictionary:
	return _placement(instance_id)


func streaming_module(module_id: String) -> Dictionary:
	return _modules_by_id.get(module_id, {})


func streaming_player_position() -> Vector3:
	return _player.global_position if _player != null else Vector3.ZERO


func stream_load_room(instance_id: String) -> bool:
	if _instances_by_id.has(instance_id):
		return true
	var placement := _placement(instance_id)
	if placement.is_empty():
		push_error("#156 requested unknown room instance: %s" % instance_id)
		return false
	var module_id: String = placement.module_id
	var room := _take_cached_room(module_id)
	if room == null:
		room = _instantiate_module(placement)
	if room == null:
		return false
	room.name = instance_id
	room.position = _vector3(placement.transform.position)
	room.rotation.y = deg_to_rad(placement.transform.yaw_degrees)
	room.set_meta("layout_module_id", placement.module_id)
	room.set_meta("layout_instance_id", instance_id)
	add_child(room)
	if not _module_sockets_match(room, placement):
		remove_child(room)
		room.queue_free()
		return false
	_instances_by_id[instance_id] = room
	_apply_stream_mutations(instance_id, room)
	return true


func stream_unload_room(instance_id: String) -> void:
	var room: Node3D = _instances_by_id.get(instance_id)
	if room == null:
		return
	_instances_by_id.erase(instance_id)
	remove_child(room)
	_store_cached_room(String(room.get_meta("layout_module_id", "")), room)


func _take_cached_room(module_id: String) -> Node3D:
	var room: Node3D = _cached_rooms_by_module.get(module_id)
	if room == null:
		return null
	_cached_rooms_by_module.erase(module_id)
	_room_cache_order.erase(module_id)
	return room


func _store_cached_room(module_id: String, room: Node3D) -> void:
	if module_id.is_empty():
		room.free()
		return
	if _cached_rooms_by_module.has(module_id):
		var previous: Node3D = _cached_rooms_by_module[module_id]
		previous.free()
		_room_cache_order.erase(module_id)
	_cached_rooms_by_module[module_id] = room
	_room_cache_order.append(module_id)
	while _room_cache_order.size() > MAX_CACHED_MODULE_TYPES:
		var oldest: String = _room_cache_order.pop_front()
		var expired: Node3D = _cached_rooms_by_module[oldest]
		_cached_rooms_by_module.erase(oldest)
		expired.free()


func stream_rebuild_geometry(active_ids: Array[String]) -> void:
	if _connection_geometry != null:
		remove_child(_connection_geometry)
		_connection_geometry.free()
	_connection_geometry = Node3D.new()
	_connection_geometry.name = "ConnectionGeometry"
	add_child(_connection_geometry)
	_build_connection_geometry(active_ids)


func _build_floor_material() -> Material:
	var material := StandardMaterial3D.new()
	material.albedo_texture = load("res://assets/psx_extension/textures/floor_source_video.png")
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _build_connection_geometry(active_ids: Array[String]) -> void:
	var active := {}
	for instance_id in active_ids:
		active[instance_id] = true
	var floor_material: Material = null
	if not get_meta("stream_floor_removed", false):
		floor_material = _build_floor_material()
	var trim := _solid_material(Color(0.37, 0.34, 0.23))
	var cap := _textured_material("res://assets/psx_extension/textures/wallpaper_source_video.png")
	var cap_count := 0
	for index in _layout.connections.size():
		var connection: Dictionary = _layout.connections[index]
		var left_id: String = connection.from.instance_id
		var right_id: String = connection.to.instance_id
		if active.has(left_id) and active.has(right_id):
			_add_transition(index, connection, trim, floor_material)
		elif active.has(left_id) or active.has(right_id):
			var endpoint: Dictionary = connection.from if active.has(left_id) else connection.to
			_add_stream_cap(index, endpoint, cap)
			cap_count += 1
	set_meta("stream_frontier_cap_count", cap_count)


func _add_transition(index: int, connection: Dictionary, trim: Material, floor_material: Material) -> void:
	var socket: Dictionary = _socket_world(connection.from)
	var center := to_local(socket.position)
	var normal: Vector3 = (global_basis.inverse() * socket.normal).normalized()
	var size: Array = socket.size
	var floor_size := Vector3(0.24, 0.12, size[0]) if absf(normal.x) > 0.9 else Vector3(size[0], 0.12, 0.24)
	if floor_material != null:
		GEOMETRY.add_box(_connection_geometry, "ConnectorThreshold_%03d" % index,
			center + Vector3.DOWN * 0.06, floor_size, floor_material)
	_add_portal_frame(index, center, normal, size, trim)


func _add_stream_cap(index: int, endpoint: Dictionary, material: Material) -> void:
	var socket: Dictionary = _socket_world(endpoint)
	var center := to_local(socket.position)
	var normal: Vector3 = (global_basis.inverse() * socket.normal).normalized()
	var size: Array = socket.size
	var cap_size := Vector3(0.12, size[1], size[0]) if absf(normal.x) > 0.9 else Vector3(size[0], size[1], 0.12)
	GEOMETRY.add_box(_connection_geometry, "StreamCap_%03d" % index,
		center + Vector3.UP * (float(size[1]) * 0.5), cap_size, material)


func _add_portal_frame(index: int, center: Vector3, normal: Vector3,
		size: Array, material: Material) -> void:
	var half_width := float(size[0]) * 0.5
	var height: float = size[1]
	var horizontal_x := absf(normal.x) < 0.9
	for side in [-1.0, 1.0]:
		var offset := Vector3(side * half_width, height * 0.5, 0.0) if horizontal_x else Vector3(0.0, height * 0.5, side * half_width)
		var jamb := Vector3(0.08, height, 0.08)
		GEOMETRY.add_box(_connection_geometry, "Portal_%03d_Jamb_%s" % [index, str(side)],
			center + offset, jamb, material, true, false)
	var header_offset := Vector3(0.0, height, 0.0)
	var header_size := Vector3(size[0], 0.08, 0.08) if horizontal_x else Vector3(0.08, 0.08, size[0])
	GEOMETRY.add_box(_connection_geometry, "Portal_%03d_Header" % index,
		center + header_offset, header_size, material, true, false)


func _solid_material(color: Color) -> Material:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _textured_material(path: String) -> Material:
	var material := StandardMaterial3D.new()
	material.albedo_texture = load(path)
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func stream_set_state(center_id: String, loaded_ids: Array[String], peak: int,
		loads: int, unloads: int) -> void:
	set_meta("streaming_enabled", true)
	set_meta("stream_center_id", center_id)
	set_meta("stream_loaded_ids", PackedStringArray(loaded_ids))
	set_meta("stream_loaded_count", loaded_ids.size())
	set_meta("stream_peak_resident", peak)
	set_meta("stream_load_events", loads)
	set_meta("stream_unload_events", unloads)
	set_meta("stream_window_radius", _layout.settings.streaming.graph_radius)
	set_meta("stream_max_resident", _layout.settings.streaming.max_resident_modules)
	set_meta("stream_cached_module_count", _cached_rooms_by_module.size())
	set_meta("stream_total_module_instances", loaded_ids.size() + _cached_rooms_by_module.size())
	set_meta("stream_max_cached_module_types", MAX_CACHED_MODULE_TYPES)


func stream_set_floor_negative(enabled: bool) -> void:
	set_meta("stream_floor_removed", enabled)
	for instance_id: String in _instances_by_id:
		var room: Node3D = _instances_by_id[instance_id]
		_remove_room_floors(room)
	if enabled and _connection_geometry != null:
		remove_child(_connection_geometry)
		_connection_geometry.queue_free()
		_connection_geometry = null


func stream_set_boundary_negative(instance_id: String, relative_path: String) -> bool:
	set_meta("stream_boundary_negative_instance", instance_id)
	set_meta("stream_boundary_negative_path", relative_path)
	var room: Node3D = _instances_by_id.get(instance_id)
	if room == null:
		return true
	return _remove_boundary(room, relative_path)


func _apply_stream_mutations(instance_id: String, room: Node3D) -> void:
	if get_meta("stream_floor_removed", false):
		_remove_room_floors(room)
	if get_meta("stream_boundary_negative_instance", "") == instance_id:
		_remove_boundary(room, get_meta("stream_boundary_negative_path", ""))


func _remove_room_floors(room: Node3D) -> void:
	for child: Node in room.get_children():
		if child.name in ["AuthoredFloor", "AuthoredPlanarRouteFloor"]:
			child.queue_free()


func _remove_boundary(room: Node3D, relative_path: String) -> bool:
	var boundary := room.get_node_or_null(relative_path)
	if boundary == null:
		return false
	boundary.queue_free()
	return true
