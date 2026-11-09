extends SceneTree

## Headless reverb-metadata test for gmap-0.11.0 (#204).
## godot4 --headless --path godot_walk --script res://scripts/test_issue204_reverb.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--legacy-map=res://.../gmap-1-gmap-0.10.0.json] \
##   [--legacy-rooms=res://.../gmap-1-gmap-0.10.0/index.json] \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"

var failures: Array[String] = []
var map: Dictionary = {}
var specs: Dictionary = {}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var map_data: Variant = ASSEMBLY.load_json(ASSEMBLY.argument("--map="))
	var index_data: Variant = ASSEMBLY.load_json(ASSEMBLY.argument("--rooms="))
	if not map_data is Dictionary or not index_data is Dictionary:
		_fail("Pass --map=res://...json and --rooms=res://.../index.json after --")
		quit(1)
		return
	map = map_data
	specs = ASSEMBLY.load_specs(ASSEMBLY.argument("--rooms="))
	var report := {"map_id": map.map_id, "rooms_checked": specs.size()}
	report["positive"] = await _run_positive()
	report["negative_controls"] = await _run_negative_controls()
	report["legacy"] = await _run_legacy()
	report["scene"] = await _check_scene()
	report["failures"] = failures
	_write_report(report)
	var positive: Dictionary = report.positive
	print("ISSUE204_REVERB: %s map=%s wet=%d/%d dry=%d/%d rooms=%d/%d module_rooms=%d volumes=%d/%d mutated=%d/%d legacy=%s controls=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		positive.wet_rooms, positive.rooms, positive.dry_rooms, positive.rooms,
		positive.checked_rooms, positive.rooms, positive.module_rooms,
		positive.volume_checks, positive.rooms,
		positive.mutated, positive.mutation_checks,
		str(report.legacy.get("status", "not_run")), str(report.negative_controls.keys())])
	quit(0 if failures.is_empty() else 1)


func _build(map_data: Dictionary, room_specs: Dictionary) -> Node3D:
	var assembly := ASSEMBLY.new()
	assembly.auto_start = false
	root.add_child(assembly)
	assembly.assemble(map_data, room_specs)
	await physics_frame
	await physics_frame
	return assembly


func _release(assembly: Node3D) -> void:
	root.remove_child(assembly)
	assembly.free()
	await physics_frame


func _walkable(document: Dictionary) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for cell: Dictionary in document.cells:
		if String(cell.role) != "void":
			result.append(cell)
	return result


func _run_positive() -> Dictionary:
	var result := {"rooms": 0, "checked_rooms": 0, "wet_rooms": 0, "dry_rooms": 0,
		"module_rooms": 0, "volume_checks": 0, "mutated": 0, "mutation_checks": 0,
		"failures": [] as Array[String]}
	var assembly := await _build(map, specs)
	var spawn_id := String(map.cells[0].cell_id)
	for cell: Dictionary in _walkable(map):
		result.rooms += 1
		var cell_id := String(cell.cell_id)
		var expected := bool(cell.get("reverb", false))
		var room: Node3D = assembly.room_node(cell_id)
		if room == null:
			result.failures.append("%s: no instanced room" % cell_id)
			continue
		result.checked_rooms += 1
		if cell.has("module"):
			result.module_rooms += 1
		if cell_id == spawn_id and expected:
			result.failures.append("%s: spawn cell is wet in the map" % cell_id)
		if expected:
			result.wet_rooms += 1
		else:
			result.dry_rooms += 1
		if not room.has_meta("reverb_enabled"):
			result.failures.append("%s: room has no reverb_enabled metadata" % cell_id)
		elif typeof(room.get_meta("reverb_enabled")) != TYPE_BOOL:
			result.failures.append("%s: reverb_enabled is not a bool" % cell_id)
		elif bool(room.get_meta("reverb_enabled")) != expected:
			result.failures.append("%s: reverb_enabled %s, map %s" % [
				cell_id, str(room.get_meta("reverb_enabled")), str(expected)])
		if not room.has_meta("room_volume_m3"):
			result.failures.append("%s: room has no room_volume_m3 metadata" % cell_id)
		else:
			var volume := float(room.get_meta("room_volume_m3"))
			var expected_volume := ASSEMBLY.nominal_room_volume_m3(cell)
			result.volume_checks += 1
			if volume <= 0.0 or absf(volume - expected_volume) > 0.01:
				result.failures.append("%s: room_volume_m3 %.3f, expected %.3f" % [
					cell_id, volume, expected_volume])
		if assembly.room_reverb_enabled(cell_id) != expected:
			result.failures.append("%s: room_reverb_enabled disagrees with the map" % cell_id)
		# Runtime mutation: flip the metadata without touching the map or geometry.
		var children_before := room.get_child_count()
		result.mutation_checks += 1
		if not assembly.set_room_reverb(cell_id, not expected):
			result.failures.append("%s: set_room_reverb refused" % cell_id)
		elif assembly.room_reverb_enabled(cell_id) != (not expected):
			result.failures.append("%s: set_room_reverb did not stick" % cell_id)
		elif room.get_child_count() != children_before:
			result.failures.append("%s: set_room_reverb changed the room geometry" % cell_id)
		else:
			result.mutated += 1
		assembly.set_room_reverb(cell_id, expected)
	if result.wet_rooms == 0 or result.dry_rooms == 0:
		result.failures.append("sample map has no wet/dry mix: wet=%d dry=%d" % [
			result.wet_rooms, result.dry_rooms])
	if result.module_rooms == 0:
		result.failures.append("sample map has no module room to check")
	_fail_all(result.failures)
	await _release(assembly)
	return result


func _run_negative_controls() -> Dictionary:
	var controls := {}
	controls["map_flag_flip"] = await _control_map_flag_flip()
	controls["missing_flag_is_dry"] = await _control_missing_flag()
	for name: String in controls:
		_expect(not controls[name].applicable or controls[name].failed_as_expected,
			"Negative control %s did not fail" % name)
	return controls


func _control_map_flag_flip() -> Dictionary:
	var altered := map.duplicate(true)
	var target := {}
	for cell: Dictionary in altered.cells:
		if String(cell.role) != "void" and String(cell.cell_id) != String(altered.cells[0].cell_id):
			target = cell
			cell["reverb"] = not bool(cell.get("reverb", false))
			break
	if target.is_empty():
		return {"applicable": false, "failed_as_expected": false, "reason": "no non-spawn room"}
	var assembly := await _build(altered, specs)
	var room: Node3D = assembly.room_node(String(target.cell_id))
	var followed := room != null and bool(room.get_meta("reverb_enabled", not bool(target.reverb))) == bool(target.reverb)
	await _release(assembly)
	return {"applicable": true, "cell_id": String(target.cell_id),
		"failed_as_expected": followed, "map_flag": bool(target.reverb),
		"metadata_matches": followed}


func _control_missing_flag() -> Dictionary:
	var altered := map.duplicate(true)
	var target := {}
	for cell: Dictionary in altered.cells:
		if String(cell.role) != "void" and String(cell.cell_id) != String(altered.cells[0].cell_id):
			target = cell
			cell.erase("reverb")
			break
	if target.is_empty():
		return {"applicable": false, "failed_as_expected": false, "reason": "no non-spawn room"}
	var assembly := await _build(altered, specs)
	var room: Node3D = assembly.room_node(String(target.cell_id))
	var dry := room != null and room.has_meta("reverb_enabled") and bool(room.get_meta("reverb_enabled")) == false
	await _release(assembly)
	return {"applicable": true, "cell_id": String(target.cell_id),
		"failed_as_expected": dry, "treated_as_dry": dry}


func _run_legacy() -> Dictionary:
	var legacy_map := ASSEMBLY.argument("--legacy-map=")
	var legacy_rooms := ASSEMBLY.argument("--legacy-rooms=")
	if legacy_map.is_empty() or legacy_rooms.is_empty():
		return {"status": "not_run", "reason": "no --legacy-map= / --legacy-rooms="}
	var legacy_data: Variant = ASSEMBLY.load_json(legacy_map)
	if not legacy_data is Dictionary:
		_fail("Legacy map did not load: " + legacy_map)
		return {"status": "failed"}
	var legacy_specs := ASSEMBLY.load_specs(legacy_rooms)
	var assembly := await _build(legacy_data, legacy_specs)
	var checked := 0
	var wet := 0
	for cell: Dictionary in _walkable(legacy_data):
		var room: Node3D = assembly.room_node(String(cell.cell_id))
		if room == null:
			continue
		checked += 1
		if room.has_meta("reverb_enabled") and bool(room.get_meta("reverb_enabled")):
			wet += 1
			_fail("%s: legacy room is wet, expected dry" % String(cell.cell_id))
	await _release(assembly)
	return {"status": "pass" if wet == 0 else "fail", "checked": checked, "wet": wet,
		"generator_version": String(legacy_data.get("generator_version", ""))}


func _check_scene() -> Dictionary:
	var packed := load(SCENE_PATH) as PackedScene
	_expect(packed != null, "Walkthrough scene did not load")
	if packed == null:
		return {}
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await physics_frame
	await physics_frame
	var result := {"ready": scene.get_meta("walkthrough_ready", false)}
	_expect(result.ready, "Walkthrough scene is not ready")
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, "Walkthrough player is missing")
	var checked := 0
	for cell: Dictionary in _walkable(map):
		var room: Node3D = scene.room_node(String(cell.cell_id))
		if room == null:
			continue
		checked += 1
		if bool(room.get_meta("reverb_enabled", false)) != bool(cell.get("reverb", false)):
			_fail("%s: scene room reverb metadata disagrees with the map" % String(cell.cell_id))
	result["rooms_checked"] = checked
	result["spawn_reverb"] = scene.room_reverb_enabled(String(scene.origin_cell))
	_expect(result.spawn_reverb == false, "Walkthrough spawn room is wet")
	await _release(scene)
	return result


func _write_report(report: Dictionary) -> void:
	var out := ASSEMBLY.argument("--out=")
	if out.is_empty():
		return
	var text := JSON.stringify(report, "\t", true) + "\n"
	var absolute := ProjectSettings.globalize_path(out)
	if FileAccess.file_exists(absolute) and FileAccess.get_file_as_string(absolute) != text:
		_fail("Refusing to overwrite a different runtime report: " + out)
		return
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	var file := FileAccess.open(absolute, FileAccess.WRITE)
	if file == null:
		_fail("Cannot write runtime report: " + out)
		return
	file.store_string(text)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail_all(messages: Array) -> void:
	for message: String in messages:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE204_REVERB: " + message)
