class_name MazeRewireRuntime
extends Node

## Live M6 re-roll rebuild and reveal driver (#236).
##
## The M5 enumerator is cached when an eligible leaf latches. On the later open
## request from the B side, this driver chooses from the cached shortlist,
## applies the stored passage delta to the same cells, rebuilds only the rooms
## whose doorway set changed, validates F0-F2 with the real specs, and swaps the
## nodes while the leaf is still closed. The door then opens to the new layout.
##
## The committed map, shape-room files and library scenes are never edited. A
## failed rebuild keeps the old nodes and opens the old branch; the door is
## blocked for the rest of the run. The event stores ``P`` and the doorway
## records, so replay never re-enumerates.

const REROLL := preload("res://scripts/maze_reroll.gd")
const REWIRE := preload("res://scripts/maze_rewire.gd")
const GRAPH := preload("res://scripts/maze_graph.gd")
const DOORS := preload("res://scripts/maze_doors.gd")
const LEAF := preload("res://scripts/maze_door_leaf.gd")
const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const LIGHT := preload("res://scripts/maze_light_controller.gd")

const VISIBILITY_DEPTH := 2
const RUNTIME_CHECKS := ["F0", "F1", "F2", "geometry", "cell_identity",
	"not_visible"]

var enabled := true
var assembly: Node3D
var door_runtime: Node
var map: Dictionary = {}
var specs: Dictionary = {}
var base_specs: Dictionary = {}
var passage_state: Dictionary = {}
var passage_revisions: Dictionary = {}
var exit_record: Dictionary = {}
var exit_cell := ""
var branch_epoch := 0
var reroll_serial := 0
var pending: Dictionary = {}
var accepted_thresholds: Dictionary = {}
var blocked: Dictionary = {}
var accepted_events: Array[Dictionary] = []


func setup(assembly_node: Node3D, door_node: Node) -> void:
	assembly = assembly_node
	door_runtime = door_node
	map = assembly.map
	specs = assembly.specs
	base_specs = specs.duplicate(true)
	passage_state = REROLL.base_passage_state(map)
	exit_record = assembly.exit_record_data()
	exit_cell = String(exit_record.get("cell_id", ""))


## Cache the ranked list when an eligible leaf latches (§4.6 step 1).
func prepare(door: Dictionary, from_cell: String, to_cell: String,
		visible_cells: Array = []) -> Dictionary:
	if not enabled:
		return {"ok": false, "reason": "disabled", "analysis": {}}
	var threshold := String(door.get("threshold_id", ""))
	if threshold.is_empty():
		return {"ok": false, "reason": "no_door", "analysis": {}}
	if blocked.has(threshold):
		return {"ok": false, "reason": "door_blocked", "analysis": {}}
	if accepted_thresholds.has(threshold):
		return {"ok": false, "reason": "door_already_rerolled", "analysis": {}}
	if accepted_events.size() >= REROLL.MAX_REROLLS_PER_RUN:
		return {"ok": false, "reason": "run_reroll_cap", "analysis": {}}
	var options := {
		"seed": int(map.get("seed", 0)),
		"attempt": int(map.get("attempt", 0)),
		"reroll_index": 1,
		"exit_cell": exit_cell,
		"visible_cells": visible_cells,
		"state": passage_state,
	}
	var analysis := REROLL.analyze_target(current_map(), from_cell, to_cell, options)
	if not bool(analysis.get("ok", false)):
		return {"ok": false, "reason": String(analysis.get("reason", "no_candidate")),
			"analysis": analysis}
	analysis["seed"] = int(map.get("seed", 0))
	analysis["attempt"] = int(map.get("attempt", 0))
	pending[threshold] = {
		"analysis": analysis,
		"from_cell": from_cell,
		"to_cell": to_cell,
	}
	return {"ok": true, "reason": "", "analysis": analysis}


func cancel_pending(threshold: String) -> void:
	pending.erase(threshold)


func has_pending(threshold: String) -> bool:
	return pending.has(threshold)


## Commit the pending re-roll before the leaf opens. The returned ``event`` is
## appended by the door runtime whether the rebuild is accepted or rejected.
func commit(threshold: String, player_cell: String, event_index: int) -> Dictionary:
	var entry: Dictionary = pending.get(threshold, {})
	if entry.is_empty():
		return {"ok": false, "reason": "no_pending",
			"event": rejected_event(threshold, "", "", event_index, "no_pending")}
	var analysis: Dictionary = entry.get("analysis", {})
	var draw := REROLL.choose_candidate(analysis, event_index)
	if draw.is_empty():
		blocked[threshold] = true
		pending.erase(threshold)
		var reason := "no_candidate"
		return {"ok": false, "reason": reason,
			"event": rejected_event(threshold, String(entry.get("from_cell", "")),
				String(entry.get("to_cell", "")), event_index, reason, analysis)}
	analysis["draw"] = draw
	analysis["chosen"] = draw.get("chosen")
	analysis["chosen_rank"] = int(draw.get("chosen_rank", 0))
	var event := accepted_event(analysis, event_index, player_cell)
	var result := apply_stored_event(event, player_cell, true)
	if bool(result.get("ok", false)):
		pending.erase(threshold)
		return {"ok": true, "reason": "", "event": event,
			"changed_cells": result.get("changed_cells", [])}
	blocked[threshold] = true
	pending.erase(threshold)
	var rejected := rejected_event(threshold, String(entry.get("from_cell", "")),
		String(entry.get("to_cell", "")), event_index,
		String(result.get("reason", "candidate_failed_runtime")), analysis)
	return {"ok": false, "reason": String(result.get("reason", "")),
		"event": rejected}


## Apply one already-stored ``rewire-1`` event. This is the replay path: it
## reads ``P`` and the doorway records and never re-enumerates.
func apply_stored_event(event: Dictionary, player_cell: String = "",
		require_closed: bool = true) -> Dictionary:
	if not enabled:
		return {"ok": false, "reason": "disabled", "changed_cells": []}
	if String(event.get("event_type", "")) != "door_reroll":
		return {"ok": false, "reason": "event_type_invalid", "changed_cells": []}
	var validation: Variant = event.get("validation")
	if validation is Dictionary and String((validation as Dictionary).get(
			"outcome", "")) == "rejected":
		return {"ok": false, "reason": "event_rejected", "changed_cells": []}
	var rewire: Variant = event.get("rewire")
	if not (rewire is Dictionary):
		return {"ok": false, "reason": "rewire_invalid", "changed_cells": []}
	var target_raw: Variant = event.get("target")
	var target: Dictionary = target_raw if target_raw is Dictionary else {}
	var door_threshold := String(target.get("door_threshold_id", ""))
	if door_threshold.is_empty():
		door_threshold = String((rewire as Dictionary).get("door_threshold_id", ""))
	var player := player_cell if not player_cell.is_empty() \
		else String(target.get("to_cell", ""))
	if accepted_thresholds.has(door_threshold):
		return {"ok": false, "reason": "door_already_rerolled", "changed_cells": []}
	if require_closed and not _door_is_closed(door_threshold):
		return {"ok": false, "reason": "door_not_closed", "changed_cells": []}
	var applied := REWIRE.apply_event_to_state(passage_state, event)
	if not bool(applied.get("ok", false)):
		return {"ok": false, "reason": String(applied.get("reason", "")),
			"changed_cells": []}
	var derived := REWIRE.derive_specs(map, specs, event)
	if not bool(derived.get("ok", false)):
		return {"ok": false, "reason": String(derived.get("reason", "")),
			"changed_cells": []}
	var derived_specs: Dictionary = derived.get("specs", {})
	var changed_cells: Array = derived.get("changed_cells", [])
	var issues := REWIRE.geometry_issues(map, specs, derived_specs, event)
	if not issues.is_empty():
		return {"ok": false, "reason": String(issues[0]), "changed_cells": []}
	var graph := GRAPH.f0_f1_f2(map, applied.get("state", {}), player, exit_cell)
	if not bool(graph.get("F0", false)):
		return {"ok": false, "reason": "F0_not_strongly_connected",
			"changed_cells": []}
	if not bool(graph.get("F1", false)):
		return {"ok": false, "reason": "F1_exit_unreachable", "changed_cells": []}
	if not bool(graph.get("F2", false)):
		return {"ok": false, "reason": "F2_trap", "changed_cells": []}
	if require_closed:
		var visible := _visible_from(player, door_threshold)
		for cell_id: String in (rewire as Dictionary).get("target_cells", []):
			if visible.has(cell_id):
				return {"ok": false, "reason": "visible_target", "changed_cells": []}
	var built := _build_rooms(derived_specs, changed_cells)
	if not bool(built.get("ok", false)):
		return {"ok": false, "reason": String(built.get("reason", "candidate_failed_runtime")),
			"changed_cells": []}
	var new_rooms: Dictionary = built.get("rooms", {})
	_swap_rooms(new_rooms)
	passage_state = applied.get("state", passage_state)
	for cell_id: String in derived_specs:
		specs[cell_id] = derived_specs[cell_id]
		passage_revisions[cell_id] = int(derived_specs[cell_id].get(
			"passage_revision", 0))
	branch_epoch += 1
	reroll_serial += 1
	accepted_events.append(event.duplicate(true))
	if not door_threshold.is_empty():
		accepted_thresholds[door_threshold] = true
	_refresh_doors()
	return {
		"ok": true,
		"reason": "",
		"changed_cells": changed_cells,
		"checks": RUNTIME_CHECKS.duplicate(),
		"state_hash": state_hash(),
		"branch_epoch": branch_epoch,
	}


func accepted_event(analysis: Dictionary, event_index: int,
		player_cell: String) -> Dictionary:
	var rewire := REROLL.rewire_block(map, analysis, event_index)
	var visible := _visible_from(player_cell, String(analysis.get("door_threshold_id", "")))
	var target := {
		"cell_id": String(analysis.get("root_cell_id", "")),
		"port_id": String(analysis.get("threshold_id", "")),
		"threshold_id": String(analysis.get("threshold_id", "")),
		"branch_root": String(analysis.get("root_cell_id", "")),
		"door_threshold_id": String(analysis.get("door_threshold_id", "")),
		"from_cell": String(analysis.get("from_cell", "")),
		"to_cell": String(analysis.get("to_cell", "")),
	}
	var draw: Dictionary = analysis.get("draw", {})
	return {
		"schema_version": 1,
		"event_index": event_index,
		"record_kind": "mutation",
		"event_type": "door_reroll",
		"target": target,
		"stream": REROLL.EVENT_STREAM,
		"rewire": rewire,
		"draw": {
			"purpose": String(draw.get("purpose", "rewire-1:choose")),
			"index": int(draw.get("index", 0)),
			"reroll_serial": reroll_serial + 1,
			"branch_attempt": int(analysis.get("chosen_rank", 0)),
		},
		"validation": {
			"outcome": "accepted",
			"checks": (analysis.get("checks", []) as Array).duplicate() + RUNTIME_CHECKS,
		},
		"visibility": {
			"player_cell": player_cell,
			"visible_cells": _array_of(visible),
			"target_hidden": true,
		},
	}


func rejected_event(threshold: String, from_cell: String, to_cell: String,
		event_index: int, reason: String, analysis: Dictionary = {}) -> Dictionary:
	var door := DOORS.door_by_threshold(door_runtime.plan, threshold) \
		if door_runtime != null else {}
	var target := {
		"cell_id": String(analysis.get("root_cell_id", from_cell)),
		"port_id": String(analysis.get("threshold_id", "")),
		"threshold_id": String(analysis.get("threshold_id", "")),
		"branch_root": String(analysis.get("root_cell_id", from_cell)),
		"door_threshold_id": threshold,
		"from_cell": from_cell,
		"to_cell": to_cell,
	}
	if String(target["threshold_id"]).is_empty() and not door.is_empty():
		target["threshold_id"] = String(door.get("threshold_id", ""))
	var rewire := {
		"algorithm_version": REROLL.ALGORITHM_VERSION,
		"target_cells": (analysis.get("target_cells", []) as Array).duplicate(),
		"root_cell_id": String(analysis.get("root_cell_id", from_cell)),
		"threshold_id": String(target["threshold_id"]),
		"passages_before": REROLL._pair_list(analysis.get("edges_before", {})),
		"candidate_count": (analysis.get("candidates", []) as Array).size(),
		"shortlist_size": (analysis.get("shortlist", []) as Array).size(),
		"consistency_relaxed": bool(analysis.get("consistency_relaxed", false)),
		"candidate_set_hash": String(analysis.get("candidate_set_hash", "")),
	}
	return {
		"schema_version": 1,
		"event_index": event_index,
		"record_kind": "mutation",
		"event_type": "door_reroll",
		"target": target,
		"stream": REROLL.EVENT_STREAM,
		"rewire": rewire,
		"validation": {"outcome": "rejected", "reason": reason,
			"checks": [reason]},
	}


func current_map() -> Dictionary:
	var result := map.duplicate(true)
	var base_edges := {}
	for edge: Dictionary in map.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var pair := REWIRE.pair_key(String(edge.get("from", "")).get_slice(":", 0),
			String(edge.get("to", "")).get_slice(":", 0))
		if not base_edges.has(pair):
			base_edges[pair] = edge
	var edges: Array = []
	for edge: Dictionary in map.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			edges.append(edge.duplicate(true))
	var keys: Array = passage_state.keys()
	keys.sort()
	for key: String in keys:
		var pair := REWIRE.pair_cells(key)
		if pair.size() != 2:
			continue
		var left := String(pair[0])
		var right := String(pair[1])
		var edge: Dictionary = base_edges.get(key, {})
		if not edge.is_empty() and _base_edge_ports_are_current(edge, left, right):
			edges.append(edge.duplicate(true))
			continue
		edges.append({
			"connector": "direct",
			"from": REWIRE.port_id(left, right),
			"to": REWIRE.port_id(right, left),
			"vertical": String((passage_state[key] as Dictionary).get(
				"vertical", "level")),
		})
	result["edges"] = edges
	return result


func _base_edge_ports_are_current(edge: Dictionary, left: String, right: String) -> bool:
	if not specs.has(left) or not specs.has(right):
		return true
	var port_left := String(edge.get("from", ""))
	var port_right := String(edge.get("to", ""))
	if String(port_left).get_slice(":", 0) != left:
		var swap := port_left
		port_left = port_right
		port_right = swap
	return not DOORS.doorway(specs[left], port_left).is_empty() \
		and not DOORS.doorway(specs[right], port_right).is_empty()


func state_hash() -> String:
	return REWIRE.state_hash(passage_state, passage_revisions, branch_epoch,
		reroll_serial)


func passage_revision(cell_id: String) -> int:
	return int(passage_revisions.get(cell_id, 0))


func snapshot() -> Dictionary:
	var passages: Array = []
	var keys: Array = passage_state.keys()
	keys.sort()
	for key: String in keys:
		passages.append(key)
	return {
		"layer_version": REWIRE.RUNTIME_LAYER_VERSION,
		"map_id": String(map.get("map_id", "")),
		"seed": int(map.get("seed", 0)),
		"branch_epoch": branch_epoch,
		"reroll_serial": reroll_serial,
		"passages": passages,
		"passage_revisions": passage_revisions.duplicate(true),
		"pending": pending.keys(),
		"accepted": accepted_thresholds.keys(),
		"blocked": blocked.keys(),
		"accepted_events": accepted_events.size(),
		"state_hash": state_hash(),
	}


func _door_is_closed(door_threshold: String) -> bool:
	if door_runtime == null:
		return false
	if door_runtime.state_of(door_threshold) != "latched":
		return false
	var leaf: Node3D = door_runtime.leaf_node(door_threshold)
	return leaf != null and LEAF.is_closed(leaf)


func _visible_from(player_cell: String, door_threshold: String) -> PackedStringArray:
	var door_states := {}
	var door := DOORS.door_by_threshold(door_runtime.plan, door_threshold) \
		if door_runtime != null else {}
	if not door.is_empty():
		door_states[String(door.port_a)] = "latched"
		door_states[String(door.port_b)] = "latched"
	return VISIBILITY.visible_cells(current_map(), player_cell, VISIBILITY_DEPTH,
		door_states)


func _build_rooms(derived_specs: Dictionary, changed_cells: Array) -> Dictionary:
	var rooms := {}
	for cell_id: String in changed_cells:
		var spec: Dictionary = derived_specs.get(cell_id, {})
		if spec.is_empty():
			_free_rooms(rooms)
			return {"ok": false, "reason": "missing_spec", "rooms": {}}
		var room := _build_room(cell_id, spec)
		if room == null:
			_free_rooms(rooms)
			return {"ok": false, "reason": "candidate_failed_runtime", "rooms": {}}
		rooms[cell_id] = room
	return {"ok": true, "reason": "", "rooms": rooms}


func _build_room(cell_id: String, spec: Dictionary) -> Node3D:
	var old_room: Node3D = assembly.room_node(cell_id)
	if old_room == null:
		return null
	var room: Node3D = assembly.build_room_from_spec(spec)
	if room == null:
		return null
	room.name = "%s__rewire" % cell_id
	room.position.y = _cell_floor_y(cell_id)
	room.visible = false
	room.set_meta("reverb_enabled", bool(old_room.get_meta("reverb_enabled", false)))
	var cell: Dictionary = _cell(cell_id)
	if not cell.is_empty():
		room.set_meta("room_volume_m3", assembly.nominal_room_volume_m3(cell))
	var materials: Dictionary = assembly.materials_for(spec)
	LIGHT.tag_room(room, spec, materials.get("lamp"))
	if not _reapply_lamps(old_room, room):
		room.queue_free()
		return null
	return room


func _reapply_lamps(old_room: Node3D, new_room: Node3D) -> bool:
	if old_room == null or new_room == null:
		return true
	if not old_room.has_meta("maze_lamp_states") \
			or not new_room.has_meta("maze_lamp_states"):
		return true
	var old_seeds := {}
	for entry: Dictionary in LIGHT.lamp_flicker_seeds(old_room):
		old_seeds[int(entry.get("lamp_index", -1))] = int(entry.get("flicker_seed", 0))
	var new_seeds := {}
	for entry: Dictionary in LIGHT.lamp_flicker_seeds(new_room):
		new_seeds[int(entry.get("lamp_index", -1))] = int(entry.get("flicker_seed", 0))
	for entry: Dictionary in LIGHT.lamp_states(old_room):
		var index := int(entry.get("lamp_index", -1))
		var state := String(entry.get("state", ""))
		var seed := int(old_seeds.get(index, -1))
		if state == LIGHT.lamp_state(new_room, index) \
				and seed == int(new_seeds.get(index, -2)):
			continue
		if not LIGHT.apply_lamp_state(new_room, index, state, seed):
			return false
	return true


func _swap_rooms(new_rooms: Dictionary) -> void:
	for cell_id: String in new_rooms:
		var old_room: Node3D = assembly.rooms.get(cell_id, null) as Node3D
		var new_room: Node3D = new_rooms[cell_id] as Node3D
		if old_room == null or new_room == null:
			continue
		var leaves := _leaves_in(old_room)
		for leaf: Node3D in leaves:
			leaf.reparent(assembly, true)
		old_room.name = "%s__old" % cell_id
		old_room.visible = false
		new_room.name = cell_id
		assembly.rooms[cell_id] = new_room
		new_room.visible = true
		for leaf: Node3D in leaves:
			leaf.reparent(new_room, true)
		old_room.queue_free()


func _leaves_in(room: Node3D) -> Array[Node3D]:
	var result: Array[Node3D] = []
	for child: Node in room.get_children():
		if child is Node3D and String(child.name).begins_with("MazeDoorLeaf_"):
			result.append(child as Node3D)
	return result


func _free_rooms(rooms: Dictionary) -> void:
	for room: Node3D in rooms.values():
		if room != null:
			room.queue_free()


func _refresh_doors() -> void:
	if assembly == null or door_runtime == null:
		return
	var runtime_map := current_map()
	var new_plan: Dictionary = assembly.refresh_door_plan(runtime_map)
	door_runtime.apply_rewire_plan(runtime_map, new_plan)
	var follower: Node = assembly.get_meta("maze_follower_runtime", null)
	if follower != null and follower.has_method("set_runtime_map"):
		follower.set_runtime_map(runtime_map)


static func _array_of(values: PackedStringArray) -> Array:
	var result: Array = []
	for value: String in values:
		result.append(value)
	return result


func _cell(cell_id: String) -> Dictionary:
	for cell: Dictionary in map.get("cells", []):
		if String(cell.get("cell_id", "")) == cell_id:
			return cell
	return {}


func _cell_floor_y(cell_id: String) -> float:
	return float(_cell(cell_id).get("floor_y", 0.0))
