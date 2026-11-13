class_name MazeDoorRuntime
extends Node

## Live M4 door driver (#234).
##
## Follows the player's cell transitions.  When the player crosses an eligible
## generated doorway, the procedural leaf closes and latches behind them: a
## ``door_lock`` mutation is recorded, the leaf collider fills the port and the
## departed side is occluded.  Pressing E near a latched door (or calling
## ``open_door``) swings the leaf against the inside wall and records a
## ``door_unlock`` mutation.
##
## The driver does nothing while the player's physics processing is off, so the
## existing capture harnesses stay deterministic.  The exit threshold and every
## doorway incident to the exit cell are never latched; a library doorway has no
## leaf and is skipped.  Door state is a pure function of the door subset of the
## log, so ``restore_log`` replays it without a mutated map.

const DOORS := preload("res://scripts/maze_doors.gd")
const LEAF := preload("res://scripts/maze_door_leaf.gd")
const VISIBILITY := preload("res://scripts/maze_visibility.gd")

const INTERACT_KEY := KEY_E
const INTERACT_RANGE_M := 3.0
const VISIBILITY_DEPTH := 2

signal door_latched(threshold_id: String)
signal door_opened(threshold_id: String)

var enabled := true
var assembly: Node3D
var player: CharacterBody3D
var map: Dictionary = {}
var specs: Dictionary = {}
var exit_record: Dictionary = {}
var exit_cell := ""
var plan: Dictionary = {}
var states: Dictionary = {}
var leaves: Dictionary = {}
var door_events: Array[Dictionary] = []
var event_index := 0
var current_cell := ""
var previous_cell := ""
var exit_runtime: Node


func setup(assembly_node: Node3D, player_node: CharacterBody3D) -> void:
	assembly = assembly_node
	player = player_node
	map = assembly.map
	specs = assembly.specs
	exit_record = assembly.exit_record_data()
	exit_cell = String(exit_record.get("cell_id", ""))
	plan = DOORS.plan(map, specs, exit_record)
	states = DOORS.states_from_overlay(plan, {})
	exit_runtime = assembly.get_meta("maze_exit_runtime", null)
	set_process_unhandled_input(true)
	set_process_unhandled_key_input(true)
	assembly.set_meta("maze_doors", plan)
	_publish_states()


func _physics_process(_delta: float) -> void:
	if not enabled or assembly == null or player == null:
		return
	if not player.is_physics_processing():
		return
	if exit_runtime != null and bool(exit_runtime.get("ended")):
		return
	var cell: String = assembly.cell_at(player.global_position)
	if cell.is_empty() or cell == current_cell:
		return
	_enter_cell(cell)


func _enter_cell(cell_id: String) -> void:
	var previous := current_cell
	current_cell = cell_id
	previous_cell = previous
	if cell_id == exit_cell:
		return
	if previous.is_empty() or previous == cell_id:
		return
	var found := DOORS.crossing_for(plan, previous, cell_id)
	if found.is_empty():
		return
	if bool((found.crossing as Dictionary).eligible):
		_latch(found.door, previous, cell_id)


func _unhandled_key_input(event: InputEvent) -> void:
	if not enabled or not (event is InputEventKey):
		return
	var key := event as InputEventKey
	if key.pressed and not key.echo and key.keycode == INTERACT_KEY:
		request_open_nearest()


## Latch an eligible crossing.  Returns the accepted event, or an empty dict.
func _latch(door: Dictionary, from_cell: String, to_cell: String) -> Dictionary:
	var threshold := String(door.threshold_id)
	if String(states.get(threshold, "open")) != "open":
		return {}
	if not DOORS.exit_reachable(map, exit_cell, to_cell, [threshold]):
		return _reject_lock(door, from_cell, to_cell, "exit_route_removed")
	var door_states := {
		String(door.port_a): "latched",
		String(door.port_b): "latched",
	}
	var visible: PackedStringArray = VISIBILITY.visible_cells(
		map, to_cell, VISIBILITY_DEPTH, door_states)
	if visible.has(from_cell):
		return _reject_lock(door, from_cell, to_cell, "visible_target")
	var leaf := _ensure_leaf(door)
	if leaf == null:
		return _reject_lock(door, from_cell, to_cell, "leaf_unavailable")
	var event := DOORS.lock_event(door, from_cell, to_cell, event_index + 1, {
		"player_cell": to_cell,
		"target_hidden": true,
		"visible_cells": Array(visible),
	})
	var record := _append_event(event)
	states[threshold] = "latched"
	LEAF.set_state(leaf, "latched")
	_publish_states()
	emit_signal("door_latched", threshold)
	return record


func _reject_lock(door: Dictionary, from_cell: String, to_cell: String,
		reason: String) -> Dictionary:
	var event := DOORS.lock_event(door, from_cell, to_cell, event_index + 1)
	event["validation"] = {
		"outcome": "rejected",
		"reason": reason,
		"checks": [reason],
	}
	return _append_event(event)


func _append_event(event: Dictionary) -> Dictionary:
	event_index += 1
	var record := event.duplicate(true)
	record["event_index"] = event_index
	door_events.append(record)
	return record


## Build the leaf for a door on first use.  Returns the host node or null.
func _ensure_leaf(door: Dictionary) -> Node3D:
	var threshold := String(door.threshold_id)
	if leaves.has(threshold):
		return leaves[threshold] as Node3D
	var side := String(door.get("leaf_side", ""))
	if side.is_empty():
		return null
	var room: Node3D = assembly.room_node(side)
	if room == null:
		return null
	var spec: Dictionary = specs.get(side, {})
	if spec.is_empty():
		return null
	var doorway := DOORS.doorway(spec, String(door.get("leaf_port", "")))
	if doorway.is_empty():
		return null
	var materials: Dictionary = assembly.materials_for(spec)
	var result := LEAF.build(room, doorway, door, materials, _mesh_layer(room))
	if not bool(result.get("ok", false)):
		return null
	var leaf := result.node as Node3D
	leaves[threshold] = leaf
	return leaf


## Manual open from the player's current side.  Returns true on a real open.
func open_door(threshold: String, from_cell: String = "") -> bool:
	var door := DOORS.door_by_threshold(plan, threshold)
	if door.is_empty() or String(states.get(threshold, "open")) != "latched":
		return false
	var side := from_cell if not from_cell.is_empty() else current_cell
	if side != String(door.cell_a) and side != String(door.cell_b):
		return false
	var leaf := _ensure_leaf(door)
	if leaf == null:
		return false
	var event := DOORS.open_event(door, side, event_index + 1)
	_append_event(event)
	states[threshold] = "open"
	LEAF.set_state(leaf, "open", side == String(door.leaf_side))
	_publish_states()
	emit_signal("door_opened", threshold)
	return true


## Open the nearest latched door within reach on the player's current side.
func request_open_nearest() -> bool:
	if assembly == null or player == null or current_cell.is_empty():
		return false
	var best := ""
	var best_distance := INTERACT_RANGE_M
	for threshold: String in leaves.keys():
		if String(states.get(threshold, "open")) != "latched":
			continue
		var door := DOORS.door_by_threshold(plan, threshold)
		if door.is_empty():
			continue
		if current_cell != String(door.cell_a) and current_cell != String(door.cell_b):
			continue
		var leaf := leaves[threshold] as Node3D
		if leaf == null:
			continue
		var distance := player.global_position.distance_to(leaf.global_position)
		if distance <= best_distance:
			best = threshold
			best_distance = distance
	if best.is_empty():
		return false
	return open_door(best, current_cell)


## Capture/test hook: latch an eligible crossing without a physics frame.
func force_latch(threshold: String, from_cell: String, to_cell: String) -> bool:
	var door := DOORS.door_by_threshold(plan, threshold)
	if door.is_empty():
		return false
	var found := DOORS.crossing_for(plan, from_cell, to_cell)
	if found.is_empty() or not bool((found.crossing as Dictionary).eligible):
		return false
	current_cell = to_cell
	previous_cell = from_cell
	return not _latch(door, from_cell, to_cell).is_empty()


func restore_log(events: Array) -> String:
	door_events = []
	for event: Dictionary in events:
		door_events.append(event.duplicate(true))
	event_index = door_events.size()
	states = DOORS.fold_states(plan, door_events)
	for door: Dictionary in plan.get("doors", []):
		var threshold := String(door.threshold_id)
		var state := String(states.get(threshold, "open"))
		if state == "latched":
			var leaf := _ensure_leaf(door)
			if leaf != null:
				LEAF.set_state(leaf, "latched")
		elif leaves.has(threshold):
			LEAF.set_state(leaves[threshold] as Node3D, "open")
	_publish_states()
	return DOORS.state_hash(states)


func export_log() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for event: Dictionary in door_events:
		result.append(event.duplicate(true))
	return result


func state_of(threshold: String) -> String:
	return String(states.get(threshold, "open"))


func state_hash() -> String:
	return DOORS.state_hash(states)


func leaf_node(threshold: String) -> Node3D:
	return leaves.get(threshold, null) as Node3D


func snapshot() -> Dictionary:
	var doors: Array[Dictionary] = []
	for door: Dictionary in plan.get("doors", []):
		var threshold := String(door.threshold_id)
		doors.append({
			"threshold_id": threshold,
			"cell_a": String(door.cell_a),
			"cell_b": String(door.cell_b),
			"vertical": String(door.vertical),
			"kind": String(door.kind),
			"leaf": bool(door.leaf),
			"exit_threshold": bool(door.exit_threshold),
			"state": String(states.get(threshold, "open")),
			"has_leaf": leaves.has(threshold),
		})
	return {
		"plan": DOORS.projection(plan),
		"doors": doors,
		"states": states.duplicate(),
		"state_hash": DOORS.state_hash(states),
		"events": export_log(),
		"counters": DOORS.counters(door_events),
		"leaf_count": leaves.size(),
	}


func _publish_states() -> void:
	if assembly == null:
		return
	assembly.set_meta("maze_door_states", states.duplicate())
	assembly.set_meta("maze_door_leaf_count", leaves.size())


static func _mesh_layer(room: Node3D) -> int:
	for node in room.find_children("*", "MeshInstance3D", true, false):
		return (node as MeshInstance3D).layers
	return 1
