extends SceneTree

## Headless M3 static-exit and run-end test (#233).
## godot4 --headless --path godot_walk --script res://scripts/test_issue233_exit_threshold.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const MAZE_EXIT := preload("res://scripts/maze_exit.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const FIXTURE_PATH := "res://fixtures/maze_exit_v1.json"
const EYE_HEIGHT_M := 0.6

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
		"selection": _check_selection(),
		"runtime": await _check_runtime(),
	}
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	print("ISSUE233_EXIT_THRESHOLD: %s map=%s exit=%s port=%s visual_meshes=%d lights=%d route=%d edits=%d rooms=%d run_end=%d card_shows=%d actions=%d map_sha256=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		String(report.selection.exit_cell), String(report.selection.exit_port),
		int(report.runtime.visual_meshes), int(report.runtime.visual_lights),
		int(report.runtime.route_cells), int(report.runtime.edits),
		int(report.runtime.rooms_visited), int(report.runtime.run_end_events),
		int(report.runtime.card_shows), int(report.runtime.card_actions),
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED"])
	quit(0 if failures.is_empty() else 1)


func _check_selection() -> Dictionary:
	var expected: Dictionary = fixture.maps[str(int(map.seed))]
	var first := MAZE_EXIT.plan_run(map)
	var second := MAZE_EXIT.plan_run(map)
	_expect(JSON.stringify(first) == JSON.stringify(second), "the exit selection is not deterministic")
	_expect(String(first.exit.layer_version) == String(fixture.layer_version), "exit layer version differs")
	_expect(String(first.exit.cell_id) == String(expected.exit.cell_id), "exit cell differs from the fixture")
	_expect(String(first.exit.port_id) == String(expected.exit.port_id), "exit port differs from the fixture")
	_expect(String(first.exit.from_cell) == String(expected.exit.from_cell), "exit approach cell differs")
	_expect(String(first.exit.threshold_id) == String(expected.exit.threshold_id), "exit threshold id differs")
	_expect(String(first.exit.draw.rank) == String(expected.exit.rank), "exit keyed rank differs")
	_expect(bool(first.exit.leaf) == bool(expected.exit.leaf), "exit leaf flag differs")
	_expect(bool(first.exit.outside_targets) == bool(expected.exit.outside_targets),
		"exit outside-target flag differs")
	_expect(int(first.exit.removed_cells) == int(expected.exit.removed_cells),
		"exit removed-target count differs")
	var targets: Array = []
	for item: Dictionary in first.eligibility:
		targets.append([
			String(item.from_cell), String(item.to_cell), int(item.target_size),
			String(item.threshold_id), bool(item.eligible),
		])
	var expected_targets: Array = []
	for item: Dictionary in fixture.maps[str(int(map.seed))].eligibility:
		expected_targets.append([
			String(item.from_cell), String(item.to_cell), int(item.target_size),
			MAZE_EXIT.threshold_id(String(item.from_cell), String(item.to_cell)),
			bool(item.eligible),
		])
	_expect(targets == expected_targets, "post-exit eligibility differs from the fixture")
	var layered := map.duplicate(true)
	layered["exit"] = {
		"layer_version": String(fixture.layer_version),
		"cell_id": String(expected.exit.cell_id),
		"port_id": String(expected.exit.port_id),
		"threshold_id": String(expected.exit.threshold_id),
	}
	var recorded := MAZE_EXIT.select_exit(layered)
	_expect(String(recorded.source) == "layer", "a recorded exit layer was not used")
	_expect(String(recorded.cell_id) == String(expected.exit.cell_id),
		"a recorded exit layer selected another cell")
	var exit_cell := String(first.exit.cell_id)
	for item: Dictionary in first.eligible_directions:
		_expect(not (item.target_cells as Array).has(exit_cell),
			"an eligible re-roll target still contains the exit")
	for item: Dictionary in first.rejected_directions:
		_expect((item.reasons as Array).has("exit_inside")
			or (item.reasons as Array).has("exit_threshold_door"),
			"a rejected direction has no exit reason")
	return {
		"exit_cell": exit_cell,
		"exit_port": String(first.exit.port_id),
		"threshold_id": String(first.exit.threshold_id),
		"targets": first.eligibility.size(),
		"eligible": first.eligible_directions.size(),
		"rejected": first.rejected_directions.size(),
	}


func _check_runtime() -> Dictionary:
	var result := {
		"exit_cell": "", "visual_meshes": 0, "visual_lights": 0, "surfaces_lifted": 0,
		"route_cells": 0, "edits": 0, "rooms_visited": 0,
		"run_end_events": 0, "exit_entered_events": 0,
		"card_shows": 0, "card_actions": 0, "map_seed": 0,
	}
	var expected: Dictionary = fixture.maps[str(int(map.seed))]
	var scene := await _build_scene()
	var exit_runtime: Node = scene.get_meta("maze_exit_runtime", null)
	var follower: Node = scene.get_meta("maze_follower_runtime", null)
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if exit_runtime == null or follower == null or player == null:
		_fail("Walkthrough is missing the exit runtime, follower runtime or player")
		await _release(scene)
		return result
	result.exit_cell = String(scene.exit_cell_id())
	_expect(result.exit_cell == String(expected.exit.cell_id),
		"the runtime exit cell differs from the selection")
	_expect(String(follower.exit_cell) == result.exit_cell,
		"the follower runtime does not know the exit cell")
	_expect(String(exit_runtime.exit_cell) == result.exit_cell,
		"the exit runtime does not know the exit cell")
	_check_visual(scene, result)
	await _check_route(scene, player, follower, result)
	await _check_crossing(scene, player, exit_runtime, result)
	await _release(scene)
	return result


func _check_visual(scene: Node3D, result: Dictionary) -> void:
	var visual: Dictionary = scene.exit_threshold_visual()
	_expect(bool(visual.get("ok", false)), "the exit threshold treatment did not build")
	_expect(int(visual.get("meshes", 0)) > 0, "the exit threshold has no meshes")
	_expect(int(visual.get("lights", 0)) == 2, "the exit room has no threshold/fill lights")
	_expect(bool(visual.get("original_materials", false)), "the exit treatment does not use original materials")
	_expect(int(visual.get("surfaces_lifted", 0)) >= 5,
		"the exit room did not receive the clean surface treatment")
	result.surfaces_lifted = int(visual.get("surfaces_lifted", 0))
	result.visual_meshes = int(visual.get("meshes", 0))
	result.visual_lights = int(visual.get("lights", 0))
	var exit_cell := String(scene.exit_cell_id())
	_expect(not scene.set_cell_light(exit_cell, 0, "dead"),
		"the exit cell accepted a follower lamp edit")
	_expect(not scene.apply_cell_light_override(exit_cell, {"lamp_state": []}),
		"the exit cell accepted a folded follower override")
	var room: Node3D = scene.room_node(exit_cell)
	_expect(room != null, "the exit room is not instantiated")
	if room == null:
		return
	var group := room.find_child("MazeExitThreshold", true, false) as Node3D
	_expect(group != null, "the exit room has no MazeExitThreshold group")
	if group == null:
		return
	var port := String(scene.exit_record_data().get("port_id", "")).replace(":", "_")
	_expect(group.find_child("ExitFrameJambLeft_" + port, true, false) != null,
		"the bright threshold frame is missing")
	_expect(group.find_child("ExitDoorLeaf_" + port, true, false) != null,
		"the exit door leaf is missing")
	_expect(group.find_child("ExitSign_" + port, true, false) != null,
		"the exit sign is missing")
	var layer := _mesh_layer(room)
	_expect(layer != 0, "the exit room has no render layer")
	for node: Node in group.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		_expect(instance.layers == layer, "%s is outside the exit room's light layer" % instance.name)
		var material := instance.material_override as StandardMaterial3D
		_expect(material != null, "%s has no material" % instance.name)
		if material != null:
			_expect(material.shading_mode == BaseMaterial3D.SHADING_MODE_PER_VERTEX,
				"%s is not per-vertex" % instance.name)
			_expect(String(material.get_meta("source_path", "")).is_empty(),
				"%s references a texture instead of an original colour" % instance.name)
	var threshold_light := group.find_child("ExitThresholdLight", true, false) as OmniLight3D
	var fill_light := group.find_child("ExitRoomFillLight", true, false) as OmniLight3D
	_expect(threshold_light != null and threshold_light.light_energy > 0.0,
		"the threshold light is missing or dark")
	_expect(fill_light != null and fill_light.light_energy > 0.0,
		"the room fill light is missing or dark")
	for light in [threshold_light, fill_light]:
		if light != null:
			_expect((light as OmniLight3D).light_cull_mask == layer,
				"%s can illuminate another room" % (light as Node).name)


func _check_route(scene: Node3D, player: CharacterBody3D, follower: Node,
		result: Dictionary) -> void:
	var exit_cell := String(scene.exit_cell_id())
	var route := _bfs_order(String(scene.origin_cell))
	var travelled: Array[String] = []
	for cell_id: String in route:
		if cell_id == exit_cell:
			continue
		await _move_player(scene, player, cell_id)
		travelled.append(cell_id)
		if travelled.size() >= 9:
			break
	result.route_cells = travelled.size()
	var edits: Array = follower.edit_events
	result.edits = edits.size()
	_expect(edits.size() >= 1, "the route produced no follower edit to count")
	for event: Dictionary in edits:
		_expect(String((event.target as Dictionary).cell_id) != exit_cell,
			"the follower edited the exit cell")
		_expect(not (follower.cell_overrides as Dictionary).has(exit_cell),
			"the follower override reached the exit cell")
	_expect(travelled.has(String(scene.origin_cell)), "the route did not start in the spawn cell")


func _check_crossing(scene: Node3D, player: CharacterBody3D, exit_runtime: Node,
		result: Dictionary) -> void:
	var exit_cell := String(exit_runtime.exit_cell)
	var card_before: Dictionary = exit_runtime.card()
	_expect(bool(card_before.run_ended) == false, "the run ended before the threshold")
	_expect(exit_runtime.end_card.shown == false, "the end card is visible before the run ends")
	await _move_player(scene, player, exit_cell)
	for _frame in 3:
		await physics_frame
	_expect(bool(exit_runtime.ended), "crossing the exit did not end the run")
	result.run_end_events = _count_events(exit_runtime.run_log, "run_end")
	result.exit_entered_events = _count_events(exit_runtime.run_log, "exit_entered")
	_expect(result.run_end_events == 1, "expected exactly one run_end event")
	_expect(result.exit_entered_events == 1, "expected exactly one exit_entered trigger")
	var card: Dictionary = exit_runtime.card()
	_expect(bool(card.run_ended), "the end card does not report the ended run")
	result.card_shows = int(exit_runtime.end_card.show_count)
	result.card_actions = int(exit_runtime.end_card.action_count())
	_expect(result.card_shows == 1, "the end card was shown more than once")
	_expect(bool(exit_runtime.end_card.shown), "the end card is not visible")
	_expect(result.card_actions == 0, "the end card has a progression action")
	_expect((card.actions as Array).is_empty(), "the card dictionary offers an action")
	_expect(not exit_runtime.has_method("next_seed"), "a next-seed action exists")
	_expect(not exit_runtime.has_method("next_level"), "a next-level action exists")
	_expect(not exit_runtime.has_method("start_next_run"), "a restart action exists")
	result.map_seed = int(card.seed)
	_expect(result.map_seed == int(map.seed), "the end card shows another seed")
	_expect(String(card.map_id) == String(map.map_id), "the end card shows another map")
	var counters: Dictionary = exit_runtime.counters
	result.rooms_visited = int(card.rooms_visited)
	_expect(int(card.rooms_visited) == int(counters.rooms_visited),
		"the card's room count does not match the log")
	_expect(int(card.edits) == int(counters.edits), "the card's edit count does not match the log")
	_expect(int(card.edits) == int(exit_runtime.follower_runtime.edit_events.size()),
		"the card's edit count does not match the follower log")
	_expect(int(card.rerolls) == int(counters.rerolls), "the card's re-roll count does not match the log")
	_expect(int(card.rerolls) == 0, "a re-roll was counted before the re-roll slice")
	_expect(int(card.ended_at_event) == int(counters.ended_at_event),
		"the card's end index does not match the log")
	_expect(_count_events(exit_runtime.run_log, "run_end") == 1, "a second run_end event was logged")
	var card_text := JSON.stringify(card).to_lower()
	for forbidden in ["next_seed", "next_level", "next_run", "restart", "continue"]:
		_expect(not card_text.contains(forbidden), "the card exposes %s" % forbidden)
	# A second crossing, and an explicit force-end, must be inert.
	var from_cell := String(exit_runtime.previous_cell)
	await _move_player(scene, player, from_cell)
	await _move_player(scene, player, exit_cell)
	for _frame in 2:
		await physics_frame
	var forced: Dictionary = exit_runtime.force_end()
	_expect(JSON.stringify(forced) == JSON.stringify(card), "force_end changed the end card")
	_expect(_count_events(exit_runtime.run_log, "run_end") == 1, "the second crossing logged another run_end")
	_expect(_count_events(exit_runtime.run_log, "exit_entered") == 1, "the second crossing logged another trigger")
	_expect(int(exit_runtime.end_card.show_count) == 1, "the second crossing showed the card again")
	_expect(not bool(exit_runtime.follower_runtime.get("enabled")),
		"the follower kept running after the run ended")


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


func _bfs_order(start: String) -> Array[String]:
	var graph := {}
	for cell: Dictionary in map.cells:
		if String(cell.role) != "void":
			graph[String(cell.cell_id)] = []
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
		for neighbour: String in graph[current]:
			if seen.has(neighbour):
				continue
			seen[neighbour] = true
			queue.append(neighbour)
	return order


func _mesh_layer(room: Node3D) -> int:
	for node in room.find_children("*", "MeshInstance3D", true, false):
		return (node as MeshInstance3D).layers
	return 0


func _count_events(records: Array, kind: String) -> int:
	var count := 0
	for record: Dictionary in records:
		if String(record.get("event_type", "")) == kind:
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
	printerr("ISSUE233_EXIT_THRESHOLD: " + message)
