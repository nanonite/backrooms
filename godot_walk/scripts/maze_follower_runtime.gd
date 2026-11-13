class_name MazeFollowerRuntime
extends Node

## Live M8 follower driver (#238), extending the M2 lamp driver (#232).
##
## Counts distinct room entries from the player's position, and on a cadence
## beat applies one hidden edit through the assembly.  The implemented classes
## are reverb, lamp state/flicker, wear and surface_variant; the class draw,
## target rank and per-class arithmetic match ``maze_follower.py``.
##
## The in-memory ``cell_overrides`` and ``edit_events`` are the override records
## the later controller slice persists.

const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const SURFACE := preload("res://scripts/maze_surface_controller.gd")

const STREAM := "follower:gmap-0.13.0"
const FIRST_EDIT_AT_VISITS := 5
const IMPLEMENTED_CLASSES := ["reverb", "lamp_state", "lamp_flicker", "wear", "surface_variant"]
const LAMP_CLASSES := ["lamp_state", "lamp_flicker"]
const LAMP_STATES := ["on", "flicker", "dead"]
const MAX_FLICKER_SEED := (1 << 31) - 1
const VISIBILITY_DEPTH := 2
const LIGHT_LAYER_VERSION := "maze-light-0.1.0"
const REVERB_LAYER_VERSION := "maze-reverb-0.1.0"
const SURFACE_LAYER_VERSION := "maze-surface-0.1.0"
const MAX_WEAR := 2

signal cell_entered(cell_id: String, visit_count: int, is_new: bool)
signal edit_applied(event: Dictionary)

var enabled := true
var assembly: Node3D
var player: CharacterBody3D
var map: Dictionary = {}
var cells_by_id: Dictionary = {}
var seed_value := 0
var attempt := 0
var spawn_cell := ""
var exit_cell := ""
var current_cell := ""
var last_edited_cell := ""
var event_index := 0
var visited: Array[String] = []
var cell_overrides: Dictionary = {}
var edit_events: Array[Dictionary] = []


func setup(assembly_node: Node3D, player_node: CharacterBody3D) -> void:
	assembly = assembly_node
	player = player_node
	apply_map(assembly.map)
	exit_cell = String(assembly.get_meta("maze_exit_cell", ""))


## The M6 re-roll changes the live passage graph; the follower visibility gate
## must read the same graph. The committed map is not edited and the cells keep
## their layers, so the cell index is rebuilt on every map handoff.
func set_runtime_map(runtime_map: Dictionary) -> void:
	apply_map(runtime_map)


func apply_map(runtime_map: Dictionary) -> void:
	map = runtime_map
	seed_value = int(map.get("seed", 0))
	attempt = int(map.get("attempt", 0))
	cells_by_id = {}
	for cell: Dictionary in map.get("cells", []):
		cells_by_id[String(cell.get("cell_id", ""))] = cell
	if not map.get("cells", []).is_empty():
		spawn_cell = String(map.cells[0].cell_id)


func _physics_process(_delta: float) -> void:
	if not enabled or assembly == null or player == null:
		return
	if not player.is_physics_processing():
		return
	var cell: String = assembly.cell_at(player.global_position)
	if cell.is_empty() or cell == current_cell or not assembly.has_room(cell):
		return
	current_cell = cell
	_enter_cell(cell)
	assembly.set_meta("maze_visited_cells", visited.duplicate())


func _enter_cell(cell_id: String) -> void:
	event_index += 1
	if visited.has(cell_id):
		assembly.set_meta("maze_last_entry_was_new", false)
		cell_entered.emit(cell_id, visited.size(), false)
		return
	visited.append(cell_id)
	assembly.set_meta("maze_last_entry_was_new", true)
	cell_entered.emit(cell_id, visited.size(), true)
	if not _is_beat(visited.size()):
		return
	var edit_index := event_index + 1
	var allowed := _allowed_classes(visited.size())
	if allowed.is_empty():
		return
	var targets := {}
	for change_class: String in allowed:
		var target := _select_target(cell_id, edit_index, change_class)
		if not target.is_empty():
			targets[change_class] = target
	if targets.is_empty():
		return
	var feasible: Array[String] = []
	for change_class: String in allowed:
		if targets.has(change_class):
			feasible.append(change_class)
	var class_hex := _draw_hex(cell_id, "edit-class", edit_index)
	var chosen: String = feasible[_mod_hex(class_hex, feasible.size())]
	_apply_edit(String(targets[chosen]), cell_id, edit_index, visited.size(), chosen)


func _allowed_classes(visit_count: int) -> Array[String]:
	var result: Array[String] = []
	if visit_count < FIRST_EDIT_AT_VISITS:
		return result
	for change_class: String in IMPLEMENTED_CLASSES:
		if visit_count <= 9 and not ["reverb", "lamp_state", "lamp_flicker"].has(change_class):
			continue
		result.append(change_class)
	return result


func _select_target(player_cell: String, edit_index: int, change_class: String) -> String:
	var candidates: Array[String] = []
	for cell_id: String in visited:
		if cell_id == player_cell or cell_id == spawn_cell or cell_id == exit_cell \
				or cell_id == last_edited_cell:
			continue
		if not _class_eligible(cell_id, change_class):
			continue
		if not VISIBILITY.cell_is_hidden(map, player_cell, cell_id, VISIBILITY_DEPTH):
			continue
		candidates.append(cell_id)
	if candidates.is_empty():
		return ""
	var degrees := _degrees()
	var best := ""
	var best_recent := 2
	var best_degree := 2
	var best_rank := ""
	for cell_id: String in candidates:
		var age := visited.size() - 1 - visited.find(cell_id)
		var recent := 0 if age >= 1 and age <= 3 else 1
		var degree := 0 if int(degrees.get(cell_id, 0)) >= 2 else 1
		var rank := _draw_hex(cell_id, "target", edit_index)
		if best.is_empty() or recent < best_recent \
				or (recent == best_recent and degree < best_degree) \
				or (recent == best_recent and degree == best_degree and rank < best_rank):
			best = cell_id
			best_recent = recent
			best_degree = degree
			best_rank = rank
	return best


func _class_eligible(cell_id: String, change_class: String) -> bool:
	var cell: Dictionary = cells_by_id.get(cell_id, {})
	if cell.is_empty() or String(cell.get("role", "")) == "void":
		return false
	if cell.get("landmark") != null:
		return false
	if change_class == "reverb":
		return typeof(cell.get("reverb")) == TYPE_BOOL
	if cell.get("module") != null:
		return false
	if LAMP_CLASSES.has(change_class):
		var spec: Dictionary = assembly.specs.get(cell_id, {})
		return not spec.is_empty() and spec.has("light") and not spec.light.lamps.is_empty()
	if change_class == "wear":
		if not cell.has("wear"):
			return false
		var wear_type := typeof(cell.get("wear"))
		if wear_type != TYPE_INT and wear_type != TYPE_FLOAT:
			return false
		var base_wear := float(cell.get("wear"))
		if base_wear != floor(base_wear) or base_wear < 0.0 or base_wear > float(MAX_WEAR):
			return false
		return _effective_wear(cell_id) < MAX_WEAR
	if change_class == "surface_variant":
		return not _escalatable_surfaces(cell_id).is_empty() \
			and not _palette_for(cell_id).is_empty()
	return false


func _apply_edit(target: String, player_cell: String, edit_index: int,
		visit_count: int, change_class: String) -> void:
	if LAMP_CLASSES.has(change_class):
		_apply_lamp_edit(target, player_cell, edit_index, visit_count, change_class)
	elif change_class == "reverb":
		_apply_reverb_edit(target, player_cell, edit_index, visit_count)
	elif change_class == "wear":
		_apply_wear_edit(target, player_cell, edit_index, visit_count)
	else:
		_apply_variant_edit(target, player_cell, edit_index, visit_count)


func _apply_lamp_edit(target: String, player_cell: String, edit_index: int,
		visit_count: int, change_class: String) -> void:
	var cell: Dictionary = assembly.specs[target]
	var states_before := _override_value(target, "lamp_state", _state_record(cell))
	var flicker_before := _override_value(target, "lamp_flicker", _flicker_record(cell))
	var indices: Array[int] = []
	for entry: Dictionary in states_before:
		indices.append(int(entry.lamp_index))
	indices.sort()
	var value_hex := _draw_hex(target, "lamp-edit", edit_index)
	var chosen := change_class
	var flickering: Array[int] = []
	if chosen == "lamp_flicker":
		for index: int in indices:
			if String(_state_at(states_before, index)) == "flicker":
				flickering.append(index)
		if flickering.is_empty():
			chosen = "lamp_state"
	var lamp_index := 0
	var change: Dictionary
	if chosen == "lamp_flicker":
		lamp_index = flickering[_shift_mod(value_hex, 8, flickering.size())]
		var current_seed := int(_flicker_at(flicker_before, lamp_index))
		var next_seed := _mod_hex(value_hex.substr(16), MAX_FLICKER_SEED)
		if next_seed == current_seed:
			next_seed = (next_seed + 1) % MAX_FLICKER_SEED
		var after_flicker := flicker_before.duplicate(true)
		_set_record_value(after_flicker, lamp_index, "flicker_seed", next_seed)
		change = {"class": chosen, "layer_version": LIGHT_LAYER_VERSION,
			"before": flicker_before, "after": after_flicker}
		assembly.set_cell_light(target, lamp_index, "flicker", next_seed)
	else:
		lamp_index = indices[_shift_mod(value_hex, 8, indices.size())]
		var current_state := String(_state_at(states_before, lamp_index))
		var alternatives: Array[String] = []
		for state: String in LAMP_STATES:
			if state != current_state:
				alternatives.append(state)
		var next_state := alternatives[_shift_mod(value_hex, 24, alternatives.size())]
		var after_states := states_before.duplicate(true)
		_set_record_value(after_states, lamp_index, "state", next_state)
		change = {"class": chosen, "layer_version": LIGHT_LAYER_VERSION,
			"before": states_before, "after": after_states}
		assembly.set_cell_light(target, lamp_index, next_state)
	_record_edit(target, player_cell, edit_index, visit_count, change,
		{"purpose": "lamp-edit", "digest": value_hex})


func _apply_reverb_edit(target: String, player_cell: String, edit_index: int,
		visit_count: int) -> void:
	var before := _effective_reverb(target)
	if not assembly.set_room_reverb(target, not before):
		return
	var change := {"class": "reverb", "layer_version": REVERB_LAYER_VERSION,
		"before": before, "after": not before}
	_record_edit(target, player_cell, edit_index, visit_count, change, {})


func _apply_wear_edit(target: String, player_cell: String, edit_index: int,
		visit_count: int) -> void:
	var before := _effective_wear(target)
	if before >= MAX_WEAR or not assembly.set_room_wear(target, before + 1):
		return
	var change := {"class": "wear", "layer_version": SURFACE_LAYER_VERSION,
		"before": before, "after": before + 1}
	_record_edit(target, player_cell, edit_index, visit_count, change, {})


func _apply_variant_edit(target: String, player_cell: String, edit_index: int,
		visit_count: int) -> void:
	var before := _effective_variants(target)
	var palette := _palette_for(target)
	var surfaces := SURFACE.escalatable_surfaces(before, palette)
	if surfaces.is_empty() or palette.is_empty():
		return
	var value_hex := _draw_hex(target, "variant-surface", edit_index)
	var surface: String = surfaces[_mod_hex(value_hex, surfaces.size())]
	var variant := SURFACE.next_variant(String(before[surface]), palette, surface)
	if variant.is_empty():
		return
	var after := before.duplicate(true)
	after[surface] = variant
	if not assembly.set_cell_surface_variants(target, after):
		return
	var change := {"class": "surface_variant", "layer_version": SURFACE_LAYER_VERSION,
		"before": before, "after": after}
	_record_edit(target, player_cell, edit_index, visit_count, change,
		{"purpose": "variant-surface", "digest": value_hex})


func _record_edit(target: String, player_cell: String, edit_index: int,
		visit_count: int, change: Dictionary, draw: Dictionary) -> void:
	var bucket: Dictionary = cell_overrides.get(target, {})
	bucket[String(change["class"])] = change.after
	cell_overrides[target] = bucket
	last_edited_cell = target
	event_index = edit_index
	var event := {
		"event_index": edit_index,
		"event_type": "follower_edit",
		"target": {"cell_id": target},
		"stream": STREAM,
		"change": change,
		"visibility": {
			"player_cell": player_cell,
			"target_hidden": true,
			"visible_cells": Array(VISIBILITY.visible_cells(map, player_cell, VISIBILITY_DEPTH)),
		},
		"visit_count": visit_count,
		"validation": {"outcome": "accepted", "checks": _checks(String(change["class"]))},
	}
	if not draw.is_empty():
		event["draw"] = draw
	edit_events.append(event)
	edit_applied.emit(event)


func _checks(change_class: String) -> Array:
	var checks := ["cadence_beat", "target_hidden", "not_current_cell", "not_spawn_or_exit"]
	if LAMP_CLASSES.has(change_class):
		checks.append("lamp_override_only")
	elif change_class == "reverb":
		checks.append("reverb_override_only")
		checks.append("reverb_flip")
	elif change_class == "wear":
		checks.append("wear_override_only")
		checks.append("wear_capped")
	else:
		checks.append("surface_variant_override_only")
		checks.append("palette_compatible")
	return checks


func _effective_reverb(cell_id: String) -> bool:
	var bucket: Dictionary = cell_overrides.get(cell_id, {})
	if bucket.has("reverb"):
		return bool(bucket["reverb"])
	return bool((cells_by_id.get(cell_id, {}) as Dictionary).get("reverb", false))


func _effective_wear(cell_id: String) -> int:
	var bucket: Dictionary = cell_overrides.get(cell_id, {})
	if bucket.has("wear"):
		return int(bucket["wear"])
	return int((cells_by_id.get(cell_id, {}) as Dictionary).get("wear", 0))


func _effective_variants(cell_id: String) -> Dictionary:
	var cell: Dictionary = cells_by_id.get(cell_id, {})
	var result: Dictionary = (cell.get("surface_variants", {}) as Dictionary).duplicate(true)
	var bucket: Dictionary = cell_overrides.get(cell_id, {})
	if bucket.has("surface_variant"):
		for surface: String in bucket["surface_variant"]:
			result[surface] = String(bucket["surface_variant"][surface])
	return result


func _palette_for(cell_id: String) -> Dictionary:
	var cell: Dictionary = cells_by_id.get(cell_id, {})
	return SURFACE.palette_for_cell(cell)


func _escalatable_surfaces(cell_id: String) -> Array:
	return SURFACE.escalatable_surfaces(_effective_variants(cell_id), _palette_for(cell_id))


func _base_state_record(cell: Dictionary) -> Array:
	var result := []
	for lamp: Dictionary in cell.light.lamps:
		result.append({"lamp_index": int(lamp.lamp_index), "state": String(lamp.state)})
	result.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
		return int(left.lamp_index) < int(right.lamp_index))
	return result


func _base_flicker_record(cell: Dictionary) -> Array:
	var result := []
	for lamp: Dictionary in cell.light.lamps:
		result.append({"lamp_index": int(lamp.lamp_index), "flicker_seed": int(lamp.flicker_seed)})
	result.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
		return int(left.lamp_index) < int(right.lamp_index))
	return result


func _state_record(cell: Dictionary) -> Array:
	return _base_state_record(cell)


func _flicker_record(cell: Dictionary) -> Array:
	return _base_flicker_record(cell)


func _override_value(cell_id: String, change_class: String, fallback: Array) -> Array:
	var bucket: Dictionary = cell_overrides.get(cell_id, {})
	if bucket.has(change_class):
		return (bucket[change_class] as Array).duplicate(true)
	return fallback.duplicate(true)


func _state_at(record: Array, lamp_index: int) -> String:
	for entry: Dictionary in record:
		if int(entry.lamp_index) == lamp_index:
			return String(entry.state)
	return ""


func _flicker_at(record: Array, lamp_index: int) -> int:
	for entry: Dictionary in record:
		if int(entry.lamp_index) == lamp_index:
			return int(entry.flicker_seed)
	return 0


func _set_record_value(record: Array, lamp_index: int, field: String, value: Variant) -> void:
	for entry: Dictionary in record:
		if int(entry.lamp_index) == lamp_index:
			entry[field] = value
			return


func _degrees() -> Dictionary:
	var result := {}
	for cell: Dictionary in map.cells:
		if String(cell.role) != "void":
			result[String(cell.cell_id)] = 0
	for edge: Dictionary in map.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var left := String(edge.get("from", "")).get_slice(":", 0)
		var right := String(edge.get("to", "")).get_slice(":", 0)
		if left != right and result.has(left) and result.has(right):
			result[left] = int(result[left]) + 1
			result[right] = int(result[right]) + 1
	return result


func _is_beat(visit_count: int) -> bool:
	var beat := FIRST_EDIT_AT_VISITS
	while beat < visit_count:
		beat += _band_interval(beat)
	return beat == visit_count


func _band_interval(beat: int) -> int:
	if beat <= 9:
		return 4
	if beat <= 14:
		return 3
	return 2


func _draw_hex(target: String, purpose: String, edit_index: int) -> String:
	var key := "%d:%d:%d:%s:%s:%s" % [
		seed_value, attempt, edit_index, STREAM, target, purpose,
	]
	return key.sha256_text()


static func _mod_hex(hex: String, modulus: int) -> int:
	if modulus <= 0:
		return 0
	var remainder := 0
	for offset in range(0, hex.length(), 2):
		remainder = (remainder * 256 + hex.substr(offset, 2).hex_to_int()) % modulus
	return remainder


static func _shift_mod(hex: String, bits: int, modulus: int) -> int:
	if modulus <= 0:
		return 0
	var low := _mod_hex(hex, modulus << bits)
	return low >> bits
