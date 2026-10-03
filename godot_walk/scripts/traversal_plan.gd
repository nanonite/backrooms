extends RefCounted

## Runtime reader for `assets/<scene>/traversal_manifest.json`, written by
## `scripts/splat_pipeline/traversal_plan.py`.
##
## The manifest holds everything the walk test needs to be *calibrated* rather
## than hand-placed: the route's cells, the probes that must be stopped, the
## spawn derived from the collision's own floor surface, and the tolerances each
## of those is checked against.  Reading them here rather than restating them in
## the test means a regenerated plan changes the test's behaviour instead of
## silently disagreeing with it.
##
## Every getter returns a concretely typed value.  GDScript cannot infer the type
## of an expression built from an untyped Dictionary read, so returning `Variant`
## and letting `:=` at the call site fail to infer would be a trap for every
## reader.

const MANIFEST_SCHEMA_VERSION := 1

var _data: Dictionary = {}
var _load_error := ""


func _init(manifest_path: String) -> void:
	_load_error = ""
	var file := FileAccess.open(manifest_path, FileAccess.READ)
	if file == null:
		_load_error = "cannot open traversal manifest %s (error %d)" % [
			manifest_path, FileAccess.get_open_error(),
		]
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		_load_error = "traversal manifest %s is not a JSON object" % manifest_path
		return
	_data = parsed
	var schema := int(_data.get("schema_version", -1))
	if schema != MANIFEST_SCHEMA_VERSION:
		_load_error = "traversal manifest %s has schema_version %d, expected %d" % [
			manifest_path, schema, MANIFEST_SCHEMA_VERSION,
		]


func is_valid() -> bool:
	## Whether the manifest loaded and declares a schema this build understands.
	return _load_error.is_empty()


func load_error() -> String:
	## Why loading failed, or an empty string when it succeeded.
	return _load_error


func scene_id() -> String:
	return String(_data.get("scene_id", ""))


func collision_transform() -> Transform3D:
	## The transform the generated collision node must carry.
	return _transform("collision_node", "transform_3x4")


func collision_glb_path() -> String:
	## Where the collision mesh the plan was derived from lives.
	return "res://assets/corridor_splat/collision/corridor_splat.collision.glb"


func collision_md5() -> String:
	return String(_data.get("sources", {}).get("collision_glb_md5", ""))


func collision_triangles() -> int:
	return int(_data.get("sources", {}).get("collision_triangles", 0))


func spawn_marker() -> Vector3:
	## Where the contract places PlayerSpawn: a drop-in reference, not a capsule centre.
	return _vector3(_data.get("spawn", {}).get("marker_m", [0.0, 0.0, 0.0]))


func player_origin() -> Vector3:
	## Where the CharacterBody3D belongs: the collision's floor under the marker,
	## plus half the capsule height.
	return _vector3(_data.get("spawn", {}).get("player_origin_m", [0.0, 0.0, 0.0]))


func spawn_floor_surface() -> float:
	return float(_data.get("spawn", {}).get("floor_surface_m", 0.0))


func spawn_ceiling_surface() -> float:
	return float(_data.get("spawn", {}).get("ceiling_surface_m", 0.0))


func spawn_drop() -> float:
	return float(_data.get("spawn", {}).get("drop_m", 0.0))


func capsule_radius() -> float:
	return float(_data.get("player", {}).get("capsule_radius_m", 0.3))


func capsule_height() -> float:
	return float(_data.get("player", {}).get("capsule_height_m", 1.2))


func player_speed() -> float:
	## The controller's top speed, used to size a walk leg's tick budget.
	return float(_data.get("player", {}).get("speed_mps", 4.0))


func clearance_test_height() -> float:
	## The height above the contract floor at which a column is open or solid.
	return float(_data.get("clearance", {}).get("test_height_m", 1.0))


func collision_report() -> Dictionary:
	## #84's own verdict, failing checks included.
	return _data.get("collision_report", {})


func access_cells() -> Array:
	## Walkable cells from the route's end to the least-headroom boundary cell.
	return _data.get("access_cells", [])


func required_clearance() -> float:
	## Capsule height plus margin: the headroom a route must leave.
	return float(_data.get("clearance", {}).get("required_m", 1.25))


func clearance_margin() -> float:
	return float(_data.get("clearance", {}).get("margin_m", 0.05))


func route_cells() -> Array:
	## The walkable cells the route turns at, spawn first and farthest last.
	return _data.get("route_cells", [])


func opening_cells() -> Array:
	## The three cells around the tightest point on the route.
	return _data.get("opening_cells", [])


func probes() -> Array:
	## Walks that must be stopped by solid geometry.
	return _data.get("probes", [])


func tolerance(key: String, fallback: float) -> float:
	return float(_data.get("tolerances", {}).get(key, fallback))


func safety_net_top() -> float:
	return float(_data.get("safety_net", {}).get("top_m", 0.0))


func safety_net_size() -> Vector3:
	return _vector3(_data.get("safety_net", {}).get("size_m", [1.0, 1.0, 1.0]))


func waypoint_position(cell: Array) -> Vector3:
	## World position of a floor-plan cell, as ``(x, z)`` with the floor's y.
	var origin: Array = _data.get("columns", {}).get("origin_world_m", [0.0, 0.0])
	var size: float = float(_data.get("columns", {}).get("size_m", 0.25))
	var x: float = float(origin[0]) + (float(cell[0]) + 0.5) * size
	var z: float = float(origin[1]) + (float(cell[1]) + 0.5) * size
	return Vector3(x, 0.0, z)


func cell_of(world: Vector3) -> Array:
	## Inverse of :func:`waypoint_position`, for checking which cell a walker is in.
	var origin: Array = _data.get("columns", {}).get("origin_world_m", [0.0, 0.0])
	var size: float = float(_data.get("columns", {}).get("size_m", 0.25))
	return [
		int(floor((world.x - float(origin[0])) / size)),
		int(floor((world.z - float(origin[1])) / size)),
	]


func low_clearance_cell() -> Array:
	## The walkable cell with the least headroom: an unsupported boundary.
	return _data.get("low_clearance_cell", [])


func low_clearance_m() -> float:
	return float(_data.get("low_clearance_m", 0.0))


func column_record() -> Dictionary:
	return _data.get("columns", {})


func _transform(section: String, key: String) -> Transform3D:
	var rows: Array = _data.get(section, {}).get(key, [])
	if rows.size() != 3:
		return Transform3D.IDENTITY
	var basis := Basis()
	for row in range(3):
		var values: Array = rows[row]
		for column in 3:
			basis[column][row] = float(values[column])
	var translation := _vector3(rows[3]) if rows.size() > 3 else Vector3.ZERO
	return Transform3D(basis, translation)


func _vector3(value: Variant) -> Vector3:
	if value is Array and (value as Array).size() == 3:
		return Vector3(float(value[0]), float(value[1]), float(value[2]))
	return Vector3.ZERO
