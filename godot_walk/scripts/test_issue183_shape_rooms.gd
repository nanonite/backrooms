extends SceneTree

## Headless physics test for generated shape rooms and their assembly (#183).
## godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/2026-11-03-issue-183/runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const ROOM_CHECKS := preload("res://scripts/issue183_room_checks.gd")
const MAP_CHECKS := preload("res://scripts/issue183_map_checks.gd")
const TRIM_CHECKS := preload("res://scripts/issue186_trim_checks.gd")
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
	var report := {"map_id": map.map_id, "mode": index.mode, "rooms_checked": specs.size()}
	report["contract"] = _check_contract()
	report["positive"] = await _run_positive()
	report["negative_controls"] = await _run_negative_controls()
	report["scene"] = await _check_scene()
	report["failures"] = failures
	_write_report(report)
	var positive: Dictionary = report.positive
	print("ISSUE183_SHAPE_ROOMS: %s map=%s mode=%s rooms=%d edges_both_ways=%d/%d closed_blocked=%d/%d flood_cells=%d/%d void_reached=%d trim_pairs=%d trim_coplanar=%d degenerate_trim=%d/%d controls=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id, index.mode, specs.size(),
		positive.edges.passed_forward + positive.edges.passed_reverse, 2 * positive.edges.direct_edges_checked,
		positive.edges.closed_blocked, positive.edges.closed_edges,
		positive.flood.reached_cells, positive.flood.expected_cells, positive.flood.void_cells_reached,
		positive.trim.pairs_checked, positive.trim.same_facing_count,
		positive.trim.degenerate_conflicts, positive.trim.degenerate_trim_boxes,
		str(report.negative_controls.keys())])
	quit(0 if failures.is_empty() else 1)


func _check_contract() -> Dictionary:
	var checked := 0
	for cell_id: String in specs:
		var spec: Dictionary = specs[cell_id]
		_expect(spec.registration_accepted == false and spec.scale_calibrated == false, "%s: registration or scale flag changed" % cell_id)
		_expect(spec.map_id == map.map_id, "%s: spec belongs to another map" % cell_id)
		for feature: Dictionary in spec.features:
			_expect(feature.sign == "symbol", "%s: feature %s is not a symbol" % [cell_id, feature.feature_id])
		_check_margins(cell_id, spec)
		checked += 1
	return {"specs_checked": checked}


## shape-room-0.2.0 (#186): a standard room keeps a full 0.5 m of solid wall on both sides
## of every doorway; only a degenerate room lists corner doorways, exactly those with less.
func _check_margins(cell_id: String, spec: Dictionary) -> void:
	if not spec.has("mode"):
		return
	var corner: Array[String] = []
	var low_xz := Vector2(spec.envelope_xz[0][0], spec.envelope_xz[0][1])
	var high_xz := Vector2(spec.envelope_xz[2][0], spec.envelope_xz[2][1])
	for doorway: Dictionary in spec.doorways:
		var on_x_wall: bool = absf(float(doorway.normal[0])) > 0.5
		var centre := float(doorway.pos_xz[1] if on_x_wall else doorway.pos_xz[0])
		var side_low := low_xz.y if on_x_wall else low_xz.x
		var side_high := high_xz.y if on_x_wall else high_xz.x
		var margin := minf(centre - 1.0 - side_low, side_high - (centre + 1.0))
		if margin < 0.5 - 0.0001:
			corner.append(String(doorway.port_id))
	corner.sort()
	var listed: Array = spec.degenerate_port_ids.duplicate()
	listed.sort()
	if String(spec.mode) == "standard":
		_expect(corner.is_empty() and listed.is_empty(), "%s: standard room has a doorway with < 0.5 m wall margin: %s" % [cell_id, str(corner)])
	else:
		_expect(listed == corner, "%s: degenerate_port_ids %s do not match corner doorways %s" % [cell_id, str(listed), str(corner)])
		_expect(spec.degenerate_features == (["corner_doorway"] if not corner.is_empty() else []), "%s: degenerate_features mismatch" % cell_id)


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
	var rooms := ROOM_CHECKS.check_all(space, assembly)
	var edges := MAP_CHECKS.check_edges(space, assembly)
	var flood := MAP_CHECKS.check_flood(space, assembly)
	failures.append_array(rooms.failures)
	failures.append_array(edges.failures)
	failures.append_array(flood.failures)
	var trim := TRIM_CHECKS.check(assembly)
	for conflict: Dictionary in trim.same_facing:
		_fail("Trim %s is coplanar with %s (axis %d, plane %.3f)" % [conflict.trim, conflict.other, conflict.axis, conflict.plane])
	var trim_controls := TRIM_CHECKS.negative_controls(assembly)
	_expect(trim_controls.old_outside_trim_detected, "Trim control: pre-fix outside trim was not detected as coplanar")
	_expect(trim_controls.shared_plane_detected, "Trim control: a trim box sharing a wall plane was not detected")
	trim["negative_controls"] = trim_controls
	await _release(assembly)
	return {"rooms": rooms.rooms, "edges": edges, "flood": flood, "trim": trim}


func _run_negative_controls() -> Dictionary:
	var controls := {}
	controls["doorway_removed"] = await _control_doorway_removed()
	controls["floor_rect_removed"] = await _control_floor_removed()
	for name: String in controls:
		_expect(not controls[name].applicable or controls[name].failed_as_expected, "Negative control %s did not fail" % name)
	return controls


func _control_doorway_removed() -> Dictionary:
	var altered := specs.duplicate(true)
	var removed := ""
	for edge: Dictionary in map.edges:
		var cell_id := String(edge.from).get_slice(":", 0)
		if String(edge.connector) == "direct" and altered.has(cell_id) and altered.has(String(edge.to).get_slice(":", 0)):
			removed = String(edge.from)
			altered[cell_id].doorways = altered[cell_id].doorways.filter(func(d: Dictionary) -> bool: return String(d.port_id) != removed)
			break
	if removed == "":
		return {"applicable": false, "failed_as_expected": false, "reason": "no direct edge joins two rooms in this index"}
	var assembly := await _build(map, altered)
	var space := assembly.get_world_3d().direct_space_state
	var edges := MAP_CHECKS.check_edges(space, assembly)
	var flood := MAP_CHECKS.check_flood(space, assembly)
	await _release(assembly)
	var found: Array = edges.failures + flood.failures
	return {"applicable": true, "removed_doorway": removed, "failed_as_expected": not edges.failures.is_empty(),
		"edge_failures": edges.failures.size(), "flood_failures": flood.failures.size(), "first_failure": found[0] if not found.is_empty() else ""}


func _control_floor_removed() -> Dictionary:
	var altered := specs.duplicate(true)
	var removed := ""
	for cell_id: String in altered:
		if cell_id != String(map.cells[0].cell_id):
			removed = cell_id
			altered[cell_id].rects = altered[cell_id].rects.slice(1)
			break
	var assembly := await _build(map, altered)
	var rooms := ROOM_CHECKS.check_all(assembly.get_world_3d().direct_space_state, assembly)
	await _release(assembly)
	var missing: Array = rooms.failures.filter(func(message: String) -> bool: return message.begins_with(removed) and "floor missing" in message)
	return {"applicable": removed != "", "room": removed, "failed_as_expected": removed != "" and not missing.is_empty(),
		"failure_count": rooms.failures.size(), "first_failure": missing[0] if not missing.is_empty() else ""}


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
		result.merge(_check_spawn(scene, player))
	await _release(scene)
	return result


func _check_spawn(scene: Node3D, player: CharacterBody3D) -> Dictionary:
	var space := player.get_world_3d().direct_space_state
	var origin_room := scene.get_node_or_null(scene.origin_cell) as Node3D
	var polygon: PackedVector2Array = origin_room.get_meta("walkable_polygon_xz")
	var spawn := Vector2(player.global_position.x, player.global_position.z)
	var inside := Geometry2D.is_point_in_polygon(spawn, polygon)
	var clear := PROBE.floor_supported(space, spawn.x, spawn.y)
	_expect(inside and clear, "Player spawn is not on supported floor inside the origin cell")
	player.global_position = Vector3(1000.0, 1000.0, 1000.0)
	player.velocity = Vector3(3.0, 4.0, -2.0)
	scene.call("_reset_player")
	var restored: bool = player.global_position.distance_to(scene.spawn_position) < 0.001 and player.velocity.length() < 0.001
	_expect(restored, "Safe reset did not restore the spawn")
	return {"origin_cell": scene.origin_cell, "spawn_inside_origin_polygon": inside, "spawn_floor_supported": clear,
		"reset_restores_spawn": restored, "safety_net_present": scene.get_node_or_null("SafetyNet") != null}


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
	printerr("ISSUE183_SHAPE_ROOMS: " + message)
