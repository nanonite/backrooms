extends SceneTree

## Headless M4 door-leaf and lock-behind test (#234).
## godot4 --headless --path godot_walk --script res://scripts/test_issue234_doors.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const MAZE_DOORS := preload("res://scripts/maze_doors.gd")
const MAZE_EXIT := preload("res://scripts/maze_exit.gd")
const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const LEAF := preload("res://scripts/maze_door_leaf.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const FIXTURE_PATH := "res://fixtures/maze_doors_v1.json"
const EYE_HEIGHT_M := 0.6
const VISIBILITY_DEPTH := 2

var failures: Array[String] = []
var map: Dictionary = {}
var specs: Dictionary = {}
var fixture: Dictionary = {}
var map_path := ""


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	map_path = ASSEMBLY.argument("--map=")
	var rooms_path := ASSEMBLY.argument("--rooms=")
	var map_data: Variant = ASSEMBLY.load_json(map_path)
	var fixture_data: Variant = ASSEMBLY.load_json(FIXTURE_PATH)
	if not map_data is Dictionary or not fixture_data is Dictionary or rooms_path.is_empty():
		_fail("Pass --map=res://...json and --rooms=res://.../index.json after --")
		quit(1)
		return
	map = map_data
	fixture = fixture_data
	specs = ASSEMBLY.load_specs(rooms_path)
	var hash_before := _file_sha256(map_path)
	var report := {
		"map_id": String(map.map_id),
		"map_sha256_before": hash_before,
		"plan": _check_plan(),
		"replay": _check_replay(),
		"runtime": await _check_runtime(),
	}
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	var runtime: Dictionary = report.runtime
	print("ISSUE234_DOORS: %s map=%s doors=%d eligible=%d latched=%d opened=%d library=%d leaves=%d ray_closed=%s ray_open=%s exit_reachable=%s map_sha256=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		int(report.plan.get("doors", 0)), int(report.plan.get("eligible", 0)),
		int(runtime.get("latched", 0)), int(runtime.get("opened", 0)),
		int(report.plan.get("library", 0)), int(runtime.get("leaf_count", 0)),
		str(runtime.get("ray_closed", false)), str(runtime.get("ray_open", false)),
		str(runtime.get("exit_reachable", false)),
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED"])
	quit(0 if failures.is_empty() else 1)


func _check_plan() -> Dictionary:
	var expected: Dictionary = fixture.maps[str(int(map.seed))].plan
	var actual := MAZE_DOORS.projection(MAZE_DOORS.plan(map, specs, MAZE_EXIT.select_exit(map)))
	var actual_text := _normalized_text(actual)
	var expected_text := _normalized_text(expected)
	_expect(actual_text == expected_text, "the door plan differs from the shared fixture")
	if actual_text != expected_text:
		printerr("EXPECTED: " + expected_text)
		printerr("ACTUAL:   " + actual_text)
	_expect(String(actual.layer_version) == String(fixture.layer_version),
		"the door layer version differs from the fixture")
	var stats: Dictionary = actual.stats
	var doors: Array = actual.doors
	var eligible: Array = actual.eligible_crossings
	var library_count := 0
	var drop_count := 0
	var ramp_leaves := 0
	for door: Dictionary in doors:
		if String(door.kind) == "library":
			library_count += 1
			_expect(not bool(door.leaf), "a library doorway has a leaf")
			_expect(String(door.get("leaf_reason", "")) == "library_doorway",
				"a library doorway has another skip reason")
			for crossing: Dictionary in door.crossings:
				_expect(not bool(crossing.eligible), "a library doorway is lock-behind eligible")
		if String(door.vertical) == "drop":
			drop_count += 1
			_expect(not bool(door.leaf), "a drop doorway has a leaf")
			_expect(String(door.get("leaf_reason", "")) == "drop_door",
				"a drop doorway has another skip reason")
		if String(door.vertical) == "ramp" and bool(door.leaf):
			ramp_leaves += 1
		if bool(door.exit_threshold):
			_expect(not bool(door.leaf) or not _any_eligible(door),
				"the exit threshold is lock-behind eligible")
	for crossing: Dictionary in eligible:
		var door := MAZE_DOORS.door_by_threshold(actual, String(crossing.threshold_id))
		_expect(not door.is_empty(), "an eligible crossing has no door record")
		if door.is_empty():
			continue
		_expect(bool(door.leaf), "an eligible crossing has no leaf")
		_expect(String(door.kind) == "generated", "an eligible crossing is library content")
		var direction := _crossing_of(door, String(crossing.from_cell), String(crossing.to_cell))
		_expect(not direction.is_empty(), "an eligible crossing has no direction record")
		if direction.is_empty():
			continue
		var size := int(direction.target_size)
		_expect(size >= MAZE_EXIT.MIN_REROLL_CELLS and size <= MAZE_EXIT.MAX_REROLL_CELLS,
			"an eligible crossing has a target outside 3-8 cells")
		_expect((direction.reasons as Array).is_empty(),
			"an eligible crossing carries a rejection reason")
	_expect(int(stats.doors) == doors.size(), "the plan door count is inconsistent")
	_expect(int(stats.library) == library_count, "the plan library count is inconsistent")
	_expect(int(stats.eligible_crossings) == eligible.size(),
		"the plan eligible count is inconsistent")
	_expect(library_count == int(stats.library), "the fixture library count changed")
	_expect(ramp_leaves > 0, "the committed seed has no leaf-capable ramp doorway")
	return {
		"doors": doors.size(),
		"eligible": eligible.size(),
		"library": library_count,
		"drops": drop_count,
		"ramp_leaves": ramp_leaves,
		"skipped": (actual.skipped_doors as Array).size(),
	}


func _check_replay() -> Dictionary:
	var expected: Dictionary = fixture.maps[str(int(map.seed))].replay
	var plan := MAZE_DOORS.plan(map, specs, MAZE_EXIT.select_exit(map))
	var states := MAZE_DOORS.fold_states(plan, expected.events)
	var digest := MAZE_DOORS.state_hash(states)
	_expect(digest == String(expected.state_hash), "the fixture door replay hash differs")
	for threshold: String in expected.states:
		_expect(String(states.get(threshold, "open")) == String(expected.states[threshold]),
			"the fixture door replay differs at %s" % threshold)
	return {"events": (expected.events as Array).size(), "state_hash": digest}


func _any_eligible(door: Dictionary) -> bool:
	for crossing: Dictionary in door.crossings:
		if bool(crossing.eligible):
			return true
	return false


func _normalized_text(value: Variant) -> String:
	return JSON.stringify(_normalize_numbers(value), "", true)


func _normalize_numbers(value: Variant) -> Variant:
	if value is float:
		var number := float(value)
		return int(number) if number == floorf(number) else number
	if value is Array:
		var items: Array = []
		for item: Variant in value:
			items.append(_normalize_numbers(item))
		return items
	if value is Dictionary:
		var result := {}
		for key: Variant in value:
			result[key] = _normalize_numbers(value[key])
		return result
	return value


func _crossing_of(door: Dictionary, from_cell: String, to_cell: String) -> Dictionary:
	for crossing: Dictionary in door.get("crossings", []):
		if String(crossing.from_cell) == from_cell and String(crossing.to_cell) == to_cell:
			return crossing
	return {}


func _door_row(rows: Array, threshold: String) -> Dictionary:
	for row: Dictionary in rows:
		if String(row.get("threshold_id", "")) == threshold:
			return row
	return {}


func _check_runtime() -> Dictionary:
	var result := {
		"latched": 0, "opened": 0, "leaf_count": 0,
		"ray_closed": false, "ray_open": false,
		"exit_reachable": false, "occluded": false,
		"restored": false, "restore_hash": "", "library_skipped": false,
		"ineligible_skipped": false, "exit_threshold_open": true,
		"run_end_events": 0, "door_events_in_run_log": 0,
		"map_seed": 0, "error": "",
	}
	var scene := await _build_scene()
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	var exit_runtime: Node = scene.get_meta("maze_exit_runtime", null)
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if doors == null or exit_runtime == null or player == null:
		_fail("Walkthrough is missing the door runtime, exit runtime or player")
		await _release(scene)
		return result
	for _frame in 3:
		await physics_frame
	_expect(doors.current_cell == String(scene.origin_cell),
		"the door runtime did not record the spawn cell")
	_expect(String(doors.exit_cell) == String(scene.exit_cell_id()),
		"the door runtime does not know the exit cell")
	_expect(MAZE_DOORS.exit_reachable(map, String(scene.exit_cell_id()),
		String(scene.origin_cell), []), "the exit is not reachable from the spawn")
	_expect(doors.leaves.is_empty(), "a leaf exists before any door latched")
	result.leaf_count = doors.leaves.size()
	result.exit_reachable = MAZE_DOORS.exit_reachable(map, String(scene.exit_cell_id()),
		String(scene.origin_cell), [])
	var plan: Dictionary = doors.plan
	_expect(not (plan.eligible_crossings as Array).is_empty() or int(map.seed) == 3,
		"a seed other than 3 has no eligible crossing")
	await _check_runtime_library(scene, player, doors, plan, result)
	await _check_runtime_ineligible(scene, player, doors, plan, result)
	await _check_runtime_positive(scene, player, doors, plan, result)
	await _check_runtime_exit(scene, player, doors, exit_runtime, plan, result)
	await _release(scene)
	return result


func _check_runtime_library(scene: Node3D, player: CharacterBody3D, doors: Node,
		plan: Dictionary, result: Dictionary) -> void:
	for door: Dictionary in plan.doors:
		if String(door.kind) != "library":
			continue
		var threshold := String(door.threshold_id)
		await _move_to_cell(scene, player, String(door.cell_a))
		await _move_to_cell(scene, player, String(door.cell_b))
		for _frame in 2:
			await physics_frame
		_expect(doors.state_of(threshold) == "open", "a library doorway latched")
		_expect(not doors.leaves.has(threshold), "a library doorway got a leaf")
		_expect(not doors.open_door(threshold, String(door.cell_b)),
			"a library doorway accepted a manual open")
		result.library_skipped = true
		return
	_fail("the committed seed has no library doorway to skip")


func _check_runtime_ineligible(scene: Node3D, player: CharacterBody3D, doors: Node,
		plan: Dictionary, result: Dictionary) -> void:
	for door: Dictionary in plan.doors:
		if not bool(door.leaf) or bool(door.exit_threshold):
			continue
		if String(door.kind) != "generated":
			continue
		if _any_eligible(door):
			continue
		var threshold := String(door.threshold_id)
		await _move_to_cell(scene, player, String(door.cell_a))
		await _move_to_cell(scene, player, String(door.cell_b))
		for _frame in 2:
			await physics_frame
		_expect(doors.state_of(threshold) == "open", "an ineligible doorway latched")
		_expect(not doors.leaves.has(threshold), "an ineligible doorway got a leaf")
		result.ineligible_skipped = true
		return
	# Seed 3 has no eligible door at all, so the first leaf door is also ineligible.
	_fail("no ineligible leaf doorway was available to check")


func _check_runtime_positive(scene: Node3D, player: CharacterBody3D, doors: Node,
		plan: Dictionary, result: Dictionary) -> void:
	var eligible: Array = plan.eligible_crossings
	if eligible.is_empty():
		_expect(int(map.seed) == 3, "only seed 3 may have no eligible crossing")
		return
	var crossing: Dictionary = eligible[0]
	var threshold := String(crossing.threshold_id)
	var from_cell := String(crossing.from_cell)
	var to_cell := String(crossing.to_cell)
	var door := MAZE_DOORS.door_by_threshold(plan, threshold)
	_expect(not door.is_empty(), "the eligible crossing has no door")
	if door.is_empty():
		return
	await _move_to_cell(scene, player, from_cell)
	await _move_to_cell(scene, player, to_cell)
	for _frame in 3:
		await physics_frame
	_expect(doors.state_of(threshold) == "latched", "crossing did not latch the door")
	var lock_events := _count_door_events(doors.door_events, "door_lock", threshold)
	_expect(lock_events == 1, "expected exactly one door_lock event")
	var snapshot: Dictionary = doors.snapshot()
	_expect((snapshot.doors as Array).size() == (plan.doors as Array).size(),
		"the live doors[] view is incomplete")
	var row := _door_row(snapshot.doors, threshold)
	_expect(String(row.get("state", "")) == "latched",
		"the live doors[] view did not latch the door")
	_expect(String(snapshot.state_hash) == doors.state_hash(),
		"the live snapshot hash differs from the door state hash")
	var leaf: Node3D = doors.leaf_node(threshold)
	_expect(leaf != null, "the latched door has no leaf")
	if leaf == null:
		return
	_expect(LEAF.is_closed(leaf), "the latched leaf is not closed")
	var body := LEAF.collider(leaf)
	_expect(body != null, "the closed leaf has no collider")
	if body != null:
		_expect(body.collision_layer == 1, "the closed leaf collider is disabled")
	_check_leaf_visual(leaf)
	var port_states := {
		String(door.port_a): "latched",
		String(door.port_b): "latched",
	}
	_expect(VISIBILITY.cell_is_hidden(map, to_cell, from_cell, VISIBILITY_DEPTH, port_states),
		"the closed leaf does not occlude the departed side")
	result.occluded = true
	_expect(_ray_hits_leaf(scene, player, door, leaf), "a ray through the closed leaf missed it")
	result.ray_closed = true
	_expect(MAZE_DOORS.exit_reachable(map, String(plan.exit_cell), to_cell, [threshold]),
		"the exit is not reachable with the latched door closed")
	result.exit_reachable = true
	_expect(not doors.open_door(threshold, "not_a_cell"),
		"a manual open succeeded from a cell that is not a side")
	_expect(doors.state_of(threshold) == "latched", "the failed open changed the door")
	var saved_hash: String = doors.state_hash()
	var saved_log: Array = doors.export_log()
	_expect(doors.open_door(threshold, to_cell), "the manual open from the current side failed")
	_expect(doors.state_of(threshold) == "open", "the manual open did not clear the latch")
	_expect(not LEAF.is_closed(leaf), "the opened leaf is still closed")
	if body != null:
		_expect(body.collision_layer == 0, "the open leaf collider still blocks")
	_expect(not _ray_hits_leaf(scene, player, door, leaf),
		"a ray through the open doorway still hits the leaf")
	result.ray_open = true
	_expect(_count_door_events(doors.door_events, "door_unlock", threshold) == 1,
		"expected exactly one door_unlock event")
	_expect(scene.door_state(threshold) == "open", "the assembly did not publish the open state")
	_expect(doors.restore_log(saved_log) == saved_hash, "the restored door hash differs")
	_expect(doors.state_of(threshold) == "latched", "restore did not re-latch the door")
	_expect(LEAF.is_closed(doors.leaf_node(threshold)), "restore did not close the leaf")
	result.restored = true
	result.restore_hash = saved_hash
	_expect(doors.open_door(threshold, to_cell), "the second manual open failed")
	result.latched = _count_door_events(doors.door_events, "door_lock", threshold)
	result.opened = _count_door_events(doors.door_events, "door_unlock", threshold)
	result.leaf_count = doors.leaves.size()
	_expect(MAZE_DOORS.exit_reachable(map, String(plan.exit_cell), to_cell, []),
		"the exit is not reachable after the open")


func _check_leaf_visual(leaf: Node3D) -> void:
	var room: Node3D = leaf.get_parent() as Node3D
	_expect(room != null, "the leaf has no room parent")
	var layer := int(leaf.get_meta("door_leaf_layer", 0))
	_expect(layer != 0, "the leaf has no render layer")
	var panel := LEAF.panel(leaf)
	_expect(panel != null, "the leaf panel is missing")
	if panel == null:
		return
	_expect(panel.layers == layer, "the leaf panel is outside the room's light layer")
	var material := panel.material_override as StandardMaterial3D
	_expect(material != null, "the leaf panel has no material")
	if material != null:
		_expect(material.texture_filter == BaseMaterial3D.TEXTURE_FILTER_NEAREST,
			"the leaf panel is not nearest-filtered")
		var source := String(material.get_meta("source_path", ""))
		_expect(source.is_empty() or source.begins_with("res://"),
			"the leaf panel references an external texture")
	var latch := leaf.get_node_or_null("LatchBolt") as MeshInstance3D
	_expect(latch != null and latch.visible, "the latched leaf has no visible latch bolt")


func _check_runtime_exit(scene: Node3D, player: CharacterBody3D, doors: Node,
		exit_runtime: Node, plan: Dictionary, result: Dictionary) -> void:
	var exit_cell := String(plan.exit_cell)
	var exit_threshold := String(plan.exit_threshold_id)
	_expect(not exit_threshold.is_empty(), "the plan has no exit threshold")
	_expect(doors.state_of(exit_threshold) == "open", "the exit threshold latched")
	result.exit_threshold_open = doors.state_of(exit_threshold) == "open"
	await _move_to_cell(scene, player, exit_cell)
	for _frame in 3:
		await physics_frame
	_expect(bool(exit_runtime.ended), "crossing the exit did not end the run")
	_expect(_count_door_events(doors.door_events, "door_lock", exit_threshold) == 0,
		"the exit threshold logged a door_lock")
	_expect(doors.state_of(exit_threshold) == "open", "the exit threshold latched at the exit")
	result.run_end_events = _count_events(exit_runtime.run_log, "run_end")
	_expect(result.run_end_events == 1, "expected exactly one run_end event")
	result.map_seed = int(exit_runtime.card().seed)
	_expect(result.map_seed == int(map.seed), "the end card shows another seed")
	var door_events := 0
	for record: Dictionary in exit_runtime.run_log:
		if ["door_lock", "door_unlock"].has(String(record.get("event_type", ""))):
			door_events += 1
	result.door_events_in_run_log = door_events
	if int(map.seed) != 3:
		_expect(door_events >= 1, "the run log did not receive the door events")
	_expect(not bool(doors.enabled), "the door runtime kept running after the run ended")


func _build_scene() -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await physics_frame
	await physics_frame
	return scene


func _release(node: Node) -> void:
	root.remove_child(node)
	node.free()
	await physics_frame


func _move_to_cell(scene: Node3D, player: CharacterBody3D, cell_id: String) -> void:
	var spec: Dictionary = scene.specs.get(cell_id, {})
	if not spec.is_empty():
		var center := _center(spec)
		player.global_position = Vector3(center.x,
			float(spec.get("floor_y", 0.0)) + EYE_HEIGHT_M, center.y)
		await physics_frame
		await physics_frame
		return
	var cell := _map_cell(cell_id)
	var envelope := _envelope_center(cell)
	player.global_position = Vector3(envelope.x,
		float(cell.get("floor_y", 0.0)) + EYE_HEIGHT_M, envelope.y)
	await physics_frame
	await physics_frame


func _map_cell(cell_id: String) -> Dictionary:
	for cell: Dictionary in map.cells:
		if String(cell.cell_id) == cell_id:
			return cell
	return {}


func _envelope_center(cell: Dictionary) -> Vector2:
	var points: Array = cell.get("envelope_xz", [])
	if points.is_empty():
		return Vector2.ZERO
	var total := Vector2.ZERO
	for point: Array in points:
		total += Vector2(float(point[0]), float(point[1]))
	return total / float(points.size())


func _center(spec: Dictionary) -> Vector2:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _rect_area(rect) > _rect_area(largest):
			largest = rect
	return Vector2((float(largest[0]) + float(largest[2])) / 2.0,
		(float(largest[1]) + float(largest[3])) / 2.0)


func _rect_area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _cell_floor_y(cell_id: String) -> float:
	for cell: Dictionary in map.cells:
		if String(cell.cell_id) == cell_id:
			return float(cell.get("floor_y", 0.0))
	return 0.0


func _doorway(cell_id: String, port_id: String) -> Dictionary:
	var spec: Dictionary = specs.get(cell_id, {})
	for item: Dictionary in spec.get("doorways", []):
		if String(item.get("port_id", "")) == port_id:
			return item
	return {}


func _ray_hits_leaf(scene: Node3D, player: CharacterBody3D, door: Dictionary,
		leaf: Node3D) -> bool:
	var doorway := _doorway(String(door.leaf_side), String(door.leaf_port))
	if doorway.is_empty():
		return false
	var position := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1])).normalized()
	var y := _cell_floor_y(String(door.leaf_side)) \
		+ float(doorway.get("sill_height_m", 0.0)) \
		+ float(doorway.get("height_m", 2.1)) / 2.0
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(position.x + normal.x * 0.8, y, position.y + normal.y * 0.8),
		Vector3(position.x - normal.x * 0.8, y, position.y - normal.y * 0.8))
	query.collision_mask = 1
	query.collide_with_bodies = true
	query.collide_with_areas = false
	query.exclude = [player.get_rid()]
	var hit := scene.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return false
	var body := LEAF.collider(leaf)
	return body != null and hit.collider == body


func _count_door_events(events: Array, event_type: String, threshold: String) -> int:
	var count := 0
	for event: Dictionary in events:
		if String(event.get("event_type", "")) != event_type:
			continue
		var target: Variant = event.get("target")
		if target is Dictionary and String((target as Dictionary).get("threshold_id", "")) == threshold:
			count += 1
	return count


func _count_events(records: Array, event_type: String) -> int:
	var count := 0
	for record: Dictionary in records:
		if String(record.get("event_type", "")) == event_type:
			count += 1
	return count


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


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE234_DOORS: " + message)
