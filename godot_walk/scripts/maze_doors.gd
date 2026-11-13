class_name MazeDoors
extends RefCounted

## Runtime door registry and lock-behind state for the M4 overlay slice (#234).
##
## This is the GDScript twin of ``maze_doors.py``.  It reads the committed map's
## ``edges`` and the generated shape-room specs, never edits either, and derives
##
## * one record per traversable generated doorway, with its procedural-leaf fit;
## * the departed component of every crossing direction (the side the player
##   leaves, per proposal section 4.6), so an eligible crossing can close and
##   latch the leaf behind the player;
## * the door subset of the event log: ``door_lock`` / ``door_unlock`` changes of
##   ``state`` between ``open`` and ``latched``.
##
## The exit threshold and every doorway incident to the exit cell are skipped.
## A library doorway has no leaf and is skipped rather than silently locked.  A
## drop doorway never has a leaf; a ramp doorway only has one when the ramp's
## rise lands exactly at the recorded sill, so no ramp rebuild is needed.

const EXIT := preload("res://scripts/maze_exit.gd")

const SCHEMA_VERSION := 1
const LAYER_VERSION := "maze-door-0.1.0"
const STATE_HASH_PREFIX := "maze-door-state-0.1.0"
const DEFAULT_STATE := "open"
const STATES := ["open", "latched"]
const MIN_LEAF_WIDTH_M := 0.6
const MIN_LEAF_HEIGHT_M := 1.0
const SILL_TOLERANCE_M := 0.001

const REASON_ORDER := [
	"library_doorway",
	"no_leaf",
	"rewire_internal",
	"drop_door",
	"missing_doorway",
	"ramp_no_landing",
	"small_port",
	"exit_threshold_door",
	"exit_cell_door",
	"not_bridge",
	"target_too_small",
	"target_too_large",
	"exit_inside",
]

const LOCK_CHECKS := [
	"leaf_fits",
	"bridge",
	"target_size",
	"exit_outside_target",
	"exit_reachable_closed",
]
const OPEN_CHECKS := ["door_latched", "player_on_current_side"]


static func cells_by_id(document: Dictionary) -> Dictionary:
	var result := {}
	for cell: Dictionary in document.get("cells", []):
		var cell_id := String(cell.get("cell_id", ""))
		if not cell_id.is_empty():
			result[cell_id] = cell
	return result


static func is_library(cell: Dictionary) -> bool:
	return cell.get("module") is Dictionary


static func doorway(spec: Dictionary, port_id: String) -> Dictionary:
	for item: Dictionary in spec.get("doorways", []):
		if String(item.get("port_id", "")) == port_id:
			return item
	return {}


static func ramp_record(spec: Dictionary, port_id: String) -> Dictionary:
	for item: Dictionary in spec.get("ramps", []):
		if String(item.get("port_id", "")) == port_id:
			return item
	return {}


static func sill(doorway_record: Dictionary) -> float:
	return float(doorway_record.get("sill_height_m", 0.0))


## [leaf: bool, reason: String] — an empty reason means the leaf fits.
static func leaf_fit(vertical: String, spec_a: Dictionary, spec_b: Dictionary,
		door_a: Dictionary, door_b: Dictionary) -> Array:
	if vertical == "drop":
		return [false, "drop_door"]
	if door_a.is_empty() or door_b.is_empty():
		return [false, "missing_doorway"]
	if bool(door_a.get("rewire_internal", false)) or bool(door_b.get("rewire_internal", false)):
		return [false, "rewire_internal"]
	var width := minf(float(door_a.get("width_m", 0.0)),
		float(door_b.get("width_m", 0.0)))
	var height := minf(float(door_a.get("height_m", 0.0)),
		float(door_b.get("height_m", 0.0)))
	if width < MIN_LEAF_WIDTH_M or height < MIN_LEAF_HEIGHT_M:
		return [false, "small_port"]
	if vertical != "ramp":
		if absf(sill(door_a)) > SILL_TOLERANCE_M or absf(sill(door_b)) > SILL_TOLERANCE_M:
			return [false, "ramp_no_landing"]
		return [true, ""]
	var lower_spec := {}
	var lower_door := {}
	if sill(door_a) > SILL_TOLERANCE_M:
		lower_spec = spec_a
		lower_door = door_a
	elif sill(door_b) > SILL_TOLERANCE_M:
		lower_spec = spec_b
		lower_door = door_b
	if lower_spec.is_empty():
		return [false, "ramp_no_landing"]
	var ramp := ramp_record(lower_spec, String(lower_door.get("port_id", "")))
	if ramp.is_empty():
		return [false, "ramp_no_landing"]
	if absf(float(ramp.get("rise_m", 0.0)) - sill(lower_door)) > SILL_TOLERANCE_M:
		return [false, "ramp_no_landing"]
	if float(ramp.get("run_m", 0.0)) <= 0.0:
		return [false, "ramp_no_landing"]
	return [true, ""]


static func target_hash(cells: Array) -> String:
	var sorted_cells: Array = cells.duplicate()
	sorted_cells.sort()
	var names: Array[String] = []
	for cell_id: String in sorted_cells:
		names.append(cell_id)
	return "\n".join(names).sha256_text()


static func _sort_reasons(reasons: Array[String]) -> void:
	reasons.sort_custom(func(first: String, second: String) -> bool:
		return REASON_ORDER.find(first) < REASON_ORDER.find(second))


static func crossing(graph: Dictionary, exit_cell: String, exit_threshold: String,
		door: Dictionary, from_cell: String, to_cell: String) -> Dictionary:
	var reasons: Array[String] = []
	if String(door.kind) == "library":
		reasons.append("library_doorway")
	elif String(door.vertical) == "drop":
		reasons.append("drop_door")
	elif not bool(door.leaf):
		var leaf_reason := String(door.get("leaf_reason", ""))
		reasons.append(leaf_reason if not leaf_reason.is_empty() else "no_leaf")
	var threshold := String(door.threshold_id)
	if threshold == exit_threshold:
		reasons.append("exit_threshold_door")
	elif not exit_cell.is_empty() and (
			exit_cell == String(door.cell_a) or exit_cell == String(door.cell_b)):
		reasons.append("exit_cell_door")
	var component: Variant = EXIT.component_without(graph, from_cell, to_cell)
	var target_cells: Array = []
	var target_size := 0
	if component == null:
		reasons.append("not_bridge")
	else:
		target_cells = component
		target_size = target_cells.size()
		if target_size < EXIT.MIN_REROLL_CELLS:
			reasons.append("target_too_small")
		elif target_size > EXIT.MAX_REROLL_CELLS:
			reasons.append("target_too_large")
		if not exit_cell.is_empty() and target_cells.has(exit_cell):
			reasons.append("exit_inside")
	_sort_reasons(reasons)
	return {
		"from_cell": from_cell,
		"to_cell": to_cell,
		"target_cells": target_cells,
		"target_size": target_size,
		"target_hash": target_hash(target_cells),
		"eligible": reasons.is_empty(),
		"reasons": reasons,
	}


static func door_record(edge: Dictionary, cells: Dictionary, specs: Dictionary,
		graph: Dictionary, exit_cell: String, exit_threshold: String) -> Dictionary:
	var port_a := String(edge.get("from", ""))
	var port_b := String(edge.get("to", ""))
	var cell_a := port_a.get_slice(":", 0)
	var cell_b := port_b.get_slice(":", 0)
	if cell_a == cell_b or not cells.has(cell_a) or not cells.has(cell_b):
		return {}
	if String((cells[cell_a] as Dictionary).get("role", "")) == "void":
		return {}
	if String((cells[cell_b] as Dictionary).get("role", "")) == "void":
		return {}
	if cell_b < cell_a:
		var swap_cell := cell_a
		cell_a = cell_b
		cell_b = swap_cell
		var swap_port := port_a
		port_a = port_b
		port_b = swap_port
	var spec_a: Dictionary = specs.get(cell_a, {})
	var spec_b: Dictionary = specs.get(cell_b, {})
	var door_a := doorway(spec_a, port_a)
	var door_b := doorway(spec_b, port_b)
	var vertical := String(edge.get("vertical", "level"))
	var library: bool = is_library(cells[cell_a]) or is_library(cells[cell_b])
	var kind := "library" if library else "generated"
	var fit: Array = [false, "library_doorway"]
	if not library:
		fit = leaf_fit(vertical, spec_a, spec_b, door_a, door_b)
	var leaf := bool(fit[0])
	var leaf_reason := String(fit[1])
	var threshold := EXIT.threshold_id(cell_a, cell_b)
	var record := {
		"threshold_id": threshold,
		"cell_a": cell_a,
		"cell_b": cell_b,
		"port_a": port_a,
		"port_b": port_b,
		"vertical": vertical,
		"kind": kind,
		"leaf": leaf,
		"leaf_reason": null if leaf_reason.is_empty() else leaf_reason,
		"leaf_side": cell_a if leaf else null,
		"leaf_port": port_a if leaf else null,
		"exit_threshold": threshold == exit_threshold,
	}
	record["crossings"] = [
		crossing(graph, exit_cell, exit_threshold, record, cell_a, cell_b),
		crossing(graph, exit_cell, exit_threshold, record, cell_b, cell_a),
	]
	return record


static func plan(document: Dictionary, specs: Dictionary,
		exit_record: Dictionary = {}) -> Dictionary:
	var exit_data: Dictionary = exit_record
	if exit_data.is_empty():
		exit_data = EXIT.select_exit(document)
	var exit_cell := String(exit_data.get("cell_id", ""))
	var exit_threshold := String(exit_data.get("threshold_id", ""))
	var cells := cells_by_id(document)
	var graph := EXIT.adjacency(document)
	var doors: Array[Dictionary] = []
	var seen := {}
	for edge: Dictionary in document.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var record := door_record(edge, cells, specs, graph, exit_cell, exit_threshold)
		if record.is_empty() or seen.has(String(record.threshold_id)):
			continue
		seen[String(record.threshold_id)] = true
		doors.append(record)
	doors.sort_custom(func(first: Dictionary, second: Dictionary) -> bool:
		return String(first.threshold_id) < String(second.threshold_id))
	var eligible: Array[Dictionary] = []
	var skipped: Array[Dictionary] = []
	var generated := 0
	var library := 0
	var leaf_capable := 0
	for door: Dictionary in doors:
		if String(door.kind) == "generated":
			generated += 1
		else:
			library += 1
		if bool(door.leaf):
			leaf_capable += 1
		else:
			skipped.append({"threshold_id": String(door.threshold_id),
				"reason": String(door.get("leaf_reason", ""))})
		for item: Dictionary in door.crossings:
			if bool(item.eligible):
				eligible.append({
					"threshold_id": String(door.threshold_id),
					"from_cell": String(item.from_cell),
					"to_cell": String(item.to_cell),
				})
	return {
		"schema_version": SCHEMA_VERSION,
		"layer_version": LAYER_VERSION,
		"map_id": String(document.get("map_id", "")),
		"seed": int(document.get("seed", 0)),
		"exit_cell": exit_cell,
		"exit_threshold_id": exit_threshold,
		"doors": doors,
		"eligible_crossings": eligible,
		"skipped_doors": skipped,
		"stats": {
			"doors": doors.size(),
			"generated": generated,
			"library": library,
			"leaf_capable": leaf_capable,
			"eligible_crossings": eligible.size(),
		},
	}


static func projection(plan_data: Dictionary) -> Dictionary:
	var doors: Array = []
	for door: Dictionary in plan_data.get("doors", []):
		var crossings: Array = []
		for item: Dictionary in door.get("crossings", []):
			var reasons: Array = []
			for reason: String in item.reasons:
				reasons.append(reason)
			crossings.append({
				"from_cell": String(item.from_cell),
				"to_cell": String(item.to_cell),
				"target_size": int(item.target_size),
				"target_hash": String(item.target_hash),
				"eligible": bool(item.eligible),
				"reasons": reasons,
			})
		doors.append({
			"threshold_id": String(door.threshold_id),
			"cell_a": String(door.cell_a),
			"cell_b": String(door.cell_b),
			"port_a": String(door.port_a),
			"port_b": String(door.port_b),
			"vertical": String(door.vertical),
			"kind": String(door.kind),
			"leaf": bool(door.leaf),
			"leaf_reason": door.get("leaf_reason"),
			"leaf_side": door.get("leaf_side"),
			"leaf_port": door.get("leaf_port"),
			"exit_threshold": bool(door.exit_threshold),
			"crossings": crossings,
		})
	var eligible: Array = []
	for item: Dictionary in plan_data.get("eligible_crossings", []):
		eligible.append({
			"threshold_id": String(item.threshold_id),
			"from_cell": String(item.from_cell),
			"to_cell": String(item.to_cell),
		})
	var skipped: Array = []
	for item: Dictionary in plan_data.get("skipped_doors", []):
		skipped.append({
			"threshold_id": String(item.threshold_id),
			"reason": String(item.get("reason", "")),
		})
	return {
		"schema_version": int(plan_data.get("schema_version", 0)),
		"layer_version": String(plan_data.get("layer_version", "")),
		"map_id": String(plan_data.get("map_id", "")),
		"seed": int(plan_data.get("seed", 0)),
		"exit_cell": String(plan_data.get("exit_cell", "")),
		"exit_threshold_id": String(plan_data.get("exit_threshold_id", "")),
		"doors": doors,
		"eligible_crossings": eligible,
		"skipped_doors": skipped,
		"stats": {
			"doors": int(plan_data.get("stats", {}).get("doors", 0)),
			"generated": int(plan_data.get("stats", {}).get("generated", 0)),
			"library": int(plan_data.get("stats", {}).get("library", 0)),
			"leaf_capable": int(plan_data.get("stats", {}).get("leaf_capable", 0)),
			"eligible_crossings": int(
				plan_data.get("stats", {}).get("eligible_crossings", 0)),
		},
	}


static func door_by_threshold(plan_data: Dictionary, threshold: String) -> Dictionary:
	for door: Dictionary in plan_data.get("doors", []):
		if String(door.threshold_id) == threshold:
			return door
	return {}


static func crossing_for(plan_data: Dictionary, from_cell: String,
		to_cell: String) -> Dictionary:
	for door: Dictionary in plan_data.get("doors", []):
		for item: Dictionary in door.get("crossings", []):
			if String(item.from_cell) == from_cell and String(item.to_cell) == to_cell:
				return {"door": door, "crossing": item}
	return {}


static func states_from_overlay(plan_data: Dictionary, overlay: Dictionary) -> Dictionary:
	var overrides: Dictionary = overlay.get("door_overrides", {})
	var states := {}
	for door: Dictionary in plan_data.get("doors", []):
		var threshold := String(door.threshold_id)
		var state := DEFAULT_STATE
		var value: Variant = overrides.get(threshold, {})
		if value is Dictionary:
			state = String((value as Dictionary).get("state", DEFAULT_STATE))
		states[threshold] = state if STATES.has(state) else DEFAULT_STATE
	return states


static func fold_states(plan_data: Dictionary, events: Array) -> Dictionary:
	var states := {}
	for door: Dictionary in plan_data.get("doors", []):
		states[String(door.threshold_id)] = DEFAULT_STATE
	for event: Dictionary in events:
		if event.get("record_kind") != null and String(event.get("record_kind", "")) != "mutation":
			continue
		var event_type := String(event.get("event_type", ""))
		if event_type != "door_lock" and event_type != "door_unlock":
			continue
		var validation: Variant = event.get("validation")
		if validation is Dictionary and String((validation as Dictionary).get("outcome", "")) == "rejected":
			continue
		var target: Variant = event.get("target")
		if not (target is Dictionary):
			continue
		var threshold := String((target as Dictionary).get("threshold_id", ""))
		if not states.has(threshold):
			continue
		var change: Variant = event.get("change")
		if not (change is Dictionary):
			continue
		var before: Variant = (change as Dictionary).get("before")
		if before != null and String(before) != String(states[threshold]):
			push_error("MazeDoors: %s is %s, event says %s" % [
				threshold, String(states[threshold]), String(before)])
			continue
		var after := String((change as Dictionary).get("after", ""))
		if STATES.has(after):
			states[threshold] = after
	return states


static func state_hash(states: Dictionary) -> String:
	var thresholds: Array = states.keys()
	thresholds.sort()
	var payload := STATE_HASH_PREFIX + "\n"
	for threshold: String in thresholds:
		payload += "%s=%s\n" % [threshold, String(states[threshold])]
	return payload.sha256_text()


static func port_states(plan_data: Dictionary, states: Dictionary) -> Dictionary:
	var result := {}
	for door: Dictionary in plan_data.get("doors", []):
		var state := String(states.get(String(door.threshold_id), DEFAULT_STATE))
		if state == DEFAULT_STATE:
			continue
		result[String(door.port_a)] = state
		result[String(door.port_b)] = state
	return result


static func reachable(document: Dictionary, start: String, goal: String,
		blocked: Array = []) -> bool:
	if start.is_empty() or goal.is_empty():
		return false
	var graph := EXIT.adjacency(document)
	for pair: Array in EXIT.passage_pairs(document):
		var threshold := EXIT.threshold_id(String(pair[0]), String(pair[1]))
		if not blocked.has(threshold):
			continue
		(graph[String(pair[0])] as Array[String]).erase(String(pair[1]))
		(graph[String(pair[1])] as Array[String]).erase(String(pair[0]))
	if not graph.has(start) or not graph.has(goal):
		return false
	var seen := {start: true}
	var queue: Array[String] = [start]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		if current == goal:
			return true
		for neighbour: String in graph[current]:
			if seen.has(neighbour):
				continue
			seen[neighbour] = true
			queue.append(neighbour)
	return seen.has(goal)


static func exit_reachable(document: Dictionary, exit_cell: String, start_cell: String,
		blocked: Array = []) -> bool:
	return reachable(document, start_cell, exit_cell, blocked)


static func counters(events: Array) -> Dictionary:
	var locks := 0
	var opens := 0
	var rejected := 0
	for event: Dictionary in events:
		var event_type := String(event.get("event_type", ""))
		if event_type != "door_lock" and event_type != "door_unlock":
			continue
		var validation: Variant = event.get("validation")
		if validation is Dictionary and String(
				(validation as Dictionary).get("outcome", "")) == "rejected":
			rejected += 1
			continue
		if event_type == "door_lock":
			locks += 1
		else:
			opens += 1
	return {"locks": locks, "opens": opens, "rejected": rejected}


static func state_change(before: String, after: String) -> Dictionary:
	return {
		"class": "state",
		"layer_version": LAYER_VERSION,
		"before": before,
		"after": after,
	}


static func lock_event(door: Dictionary, from_cell: String,
		to_cell: String, event_index: int, visibility: Dictionary = {}) -> Dictionary:
	var event := {
		"schema_version": SCHEMA_VERSION,
		"event_index": event_index,
		"record_kind": "mutation",
		"event_type": "door_lock",
		"target": {
			"threshold_id": String(door.threshold_id),
			"from_cell": from_cell,
			"to_cell": to_cell,
		},
		"stream": "door:gmap-0.13.0",
		"change": state_change("open", "latched"),
		"validation": {"outcome": "accepted", "checks": LOCK_CHECKS.duplicate()},
	}
	if not visibility.is_empty():
		event["visibility"] = visibility
	return event


static func open_event(door: Dictionary, from_cell: String, event_index: int) -> Dictionary:
	return {
		"schema_version": SCHEMA_VERSION,
		"event_index": event_index,
		"record_kind": "mutation",
		"event_type": "door_unlock",
		"target": {"threshold_id": String(door.threshold_id), "from_cell": from_cell},
		"stream": "door:gmap-0.13.0",
		"change": state_change("latched", "open"),
		"validation": {"outcome": "accepted", "checks": OPEN_CHECKS.duplicate()},
	}
