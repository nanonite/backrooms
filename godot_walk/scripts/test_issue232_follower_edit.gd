extends SceneTree

## Headless M2 follower lamp-edit test (#232).
## godot4 --headless --path godot_walk --script res://scripts/test_issue232_follower_edit.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const FLICKER := preload("res://scripts/shape_room_lamp_flicker.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const EYE_HEIGHT_M := 0.6
const DEPTH := 2

var failures: Array[String] = []
var map: Dictionary = {}
var specs: Dictionary = {}
var map_path := ""


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	map_path = ASSEMBLY.argument("--map=")
	var rooms_path := ASSEMBLY.argument("--rooms=")
	var map_data: Variant = ASSEMBLY.load_json(map_path)
	if not map_data is Dictionary or rooms_path.is_empty():
		_fail("Pass --map=res://...json and --rooms=res://.../index.json after --")
		quit(1)
		return
	map = map_data
	specs = ASSEMBLY.load_specs(rooms_path)
	var hash_before := _file_sha256(map_path)
	var report := {
		"map_id": String(map.map_id),
		"map_sha256_before": hash_before,
		"visibility": _check_visibility(),
		"runtime": await _run_runtime(),
		"positive": await _run_positive(),
		"negative_controls": await _run_negative_controls(),
	}
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	var positive: Dictionary = report.positive
	var runtime: Dictionary = report.runtime
	print("ISSUE232_FOLLOWER_EDIT: %s map=%s route=%d target=%s lamp=%d before=%s after=%s changed_cells=%d/%d live_edit=%s@%s map_sha256=%s controls=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		int(positive.get("route_visits", 0)), String(positive.get("target_cell", "")),
		int(positive.get("lamp_index", -1)), String(positive.get("before_state", "")),
		String(positive.get("after_state", "")), int(positive.get("changed_cells", 0)),
		int(positive.get("checked_cells", 0)),
		String(runtime.get("change_class", "")), String(runtime.get("target_cell", "")),
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED",
		str(report.negative_controls.keys())])
	quit(0 if failures.is_empty() else 1)


func _run_runtime() -> Dictionary:
	var result := {
		"edit_count": 0, "target_cell": "", "change_class": "",
		"lamp_index": -1, "state_after": "", "visit_count": 0,
		"reentry_checks": 0, "failures": [] as Array[String],
	}
	var scene := await _build_scene()
	var runtime: Node = scene.get_meta("maze_follower_runtime", null)
	if runtime == null:
		_fail("Walkthrough has no live follower runtime")
		await _release(scene)
		return result
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		_fail("Walkthrough player is missing")
		await _release(scene)
		return result
	for _frame in 3:
		await physics_frame
	_expect(runtime.current_cell == String(scene.origin_cell),
		"live runtime did not record the spawn cell")
	var route := _bfs_order(String(scene.origin_cell))
	var beat_cell := ""
	for cell_id: String in route:
		await _move_player(scene, player, cell_id)
		for _frame in 2:
			await physics_frame
		if not runtime.edit_events.is_empty():
			beat_cell = cell_id
			break
	if runtime.edit_events.is_empty():
		_fail("live runtime produced no lamp edit on the first beat")
		await _release(scene)
		return result
	var event: Dictionary = runtime.edit_events[0]
	var target := String(event.target.cell_id)
	var change: Dictionary = event.change
	var change_class := String(change.class)
	result.edit_count = runtime.edit_events.size()
	result.target_cell = target
	result.change_class = change_class
	result.visit_count = int(event.get("visit_count", 0))
	if ["lamp_state", "lamp_flicker"].has(change_class):
		var before: Array = change.before
		var after: Array = change.after
		var field := "state" if change_class == "lamp_state" else "flicker_seed"
		var lamp_index := _changed_lamp_index(before, after, field)
		result.lamp_index = lamp_index
		_expect(lamp_index >= 0, "live edit record has no changed lamp")
		if change_class == "lamp_state":
			result.state_after = String(_record_value(after, lamp_index, "state"))
			_expect(scene.cell_light_state(target, lamp_index) == result.state_after,
				"live edit did not reach the assembly")
		else:
			result.state_after = "flicker"
			_expect(scene.cell_light_state(target, lamp_index) == "flicker",
				"live flicker edit did not reach the assembly")
	elif change_class == "reverb":
		result.state_after = str(change.after)
		_expect(scene.room_reverb_enabled(target) == bool(change.after),
			"live reverb edit did not reach the assembly")
	elif change_class == "wear":
		result.state_after = str(change.after)
		_expect(scene.cell_wear(target) == int(change.after),
			"live wear edit did not reach the assembly")
	elif change_class == "surface_variant":
		var surface := _changed_surface(change.before, change.after)
		_expect(not surface.is_empty(), "live variant edit changed no surface")
		result.state_after = "%s=%s" % [surface, String(change.after[surface])]
		_expect(String(scene.cell_surface_variants(target).get(surface, ""))
			== String(change.after[surface]),
			"live variant edit did not reach the assembly")
	else:
		_fail("live edit has an unknown class %s" % change_class)
	_expect(runtime.cell_overrides.has(target), "live edit left no override record")
	if String(map.map_id) == "gmap-279-gmap-0.13.0":
		_expect(target == "c04" and change_class == "lamp_state",
			"live first edit does not match the Python reference target/class")
		_expect(result.lamp_index == 2 and result.state_after == "flicker",
			"live first edit does not match the Python reference lamp/state")
	await _move_player(scene, player, target)
	for _frame in 2:
		await physics_frame
	result.reentry_checks += 1
	_expect(_live_state(scene, target, change) == result.state_after,
		"live re-entry lost the edit")
	_expect(runtime.edit_events.size() == 1, "re-entry re-fired the same beat")
	await _move_player(scene, player, beat_cell)
	await _move_player(scene, player, target)
	for _frame in 2:
		await physics_frame
	result.reentry_checks += 1
	_expect(_live_state(scene, target, change) == result.state_after,
		"second live re-entry lost the edit")
	_expect(runtime.edit_events.size() == 1, "second re-entry re-fired the same beat")
	_fail_all(result.failures)
	await _release(scene)
	return result


func _live_state(scene: Node3D, target: String, change: Dictionary) -> String:
	var change_class := String(change.class)
	if change_class == "lamp_state":
		var lamp_index := _changed_lamp_index(
			change.before, change.after, "state")
		return String(scene.cell_light_state(target, lamp_index))
	if change_class == "lamp_flicker":
		return String(scene.cell_light_state(target, _changed_lamp_index(
			change.before, change.after, "flicker_seed")))
	if change_class == "reverb":
		return str(scene.room_reverb_enabled(target))
	if change_class == "wear":
		return str(scene.cell_wear(target))
	var surface := _changed_surface(change.before, change.after)
	return "%s=%s" % [surface, String(scene.cell_surface_variants(target).get(surface, ""))]


func _changed_surface(before: Dictionary, after: Dictionary) -> String:
	for surface: String in ["floor", "wall", "ceiling", "trim"]:
		if String(before.get(surface, "")) != String(after.get(surface, "")):
			return surface
	return ""


func _changed_lamp_index(before: Array, after: Array, field: String) -> int:
	for index in before.size():
		var old: Dictionary = before[index]
		var new: Dictionary = after[index]
		if int(old.lamp_index) != int(new.lamp_index):
			return -1
		if old.get(field) != new.get(field):
			return int(new.lamp_index)
	return -1


func _record_value(record: Array, lamp_index: int, field: String) -> Variant:
	for entry: Dictionary in record:
		if int(entry.lamp_index) == lamp_index:
			return entry.get(field)
	return null


func _run_positive() -> Dictionary:
	var result := {
		"route_visits": 0, "target_cell": "", "lamp_index": -1,
		"before_state": "", "after_state": "", "changed_cells": 0,
		"checked_cells": 0, "reentry_checks": 0, "geometry_unchanged": false,
		"override_replay": false, "failures": [] as Array[String],
	}
	var scene := await _build_scene()
	var runtime: Node = scene.get_meta("maze_follower_runtime", null)
	if runtime != null:
		runtime.enabled = false
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		_fail("Walkthrough player is missing")
		await _release(scene)
		return result
	player.set_physics_process(false)
	var route := _bfs_order(String(scene.origin_cell))
	var visited: Array[String] = []
	var beat := {}
	for cell_id: String in route:
		visited.append(cell_id)
		if visited.size() < 5:
			continue
		var target := _hidden_lamp_target(visited, cell_id)
		if not target.is_empty():
			beat = {"current": cell_id, "target": target, "visits": visited.duplicate()}
			break
	if beat.is_empty():
		_fail("No hidden lamp target exists on the first visible beat")
		await _release(scene)
		return result
	var current := String(beat.current)
	var target := String(beat.target)
	result.route_visits = int(beat.visits.size())
	result.target_cell = target
	await _move_player(scene, player, current)
	_expect(scene.cell_at(player.global_position) == current, "player did not reach %s" % current)
	_expect(VISIBILITY.cell_is_hidden(map, current, target, DEPTH),
		"target %s is visible from %s at the edit beat" % [target, current])
	var before_states := _snapshot_light(scene)
	var before_geometry := _snapshot_geometry(scene)
	result.checked_cells = before_states.size()
	var lamp_index := _first_on_lamp(scene, target)
	if lamp_index < 0:
		lamp_index = 0
	result.lamp_index = lamp_index
	var before_state: String = scene.cell_light_state(target, lamp_index)
	result.before_state = before_state
	var after_state := "dead" if before_state != "dead" else "on"
	_expect(scene.set_cell_light(target, lamp_index, after_state),
		"set_cell_light refused %s[%d] -> %s" % [target, lamp_index, after_state])
	result.after_state = after_state
	var after_states := _snapshot_light(scene)
	for cell_id: String in before_states:
		var changed := JSON.stringify(before_states[cell_id]) != JSON.stringify(after_states.get(cell_id, []))
		if cell_id == target:
			if not changed:
				result.failures.append("target %s did not change" % target)
			else:
				result.changed_cells += 1
		elif changed:
			result.failures.append("non-target cell %s changed" % cell_id)
	_expect(result.changed_cells == 1, "expected exactly one changed cell")
	_expect(scene.cell_light_state(target, lamp_index) == after_state,
		"target lamp did not keep its new state")
	_check_lamp_nodes(scene, target, lamp_index, after_state)
	await _move_player(scene, player, target)
	_expect(scene.cell_at(player.global_position) == target, "player did not re-enter %s" % target)
	result.reentry_checks += 1
	_expect(scene.cell_light_state(target, lamp_index) == after_state,
		"re-entry lost the lamp state on %s[%d]" % [target, lamp_index])
	await _move_player(scene, player, current)
	await _move_player(scene, player, target)
	result.reentry_checks += 1
	_expect(scene.cell_light_state(target, lamp_index) == after_state,
		"second re-entry lost the lamp state on %s[%d]" % [target, lamp_index])
	# The same room must accept the flicker and on/dead states without a rebuild.
	_expect(scene.set_cell_light(target, lamp_index, "flicker", 424242),
		"set_cell_light refused flicker on %s[%d]" % [target, lamp_index])
	_expect(scene.cell_light_state(target, lamp_index) == "flicker",
		"flicker state did not stick")
	var flicker_light := _lamp_light(scene, target, lamp_index)
	_expect(flicker_light != null and flicker_light.get_script() == FLICKER,
		"flicker lamp did not receive the seeded flicker script")
	if flicker_light != null:
		for _frame in 3:
			await process_frame
		_expect(flicker_light.light_energy > 0.0, "flicker lamp has no energy")
	_expect(scene.set_cell_light(target, lamp_index, "on"), "set_cell_light refused on")
	_check_lamp_nodes(scene, target, lamp_index, "on")
	_expect(scene.set_cell_light(target, lamp_index, "dead"), "set_cell_light refused dead")
	_check_lamp_nodes(scene, target, lamp_index, "dead")
	result.override_replay = _check_override_replay(scene, target, lamp_index)
	# Restore the map state so the room snapshot reflects only the tested lamp.
	scene.set_cell_light(target, lamp_index, before_state)
	result.geometry_unchanged = JSON.stringify(before_geometry) == JSON.stringify(_snapshot_geometry(scene))
	_expect(result.geometry_unchanged, "lamp edits changed room geometry")
	_fail_all(result.failures)
	await _release(scene)
	return result


func _run_negative_controls() -> Dictionary:
	var controls := {}
	var assembly := await _build_assembly()
	var spawn := String(map.cells[0].cell_id)
	var target := ""
	for cell: Dictionary in map.cells:
		if String(cell.cell_id) != spawn and String(cell.role) != "void" and cell.has("light"):
			target = String(cell.cell_id)
			break
	controls["unknown_cell"] = not assembly.set_cell_light("missing", 0, "dead")
	controls["invalid_state"] = target.is_empty() or not assembly.set_cell_light(target, 0, "strobe")
	controls["invalid_lamp"] = target.is_empty() or not assembly.set_cell_light(target, 99, "dead")
	var module_cell := ""
	for cell: Dictionary in map.cells:
		if cell.has("module"):
			module_cell = String(cell.cell_id)
			break
	controls["module_refused"] = module_cell.is_empty() or not assembly.set_cell_light(module_cell, 0, "dead")
	var landmark_cell := ""
	for cell: Dictionary in map.cells:
		if cell.has("landmark") and cell["landmark"] != null:
			landmark_cell = String(cell.cell_id)
			break
	controls["landmark_refused"] = landmark_cell.is_empty() or not assembly.set_cell_light(landmark_cell, 0, "dead")
	for name: String in controls:
		if not controls[name]:
			_fail("Negative control %s did not fail as expected" % name)
	await _release(assembly)
	return controls


func _check_override_replay(scene: Node3D, cell_id: String, lamp_index: int) -> bool:
	var states: Array = scene.cell_light_states(cell_id)
	var seeds: Array = scene.cell_lamp_flicker_seeds(cell_id)
	var state_record := []
	var flicker_record := []
	for entry: Dictionary in states:
		state_record.append({"lamp_index": int(entry.lamp_index), "state": String(entry.state)})
	for entry: Dictionary in seeds:
		flicker_record.append({"lamp_index": int(entry.lamp_index), "flicker_seed": int(entry.flicker_seed)})
	if state_record.is_empty() or flicker_record.is_empty():
		_fail("override replay has no lamp records")
		return false
	for entry: Dictionary in state_record:
		if int(entry.lamp_index) == lamp_index:
			entry["state"] = "dead"
	for entry: Dictionary in flicker_record:
		if int(entry.lamp_index) == lamp_index:
			entry["flicker_seed"] = 777001
	var record := {"lamp_state": state_record, "lamp_flicker": flicker_record}
	var applied: bool = scene.apply_cell_light_override(cell_id, record)
	_expect(applied, "apply_cell_light_override refused the folded record")
	_expect(scene.cell_light_state(cell_id, lamp_index) == "dead",
		"override record did not apply the lamp state")
	var seed := 0
	for entry: Dictionary in scene.cell_lamp_flicker_seeds(cell_id):
		if int(entry.lamp_index) == lamp_index:
			seed = int(entry.flicker_seed)
	_expect(seed == 777001, "override record did not apply the flicker seed")
	return applied


func _check_visibility() -> Dictionary:
	var result := {"checks": 0, "by_cell": {}, "failures": [] as Array[String]}
	var cells := {}
	for cell: Dictionary in map.cells:
		cells[String(cell.cell_id)] = cell
	for cell_id: String in ["c03", "c09"]:
		if not cells.has(cell_id):
			continue
		var depth_one := VISIBILITY.visible_cells(map, cell_id, 1)
		var depth_two := VISIBILITY.visible_cells(map, cell_id, DEPTH)
		result.by_cell[cell_id] = {"depth_one": Array(depth_one), "depth_two": Array(depth_two)}
		result.checks += 1
		for visible: String in depth_two:
			if String(cells[visible].get("role", "")) == "void":
				result.failures.append("%s: void cell %s is visible" % [cell_id, visible])
		_expect(depth_two.has(cell_id), "%s: current cell is not visible" % cell_id)
	if String(map.map_id) == "gmap-279-gmap-0.13.0":
		if cells.has("c03") and cells.has("c02"):
			_expect(VISIBILITY.visible_cells(map, "c03", 1).has("c02"),
				"c02 is not visible from c03 at one hop")
			_expect(VISIBILITY.cell_is_hidden(map, "c03", "c03", DEPTH) == false,
				"the current cell is not hidden")
		if cells.has("c09") and cells.has("c02"):
			_expect(VISIBILITY.cell_is_hidden(map, "c09", "c02", 2),
				"c02 should be hidden from c09 at depth 2")
			_expect(not VISIBILITY.cell_is_hidden(map, "c09", "c02", 3),
				"c02 should become visible from c09 at depth 3")
		if cells.has("c09") and cells.has("c13"):
			_expect(not VISIBILITY.visible_cells(map, "c09", DEPTH).has("c13"),
				"the void cell c13 is visible through a closed_visible edge")
		if cells.has("c03") and cells.has("c07"):
			var closed := VISIBILITY.visible_cells(map, "c03", 1, {"c03:p1": "closed"})
			_expect(not closed.has("c07"), "a closed door did not hide its neighbor")
	_fail_all(result.failures)
	return result


func _bfs_order(start: String) -> Array[String]:
	var cells := {}
	for cell: Dictionary in map.cells:
		if String(cell.role) != "void":
			cells[String(cell.cell_id)] = cell
	var graph := {}
	for cell_id: String in cells:
		graph[cell_id] = []
	for edge: Dictionary in map.get("edges", []):
		if not ["direct", "closed_visible"].has(String(edge.get("connector", ""))):
			continue
		var left := String(edge.get("from", "")).get_slice(":", 0)
		var right := String(edge.get("to", "")).get_slice(":", 0)
		if left != right and graph.has(left) and graph.has(right):
			(graph[left] as Array).append(right)
			(graph[right] as Array).append(left)
	for cell_id: String in graph:
		(graph[cell_id] as Array).sort()
	var order: Array[String] = []
	if not graph.has(start):
		return order
	var seen := {start: true}
	var queue: Array[String] = [start]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		order.append(current)
		for neighbor: String in graph[current]:
			if seen.has(neighbor):
				continue
			seen[neighbor] = true
			queue.append(neighbor)
	return order


func _hidden_lamp_target(visited: Array[String], player_cell: String) -> String:
	var spawn := String(map.cells[0].cell_id)
	for index in range(visited.size() - 2, -1, -1):
		var candidate := visited[index]
		if candidate == spawn or candidate == player_cell:
			continue
		var cell: Dictionary = specs.get(candidate, {})
		if cell.is_empty() or (cell.has("landmark") and cell["landmark"] != null) or not cell.has("light"):
			continue
		if not VISIBILITY.cell_is_hidden(map, player_cell, candidate, DEPTH):
			continue
		return candidate
	return ""


func _build_scene() -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await physics_frame
	await physics_frame
	return scene


func _build_assembly() -> Node3D:
	var assembly := ASSEMBLY.new()
	assembly.auto_start = false
	root.add_child(assembly)
	assembly.assemble(map, specs)
	await physics_frame
	await physics_frame
	return assembly


func _release(node: Node) -> void:
	root.remove_child(node)
	node.free()
	await physics_frame


func _move_player(scene: Node3D, player: CharacterBody3D, cell_id: String) -> void:
	var spec: Dictionary = scene.specs[cell_id]
	var center := _center(spec)
	player.global_position = Vector3(center.x, float(spec.get("floor_y", 0.0)) + EYE_HEIGHT_M, center.y)
	await physics_frame
	await physics_frame


func _center(spec: Dictionary) -> Vector2:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _rect_area(rect) > _rect_area(largest):
			largest = rect
	return Vector2((float(largest[0]) + float(largest[2])) / 2.0,
		(float(largest[1]) + float(largest[3])) / 2.0)


func _rect_area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _first_on_lamp(scene: Node3D, cell_id: String) -> int:
	for entry: Dictionary in scene.cell_light_states(cell_id):
		if String(entry.state) == "on":
			return int(entry.lamp_index)
	return -1


func _snapshot_light(scene: Node3D) -> Dictionary:
	var snapshot := {}
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		if not scene.has_room(cell_id):
			continue
		snapshot[cell_id] = {
			"states": scene.cell_light_states(cell_id),
			"seeds": scene.cell_lamp_flicker_seeds(cell_id),
		}
	return snapshot


func _snapshot_geometry(scene: Node3D) -> Dictionary:
	var snapshot := {}
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		var room: Node3D = scene.room_node(cell_id)
		if room == null:
			continue
		var nodes := []
		for node: Node in room.find_children("*", "", true, false):
			nodes.append("%s:%s" % [node.name, node.get_class()])
		nodes.sort()
		snapshot[cell_id] = {
			"position": room.position,
			"rotation": room.rotation,
			"nodes": nodes,
		}
	return snapshot


func _check_lamp_nodes(scene: Node3D, cell_id: String, lamp_index: int, state: String) -> void:
	var light := _lamp_light(scene, cell_id, lamp_index)
	_expect(light != null, "%s[%d]: no OmniLight" % [cell_id, lamp_index])
	if light == null:
		return
	if state == "dead":
		_expect(light.light_energy == 0.0, "%s[%d]: dead lamp still has energy" % [cell_id, lamp_index])
	else:
		_expect(light.light_energy > 0.0, "%s[%d]: lit lamp has no energy" % [cell_id, lamp_index])
	var room: Node3D = scene.room_node(cell_id)
	var mesh := room.find_child("CeilingLight_%02d" % lamp_index, true, false) as MeshInstance3D
	_expect(mesh != null, "%s[%d]: no lamp mesh" % [cell_id, lamp_index])
	if mesh != null:
		var material := mesh.material_override as StandardMaterial3D
		_expect(material != null, "%s[%d]: lamp mesh has no material" % [cell_id, lamp_index])
		if material != null:
			_expect(material.emission_enabled == (state != "dead"),
				"%s[%d]: emission does not match %s" % [cell_id, lamp_index, state])


func _lamp_light(scene: Node3D, cell_id: String, lamp_index: int) -> OmniLight3D:
	var room: Node3D = scene.room_node(cell_id)
	if room == null:
		return null
	return room.find_child("OmniLamp_%02d" % lamp_index, true, false) as OmniLight3D


func _file_sha256(path: String) -> String:
	return FileAccess.get_sha256(ProjectSettings.globalize_path(path))


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


func _fail_all(messages: Array) -> void:
	for message: String in messages:
		_fail(message)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE232_FOLLOWER_EDIT: " + message)
