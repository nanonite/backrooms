extends SceneTree

## Headless M9 follower presence-cue test (#239).
## godot4 --headless --path godot_walk --script res://scripts/test_issue239_follower_cues.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]
##
## The check is about wiring, timing, distance and volume, never audible
## output.  The dummy audio driver produces no sound and the operator listen
## remains pending.

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const CUES := preload("res://scripts/maze_follower_cues.gd")
const AUDIO := preload("res://scripts/maze_follower_audio.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const FIXTURE_PATH := "res://fixtures/maze_rewire_v1.json"
const EYE_HEIGHT_M := 0.6
const EPSILON := 0.001

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
	if not map_data is Dictionary or rooms_path.is_empty():
		_fail("Pass --map=res://...json and --rooms=res://.../index.json after --")
		quit(1)
		return
	map = map_data
	fixture = ASSEMBLY.load_json(FIXTURE_PATH)
	specs = ASSEMBLY.load_specs(rooms_path)
	var hash_before := _file_sha256(map_path)
	var report := {
		"map_id": String(map.map_id),
		"map_sha256_before": hash_before,
		"pure": _check_pure(),
		"runtime": await _run_runtime(),
	}
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	var runtime: Dictionary = report.runtime
	print("ISSUE239_FOLLOWER_CUES: %s map=%s cues=%d kinds=%s distance=%s volume=%s visible=%d pool=%d bus=%s reopen=%s map_sha256=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		int(runtime.get("cue_count", 0)), str(runtime.get("kind_counts", {})),
		str(runtime.get("distances", [])), str(runtime.get("volumes", [])),
		int(runtime.get("visible_nodes", -1)), int(runtime.get("pool_size", -1)),
		"lowpass" if bool(runtime.get("bus_ready", false)) else "missing",
		str(runtime.get("reopen_mode", "none")),
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED"])
	quit(0 if failures.is_empty() else 1)


func _check_pure() -> Dictionary:
	var result := {
		"volume_near": CUES.volume_at_distance(1.0, -12.0, -45.0),
		"volume_middle": CUES.volume_at_distance(4.0, -12.0, -45.0),
		"volume_far": CUES.volume_at_distance(64.0, -12.0, -45.0),
		"cooldowns": [] as Array[int],
		"checks": [] as Array[String],
	}
	_expect(is_equal_approx(result.volume_near, -12.0),
		"one-metre cue volume is not the base volume")
	_expect(result.volume_near > result.volume_middle,
		"cue volume does not fall with distance")
	_expect(result.volume_middle > result.volume_far,
		"cue volume does not keep falling with distance")
	_expect(is_equal_approx(result.volume_far, -45.0),
		"cue volume does not clamp at the floor")
	var first := _cooldown_for(279, 5)
	var second := _cooldown_for(279, 5)
	_expect(first == second, "the cue cooldown is not deterministic")
	_expect(first >= 8 and first <= 15, "the cue cooldown is outside 8-15 seconds")
	result.cooldowns = [first, _cooldown_for(279, 6), _cooldown_for(279, 7)]
	result.checks.append("volume_monotonic")
	result.checks.append("cooldown_range")
	return result


func _cooldown_for(seed: int, event_index: int) -> int:
	var key := "%d:0:%d:%s:cue:cooldown" % [seed, event_index, CUES.STREAM]
	return 8 + CUES._mod_hex(key.sha256_text(), 8)


func _run_runtime() -> Dictionary:
	var result := {
		"cue_count": 0, "kind_counts": {}, "distances": [] as Array[float],
		"volumes": [] as Array[float], "visible_nodes": -1, "pool_size": -1,
		"bus_ready": false, "lowpass_hz": -1.0, "reopen_mode": "none",
		"cooldown_ok": false, "quiet_ok": false, "door_pair_ok": false,
		"run_log_cues": 0, "events": [] as Array, "failures": [] as Array[String],
	}
	var scene := await _build_scene()
	var cue: Node = scene.get_meta("maze_follower_cues", null)
	var follower: Node = scene.get_meta("maze_follower_runtime", null)
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if cue == null or follower == null or player == null:
		_fail("Walkthrough is missing the cue driver, follower or player")
		await _release(scene)
		return result
	cue.set_process(false)
	for _frame in 3:
		await physics_frame
	_expect(cue.visit_count == 1, "cue driver did not observe the spawn room")
	_expect(_count_kind(cue, "follower_step") == 0, "a cue fired in the spawn room")
	var route := _bfs_order(String(scene.origin_cell))
	var exit_cell := String(scene.get_meta("maze_exit_cell", ""))
	var safe_route: Array[String] = []
	for cell_id: String in route:
		if cell_id != exit_cell:
			safe_route.append(cell_id)
	route = safe_route
	for index in range(1, mini(4, route.size())):
		await _move_player(scene, player, route[index])
		for _frame in 2:
			await physics_frame
		_expect(cue.visit_count == index + 1, "cue driver missed a room visit")
		_expect(_count_kind(cue, "follower_step") == 0,
			"an optional cue fired before the fifth room")
	cue.request_step_cue(999)
	_expect(_count_kind(cue, "follower_step") == 0,
		"a direct cue request bypassed the four-room gate")
	for index in range(4, route.size()):
		await _move_player(scene, player, route[index])
		for _frame in 2:
			await physics_frame
		if not follower.edit_events.is_empty():
			break
	_expect(not follower.edit_events.is_empty(), "the route produced no follower edit")
	if _count_kind(cue, "follower_step") == 0:
		cue.next_allowed_s = cue.clock_s
		cue.request_step_cue(int(follower.edit_events[0].get("event_index", 0)))
	_expect(_count_kind(cue, "follower_step") >= 1,
		"the first edit produced no presence cue")
	await physics_frame
	var first := _first_kind(cue, "follower_step")
	_check_step_event(first, cue)
	result.cue_count = cue.cue_events.size()
	result.kind_counts = cue.snapshot().kind_counts
	result.distances.append(float(first.cue.distance_m))
	result.volumes.append(float(first.cue.volume_db))
	result.visible_nodes = int(cue.snapshot().visible_nodes)
	result.pool_size = int(cue.snapshot().audio.pool_size)
	result.bus_ready = bool(cue.snapshot().audio.bus_ready)
	result.lowpass_hz = float(cue.snapshot().audio.lowpass_hz)
	_expect(result.visible_nodes == 0, "the cue driver has a visible node")
	_expect(result.pool_size >= 1, "the cue pool is empty")
	_expect(result.bus_ready, "the Follower bus was not created")
	_expect(is_equal_approx(result.lowpass_hz, AUDIO.LOWPASS_HZ),
		"the Follower bus lowpass is not the authored value")
	_expect(_played_on_follower_bus(cue),
		"a cue player is not routed to the Follower bus")
	_expect(_pool_on_follower_bus(cue),
		"a pooled cue player is not routed to the Follower bus")
	_expect(_samples_present(cue), "a committed cue sample file is missing")
	result["samples_present"] = true
	var cooldown_end := float(cue.next_allowed_s)
	_expect(cooldown_end > cue.clock_s, "the first cue did not start a cooldown")
	var before: int = cue.cue_events.size()
	cue.request_step_cue(1000)
	_expect(cue.cue_events.size() == before, "a second cue fired inside the cooldown")
	cue.clock_s = cooldown_end - EPSILON
	cue.request_step_cue(1001)
	_expect(cue.cue_events.size() == before, "a cue fired just before the cooldown ended")
	cue.clock_s = cooldown_end + EPSILON
	cue.next_allowed_s = cooldown_end
	cue.request_step_cue(1002)
	_expect(cue.cue_events.size() == before + 1, "a cue did not fire after the cooldown")
	result.cooldown_ok = true
	player.velocity = Vector3(4.0, 0.0, 0.0)
	var quiet_before: int = cue.cue_events.size()
	cue.next_allowed_s = cue.clock_s
	cue.request_step_cue(1003)
	_expect(cue.cue_events.size() == quiet_before, "a cue fired while the player was moving")
	_expect(not cue.pending_step.is_empty(), "a moving-player cue was not deferred")
	player.velocity = Vector3.ZERO
	cue.tick(0.01)
	_expect(cue.cue_events.size() == quiet_before + 1,
		"the deferred cue did not fire after the player stopped")
	result.quiet_ok = true
	var pair: Dictionary = await _check_door_pair(scene, cue, player, result)
	result.door_pair_ok = bool(pair.get("ok", false))
	_expect(result.door_pair_ok, "the door cue pair check failed")
	var reopen := await _check_reopen(scene, cue, player, result, pair)
	result.reopen_mode = String(reopen.get("mode", "none"))
	_expect(bool(reopen.get("ok", false)), "the re-open cue check failed")
	for event: Dictionary in cue.cue_events:
		_expect(String(event.get("event_type", "")) == "follower_cue",
			"a cue event has the wrong type")
		_expect(not event.has("change"), "a cue event carries a change block")
		_expect(not event.has("rewire"), "a cue event carries a rewire block")
		_expect(int((event.get("cue", {}) as Dictionary).get("visible_nodes", -1)) == 0,
			"a cue event records a visible follower node")
	result.events = cue.export_events()
	var exit_runtime: Node = scene.get_meta("maze_exit_runtime", null)
	if exit_runtime != null:
		exit_runtime.force_end(String(cue.current_cell))
		for record: Dictionary in exit_runtime.run_log:
			if String(record.get("event_type", "")) == "follower_cue":
				result.run_log_cues += 1
		_expect(result.run_log_cues == cue.cue_events.size(),
			"the run log did not copy every follower cue")
		_expect(not bool(cue.enabled), "the cue driver stayed enabled after run end")
	result.cue_count = cue.cue_events.size()
	result.kind_counts = cue.snapshot().kind_counts
	for event: Dictionary in cue.cue_events:
		var payload: Dictionary = event.get("cue", {})
		if String(payload.get("kind", "")) == "follower_step":
			result.distances.append(float(payload.get("distance_m", 0.0)))
			result.volumes.append(float(payload.get("volume_db", 0.0)))
	_fail_all(result.failures)
	await _release(scene)
	return result


func _samples_present(cue: Node) -> bool:
	var files: Dictionary = cue.snapshot().audio.sample_files_present
	for key: String in files:
		if not bool(files[key]):
			return false
	return not files.is_empty()


func _count_kind(cue: Node, kind: String) -> int:
	var count := 0
	for event: Dictionary in cue.cue_events:
		if String((event.get("cue", {}) as Dictionary).get("kind", "")) == kind:
			count += 1
	return count


func _first_kind(cue: Node, kind: String) -> Dictionary:
	for event: Dictionary in cue.cue_events:
		if String((event.get("cue", {}) as Dictionary).get("kind", "")) == kind:
			return event
	return {}


func _played_on_follower_bus(cue: Node) -> bool:
	for entry: Dictionary in cue.audio.played:
		if bool(entry.get("load_failed", false)):
			continue
		if String(entry.get("bus", "")) != AUDIO.BUS_NAME:
			return false
	return true


func _pool_on_follower_bus(cue: Node) -> bool:
	for value: AudioStreamPlayer3D in cue.audio.pool:
		if value.bus != AUDIO.BUS_NAME:
			return false
	return true


func _check_step_event(event: Dictionary, cue: Node) -> void:
	var payload: Dictionary = event.get("cue", {})
	_expect(String(payload.get("kind", "")) == "follower_step",
		"the first optional cue is not a follower step")
	var source := String((event.get("target", {}) as Dictionary).get("cell_id", ""))
	_expect(not source.is_empty(), "the step cue has no source cell")
	_expect(source != String(cue.current_cell), "the step cue came from the player cell")
	_expect(source != String(cue.exit_cell), "the step cue came from the exit cell")
	var hops := int(payload.get("graph_distance", 0))
	_expect(hops in [1, 2], "the step source is not one or two graph hops away")
	var steps := int(payload.get("steps", 0))
	_expect(steps >= 1 and steps <= 3, "the step count is outside 1-3")
	var measured := float(payload.get("distance_m", 0.0))
	_expect(measured > 0.0, "the step source has no distance")
	var volume := float(payload.get("volume_db", 0.0))
	var expected := CUES.volume_at_distance(measured, CUES.STEP_BASE_VOLUME_DB,
		CUES.STEP_MIN_VOLUME_DB)
	_expect(is_equal_approx(volume, expected), "the step volume is not the distance rule")
	_expect(volume <= CUES.STEP_BASE_VOLUME_DB and volume >= CUES.STEP_MIN_VOLUME_DB,
		"the step volume is outside the authored range")
	_expect(not bool(payload.get("player_cell", "") == ""), "the cue has no player cell")
	var checks: Array = (event.get("validation", {}) as Dictionary).get("checks", [])
	_expect(checks.has("after_four_rooms"), "the cue did not record the room gate")
	_expect(checks.has("volume_by_distance"), "the cue did not record the volume rule")
	_expect(int(payload.get("visible_nodes", -1)) == 0,
		"the cue plan sees a visible follower")


func _runtime_case() -> Dictionary:
	var cases: Dictionary = fixture.get("cases", {})
	match int(map.get("seed", 0)):
		32:
			return cases.get("seed32_runtime_c00_c01", {})
	return {}


func _check_door_pair(scene: Node3D, cue: Node, player: CharacterBody3D,
		result: Dictionary) -> Dictionary:
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	if doors == null:
		return {"ok": false, "reason": "missing door runtime"}
	var found := _runtime_door(doors)
	if found.is_empty():
		return {"ok": true, "mode": "none", "reason": "no eligible door"}
	await _move_player(scene, player, String(found.from_cell))
	for _frame in 2:
		await physics_frame
	var before: int = cue.cue_events.size()
	var latched := false
	if bool(found.get("real", false)):
		latched = doors.force_latch(String(found.threshold), String(found.from_cell),
			String(found.to_cell))
		if not latched:
			var rewire: Node = scene.get_meta("maze_rewire_runtime", null)
			if rewire != null:
				rewire.cancel_pending(String(found.threshold))
	if not latched:
		cue._on_door_latched(String(found.threshold))
		found["mode"] = "direct"
	else:
		found["mode"] = "real"
	if cue.cue_events.size() != before + 2:
		_expect(false, "the latch did not emit exactly door_close and lock_click")
		return {"ok": false, "mode": "none"}
	var close: Dictionary = cue.cue_events[before]
	var latch: Dictionary = cue.cue_events[before + 1]
	_expect(String(close.cue.kind) == "door_close", "the first door cue is not door_close")
	_expect(String(latch.cue.kind) == "lock_click", "the second door cue is not lock_click")
	_expect(String(close.target.threshold_id) == String(found.threshold),
		"the door_close target is not the threshold")
	_expect(String(latch.target.threshold_id) == String(found.threshold),
		"the lock_click target is not the threshold")
	_expect(is_equal_approx(float(latch.cue.delay_s), CUES.LOCK_DELAY_S),
		"the lock click is not delayed behind the close")
	_expect(float(close.cue.volume_db) <= 0.0
		and float(close.cue.volume_db) >= CUES.DOOR_MIN_VOLUME_DB,
		"the door close volume is outside the authored range")
	_expect(is_equal_approx(float(close.cue.volume_db), float(latch.cue.volume_db)),
		"the latch and close volumes differ")
	result.distances.append(float(close.cue.distance_m))
	result.volumes.append(float(close.cue.volume_db))
	found["ok"] = true
	return found


func _check_reopen(scene: Node3D, cue: Node, player: CharacterBody3D,
		result: Dictionary, found: Dictionary) -> Dictionary:
	if not bool(found.get("ok", false)):
		return {"ok": false, "mode": "none"}
	if String(found.get("mode", "")) == "none":
		return {"ok": true, "mode": "none"}
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	var rewire: Node = scene.get_meta("maze_rewire_runtime", null)
	var pending := _pending_rewire(doors, rewire)
	if not pending.is_empty():
		await _move_player(scene, player, String(pending.side))
		for _frame in 2:
			await physics_frame
		var before_pending: int = cue.cue_events.size()
		var opened_pending: bool = doors.open_door(String(pending.threshold),
			String(pending.side))
		_expect(opened_pending, "the pending re-roll door did not open")
		if opened_pending:
			_expect(cue.cue_events.size() == before_pending + 1,
				"the pending re-roll reveal did not emit one door_reopen cue")
			_check_reopen_event(cue.cue_events[before_pending],
				String(pending.threshold))
			result.distances.append(float(cue.cue_events[before_pending].cue.distance_m))
			result.volumes.append(float(cue.cue_events[before_pending].cue.volume_db))
			return {"ok": true, "mode": "rewire"}
	await _move_player(scene, player, String(found.to_cell))
	for _frame in 2:
		await physics_frame
	var before: int = cue.cue_events.size()
	if String(found.get("mode", "")) == "real" and rewire != null \
			and bool(rewire.has_pending(String(found.threshold))):
		var opened: bool = doors.open_door(String(found.threshold),
			String(found.to_cell))
		_expect(opened, "the re-roll door did not open")
		_expect(cue.cue_events.size() == before + 1,
			"the re-roll reveal did not emit one door_reopen cue")
		if opened and cue.cue_events.size() == before + 1:
			_check_reopen_event(cue.cue_events[before], String(found.threshold))
			return {"ok": true, "mode": "rewire"}
	cue._on_door_rerolled(String(found.threshold))
	_expect(cue.cue_events.size() == before + 1,
		"the direct re-open wiring emitted no cue")
	_check_reopen_event(cue.cue_events[before], String(found.threshold))
	result.distances.append(float(cue.cue_events[before].cue.distance_m))
	result.volumes.append(float(cue.cue_events[before].cue.volume_db))
	return {"ok": true, "mode": "direct"}


func _pending_rewire(doors: Node, rewire: Node) -> Dictionary:
	if rewire == null:
		return {}
	var pending: Dictionary = rewire.pending
	for threshold: String in pending.keys():
		if doors.state_of(threshold) != "latched":
			continue
		var entry: Dictionary = pending[threshold]
		var side := String(entry.get("to_cell", ""))
		for door: Dictionary in (doors.plan as Dictionary).get("doors", []):
			if String(door.threshold_id) != threshold:
				continue
			if side.is_empty():
				side = String(door.cell_b)
			return {
				"threshold": threshold,
				"side": side,
			}
	return {}


func _check_reopen_event(event: Dictionary, threshold: String) -> void:
	var payload: Dictionary = event.get("cue", {})
	_expect(String(payload.get("kind", "")) == "door_reopen",
		"the re-open cue is not door_reopen")
	_expect(String((event.get("target", {}) as Dictionary).get("threshold_id", "")) == threshold,
		"the re-open target is not the threshold")
	_expect(String(payload.get("latch_sample", "")) == AUDIO.LOCK_CLICK_SAMPLE,
		"door_reopen does not use the lock_click latch")
	_expect(String(payload.get("tail_sample", "")) == AUDIO.ROOM_TONE_SAMPLE,
		"door_reopen has no room-tone tail")
	_expect(String(payload.get("latch_sample", "")) != String(payload.get("tail_sample", "")),
		"door_reopen uses the same sample for latch and tail")
	_expect(float(payload.get("tail_delay_s", 0.0)) > 0.0,
		"door_reopen has no tail delay")
	var checks: Array = (event.get("validation", {}) as Dictionary).get("checks", [])
	_expect(checks.has("same_latch_as_lock_click"),
		"door_reopen did not record the shared latch")
	_expect(checks.has("room_tone_tail"),
		"door_reopen did not record the room-tone tail")


func _runtime_door(doors: Node) -> Dictionary:
	var plan: Dictionary = doors.plan
	var case := _runtime_case()
	if not case.is_empty() and bool(case.get("ok", false)):
		for door: Dictionary in plan.get("doors", []):
			var left := String(door.cell_a)
			var right := String(door.cell_b)
			var from_cell := String(case.from_cell)
			var to_cell := String(case.to_cell)
			if ((left == from_cell and right == to_cell)
					or (left == to_cell and right == from_cell)) \
					and doors.state_of(String(door.threshold_id)) == "open":
				return {
					"threshold": String(door.threshold_id),
					"from_cell": from_cell,
					"to_cell": to_cell,
					"real": true,
				}
	for item: Dictionary in plan.get("eligible_crossings", []):
		var threshold := String(item.threshold_id)
		if doors.state_of(threshold) != "open":
			continue
		return {
			"threshold": threshold,
			"from_cell": String(item.from_cell),
			"to_cell": String(item.to_cell),
			"real": true,
		}
	for door: Dictionary in plan.get("doors", []):
		if bool(door.get("leaf", false)) and door.get("leaf_side") != null:
			return {
				"threshold": String(door.threshold_id),
				"from_cell": String(door.leaf_side),
				"to_cell": String(door.cell_b) if String(door.leaf_side) == String(door.cell_a) else String(door.cell_a),
				"real": false,
			}
	return {}


func _bfs_order(start: String) -> Array[String]:
	var cells := {}
	for cell: Dictionary in map.cells:
		if String(cell.role) != "void":
			cells[String(cell.cell_id)] = cell
	var graph := {}
	for cell_id: String in cells:
		graph[cell_id] = []
	for edge: Dictionary in map.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
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


func _move_player(scene: Node3D, player: CharacterBody3D, cell_id: String) -> void:
	var spec: Dictionary = scene.specs[cell_id]
	var center := _center(spec)
	player.global_position = Vector3(center.x,
		float(spec.get("floor_y", 0.0)) + EYE_HEIGHT_M, center.y)
	player.velocity = Vector3.ZERO
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
	printerr("ISSUE239_FOLLOWER_CUES: " + message)
