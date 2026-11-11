extends SceneTree

## Re-run the #205 room acoustic probe on each admitted library module in isolation.

const INDEX_PATH := "res://room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
const DEFAULT_OUTPUT := "res://evidence/2026-11-11-issue-216/module_acoustics_probe_results.json"
const PROBE := preload("res://scripts/room_acoustic_probe.gd")
const FLOOR_PROBE := preload("res://scripts/shape_room_probe.gd")
const HEAD_OFFSET_M := 1.1
const SETTLE_FRAMES := 3
const FLOOR_RAY_TOP_M := 100.0
const FLOOR_RAY_BOTTOM_M := -100.0

var _failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var index := _read_json(INDEX_PATH)
	if index.is_empty():
		quit(2)
		return
	var measurements := await _measure_modules(index.get("modules", []))
	if not _failures.is_empty():
		for failure: String in _failures:
			printerr("ISSUE216_PROBE: " + failure)
		quit(1)
		return
	var report := _report(measurements)
	if not _write_report(report):
		quit(2)
		return
	print("ISSUE216_MODULE_ACOUSTICS modules=%d" % measurements.size())
	quit(0)


func _measure_modules(entries: Array) -> Dictionary:
	var ordered: Array = entries.duplicate()
	ordered.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
		return String(left.get("module_id", "")) < String(right.get("module_id", "")))
	var measurements: Dictionary = {}
	for entry: Dictionary in ordered:
		var key := "%s@%d" % [entry.get("module_id", ""), int(entry.get("version", 0))]
		var result: Dictionary = await _measure_module(entry)
		if result.is_empty():
			_failures.append("%s could not be probed" % key)
		else:
			measurements[key] = result
	return measurements


func _measure_module(entry: Dictionary) -> Dictionary:
	var profile := _read_json(_profile_path(entry))
	var packed := load(String(entry.get("scene", ""))) as PackedScene
	if profile.is_empty() or packed == null:
		_failures.append("%s profile or scene is missing" % entry.get("module_id", "unknown"))
		return {}
	var room := packed.instantiate() as Node3D
	if room == null:
		_failures.append("%s scene root is not Node3D" % entry.get("module_id", "unknown"))
		return {}
	var assembly := Node3D.new()
	assembly.name = "AcousticProbeAssembly"
	root.add_child(assembly)
	assembly.add_child(room)
	await _settle_physics()
	var result := _sample_room(room, profile)
	await _free_assembly(assembly)
	return result


func _sample_room(room: Node3D, profile: Dictionary) -> Dictionary:
	var shape: Dictionary = profile.get("shape", {})
	var polygon := _polygon(shape.get("footprint_xz", []))
	var center := _polygon_centroid(polygon)
	var space := room.get_world_3d().direct_space_state
	var floor_y := _floor_y(room, space, center)
	if not is_finite(floor_y):
		_failures.append("%s has no named floor below footprint centroid %s" % [room.name, center])
		return {}
	var local_head := Vector3(center.x, floor_y + HEAD_OFFSET_M, center.y)
	var head_origin := room.to_global(local_head)
	var world_floor_y := room.to_global(Vector3(0.0, floor_y, 0.0)).y
	var ceiling_hint := float(shape.get("ceiling_height_m", 0.0))
	var probe := PROBE.new()
	var parameters: Dictionary = probe.sample(space, head_origin, world_floor_y,
		[] as Array[RID], ceiling_hint)
	var metrics: Dictionary = probe.metrics.duplicate()
	metrics.merge(parameters, true)
	probe.free()
	return {
		"sample_method": "accepted_footprint_area_centroid",
		"sample_point_m": [head_origin.x, head_origin.y, head_origin.z],
		"floor_y_m": floor_y,
		"ceiling_hint_m": ceiling_hint,
		"metrics": metrics,
	}


func _floor_y(room: Node3D, space: PhysicsDirectSpaceState3D, center: Vector2) -> float:
	if room.has_meta("walk_floor_y"):
		return float(room.get_meta("walk_floor_y"))
	var ray_origin := room.to_global(Vector3(center.x, FLOOR_RAY_TOP_M, center.y))
	var world_floor_y := _floor_at(space, ray_origin)
	if not is_finite(world_floor_y):
		return NAN
	return room.to_local(Vector3(ray_origin.x, world_floor_y, ray_origin.z)).y


func _floor_at(space: PhysicsDirectSpaceState3D, point: Vector3) -> float:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(point.x, FLOOR_RAY_TOP_M, point.z),
		Vector3(point.x, FLOOR_RAY_BOTTOM_M, point.z))
	query.collision_mask = PROBE.COLLISION_MASK
	for attempt in 32:
		var hit := space.intersect_ray(query)
		if hit.is_empty():
			return NAN
		var collider := hit.get("collider") as CollisionObject3D
		if collider != null and FLOOR_PROBE.is_floor_body(collider):
			return float(hit.position.y)
		if collider == null:
			return NAN
		query.exclude.append(collider.get_rid())
	return NAN


func _polygon_centroid(points: Array[Vector2]) -> Vector2:
	var twice_area := 0.0
	var weighted := Vector2.ZERO
	for index in points.size():
		var current: Vector2 = points[index]
		var next: Vector2 = points[(index + 1) % points.size()]
		var cross := current.x * next.y - next.x * current.y
		twice_area += cross
		weighted += (current + next) * cross
	if absf(twice_area) < 0.000001:
		return Vector2(NAN, NAN)
	return weighted / (3.0 * twice_area)


func _polygon(value: Variant) -> Array[Vector2]:
	var points: Array[Vector2] = []
	if not value is Array:
		return points
	for point: Array in value:
		if point.size() >= 2:
			points.append(Vector2(float(point[0]), float(point[1])))
	return points


func _profile_path(entry: Dictionary) -> String:
	var room_dir_value: Variant = entry.get("room_dir")
	var room_dir := "" if room_dir_value == null else str(room_dir_value)
	if not room_dir.is_empty():
		return "res://%s/module_profile_v1.json" % room_dir.trim_prefix("godot_walk/")
	return "res://room_catalog/module_profiles/%s-v%d.json" % [
		entry.get("module_id", ""), int(entry.get("version", 0))]


func _read_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_failures.append("cannot read %s" % path)
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		_failures.append("%s is not a JSON object" % path)
		return {}
	return parsed


func _report(measurements: Dictionary) -> Dictionary:
	return {
		"schema_version": 1,
		"probe_version": "room-acoustic-probe-#205",
		"runner_version": "module-acoustics-probe-0.1.0",
		"settings": {
			"ray_count": PROBE.RAY_COUNT,
			"ray_length_m": PROBE.RAY_LENGTH_M,
			"collision_mask": PROBE.COLLISION_MASK,
			"head_offset_m": HEAD_OFFSET_M,
			"sample_method": "accepted_footprint_area_centroid",
			"floor_y_source": "scene_meta.walk_floor_y_or_named_floor_collider",
			"ceiling_hint_source": "module_profile_v1.shape.ceiling_height_m",
			"physics_settle_frames": SETTLE_FRAMES,
		},
		"modules": measurements,
	}


func _write_report(report: Dictionary) -> bool:
	var path := _argument("--output=", DEFAULT_OUTPUT)
	var absolute := ProjectSettings.globalize_path(path) if path.begins_with("res://") else path
	var parent := absolute.get_base_dir()
	if DirAccess.make_dir_recursive_absolute(parent) != OK and not DirAccess.dir_exists_absolute(parent):
		printerr("ISSUE216_PROBE: cannot create output directory %s" % parent)
		return false
	var file := FileAccess.open(absolute, FileAccess.WRITE)
	if file == null:
		printerr("ISSUE216_PROBE: cannot write %s" % absolute)
		return false
	file.store_string(JSON.stringify(report, "\t") + "\n")
	return true


func _argument(prefix: String, fallback: String) -> String:
	for argument: String in OS.get_cmdline_user_args() + OS.get_cmdline_args():
		if argument.begins_with(prefix):
			return argument.trim_prefix(prefix)
	return fallback


func _settle_physics() -> void:
	for frame in SETTLE_FRAMES:
		await physics_frame


func _free_assembly(assembly: Node3D) -> void:
	root.remove_child(assembly)
	assembly.free()
