class_name MazeFollowerRuntime
extends Node

## Live M2 follower lamp driver (#232).
##
## Counts distinct room entries from the player's position, and on a cadence
## beat applies one hidden lamp state/flicker edit through the assembly. The
## draw key and choice arithmetic match the Python reference in
## ``maze_follower.py``; the event record kept in memory is the override record
## the later controller slice will persist.

const VISIBILITY := preload("res://scripts/maze_visibility.gd")

const STREAM := "follower:gmap-0.13.0"
const FIRST_EDIT_AT_VISITS := 5
const LAMP_CLASSES := ["lamp_state", "lamp_flicker"]
const LAMP_STATES := ["on", "flicker", "dead"]
const MAX_FLICKER_SEED := (1 << 31) - 1
const VISIBILITY_DEPTH := 2

var enabled := true
var assembly: Node3D
var player: CharacterBody3D
var map: Dictionary = {}
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
	map = assembly.map
	seed_value = int(map.get("seed", 0))
	attempt = int(map.get("attempt", 0))
	spawn_cell = String(map.cells[0].cell_id)
	exit_cell = String(assembly.get_meta("maze_exit_cell", ""))


func _physics_process(_delta: float) -> void:
	if not enabled or assembly == null or player == null:
		return
	if not player.is_physics_processing():
		return
	var cell: String = assembly.cell_at(player.global_position)
	if cell.is_empty() or cell == current_cell:
		return
	current_cell = cell
	_enter_cell(cell)
	assembly.set_meta("maze_visited_cells", visited.duplicate())


func _enter_cell(cell_id: String) -> void:
	event_index += 1
	if visited.has(cell_id):
		assembly.set_meta("maze_last_entry_was_new", false)
		return
	visited.append(cell_id)
	assembly.set_meta("maze_last_entry_was_new", true)
	if not _is_beat(visited.size()):
		return
	var edit_index := event_index + 1
	var target := _select_target(cell_id, edit_index)
	if target.is_empty():
		return
	_apply_edit(target, cell_id, edit_index, visited.size())


func _select_target(player_cell: String, edit_index: int) -> String:
	var candidates: Array[String] = []
	for cell_id: String in visited:
		if (
			cell_id == player_cell
			or cell_id == spawn_cell
			or cell_id == exit_cell
			or cell_id == last_edited_cell
		):
			continue
		var spec: Dictionary = assembly.specs.get(cell_id, {})
		if spec.is_empty() or not spec.has("light") or spec.light.lamps.is_empty():
			continue
		if spec.has("landmark") and spec["landmark"] != null:
			continue
		if assembly.module_rooms.has(cell_id):
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


func _apply_edit(target: String, player_cell: String, edit_index: int, visit_count: int) -> void:
	var cell: Dictionary = assembly.specs[target]
	var states_before := _override_value(target, "lamp_state", _state_record(cell))
	var flicker_before := _override_value(target, "lamp_flicker", _flicker_record(cell))
	var indices: Array[int] = []
	for entry: Dictionary in states_before:
		indices.append(int(entry.lamp_index))
	indices.sort()
	var value_hex := _draw_hex(target, "lamp-edit", edit_index)
	var change_class := String(LAMP_CLASSES[_mod_hex(value_hex, LAMP_CLASSES.size())])
	var flickering: Array[int] = []
	if change_class == "lamp_flicker":
		for index: int in indices:
			if String(_state_at(states_before, index)) == "flicker":
				flickering.append(index)
		if flickering.is_empty():
			change_class = "lamp_state"
	var lamp_index := 0
	var change: Dictionary
	if change_class == "lamp_flicker":
		lamp_index = flickering[_shift_mod(value_hex, 8, flickering.size())]
		var current_seed := int(_flicker_at(flicker_before, lamp_index))
		var next_seed := _mod_hex(value_hex.substr(16), MAX_FLICKER_SEED)
		if next_seed == current_seed:
			next_seed = (next_seed + 1) % MAX_FLICKER_SEED
		var after_flicker := flicker_before.duplicate(true)
		_set_record_value(after_flicker, lamp_index, "flicker_seed", next_seed)
		change = {"class": change_class, "before": flicker_before, "after": after_flicker}
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
		change = {"class": change_class, "before": states_before, "after": after_states}
		assembly.set_cell_light(target, lamp_index, next_state)
	var bucket: Dictionary = cell_overrides.get(target, {})
	bucket[change_class] = change.after
	cell_overrides[target] = bucket
	last_edited_cell = target
	event_index = edit_index
	edit_events.append({
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
		"draw": {"purpose": "lamp-edit", "digest": value_hex},
		"visit_count": visit_count,
	})


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
