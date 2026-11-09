extends SceneTree

## Headless elevation test for gmap-0.10.0 (#201).
## godot4 --headless --path godot_walk --script res://scripts/test_issue201_elevation.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const CHECKS := preload("res://scripts/issue201_elevation_checks.gd")
const PROBE := preload("res://scripts/shape_room_probe.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"

var failures: Array[String] = []
var map: Dictionary = {}
var specs: Dictionary = {}
var index: Dictionary = {}


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
	index = index_data
	specs = ASSEMBLY.load_specs(ASSEMBLY.argument("--rooms="))
	var report := {"map_id": map.map_id, "rooms_checked": specs.size()}
	report["positive"] = await _run_positive()
	report["negative_controls"] = await _run_negative_controls()
	report["scene"] = await _check_scene()
	report["failures"] = failures
	_write_report(report)
	var positive: Dictionary = report.positive
	print("ISSUE201_ELEVATION: %s map=%s levels=%s edges=%s graph=%d/%d level_edges=%d/%d ramp_edges=%d/%d drops=%d/%d landing_events=%d risers=%d/%d riser_samples=%d/%d coplanar=%d controls=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		JSON.stringify(positive.levels), JSON.stringify(positive.vertical),
		positive.graph.reached_cells, positive.graph.expected_cells,
		positive.edges.level_passed, positive.edges.level_edges,
		positive.edges.ramp_passed, positive.edges.ramp_edges,
		positive.drops.landed, positive.drops.checked, positive.drops.landing_events,
		positive.risers.present, positive.risers.expected,
		positive.risers.covered_samples, positive.risers.samples,
		positive.coplanar.same_facing_count, str(report.negative_controls.keys())])
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


func _run_positive() -> Dictionary:
	var assembly := await _build(map, specs)
	var space := assembly.get_world_3d().direct_space_state
	var graph := CHECKS.check_graph(assembly)
	var strong := CHECKS.check_strong(assembly)
	_fail_all(graph.failures)
	_fail_all(strong.failures)
	var edges := CHECKS.check_edges(space, assembly)
	_fail_all(edges.failures)
	var risers := CHECKS.check_risers(assembly)
	_fail_all(risers.failures)
	var coplanar := CHECKS.check_coplanar(assembly)
	for conflict: Dictionary in coplanar.conflicts:
		_fail("Elevation box %s shares face plane %.3f (axis %d) with %s" % [
			conflict.trim, conflict.plane, conflict.axis, conflict.other])
	var drops := await _run_drop_walks(assembly)
	var levels := _level_distribution(assembly)
	var vertical := _vertical_distribution(assembly)
	await _release(assembly)
	return {"graph": graph, "strong": strong, "edges": edges, "risers": risers,
		"coplanar": coplanar, "drops": drops, "levels": levels, "vertical": vertical}


func _level_distribution(assembly: Node3D) -> Dictionary:
	var result := {}
	for cell: Dictionary in assembly.map.cells:
		if String(cell.role) == "void":
			continue
		var key := "%.1f" % float(cell.get("floor_y", 0.0))
		result[key] = int(result.get(key, 0)) + 1
	return result


func _vertical_distribution(assembly: Node3D) -> Dictionary:
	var result := {"level": 0, "ramp": 0, "drop": 0}
	for edge: Dictionary in assembly.map.edges:
		if String(edge.connector) != "direct":
			continue
		var key := String(edge.get("vertical", "level"))
		result[key] = int(result.get(key, 0)) + 1
	return result


func _run_drop_walks(assembly: Node3D) -> Dictionary:
	var result := {"checked": 0, "landed": 0, "landing_events": 0, "climb_checked": 0,
		"climb_blocked": 0, "walks": [] as Array[Dictionary], "failures": [] as Array[String]}
	assembly._build_player()
	await physics_frame
	await physics_frame
	var player: CharacterBody3D = assembly.player
	if player == null:
		result.failures.append("drop walk needs the walkthrough player")
		_fail_all(result.failures)
		return result
	var landing_count := [0]
	var landing_positions: Array = []
	player.connect("landing_event", func() -> void:
		landing_count[0] += 1
		landing_positions.append([player.global_position.x, player.global_position.y, player.global_position.z]))
	var edges := CHECKS.drop_edges(assembly)
	for edge: Dictionary in edges:
		var walk := await _walk_off_drop(assembly, player, edge, landing_count, landing_positions)
		result.checked += 1
		result.landing_events += int(walk.landing_events)
		result.landed += 1 if walk.landed else 0
		result.walks.append(walk)
		_fail_all(walk.failures)
		var climb := await _try_climb(assembly, player, edge)
		result.climb_checked += 1
		result.climb_blocked += 1 if climb.blocked else 0
		_fail_all(climb.failures)
	Input.action_release("move_forward")
	return result


func _walk_off_drop(assembly: Node3D, player: CharacterBody3D, edge: Dictionary, landing_count: Array, landing_positions: Array) -> Dictionary:
	var cells := CHECKS.cell_index(assembly.map)
	var drop: Dictionary = edge.drop
	var upper_id := String(drop.upper_cell_id)
	var lower_id := String(drop.lower_cell_id)
	var upper_floor := CHECKS.floor_of(cells[upper_id])
	var lower_floor := CHECKS.floor_of(cells[lower_id])
	var end := _upper_port(assembly, edge, upper_id)
	var result := {"upper": upper_id, "lower": lower_id, "landed": false, "landing_events": 0,
		"failures": [] as Array[String]}
	if end.is_empty():
		result.failures.append("%s: drop has no upper doorway" % upper_id)
		return result
	var normal: Vector2 = end.normal
	var start: Vector2 = end.pos - normal * 1.2
	landing_count[0] = 0
	landing_positions.clear()
	player.global_position = Vector3(start.x, upper_floor + CHECKS.CAPSULE_CENTER, start.y)
	player.rotation = Vector3(0.0, atan2(-normal.x, -normal.y), 0.0)
	player.velocity = Vector3.ZERO
	player.get_node("Head").rotation = Vector3.ZERO
	for _frame in 8:
		await physics_frame
	Input.action_press("move_forward")
	var landed := false
	for _frame in 300:
		await physics_frame
		if player.is_on_floor() and player.global_position.y < upper_floor - 0.25:
			landed = true
			break
	Input.action_release("move_forward")
	for _frame in 12:
		await physics_frame
	result.landing_events = int(landing_count[0])
	result["start"] = [start.x, upper_floor, start.y]
	result["final"] = [player.global_position.x, player.global_position.y, player.global_position.z]
	result["landings"] = landing_positions.duplicate()
	result["landed"] = landed and absf(player.global_position.y - (lower_floor + CHECKS.CAPSULE_CENTER)) < 0.2
	var lower_rect := CHECKS.envelope_rect(cells[lower_id])
	var position := Vector2(player.global_position.x, player.global_position.z)
	if not lower_rect.has_point(position):
		result.failures.append("%s: drop landed outside the lower cell (%s, rect %s)" % [lower_id, str(result.final), str(lower_rect)])
	if not landed:
		result.failures.append("%s -> %s: the player did not fall off the ledge (start %s final %s)" % [upper_id, lower_id, str(result.start), str(result.final)])
	if int(landing_count[0]) != 1:
		result.failures.append("%s -> %s: %d landing events, expected 1 at %s" % [upper_id, lower_id, int(landing_count[0]), str(landing_positions)])
	if player.global_position.distance_to(assembly.spawn_position) < 0.5:
		result.failures.append("%s -> %s: the player reset to spawn" % [upper_id, lower_id])
	return result


func _try_climb(assembly: Node3D, player: CharacterBody3D, edge: Dictionary) -> Dictionary:
	var cells := CHECKS.cell_index(assembly.map)
	var drop: Dictionary = edge.drop
	var upper_id := String(drop.upper_cell_id)
	var lower_id := String(drop.lower_cell_id)
	var lower_floor := CHECKS.floor_of(cells[lower_id])
	var upper_floor := CHECKS.floor_of(cells[upper_id])
	var end := _upper_port(assembly, edge, upper_id)
	var normal: Vector2 = -end.normal
	var start: Vector2 = end.pos - normal * 1.2
	var result := {"blocked": false, "failures": [] as Array[String]}
	player.global_position = Vector3(start.x, lower_floor + CHECKS.CAPSULE_CENTER, start.y)
	player.rotation = Vector3(0.0, atan2(-normal.x, -normal.y), 0.0)
	player.velocity = Vector3.ZERO
	for _frame in 8:
		await physics_frame
	Input.action_press("move_forward")
	var maximum := player.global_position.y
	for _frame in 180:
		await physics_frame
		maximum = maxf(maximum, player.global_position.y)
	Input.action_release("move_forward")
	result["blocked"] = maximum < upper_floor - 0.35
	if not result.blocked:
		result.failures.append("%s -> %s: the capsule climbed the drop (max y %.2f, upper floor %.2f)" % [
			lower_id, upper_id, maximum, upper_floor])
	return result


func _upper_port(assembly: Node3D, edge: Dictionary, upper_id: String) -> Dictionary:
	var from_end := CHECKS.port_end(assembly, String(edge.from))
	var to_end := CHECKS.port_end(assembly, String(edge.to))
	if String(from_end.get("cell_id", "")) == upper_id:
		return from_end
	if String(to_end.get("cell_id", "")) == upper_id:
		return to_end
	return {}


func _run_negative_controls() -> Dictionary:
	var controls := {}
	controls["riser_removed"] = await _control_riser_removed()
	controls["ramp_collider_removed"] = await _control_ramp_removed()
	controls["drop_without_return"] = await _control_drop_without_return()
	for name: String in controls:
		_expect(not controls[name].applicable or controls[name].failed_as_expected,
			"Negative control %s did not fail" % name)
	return controls


func _control_riser_removed() -> Dictionary:
	var assembly := await _build(map, specs)
	var host := assembly.get_node_or_null("Risers")
	if host == null or host.get_child_count() == 0:
		await _release(assembly)
		return {"applicable": false, "failed_as_expected": false, "reason": "map has no risers"}
	var intact := CHECKS.check_risers(assembly)
	var body := _first_riser_body(host)
	var name := String(body.name) if body != null else ""
	if body != null:
		body.get_parent().remove_child(body)
		body.free()
	var changed := CHECKS.check_risers(assembly)
	await _release(assembly)
	return {"applicable": true, "riser": name, "intact_failures": intact.failures.size(),
		"failed_as_expected": intact.failures.is_empty() and not changed.failures.is_empty(),
		"changed_failures": changed.failures.size(),
		"first_failure": changed.failures[0] if not changed.failures.is_empty() else ""}


func _first_riser_body(host: Node3D) -> StaticBody3D:
	for child in host.get_children():
		if child is StaticBody3D and String(child.name).begins_with("WallRiser_"):
			return child as StaticBody3D
	return null


func _control_ramp_removed() -> Dictionary:
	var assembly := await _build(map, specs)
	var body := _first_ramp_body(assembly)
	if body == null:
		await _release(assembly)
		return {"applicable": false, "failed_as_expected": false, "reason": "map has no ramp"}
	var name := String(body.name)
	var intact := CHECKS.check_edges(assembly.get_world_3d().direct_space_state, assembly)
	body.get_parent().remove_child(body)
	body.free()
	var changed := CHECKS.check_edges(assembly.get_world_3d().direct_space_state, assembly)
	await _release(assembly)
	return {"applicable": true, "ramp": name,
		"failed_as_expected": intact.ramp_passed == intact.ramp_edges and changed.ramp_passed < changed.ramp_edges,
		"intact_passed": intact.ramp_passed, "intact_edges": intact.ramp_edges,
		"changed_passed": changed.ramp_passed, "changed_edges": changed.ramp_edges}


func _first_ramp_body(assembly: Node3D) -> StaticBody3D:
	for room: Node3D in assembly.rooms.values():
		var boundaries := room.get_node_or_null("AuthoredBoundaries")
		if boundaries == null:
			continue
		for node in boundaries.find_children("Ramp_*", "StaticBody3D", true, false):
			return node as StaticBody3D
	return null


func _control_drop_without_return() -> Dictionary:
	var altered := map.duplicate(true)
	var changed := ""
	for edge: Dictionary in altered.edges:
		if String(edge.connector) != "direct":
			continue
		var vertical := String(edge.get("vertical", "level"))
		if vertical != "ramp":
			continue
		var ramp: Dictionary = edge.ramp
		edge["vertical"] = "drop"
		edge.erase("ramp")
		edge["drop"] = {"upper_cell_id": String(ramp.upper_cell_id),
			"lower_cell_id": String(ramp.lower_cell_id),
			"drop_m": absf(CHECKS.floor_of(_cell(altered, String(ramp.upper_cell_id))) -
				CHECKS.floor_of(_cell(altered, String(ramp.lower_cell_id))))}
		changed = "%s -> %s" % [ramp.lower_cell_id, ramp.upper_cell_id]
		break
	if changed.is_empty():
		return {"applicable": false, "failed_as_expected": false, "reason": "map has no ramp to make one-way"}
	var assembly := await _build(altered, specs)
	var strong := CHECKS.check_strong(assembly)
	await _release(assembly)
	return {"applicable": true, "edge": changed, "failed_as_expected": not strong.failures.is_empty(),
		"failures": strong.failures.size(), "first_failure": strong.failures[0] if not strong.failures.is_empty() else ""}


func _cell(document: Dictionary, cell_id: String) -> Dictionary:
	for cell: Dictionary in document.cells:
		if String(cell.cell_id) == cell_id:
			return cell
	return {}


func _check_scene() -> Dictionary:
	var packed := load(SCENE_PATH) as PackedScene
	_expect(packed != null, "Walkthrough scene did not load")
	if packed == null:
		return {}
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await physics_frame
	await physics_frame
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null and scene.get_meta("walkthrough_ready", false), "Walkthrough player or ready state is missing")
	var result := {"player_spawned": player != null}
	if player != null:
		var origin_cell: Dictionary = _cell(map, scene.origin_cell)
		var expected_y := CHECKS.floor_of(origin_cell) + CHECKS.CAPSULE_CENTER
		_expect(absf(player.global_position.y - expected_y) < 0.3,
			"Spawn is not at the origin cell's floor")
		var safe := scene.get_node_or_null("SafetyNet")
		_expect(safe != null, "Safety net is missing")
		if safe != null:
			var lowest := CHECKS.floor_of(map.cells[0])
			for cell: Dictionary in map.cells:
				lowest = minf(lowest, CHECKS.floor_of(cell))
			_expect(absf(safe.global_position.y - (lowest - 4.0)) < 0.01,
				"Safety net is not at min(floor_y) - 4 m")
		result["spawn_y"] = player.global_position.y
		result["safety_net_y"] = safe.global_position.y if safe != null else null
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
	printerr("ISSUE201_ELEVATION: " + message)
