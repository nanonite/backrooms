extends Node

const DEFAULT_GRAPH_RADIUS := 1
const DEFAULT_MAX_RESIDENT := 4

var _host: Node3D
var _graph_radius := DEFAULT_GRAPH_RADIUS
var _max_resident := DEFAULT_MAX_RESIDENT
var _adjacency: Dictionary = {}
var _center_id := ""
var _loaded_ids: Array[String] = []
var _peak_resident := 0
var _load_events := 0
var _unload_events := 0
var _reported_failure := false


func configure(host: Node3D, graph_radius: int, max_resident: int) -> bool:
	if host == null or graph_radius < 0 or max_resident < 1:
		return false
	_host = host
	_graph_radius = graph_radius
	_max_resident = max_resident
	_adjacency = _make_adjacency(host.call("streaming_layout"))
	_center_id = String(host.call("streaming_layout").spawn.instance_id)
	return not _center_id.is_empty()


func _process(_delta: float) -> void:
	if _host == null:
		return
	if not refresh():
		if not _reported_failure:
			push_error("#156 could not load the next bounded room window; the current window remains active")
			_reported_failure = true


func refresh(force: bool = false) -> bool:
	var candidate := _find_center_id()
	if candidate.is_empty():
		return false
	if not force and candidate == _center_id:
		return true
	var desired := _desired_window(candidate)
	if desired.size() > _max_resident:
		return false
	var retained := _retained_window(candidate, desired)
	if not _replace_window(retained, desired):
		return false
	_center_id = candidate
	_peak_resident = maxi(_peak_resident, _loaded_ids.size())
	_host.call("stream_set_state", _center_id, _loaded_ids, _peak_resident,
		_load_events, _unload_events)
	_reported_failure = false
	return true


func _retained_window(candidate: String, desired: Array[String]) -> Array[String]:
	var retained: Array[String] = []
	if not _loaded_ids.has(candidate):
		return retained
	for instance_id in _loaded_ids.duplicate():
		if desired.has(instance_id):
			retained.append(instance_id)
	return retained


func _replace_window(retained: Array[String], desired: Array[String]) -> bool:
	if not _same_ids(_loaded_ids, retained):
		_host.call("stream_rebuild_geometry", retained)
		_unload_outside_window(retained)
		_loaded_ids = retained
	for instance_id in desired:
		if _loaded_ids.has(instance_id):
			continue
		if _loaded_ids.size() >= _max_resident or not bool(_host.call("stream_load_room", instance_id)):
			return false
		_loaded_ids.append(instance_id)
		_loaded_ids.sort()
		_load_events += 1
		_peak_resident = maxi(_peak_resident, _loaded_ids.size())
		_host.call("stream_rebuild_geometry", _loaded_ids)
	return true


func _unload_outside_window(retained: Array[String]) -> void:
	for instance_id in _loaded_ids.duplicate():
		if retained.has(instance_id):
			continue
		_host.call("stream_unload_room", instance_id)
		_unload_events += 1


func _find_center_id() -> String:
	var position: Vector3 = _host.call("streaming_player_position")
	if _contains(_center_id, position):
		return _center_id
	for placement: Dictionary in _host.call("streaming_layout").placements:
		var instance_id := String(placement.instance_id)
		if _contains(instance_id, position):
			return instance_id
	return _center_id


func _contains(instance_id: String, world_position: Vector3) -> bool:
	var placement: Dictionary = _host.call("streaming_placement", instance_id)
	var module: Dictionary = _host.call("streaming_module", placement.get("module_id", ""))
	if placement.is_empty() or module.is_empty():
		return false
	var transform: Dictionary = placement.transform
	var origin := Vector3(transform.position[0], transform.position[1], transform.position[2])
	var local_transform := Transform3D(Basis(Vector3.UP,
		deg_to_rad(float(transform.yaw_degrees))), origin)
	var local_position: Vector3 = local_transform.affine_inverse() * _host.to_local(world_position)
	var polygon := PackedVector2Array()
	for point: Array in module.placement_footprint_xz:
		polygon.append(Vector2(point[0], point[1]))
	return _point_in_polygon(Vector2(local_position.x, local_position.z), polygon)


func _point_in_polygon(point: Vector2, polygon: PackedVector2Array) -> bool:
	var inside := false
	var previous := polygon.size() - 1
	for current in polygon.size():
		var a: Vector2 = polygon[previous]
		var b: Vector2 = polygon[current]
		if _on_segment(point, a, b):
			return true
		if (a.y > point.y) != (b.y > point.y):
			var crossing_x := (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x
			if point.x < crossing_x:
				inside = not inside
		previous = current
	return inside


func _on_segment(point: Vector2, start: Vector2, end: Vector2) -> bool:
	var edge := end - start
	var relative := point - start
	if absf(edge.cross(relative)) > 0.002:
		return false
	return relative.dot(edge) >= -0.002 and relative.dot(edge) <= edge.length_squared() + 0.002


func _desired_window(center_id: String) -> Array[String]:
	var depths := {center_id: 0}
	var queue: Array = [center_id]
	var head := 0
	while head < queue.size():
		var current_id: String = queue[head]
		head += 1
		var depth: int = depths[current_id]
		if depth >= _graph_radius:
			continue
		for neighbor: String in _adjacency.get(current_id, []):
			if depths.has(neighbor):
				continue
			depths[neighbor] = depth + 1
			queue.append(neighbor)
	var result: Array[String] = []
	for instance_id: String in depths:
		result.append(instance_id)
	result.sort()
	return result


func _make_adjacency(layout: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for placement: Dictionary in layout.placements:
		result[placement.instance_id] = []
	for connection: Dictionary in layout.connections:
		var left: String = connection.from.instance_id
		var right: String = connection.to.instance_id
		result[left].append(right)
		result[right].append(left)
	return result


func _same_ids(left: Array[String], right: Array[String]) -> bool:
	if left.size() != right.size():
		return false
	for index in left.size():
		if left[index] != right[index]:
			return false
	return true
