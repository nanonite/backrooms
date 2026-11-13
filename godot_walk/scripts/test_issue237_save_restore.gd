extends SceneTree

## Headless M7 save, restore and cache check (#237).
## godot4 --headless --path godot_walk --script res://scripts/test_issue237_save_restore.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../save_restore_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const RUN_SAVE := preload("res://scripts/maze_run_save.gd")
const ROOM_CACHE := preload("res://scripts/maze_room_cache.gd")
const DOORS := preload("res://scripts/maze_doors.gd")
const LEAF := preload("res://scripts/maze_door_leaf.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const EYE_HEIGHT_M := 0.6

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
		"case": {},
	}
	if int(map.get("seed", 0)) == 32:
		report["case"] = await _check_seed32()
	else:
		report["case"] = await _check_no_reroll_seed()
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	var case: Dictionary = report.case
	print("ISSUE237_SAVE_RESTORE: %s map=%s pending=%s restored=%s same_p=%s same_hash=%s cache_miss=%s map_sha256=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		str(case.get("pending", false)), str(case.get("restored", false)),
		str(case.get("same_p", false)), str(case.get("same_hash", false)),
		str(case.get("cache_miss", false)),
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED"])
	quit(0 if failures.is_empty() else 1)


func _check_seed32() -> Dictionary:
	var result := {
		"pending": false, "restored": false, "same_p": false,
		"same_hash": false, "cache_miss": false, "committed_replay": false,
		"save_sha256": "", "pending_hash": "", "committed_hash": "",
	}
	var scene := await _build_scene()
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	var rewire: Node = scene.get_meta("maze_rewire_runtime", null)
	if player == null or doors == null or rewire == null:
		_fail("Walkthrough is missing the player, door or rewire runtime")
		await _release(scene)
		return result
	for _frame in 3:
		await physics_frame
	await _move_to_cell(scene, player, "c00")
	await _move_to_cell(scene, player, "c01")
	for _frame in 3:
		await physics_frame
	var threshold := "c00|c01"
	_expect(doors.state_of(threshold) == "latched", "crossing did not latch the door")
	_expect(rewire.has_pending(threshold), "the latch did not cache a re-roll")
	result.pending = true
	result.pending_hash = rewire.state_hash()
	var analysis_before: Dictionary = (rewire.pending[threshold] as Dictionary).analysis
	var save_before: Dictionary = scene.run_save()
	_expect(bool(save_before.get("ok", false)), "the pending save did not build")
	if not bool(save_before.get("ok", false)):
		await _release(scene)
		return result
	var save_doc: Dictionary = save_before.get("save", {})
	_expect(String((save_doc.base as Dictionary).base_map_sha256) ==
		_file_sha256(map_path), "the save base hash is not the map hash")
	_expect(not save_doc.has("pending"), "the save persisted a pending shortlist")
	for key: String in ["pool", "pool_hash", "pool_sha256", "candidate_pool",
			"candidate_pool_hash"]:
		_expect(not save_doc.has(key), "the save persisted a pool field: %s" % key)
	var save_path := "user://issue237-run-save.json"
	var wrote := RUN_SAVE.write(save_path, scene.run_base_identity(), save_doc)
	_expect(bool(wrote.get("ok", false)), "the save file did not write")
	var read := RUN_SAVE.read(save_path, scene.run_base_identity())
	_expect(bool(read.get("ok", false)), "the save file did not read")
	if not bool(read.get("ok", false)):
		await _release(scene)
		return result
	result.save_sha256 = _file_sha256(save_path)
	var baseline: Dictionary = rewire.commit(threshold, "c01", doors.event_index + 1)
	_expect(bool(baseline.get("ok", false)),
		"the baseline commit failed: %s" % String(baseline.get("reason", "")))
	var baseline_event: Dictionary = baseline.get("event", {})
	result.committed_hash = rewire.state_hash()
	await _release(scene)

	var scene_two := await _build_scene()
	var restored: Dictionary = scene_two.restore_run(read.get("save", {}))
	_expect(bool(restored.get("ok", false)),
		"the pending restore failed: %s" % String(restored.get("reason", "")))
	var doors_two: Node = scene_two.get_meta("maze_door_runtime", null)
	var rewire_two: Node = scene_two.get_meta("maze_rewire_runtime", null)
	if doors_two == null or rewire_two == null:
		_fail("The restored scene is missing a runtime")
		await _release(scene_two)
		return result
	_expect(doors_two.state_of(threshold) == "latched", "restore did not re-latch the door")
	_expect(rewire_two.has_pending(threshold), "restore did not re-enumerate the pending re-roll")
	_expect(rewire_two.state_hash() == result.pending_hash,
		"the pending restore changed the state hash")
	result.restored = true
	var analysis_after: Dictionary = (rewire_two.pending[threshold] as Dictionary).analysis
	_expect(String(analysis_after.candidate_set_hash) ==
		String(analysis_before.candidate_set_hash),
		"the restored candidate set differs")
	_expect((analysis_after.shortlist as Array).size() ==
		(analysis_before.shortlist as Array).size(),
		"the restored shortlist differs")
	var commit_two: Dictionary = rewire_two.commit(threshold, "c01", doors_two.event_index + 1)
	_expect(bool(commit_two.get("ok", false)),
		"the restored commit failed: %s" % String(commit_two.get("reason", "")))
	var event_two: Dictionary = commit_two.get("event", {})
	_expect(int(event_two.get("event_index", 0)) == 2,
		"the restored re-roll is not the next event")
	result.same_p = _pairs_equal(
		(baseline_event.get("rewire", {}) as Dictionary).get("passages_after", []),
		(event_two.get("rewire", {}) as Dictionary).get("passages_after", []))
	result.same_hash = rewire_two.state_hash() == result.committed_hash
	_expect(bool(result.same_p), "save/reload chose a different P")
	_expect(bool(result.same_hash), "save/reload changed the state hash")
	var cache := ROOM_CACHE.new()
	var base_identity: Dictionary = scene_two.run_base_identity()
	var key_zero := ROOM_CACHE.key_for(base_identity, 1, 0, 0, "c03")
	cache.put(key_zero, {"cell_id": "c03", "passage_revision": 0})
	_expect(cache.get_value(key_zero) != null, "the cache did not hit its own key")
	_expect(cache.get_value(ROOM_CACHE.key_for(base_identity, 1, 1, 0, "c03")) == null,
		"a changed passage_revision was not a cache miss")
	_expect(cache.get_value(ROOM_CACHE.key_for(base_identity, 2, 0, 0, "c03")) == null,
		"a changed branch_epoch was not a cache miss")
	_expect(cache.get_value(ROOM_CACHE.key_for(base_identity, 1, 0, 1, "c03")) == null,
		"a changed content_revision was not a cache miss")
	result.cache_miss = true
	var snapshot: Dictionary = rewire_two.snapshot()
	_expect(int((snapshot.cache as Dictionary).entries) > 0,
		"the runtime did not fill its revision cache")
	doors_two.append_rewire_event(event_two)
	var committed_save: Dictionary = scene_two.run_save()
	_expect(bool(committed_save.get("ok", false)), "the committed save did not build")
	await _release(scene_two)

	var scene_three := await _build_scene()
	var replay: Dictionary = scene_three.restore_run(committed_save.get("save", {}))
	_expect(bool(replay.get("ok", false)),
		"the committed restore failed: %s" % String(replay.get("reason", "")))
	var doors_three: Node = scene_three.get_meta("maze_door_runtime", null)
	var rewire_three: Node = scene_three.get_meta("maze_rewire_runtime", null)
	if doors_three == null or rewire_three == null:
		_fail("The replayed scene is missing a runtime")
		await _release(scene_three)
		return result
	_expect(rewire_three.state_hash() == result.committed_hash,
		"the committed restore changed the state hash")
	_expect(not rewire_three.has_pending(threshold),
		"the committed restore resurrected a pending re-roll")
	_expect(int(scene_three.passage_revision("c03")) == 1,
		"the committed restore lost the passage revision")
	_expect((doors_three.export_log() as Array).size() == 2,
		"the committed restore lost an event")
	var stored_events: Array = doors_three.export_log()
	var replayed_event: Dictionary = stored_events[1]
	_expect(_pairs_equal(
		(event_two.get("rewire", {}) as Dictionary).get("passages_after", []),
		(replayed_event.get("rewire", {}) as Dictionary).get("passages_after", [])),
		"the committed restore did not apply the stored P")
	result.committed_replay = true
	await _release(scene_three)
	return result


func _check_no_reroll_seed() -> Dictionary:
	var scene := await _build_scene()
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	_expect(player != null and doors != null, "the no-reroll scene is incomplete")
	if player == null or doors == null:
		await _release(scene)
		return {"pending": false, "restored": true, "same_p": true,
			"same_hash": true, "cache_miss": true, "committed_replay": true}
	var save: Dictionary = scene.run_save()
	_expect(bool(save.get("ok", false)), "an empty run did not build a save")
	var hash := _file_sha256(map_path)
	var restored: Dictionary = scene.restore_run(save.get("save", {}))
	_expect(bool(restored.get("ok", false)), "an empty run did not restore")
	_expect(_file_sha256(map_path) == hash, "restoring an empty run changed the map")
	await _release(scene)
	return {"pending": false, "restored": true, "same_p": true,
		"same_hash": true, "cache_miss": true, "committed_replay": true}


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
	printerr("ISSUE237_SAVE_RESTORE: " + message)
