extends SceneTree

## Headless physics test for generated shape rooms and their assembly (#183).
## godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/2026-11-03-issue-183/runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const ROOM_CHECKS := preload("res://scripts/issue183_room_checks.gd")
const MAP_CHECKS := preload("res://scripts/issue183_map_checks.gd")
const TRIM_CHECKS := preload("res://scripts/issue186_trim_checks.gd")
const MODULE_CHECKS := preload("res://scripts/issue188_module_checks.gd")
const DIAGONAL_CHECKS := preload("res://scripts/issue190_diagonal_checks.gd")
const PALETTE_CHECKS := preload("res://scripts/issue192_palette_checks.gd")
const DIAGONAL := preload("res://scripts/shape_room_diagonal.gd")
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
	var modules: Dictionary = positive.modules
	var diagonal: Dictionary = positive.diagonal
	var summary := "ISSUE183_SHAPE_ROOMS: %s map=%s mode=%s rooms=%d edges_both_ways=%d/%d closed_blocked=%d/%d flood_cells=%d/%d void_reached=%d trim_pairs=%d trim_coplanar=%d degenerate_trim=%d/%d modules=%d landed=%d open=%d aperture_clear=%d wall_coplanar=%d reveal_faces=%d diagonal_edges=%d diagonal_stopped=%d/%d floor_missing=%d/%d joint_uncovered=%d/%d diagonal_coplanar=%d controls=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id, index.mode, specs.size(),
		positive.edges.passed_forward + positive.edges.passed_reverse, 2 * positive.edges.direct_edges_checked,
		positive.edges.closed_blocked, positive.edges.closed_edges,
		positive.flood.reached_cells, positive.flood.expected_cells, positive.flood.void_cells_reached,
		positive.trim.pairs_checked, positive.trim.same_facing_count,
		positive.trim.degenerate_conflicts, positive.trim.degenerate_trim_boxes,
		modules.get("module_cells", 0), modules.get("sockets_landed", 0), modules.get("sockets_open", 0),
		modules.get("apertures_clear", 0), modules.get("wall_coplanar_conflicts", 0),
		modules.get("reveal_coplanar_faces", 0), diagonal.diagonal_edges, diagonal.push_stopped, diagonal.push_samples,
		diagonal.floor_missing, diagonal.floor_samples, diagonal.joint_uncovered, diagonal.joint_samples, diagonal.coplanar_faces, str(report.negative_controls.keys())]
	var palette: Dictionary = positive.get("palette", {"rooms": 0})
	if palette.rooms > 0:  # shape-room-0.5.0 maps only: older maps print the line they always did
		summary += " palette_rooms=%d palette_surfaces=%d palette_mismatch=%d palettes=%s" % [
			palette.rooms, palette.surfaces, palette.mismatches, JSON.stringify(palette.palettes)]
	print(summary)
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
		var half := float(doorway.width_m) / 2.0
		var margin := minf(centre - half - side_low, side_high - (centre + half))
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


func _build(map_data: Dictionary, room_specs: Dictionary, open_modules: bool = true, recess_joints: bool = true,
		diagonal_collision: bool = true, diagonal_pullback: float = 0.0) -> Node3D:
	var assembly := ASSEMBLY.new()
	assembly.auto_start = false
	assembly.open_modules = open_modules
	assembly.recess_joints = recess_joints
	assembly.diagonal_collision = diagonal_collision
	assembly.diagonal_pullback = diagonal_pullback
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
	_fail_all(rooms.failures)
	_fail_all(edges.failures)
	_fail_all(flood.failures)
	var trim := TRIM_CHECKS.check(assembly)
	for conflict: Dictionary in trim.same_facing:
		_fail("Trim %s is coplanar with %s (axis %d, plane %.3f)" % [conflict.trim, conflict.other, conflict.axis, conflict.plane])
	var trim_controls := TRIM_CHECKS.negative_controls(assembly)
	_expect(trim_controls.old_outside_trim_detected, "Trim control: pre-fix outside trim was not detected as coplanar")
	_expect(trim_controls.shared_plane_detected, "Trim control: a trim box sharing a wall plane was not detected")
	trim["negative_controls"] = trim_controls
	var modules := {}
	if not assembly.module_rooms.is_empty():
		modules = MODULE_CHECKS.check(space, assembly)
		_fail_all(modules.failures)
	var diagonal := DIAGONAL_CHECKS.check(assembly)
	_fail_all(diagonal.failures)
	var palette := PALETTE_CHECKS.check(assembly, specs)
	_fail_all(palette.failures)
	await _release(assembly)
	var positive := {"rooms": rooms.rooms, "edges": edges, "flood": flood, "trim": trim, "modules": modules, "diagonal": diagonal}
	if palette.rooms > 0:  # only shape-room-0.5.0 maps: older reports keep their keys
		positive["palette"] = palette
	return positive


func _run_negative_controls() -> Dictionary:
	var controls := {}
	controls["doorway_removed"] = await _control_doorway_removed()
	controls["floor_rect_removed"] = await _control_floor_removed()
	controls["module_socket_closed"] = await _control_module_closed()
	controls["module_joint_recess_removed"] = await _control_joint_recess_removed()
	controls["diagonal_collision_removed"] = await _control_diagonal_collision_removed()
	controls["unmitred_joint"] = await _control_unmitred_joint()
	if specs.values().any(func(spec: Dictionary) -> bool: return spec.materials.has("palette_id")):
		controls["wrong_palette"] = await _control_wrong_palette()
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


## The library room's socket left closed (connector_open false): the joint must read as blocked.
func _control_module_closed() -> Dictionary:
	var joint := ""
	for cell: Dictionary in map.cells:
		if cell.has("module"):
			joint = String(cell.cell_id)
			break
	if joint == "":
		return {"applicable": false, "failed_as_expected": false, "reason": "this map places no library module"}
	var assembly := await _build(map, specs, false)
	var space := assembly.get_world_3d().direct_space_state
	var edges := MAP_CHECKS.check_edges(space, assembly)
	var modules := MODULE_CHECKS.check(space, assembly)
	await _release(assembly)
	var blocked: Array = edges.failures.filter(func(message: String) -> bool: return joint + ":" in message)
	return {"applicable": true, "module_cell": joint, "failed_as_expected": not blocked.is_empty() and not modules.failures.is_empty(),
		"edge_failures": edges.failures.size(), "module_check_failures": modules.failures.size(),
		"first_failure": blocked[0] if not blocked.is_empty() else ""}


## The pre-#189 parent doorway (cut exactly as large as the library opening): the reveal
## and lintel faces of the two rooms share planes and the module check must report them.
func _control_joint_recess_removed() -> Dictionary:
	if not map.cells.any(func(cell: Dictionary) -> bool: return cell.has("module")):
		return {"applicable": false, "failed_as_expected": false, "reason": "this map places no library module"}
	var assembly := await _build(map, specs, true, false)
	var space := assembly.get_world_3d().direct_space_state
	var modules := MODULE_CHECKS.check(space, assembly)
	await _release(assembly)
	return {"applicable": true, "failed_as_expected": modules.reveal_coplanar_faces > 0 and not modules.failures.is_empty(),
		"reveal_coplanar_faces": modules.reveal_coplanar_faces, "module_check_failures": modules.failures.size()}


func _has_diagonal_rooms() -> bool:
	return specs.values().any(func(spec: Dictionary) -> bool: return DIAGONAL.is_chamfered(spec))


## Diagonal walls built without collision: a capsule pushed into them must get through, and the
## wall checks (blocked samples, push test) must report it.
func _control_diagonal_collision_removed() -> Dictionary:
	if not _has_diagonal_rooms():
		return {"applicable": false, "failed_as_expected": false, "reason": "this map has no 45-degree room"}
	var assembly := await _build(map, specs, true, true, false)
	var rooms := ROOM_CHECKS.check_all(assembly.get_world_3d().direct_space_state, assembly)
	var diagonal := DIAGONAL_CHECKS.check(assembly, false)
	await _release(assembly)
	var passed_through: Array = rooms.failures.filter(func(message: String) -> bool: return "capsule passes" in message)
	return {"applicable": true, "failed_as_expected": not passed_through.is_empty() and diagonal.push_stopped < diagonal.push_samples,
		"wall_failures": passed_through.size(), "push_stopped": diagonal.push_stopped, "push_samples": diagonal.push_samples}


## Diagonal walls shortened at both ends (an unmitred joint): the wall band around the joint is left
## open and the coverage check must find it.
func _control_unmitred_joint() -> Dictionary:
	if not _has_diagonal_rooms():
		return {"applicable": false, "failed_as_expected": false, "reason": "this map has no 45-degree room"}
	var assembly := await _build(map, specs, true, true, true, 0.32)
	var diagonal := DIAGONAL_CHECKS.check(assembly, false)
	await _release(assembly)
	return {"applicable": true, "failed_as_expected": diagonal.joint_uncovered > 0, "joint_uncovered": diagonal.joint_uncovered,
		"joint_samples": diagonal.joint_samples}


## Every room built with the wrong palette (textures swapped for colours and the reverse, trim and lamp
## recoloured) but checked against the true specs: each room's surfaces must be reported.
func _control_wrong_palette() -> Dictionary:
	var altered := specs.duplicate(true)
	for cell_id: String in altered:
		var materials: Dictionary = altered[cell_id].materials
		for key: String in ["wall", "floor", "ceiling"]:
			materials[key] = {"color": [0.9, 0.1, 0.1]} if materials[key].has("texture") else {
				"texture": "res://assets/psx_extension/textures/wallpaper_source_video.png", "tile_m": 1.5}
		materials.trim_color = [0.1, 0.9, 0.1]
		materials.lamp_color = [0.1, 0.1, 0.9]
	var assembly := await _build(map, altered)
	var palette := PALETTE_CHECKS.check(assembly, specs)
	await _release(assembly)
	return {"applicable": true, "failed_as_expected": palette.rooms > 0 and palette.mismatches >= palette.surfaces,
		"rooms": palette.rooms, "surfaces": palette.surfaces, "mismatches": palette.mismatches,
		"first_failure": palette.failures[0] if not palette.failures.is_empty() else ""}


func _control_floor_removed() -> Dictionary:
	var altered := specs.duplicate(true)
	var removed := ""
	for cell_id: String in altered:
		if cell_id != String(map.cells[0].cell_id) and not DIAGONAL.is_chamfered(altered[cell_id]):
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


func _fail_all(messages: Array) -> void:
	for message: String in messages:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE183_SHAPE_ROOMS: " + message)
