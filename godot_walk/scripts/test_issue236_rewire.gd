extends SceneTree

## Headless M6 re-roll rebuild and reveal test (#236).
## godot4 --headless --path godot_walk --script res://scripts/test_issue236_rewire.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const REROLL := preload("res://scripts/maze_reroll.gd")
const REWIRE := preload("res://scripts/maze_rewire.gd")
const GRAPH := preload("res://scripts/maze_graph.gd")
const DOORS := preload("res://scripts/maze_doors.gd")
const LEAF := preload("res://scripts/maze_door_leaf.gd")
const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const FIXTURE_PATH := "res://fixtures/maze_rewire_v1.json"
const EYE_HEIGHT_M := 0.6
const VISIBILITY_DEPTH := 2
const FLOAT_TOLERANCE := 0.000001

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
		"fixture": _check_fixture(),
		"negative": _check_negative_cases(),
		"runtime": await _check_runtime(),
	}
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	var runtime: Dictionary = report.runtime
	print("ISSUE236_REWIRE: %s map=%s case=%s changed=%d rebuilt=%d rerolled=%s replay=%s hidden=%s map_sha256=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		String(report.fixture.get("case", "")), int(runtime.get("changed", 0)),
		int(runtime.get("rebuilt", 0)), str(runtime.get("rerolled", false)),
		str(runtime.get("replay", false)), str(runtime.get("hidden", false)),
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED"])
	quit(0 if failures.is_empty() else 1)


func _case_for_seed() -> Dictionary:
	var cases: Dictionary = fixture.get("cases", {})
	match int(map.get("seed", 0)):
		32:
			return cases.get("seed32_runtime_c00_c01", {})
		279:
			return cases.get("seed279_c06_c11", {})
		1:
			return cases.get("seed1_no_candidate", {})
		2:
			return cases.get("seed2_no_candidate", {})
	return {}


func _check_fixture() -> Dictionary:
	var case: Dictionary = _case_for_seed()
	if case.is_empty():
		return {"case": "", "checked": false}
	if not bool(case.get("ok", false)):
		var plan := REROLL.plan(map, String(case.from_cell), String(case.to_cell),
			int(case.event_index), {"exit_cell": String(case.get("exit_cell", ""))})
		_expect(not bool(plan.get("ok", true)), "the fixture no-candidate case planned a re-roll")
		_expect(String(plan.get("reason", "")) == String(case.reason),
			"the fixture no-candidate reason differs")
		return {"case": String(case.get("map_id", "")), "checked": true, "ok": false}
	var plan := REROLL.plan(map, String(case.from_cell), String(case.to_cell),
		int(case.event_index), {"exit_cell": String(case.exit_cell)})
	_expect(bool(plan.get("ok", false)), "the fixture case did not plan")
	if not bool(plan.get("ok", false)):
		return {"case": String(case.get("map_id", "")), "checked": true, "ok": false}
	var rewire := REROLL.rewire_block(map, plan, int(case.event_index))
	var expected_event: Dictionary = case.get("event", {})
	var expected_rewire: Dictionary = expected_event.get("rewire", {})
	_expect(_pairs_equal(expected_rewire.get("passages_before", []),
		rewire.get("passages_before", [])), "passages_before differs from the fixture")
	_expect(_pairs_equal(expected_rewire.get("passages_after", []),
		rewire.get("passages_after", [])), "passages_after differs from the fixture")
	_expect(_doorways_equal(expected_rewire.get("doorways", []),
		rewire.get("doorways", [])), "doorway records differ from the fixture")
	_expect(String(rewire.get("candidate_set_hash", "")) ==
		String(expected_rewire.get("candidate_set_hash", "")),
		"the candidate set hash differs from the fixture")
	_expect(int(rewire.get("chosen_rank", 0)) == int(expected_rewire.get("chosen_rank", 0)),
		"the chosen rank differs from the fixture")
	var derived := REWIRE.derive_specs(map, specs, expected_event)
	_expect(bool(derived.get("ok", false)), "the fixture event did not derive specs")
	if not bool(derived.get("ok", false)):
		return {"case": String(case.get("map_id", "")), "checked": true, "ok": false}
	_expect(_string_arrays_equal(case.get("changed_cells", []),
		derived.get("changed_cells", [])), "the changed cell set differs from the fixture")
	var derived_specs: Dictionary = derived.get("specs", {})
	var expected_specs: Dictionary = case.get("derived_doorways", {})
	for cell_id: String in derived_specs:
		_expect(expected_specs.has(cell_id), "the fixture has no derived spec for %s" % cell_id)
		if not expected_specs.has(cell_id):
			continue
		_expect(_approx_equal(expected_specs[cell_id],
			REWIRE.spec_projection(derived_specs[cell_id])),
			"the derived spec projection differs for %s" % cell_id)
	var issues := REWIRE.geometry_issues(map, specs, derived_specs, expected_event)
	_expect(issues.is_empty(), "the fixture event failed geometry: %s" % str(issues))
	var applied := REWIRE.apply_event_to_state(REROLL.base_passage_state(map), expected_event)
	_expect(bool(applied.get("ok", false)), "the fixture event did not apply to the base state")
	var graph := GRAPH.f0_f1_f2(map, applied.get("state", {}),
		String(case.to_cell), String(case.exit_cell))
	_expect(bool(graph.get("F0", false)) and bool(graph.get("F1", false))
		and bool(graph.get("F2", false)), "the fixture event failed F0-F2")
	var revisions := {}
	for cell_id: String in derived_specs:
		revisions[cell_id] = int(derived_specs[cell_id].get("passage_revision", 0))
	_expect(REWIRE.state_hash(applied.get("state", {}), revisions, 1, 1) ==
		String(case.get("state_hash", "")), "the fixture state hash differs")
	return {
		"case": String(case.get("map_id", "")),
		"checked": true,
		"ok": true,
		"changed": (derived.get("changed_cells", []) as Array).size(),
		"state_hash": String(case.get("state_hash", "")),
	}


func _check_runtime() -> Dictionary:
	var result := {
		"changed": 0, "rebuilt": 0, "rerolled": false, "replay": false,
		"hidden": false, "no_candidate": false, "visible_reject": false,
		"leaf_reparent": false, "state_hash": "", "error": "",
	}
	var scene := await _build_scene()
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	var rewire: Node = scene.get_meta("maze_rewire_runtime", null)
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if doors == null or rewire == null or player == null:
		_fail("Walkthrough is missing the door, rewire runtime or player")
		await _release(scene)
		return result
	for _frame in 3:
		await physics_frame
	match int(map.get("seed", 0)):
		32:
			await _check_runtime_positive(scene, player, doors, rewire, result)
		279:
			await _check_runtime_visible_reject(scene, player, doors, rewire, result)
			await _check_replay_reparent(scene, doors, rewire, result)
		1:
			await _check_runtime_no_candidate(scene, player, doors, result)
		2:
			await _check_runtime_no_candidate(scene, player, doors, result)
		_:
			_expect((doors.plan.get("eligible_crossings", []) as Array).is_empty(),
				"a seed outside the fixture has an eligible crossing")
	result.state_hash = String(rewire.state_hash())
	var exit_runtime: Node = scene.get_meta("maze_exit_runtime", null)
	if exit_runtime != null:
		exit_runtime.end_run("")
		result["card_rerolls"] = int((exit_runtime.card() as Dictionary).get("rerolls", 0))
		result["card_seed"] = int((exit_runtime.card() as Dictionary).get("seed", 0))
		_expect(result.card_seed == int(map.get("seed", 0)), "the end card shows another seed")
		if int(map.get("seed", 0)) == 32:
			_expect(int(result.card_rerolls) == 1, "the end card did not count the accepted re-roll")
		else:
			_expect(int(result.card_rerolls) == 0, "the end card counted a rejected re-roll")
	await _release(scene)
	return result


func _check_runtime_positive(scene: Node3D, player: CharacterBody3D, doors: Node,
		rewire: Node, result: Dictionary) -> void:
	var threshold := "c00|c01"
	var from_cell := "c00"
	var to_cell := "c01"
	var door := DOORS.door_by_threshold(doors.plan, threshold)
	_expect(not door.is_empty(), "the runtime case has no door")
	if door.is_empty():
		return
	await _move_to_cell(scene, player, from_cell)
	await _move_to_cell(scene, player, to_cell)
	for _frame in 3:
		await physics_frame
	_expect(doors.state_of(threshold) == "latched", "crossing did not latch the door")
	_expect(rewire.has_pending(threshold), "the latch did not cache a re-roll")
	var leaf: Node3D = doors.leaf_node(threshold)
	_expect(leaf != null and LEAF.is_closed(leaf), "the latched leaf is not closed")
	var target: Array = _case_for_seed().get("target_cells", [])
	var ports := {
		String(door.port_a): "latched",
		String(door.port_b): "latched",
	}
	var visible_before: PackedStringArray = VISIBILITY.visible_cells(
		doors.map, to_cell, VISIBILITY_DEPTH, ports)
	for cell_id: String in target:
		_expect(not visible_before.has(cell_id), "the closed leaf shows target cell %s" % cell_id)
	result.hidden = true
	var changed: Array = _case_for_seed().get("changed_cells", [])
	var old_rooms := {}
	var base_specs := {}
	for cell_id: String in target:
		old_rooms[cell_id] = scene.room_node(cell_id)
		if changed.has(cell_id):
			base_specs[cell_id] = (scene.specs[cell_id] as Dictionary).duplicate(true)
	var committed: Dictionary = rewire.commit(threshold, to_cell, doors.event_index + 1)
	_expect(bool(committed.get("ok", false)), "the commit failed: %s" % String(committed.get("reason", "")))
	if not bool(committed.get("ok", false)):
		return
	var event: Dictionary = committed.get("event", {})
	_expect(not event.is_empty(), "the commit returned no event")
	doors.append_rewire_event(event)
	_expect(int(doors.event_index) == 2, "the accepted event did not follow the lock")
	result.rerolled = true
	result.changed = changed.size()
	var visible_after: PackedStringArray = VISIBILITY.visible_cells(
		doors.map, to_cell, VISIBILITY_DEPTH, ports)
	_expect(_string_arrays_equal(visible_before, visible_after),
		"the closed-leaf view changed during the swap")
	await process_frame
	for cell_id: String in target:
		var current: Node3D = scene.room_node(cell_id)
		_expect(current != null, "cell %s lost its room" % cell_id)
		if changed.has(cell_id):
			_expect(current != old_rooms[cell_id], "changed cell %s kept its old node" % cell_id)
			_expect(not is_instance_valid(old_rooms[cell_id]),
				"changed cell %s did not retire its old node" % cell_id)
			_expect(int(scene.specs[cell_id].get("passage_revision", 0)) == 1,
				"changed cell %s did not bump passage_revision" % cell_id)
			_expect(REWIRE.identity_issues(base_specs[cell_id], scene.specs[cell_id]).is_empty(),
				"changed cell %s changed a non-doorway field" % cell_id)
			result.rebuilt += 1
		else:
			_expect(current == old_rooms[cell_id], "unchanged cell %s was rebuilt" % cell_id)
	_check_derived_doorways(scene, changed)
	var graph := GRAPH.f0_f1_f2(scene.map, rewire.passage_state, to_cell,
		String(scene.exit_cell_id()))
	_expect(bool(graph.get("F0", false)) and bool(graph.get("F1", false))
		and bool(graph.get("F2", false)), "the committed state failed F0-F2")
	var new_plan: Dictionary = doors.plan
	_expect(DOORS.door_by_threshold(new_plan, "c03|c04").is_empty(),
		"the removed passage kept a door record")
	var added := DOORS.door_by_threshold(new_plan, "c04|c06")
	_expect(not added.is_empty(), "the added passage has no door record")
	if not added.is_empty():
		_expect(not bool(added.get("leaf", true)), "an internal doorway got a leaf")
		_expect(str(added.get("leaf_reason", "")) == "rewire_internal",
			"an internal doorway has another skip reason")
	_expect(not DOORS.door_by_threshold(new_plan, threshold).is_empty(),
		"the threshold door disappeared")
	_expect(doors.state_of(threshold) == "latched", "the commit opened the leaf early")
	_expect(doors.open_door(threshold, to_cell), "the manual open failed")
	_expect(doors.state_of(threshold) == "open", "the open did not clear the latch")
	_expect(not LEAF.is_closed(leaf), "the leaf did not open")
	_expect(scene.room_node("c06") != null, "the rebuilt cell lost its room")
	_expect(scene.rooms.size() == specs.size(), "the room registry changed shape")
	for cell: Dictionary in map.get("cells", []):
		if cell.get("module") != null or String(cell.get("role", "")) == "void":
			continue
		_expect(scene.has_room(String(cell.cell_id)),
			"cell %s was retired" % String(cell.cell_id))


func _check_derived_doorways(scene: Node3D, changed: Array) -> void:
	for cell_id: String in changed:
		var spec: Dictionary = scene.specs.get(cell_id, {})
		_expect(not spec.is_empty(), "the rebuilt cell has no derived spec")
		for pair: Array in _added_pairs_for(cell_id):
			var other := String(pair[0]) if String(pair[1]) == cell_id else String(pair[1])
			_expect(_has_doorway(spec, other),
				"cell %s is missing the doorway to %s" % [cell_id, other])
		for pair: Array in _removed_pairs_for(cell_id):
			var other := String(pair[0]) if String(pair[1]) == cell_id else String(pair[1])
			_expect(not _has_doorway(spec, other),
				"cell %s kept the removed doorway to %s" % [cell_id, other])


func _added_pairs_for(cell_id: String) -> Array:
	var result: Array = []
	for record: Dictionary in _case_doorways():
		if String(record.get("action", "")) != "opened":
			continue
		var left := String(record.get("cell_a", ""))
		var right := String(record.get("cell_b", ""))
		if left == cell_id or right == cell_id:
			result.append([left, right])
	return result


func _removed_pairs_for(cell_id: String) -> Array:
	var result: Array = []
	for record: Dictionary in _case_doorways():
		if String(record.get("action", "")) != "closed":
			continue
		var left := String(record.get("cell_a", ""))
		var right := String(record.get("cell_b", ""))
		if left == cell_id or right == cell_id:
			result.append([left, right])
	return result


func _case_doorways() -> Array:
	var event: Dictionary = _case_for_seed().get("event", {})
	return (event.get("rewire", {}) as Dictionary).get("doorways", [])


func _check_runtime_visible_reject(scene: Node3D, player: CharacterBody3D,
		doors: Node, rewire: Node, result: Dictionary) -> void:
	var threshold := "c06|c11"
	var door := DOORS.door_by_threshold(doors.plan, threshold)
	_expect(not door.is_empty(), "the visible case has no door")
	if door.is_empty():
		return
	await _move_to_cell(scene, player, "c06")
	await _move_to_cell(scene, player, "c11")
	for _frame in 3:
		await physics_frame
	_expect(doors.state_of(threshold) == "open", "a visible-target door latched")
	_expect(not doors.leaves.has(threshold), "a visible-target door got a leaf")
	var rejected := _find_event(doors.door_events, threshold, "rejected")
	_expect(not rejected.is_empty(), "a visible-target door did not log a rejected event")
	if not rejected.is_empty():
		_expect(String((rejected.get("validation") as Dictionary).get("reason", "")) ==
			"visible_target", "the visible-target rejection reason differs")
	result.visible_reject = true


func _check_replay_reparent(scene: Node3D, doors: Node, rewire: Node,
		result: Dictionary) -> void:
	var case := _case_for_seed()
	var event: Dictionary = case.get("event", {})
	var threshold := "c06|c11"
	var door := DOORS.door_by_threshold(doors.plan, threshold)
	if event.is_empty() or door.is_empty():
		return
	var leaf: Node3D = doors._ensure_leaf(door)
	_expect(leaf != null, "the replay case could not build a leaf")
	if leaf == null:
		return
	LEAF.set_state(leaf, "latched")
	var old_c06: Node3D = scene.room_node("c06")
	var committed: Dictionary = rewire.apply_stored_event(event, "c11", false)
	_expect(bool(committed.get("ok", false)),
		"the stored event did not replay: %s" % String(committed.get("reason", "")))
	if not bool(committed.get("ok", false)):
		return
	await process_frame
	var new_c06: Node3D = scene.room_node("c06")
	_expect(new_c06 != old_c06, "the replay did not rebuild c06")
	_expect(new_c06 != null and leaf.get_parent() == new_c06,
		"the replay lost the leaf host")
	_expect(LEAF.is_closed(leaf), "the replayed leaf is not closed")
	_expect(int(scene.specs["c06"].get("passage_revision", 0)) == 1,
		"the replayed cell did not bump passage_revision")
	result.replay = true
	result.leaf_reparent = true
	result.changed = (committed.get("changed_cells", []) as Array).size()
	result.rebuilt = result.changed


func _check_runtime_no_candidate(scene: Node3D, player: CharacterBody3D,
		doors: Node, result: Dictionary) -> void:
	var eligible: Array = doors.plan.get("eligible_crossings", [])
	_expect(not eligible.is_empty(), "the no-candidate seed has no eligible crossing")
	if eligible.is_empty():
		return
	var crossing: Dictionary = eligible[0]
	var threshold := String(crossing.threshold_id)
	var from_cell := String(crossing.from_cell)
	var to_cell := String(crossing.to_cell)
	await _move_to_cell(scene, player, from_cell)
	await _move_to_cell(scene, player, to_cell)
	for _frame in 3:
		await physics_frame
	_expect(doors.state_of(threshold) == "open", "a no-candidate door latched")
	_expect(not doors.leaves.has(threshold), "a no-candidate door got a leaf")
	var rejected := _find_event(doors.door_events, threshold, "rejected")
	_expect(not rejected.is_empty(), "a no-candidate door did not log a rejected event")
	if not rejected.is_empty():
		var reason := String((rejected.get("validation") as Dictionary).get("reason", ""))
		_expect(reason.begins_with("no_candidate") or reason == "below_min_alternatives"
			or reason == "visible_target", "the no-candidate reason differs: %s" % reason)
	result.no_candidate = true


func _check_negative_cases() -> Dictionary:
	var case := _case_for_seed()
	if case.is_empty() or not bool(case.get("ok", false)):
		return {"checked": false}
	var plan := REROLL.plan(map, String(case.from_cell), String(case.to_cell),
		int(case.event_index), {"exit_cell": String(case.exit_cell)})
	var target: Array = case.get("target_cells", [])
	if not target.is_empty():
		var visible := REROLL.plan(map, String(case.from_cell), String(case.to_cell),
			int(case.event_index), {"exit_cell": String(case.exit_cell),
			"visible_cells": [String(target[0])]})
		_expect(not bool(visible.get("ok", true)), "a visible target planned")
		_expect(String(visible.get("reason", "")) == "visible_target",
			"a visible target has another reason")
	var event: Dictionary = case.get("event", {})
	var derived := REWIRE.derive_specs(map, specs, event)
	var tall := event.duplicate(true)
	for record: Dictionary in (tall.get("rewire", {}) as Dictionary).get("doorways", []):
		if String(record.get("action", "")) == "opened":
			record["height_m"] = 10.0
	var tall_issues := REWIRE.geometry_issues(map, specs, derived.get("specs", {}), tall)
	_expect(_has_prefix(tall_issues, "doorway_too_tall"), "a too-tall doorway passed")
	var changed: Array = derived.get("changed_cells", [])
	if not changed.is_empty():
		var cell_id := String(changed[0])
		var changed_spec: Dictionary = (derived.specs[cell_id] as Dictionary).duplicate(true)
		changed_spec["light"] = (changed_spec.get("light", {}) as Dictionary).duplicate(true)
		(changed_spec.light as Dictionary)["color_temp_k"] = 1
		_expect(not REWIRE.identity_issues(specs[cell_id], changed_spec).is_empty(),
			"an identity change passed")
	var stale := event.duplicate(true)
	var before: Array = (stale.get("rewire", {}) as Dictionary).get("passages_before", [])
	if not before.is_empty():
		before.remove_at(0)
	var applied := REWIRE.apply_event_to_state(REROLL.base_passage_state(map), stale)
	if bool(plan.get("ok", false)):
		_expect(not bool(applied.get("ok", true)), "a stale passages_before applied")
	return {"checked": true, "visible": true, "tall": true, "identity": true}


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


func _has_doorway(spec: Dictionary, other: String) -> bool:
	for doorway: Dictionary in spec.get("doorways", []):
		if String(doorway.get("to_cell_id", "")) == other:
			return true
	return false


func _pair_key(left: String, right: String) -> String:
	return left + "|" + right if left < right else right + "|" + left


func _pair_set(pairs: Array) -> Dictionary:
	var result := {}
	for pair: Variant in pairs:
		if pair is Array and (pair as Array).size() == 2:
			result[_pair_key(String(pair[0]), String(pair[1]))] = true
	return result


func _pairs_equal(expected: Array, actual: Array) -> bool:
	var first := _pair_set(expected)
	var second := _pair_set(actual)
	if first.size() != second.size():
		return false
	for key: String in first:
		if not second.has(key):
			return false
	return true


func _doorways_equal(expected: Array, actual: Array) -> bool:
	if expected.size() != actual.size():
		return false
	for item: Dictionary in expected:
		var found := {}
		for candidate: Dictionary in actual:
			if String(candidate.get("cell_a", "")) == String(item.get("cell_a", "")) \
					and String(candidate.get("cell_b", "")) == String(item.get("cell_b", "")):
				found = candidate
				break
		if found.is_empty():
			return false
		if String(found.get("action", "")) != String(item.get("action", "")):
			return false
		if String(item.get("action", "")) == "opened":
			if not _approx_equal(item.get("center_xz", []), found.get("center_xz", [])):
				return false
			if absf(float(item.get("width_m", 0.0)) - float(found.get("width_m", 0.0))) > FLOAT_TOLERANCE:
				return false
			if absf(float(item.get("height_m", 0.0)) - float(found.get("height_m", 0.0))) > FLOAT_TOLERANCE:
				return false
	return true


func _approx_equal(expected: Variant, actual: Variant) -> bool:
	if expected is float or actual is float:
		return absf(float(expected) - float(actual)) <= FLOAT_TOLERANCE
	if expected is int or actual is int:
		return int(expected) == int(actual)
	if expected is Array and actual is Array:
		if (expected as Array).size() != (actual as Array).size():
			return false
		for index in (expected as Array).size():
			if not _approx_equal((expected as Array)[index], (actual as Array)[index]):
				return false
		return true
	if expected is Dictionary and actual is Dictionary:
		var first: Dictionary = expected
		var second: Dictionary = actual
		if first.size() != second.size():
			return false
		for key: Variant in first:
			if not second.has(key):
				return false
			if not _approx_equal(first[key], second[key]):
				return false
		return true
	return expected == actual


func _string_arrays_equal(first: Variant, second: Variant) -> bool:
	var left: Array = []
	for value: Variant in first:
		left.append(String(value))
	var right: Array = []
	for value: Variant in second:
		right.append(String(value))
	left.sort()
	right.sort()
	return left == right


func _has_prefix(values: Array, prefix: String) -> bool:
	for value: Variant in values:
		if String(value).begins_with(prefix):
			return true
	return false


func _find_event(events: Array, threshold: String, outcome: String) -> Dictionary:
	for event: Dictionary in events:
		if String(event.get("event_type", "")) != "door_reroll":
			continue
		var target: Variant = event.get("target")
		if target is Dictionary and String((target as Dictionary).get(
				"door_threshold_id", "")) != threshold:
			continue
		var validation: Variant = event.get("validation")
		if validation is Dictionary and String((validation as Dictionary).get(
				"outcome", "")) == outcome:
			return event
	return {}


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
	printerr("ISSUE236_REWIRE: " + message)
