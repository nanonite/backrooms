extends SceneTree

## Headless M8 follower surface test (#238).
## godot4 --headless --path godot_walk --script res://scripts/test_issue238_follower_surfaces.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json \
##   [--out=res://evidence/.../runtime_<map_id>.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const SURFACE := preload("res://scripts/maze_surface_controller.gd")
const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const EYE_HEIGHT_M := 0.6
const DEPTH := 2
const LAYER_CLASSES := ["reverb", "lamp_state", "lamp_flicker", "wear", "surface_variant"]
const SURFACES := ["floor", "wall", "ceiling", "trim"]
const VARIANT_ORDER := ["clean", "worn", "damaged"]
const EXPECTED_EDITS := {
	"gmap-1-gmap-0.13.0": [["reverb", "c01"], ["lamp_state", "c07"], ["reverb", "c06"]],
	"gmap-2-gmap-0.13.0": [["lamp_state", "c05"], ["lamp_state", "c06"], ["surface_variant", "dp00"]],
	"gmap-3-gmap-0.13.0": [["lamp_state", "c04"], ["lamp_state", "c05"], ["wear", "c11"]],
	"gmap-32-gmap-0.13.0": [["lamp_state", "c06"], ["lamp_state", "c08"], ["reverb", "c09"]],
	"gmap-279-gmap-0.13.0": [["lamp_state", "c04"], ["lamp_state", "dp00"], ["reverb", "c10"]],
}

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
	var direct := await _run_direct()
	var runtime := await _run_runtime()
	var report := {
		"map_id": String(map.map_id),
		"map_sha256_before": hash_before,
		"direct": direct,
		"runtime": runtime,
		"palette": _check_palette_rules(),
	}
	report["map_sha256_after"] = _file_sha256(map_path)
	_expect(report.map_sha256_after == hash_before, "the committed map file changed")
	report["failures"] = failures
	_write_report(report)
	var direct_report: Dictionary = report.direct
	var runtime_report: Dictionary = report.runtime
	print("ISSUE238_FOLLOWER_SURFACES: %s map=%s target=%s classes=%s runtime_edits=%d isolated=%s map_sha256=%s palette=%s" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id,
		String(direct_report.get("target_cell", "")),
		str(direct_report.get("classes", [])),
		int(runtime_report.get("edit_count", 0)),
		"yes" if bool(direct_report.get("isolated", false)) else "no",
		"unchanged" if report.map_sha256_after == hash_before else "CHANGED",
		"ok" if bool(report.palette.get("ok", false)) else "FAILED"])
	quit(0 if failures.is_empty() else 1)


func _run_direct() -> Dictionary:
	var result := {
		"target_cell": "", "classes": [] as Array[String], "isolated": false,
		"reverb": false, "wear": false, "variant": false,
		"negative_controls": {}, "failures": [] as Array[String],
	}
	var scene := await _build_assembly()
	var target := _direct_target(scene)
	if target.is_empty():
		_fail("No generated room with surface layers is available")
		await _release(scene)
		return result
	result.target_cell = target
	var before := _snapshot(scene)
	var geometry := _geometry(scene)
	var reverb_before: bool = scene.room_reverb_enabled(target)
	_expect(scene.set_room_reverb(target, not reverb_before),
		"set_room_reverb refused %s" % target)
	var after_reverb := _snapshot(scene)
	_check_isolation("reverb", target, before, after_reverb)
	_expect(scene.room_reverb_enabled(target) == (not reverb_before),
		"target reverb did not flip")
	result.reverb = true
	result.classes.append("reverb")
	scene.set_room_reverb(target, reverb_before)
	var module_cell := _first_module_cell(scene)
	if not module_cell.is_empty():
		var module_before: bool = scene.room_reverb_enabled(module_cell)
		_expect(scene.set_room_reverb(module_cell, not module_before),
			"a module room refused its allowed reverb flip")
		_expect(scene.room_reverb_enabled(module_cell) == (not module_before),
			"the module reverb flip did not stick")
		scene.set_room_reverb(module_cell, module_before)
		result["module_reverb"] = true
	else:
		result["module_reverb"] = false
	var wear_before: int = scene.cell_wear(target)
	if wear_before < 2:
		_expect(scene.set_room_wear(target, wear_before + 1),
			"set_room_wear refused %s" % target)
		var after_wear := _snapshot(scene)
		_check_isolation("wear", target, before, after_wear)
		_expect(scene.cell_wear(target) == wear_before + 1,
			"target wear did not rise")
		_expect(_snapshot_field(after_wear, target, "floor").get("wear", -1)
			== wear_before + 1, "floor collider wear metadata did not rise")
		result.wear = true
		result.classes.append("wear")
		scene.set_room_wear(target, wear_before)
	var variants_before: Dictionary = scene.cell_surface_variants(target)
	var surface := _escalatable_surface(target, variants_before)
	if not surface.is_empty():
		var variants_after := variants_before.duplicate(true)
		variants_after[surface] = VARIANT_ORDER[
			VARIANT_ORDER.find(String(variants_before[surface])) + 1]
		var materials_before := _material_paths(scene.room_node(target))
		_expect(scene.set_cell_surface_variants(target, variants_after),
			"set_cell_surface_variants refused %s" % target)
		var after_variant := _snapshot(scene)
		_check_isolation("surface_variant", target, before, after_variant)
		_expect(_snapshot_field(after_variant, target, "variants") == variants_after,
			"target variants did not change")
		var materials_after := _material_paths(scene.room_node(target))
		if surface != "trim" or _has_surface_material(materials_before, "trim"):
			_expect(
				JSON.stringify(materials_before) != JSON.stringify(materials_after),
				"surface %s did not replace a material" % surface)
		var floor_after := _snapshot_field(after_variant, target, "floor")
		if surface == "floor" and not floor_after.is_empty():
			_expect(String(floor_after.get("variant", "")) == String(variants_after["floor"]),
				"floor collider variant metadata did not change")
		result.variant = true
		result.classes.append("surface_variant")
		scene.set_cell_surface_variants(target, variants_before)
	else:
		_fail("%s has no surface that can advance" % target)
	result.isolated = true
	result.negative_controls = _negative_controls(scene, target)
	_expect(JSON.stringify(geometry) == JSON.stringify(_geometry(scene)),
		"surface edits changed room geometry")
	_fail_all(result.failures)
	await _release(scene)
	return result


func _negative_controls(scene: Node3D, target: String) -> Dictionary:
	var controls := {}
	var variants: Dictionary = scene.cell_surface_variants(target)
	var bad_variant := variants.duplicate(true)
	bad_variant["floor"] = "pristine"
	controls["unknown_variant"] = not scene.set_cell_surface_variants(target, bad_variant)
	var bad_surface := variants.duplicate(true)
	bad_surface["walls"] = "worn"
	controls["unknown_surface"] = not scene.set_cell_surface_variants(target, bad_surface)
	controls["wear_above_two"] = not scene.set_room_wear(target, 3)
	controls["wear_negative"] = not scene.set_room_wear(target, -1)
	controls["unknown_cell"] = not scene.set_room_wear("missing", 1)
	var exit_cell := String(scene.exit_cell_id())
	controls["exit_refused"] = exit_cell.is_empty() or not scene.set_room_wear(exit_cell, 1)
	var module_cell := ""
	var landmark_cell := ""
	for cell: Dictionary in map.cells:
		if cell.get("module") != null:
			module_cell = String(cell.cell_id)
		if cell.get("landmark") != null:
			landmark_cell = String(cell.cell_id)
	controls["module_refused"] = module_cell.is_empty() or not scene.set_room_wear(module_cell, 1)
	controls["landmark_refused"] = landmark_cell.is_empty() or not scene.set_room_wear(landmark_cell, 1)
	for name: String in controls:
		if not controls[name]:
			_fail("Negative control %s did not fail as expected" % name)
	return controls


func _run_runtime() -> Dictionary:
	var result := {
		"edit_count": 0, "route_cells": 0, "edits": [] as Array,
		"route": [] as Array, "visited": [] as Array,
		"isolated": true, "failures": [] as Array[String],
	}
	var scene := await _build_scene()
	var runtime: Node = scene.get_meta("maze_follower_runtime", null)
	if runtime == null:
		_fail("Walkthrough has no live follower runtime")
		await _release(scene)
		return result
	# The M3 exit driver ends the run on the exit cell; M8 exercises the
	# follower across the whole route, so the end-card driver stays out of it.
	var exit_runtime: Node = scene.get_meta("maze_exit_runtime", null)
	if exit_runtime != null:
		exit_runtime.enabled = false
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		_fail("Walkthrough player is missing")
		await _release(scene)
		return result
	for _frame in 3:
		await physics_frame
	var route := _bfs_order(scene, String(scene.origin_cell))
	result.route = route
	var previous: Dictionary = _snapshot(scene)
	for cell_id: String in route:
		if runtime.edit_events.size() >= 3:
			break
		result.route_cells += 1
		await _move_player(scene, player, cell_id)
		for _frame in 2:
			await physics_frame
		var current: Dictionary = _snapshot(scene)
		var new_events: Array = runtime.edit_events.slice(result.edit_count)
		if new_events.is_empty():
			var silent := _changed_cells(previous, current)
			_expect(silent.is_empty(),
				"state changed without a new event on %s: %s" % [cell_id, str(silent)])
		else:
			var event: Dictionary = new_events[0]
			var target := String(event.target.cell_id)
			var change_class := String(event.change.class)
			var changed := _changed_cells(previous, current)
			_expect(changed == [target],
				"edit %s@%s changed cells %s" % [change_class, target, str(changed)])
			if changed != [target]:
				result.isolated = false
			_expect(_class_applied(scene, target, event), "%s@%s did not reach the assembly" % [change_class, target])
			result.edits.append({
				"event_index": int(event.event_index),
				"class": change_class,
				"cell": target,
				"player_cell": String(event.visibility.player_cell),
				"visit_count": int(event.get("visit_count", 0)),
				"changed_cells": changed,
			})
			result.edit_count = runtime.edit_events.size()
		previous = current
	var expected: Array = EXPECTED_EDITS.get(String(map.map_id), [])
	for index in mini(expected.size(), result.edits.size()):
		var actual: Dictionary = result.edits[index]
		_expect(String(actual.class) == String(expected[index][0]),
			"edit %d class %s, expected %s" % [index, actual.class, expected[index][0]])
		_expect(String(actual.cell) == String(expected[index][1]),
			"edit %d cell %s, expected %s" % [index, actual.cell, expected[index][1]])
	_expect(result.edit_count >= mini(expected.size(), 3),
		"live runtime produced %d edits, expected %d" % [result.edit_count, expected.size()])
	for event: Dictionary in runtime.edit_events:
		_expect(LAYER_CLASSES.has(String(event.change.class)),
			"live event has an unknown class %s" % event.change.class)
		_expect(event.validation.checks.has("palette_compatible")
			or String(event.change.class) != "surface_variant",
			"variant edit is missing the palette check")
	result.visited = runtime.visited
	_fail_all(result.failures)
	await _release(scene)
	return result


func _class_applied(scene: Node3D, target: String, event: Dictionary) -> bool:
	var change: Dictionary = event.change
	var change_class := String(change.class)
	if change_class == "lamp_state":
		return JSON.stringify(scene.cell_light_states(target)) == JSON.stringify(change.after)
	if change_class == "lamp_flicker":
		return JSON.stringify(scene.cell_lamp_flicker_seeds(target)) == JSON.stringify(change.after)
	if change_class == "reverb":
		return scene.room_reverb_enabled(target) == bool(change.after)
	if change_class == "wear":
		return scene.cell_wear(target) == int(change.after)
	if change_class == "surface_variant":
		return JSON.stringify(scene.cell_surface_variants(target)) == JSON.stringify(change.after)
	return false


func _check_palette_rules() -> Dictionary:
	var result := {"ok": false, "checks": 0, "failures": [] as Array[String]}
	var cell: Dictionary = {}
	for candidate: Dictionary in map.cells:
		if candidate.get("module") == null and candidate.get("palette") != null \
				and candidate.get("surface_variants") != null:
			cell = candidate
			break
	if cell.is_empty():
		_fail("No generated cell with a palette record")
		return result
	var palette := SURFACE.palette_for_cell(cell)
	_expect(not palette.is_empty(), "palette lookup failed for %s" % cell.cell_id)
	var variants: Dictionary = cell.surface_variants
	for surface: String in SURFACES:
		var current: String = variants[surface]
		result.checks += 1
		_expect(VARIANT_ORDER.has(current), "%s %s is not a known variant" % [surface, current])
		var step := SURFACE.next_variant(current, palette, surface)
		if not step.is_empty():
			_expect(SURFACE.next_variant(step, palette, surface) != current,
				"%s did not move forward from %s" % [surface, current])
	_expect(SURFACE.next_variant("damaged", palette, "floor").is_empty(),
		"damaged floor still has a next variant")
	_expect(SURFACE.surface_of(_fake_mesh("FloorRect")) == "floor", "floor mesh not classified")
	_expect(SURFACE.surface_of(_fake_mesh("Wall_00_0Visual")) == "wall", "wall mesh not classified")
	_expect(SURFACE.surface_of(_fake_mesh("TrimLintel_p0")) == "trim", "trim mesh not classified")
	_expect(SURFACE.surface_of(_fake_mesh("CeilingRect")) == "ceiling", "ceiling mesh not classified")
	result.ok = result.failures.is_empty() and failures.is_empty()
	_fail_all(result.failures)
	return result


func _fake_mesh(node_name: String) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name = node_name
	return mesh


func _first_module_cell(scene: Node3D) -> String:
	for cell: Dictionary in map.cells:
		if cell.get("module") != null and scene.has_room(String(cell.cell_id)):
			return String(cell.cell_id)
	return ""


func _direct_target(scene: Node3D) -> String:
	var exit_cell := String(scene.exit_cell_id())
	var spawn_cell := String(map.cells[0].cell_id)
	for cell: Dictionary in map.cells:
		if cell.get("module") != null or cell.get("landmark") != null \
				or cell.get("surface_variants") == null or cell.get("wear") == null:
			continue
		if String(cell.cell_id) == exit_cell or String(cell.cell_id) == spawn_cell:
			continue
		return String(cell.cell_id)
	return ""


func _escalatable_surface(cell_id: String, variants: Dictionary) -> String:
	var cell: Dictionary = _cell(cell_id)
	var palette := SURFACE.palette_for_cell(cell)
	if palette.is_empty():
		return ""
	var available := SURFACE.escalatable_surfaces(variants, palette)
	for preferred: String in ["floor", "wall", "ceiling", "trim"]:
		if available.has(preferred):
			return preferred
	return ""


func _has_surface_material(materials: Dictionary, surface: String) -> bool:
	for node_name: String in materials:
		if SURFACE.surface_of(_named(node_name)) == surface:
			return true
	return false


func _named(node_name: String) -> Node:
	var node := Node.new()
	node.name = node_name
	return node


func _cell(cell_id: String) -> Dictionary:
	for cell: Dictionary in map.cells:
		if String(cell.cell_id) == cell_id:
			return cell
	return {}


func _check_isolation(change_class: String, target: String,
		before: Dictionary, after: Dictionary) -> void:
	var changed := _changed_cells(before, after)
	_expect(changed == [target],
		"%s changed cells %s, expected only %s" % [change_class, str(changed), target])


func _changed_cells(before: Dictionary, after: Dictionary) -> Array:
	var changed: Array = []
	for cell_id: String in before:
		if JSON.stringify(before[cell_id]) != JSON.stringify(after.get(cell_id, {})):
			changed.append(cell_id)
	changed.sort()
	return changed


func _snapshot(scene: Node3D) -> Dictionary:
	var snapshot := {}
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		var room: Node3D = scene.room_node(cell_id)
		if room == null:
			continue
		snapshot[cell_id] = {
			"wear": scene.cell_wear(cell_id),
			"variants": scene.cell_surface_variants(cell_id),
			"reverb": scene.room_reverb_enabled(cell_id),
			"lights": scene.cell_light_states(cell_id),
			"flicker": scene.cell_lamp_flicker_seeds(cell_id),
			"floor": _floor_meta(room),
			"materials": _material_paths(room),
		}
	return snapshot


func _floor_meta(room: Node3D) -> Dictionary:
	var body := room.find_child("WalkableFloor", true, false) as StaticBody3D
	if body == null or not body.has_meta("surface_acoustic"):
		return {}
	return {
		"acoustic": String(body.get_meta("surface_acoustic", "")),
		"wear": int(body.get_meta("surface_wear", -1)),
		"variant": String(body.get_meta("surface_variant", "")),
	}


func _material_paths(room: Node3D) -> Dictionary:
	var result := {}
	for node: Node in room.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if SURFACE.surface_of(mesh).is_empty():
			continue
		var material := mesh.material_override as StandardMaterial3D
		result[String(mesh.name)] = "" if material == null else String(material.get_meta("source_path", ""))
	return result


func _geometry(scene: Node3D) -> Dictionary:
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
		snapshot[cell_id] = {"position": room.position, "rotation": room.rotation, "nodes": nodes}
	return snapshot


func _snapshot_field(snapshot: Dictionary, cell_id: String, field: String) -> Dictionary:
	var cell: Dictionary = snapshot.get(cell_id, {})
	return cell.get(field, {})


func _bfs_order(scene: Node3D, start: String) -> Array[String]:
	var cells := {}
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		if String(cell.role) != "void" and scene.has_room(cell_id):
			cells[cell_id] = cell
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
	var cell: Dictionary = _cell(cell_id)
	var center: Vector2
	if scene.specs.has(cell_id):
		center = _center(scene.specs[cell_id])
	else:
		center = _envelope_center(cell)
	player.global_position = Vector3(center.x,
		float(cell.get("floor_y", 0.0)) + EYE_HEIGHT_M, center.y)
	await physics_frame
	await physics_frame


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
	printerr("ISSUE238_FOLLOWER_SURFACES: " + message)
