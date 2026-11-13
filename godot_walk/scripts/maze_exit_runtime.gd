class_name MazeExitRuntime
extends Node

## Live M3 exit driver (#233).
##
## One static exit is selected by the assembly before this node exists. The
## driver follows the player's cell, records the run log in memory and ends the
## run exactly once when the player crosses the threshold. The end card is
## built from the log; no next seed, next level or restart action exists.
##
## Like the M2 follower driver it does nothing while the player's physics
## processing is off, so the existing capture harnesses stay deterministic.

const EXIT_LOGIC := preload("res://scripts/maze_exit.gd")
const END_CARD := preload("res://scripts/maze_end_card.gd")
const RUN_STREAM := "run:gmap-0.13.0"
const VISIT_TRIGGER_KINDS := ["room_entered", "exit_entered", "save_restore"]

signal run_ended(card: Dictionary)

var enabled := true
var assembly: Node3D
var player: CharacterBody3D
var exit_record: Dictionary = {}
var exit_cell := ""
var current_cell := ""
var previous_cell := ""
var ended := false
var counters: Dictionary = {}
var run_log: Array[Dictionary] = []
var end_card: Node
var follower_runtime: Node
var door_runtime: Node
var _synced_edits := 0
var _synced_doors := 0


func setup(assembly_node: Node3D, player_node: CharacterBody3D) -> void:
	assembly = assembly_node
	player = player_node
	exit_record = assembly.get_meta("maze_exit", {})
	exit_cell = String(exit_record.get("cell_id", ""))
	end_card = END_CARD.new()
	end_card.name = "MazeEndCard"
	add_child(end_card)
	follower_runtime = assembly.get_meta("maze_follower_runtime", null)
	if assembly.has_meta("maze_door_runtime"):
		door_runtime = assembly.get_meta("maze_door_runtime")

func _physics_process(_delta: float) -> void:
	if not enabled or ended or assembly == null or player == null:
		return
	if not player.is_physics_processing():
		return
	var cell: String = assembly.cell_at(player.global_position)
	if cell.is_empty() or cell == current_cell:
		return
	_enter_cell(cell)


func _enter_cell(cell_id: String) -> void:
	previous_cell = current_cell
	current_cell = cell_id
	if not exit_cell.is_empty() and cell_id == exit_cell:
		end_run(previous_cell)
		return
	_append_trigger("room_entered", cell_id, "")


func _append_trigger(kind: String, player_cell: String, from_cell: String) -> Dictionary:
	var record := {
		"record_kind": "trigger",
		"event_type": kind,
		"event_index": run_log.size() + 1,
		"player_cell": player_cell,
	}
	if not from_cell.is_empty():
		record["from_cell"] = from_cell
	run_log.append(record)
	return record


## Stop the run once. A second call (or a second entry) changes nothing.
func end_run(from_cell: String = "") -> Dictionary:
	if ended:
		return card()
	if exit_cell.is_empty():
		return {}
	var crossed_from := from_cell
	if crossed_from.is_empty():
		crossed_from = previous_cell
	_append_trigger("exit_entered", exit_cell, crossed_from)
	_sync_edits()
	_sync_doors()
	run_log.append({
		"record_kind": "mutation",
		"event_type": "run_end",
		"event_index": run_log.size() + 1,
		"target": {"cell_id": exit_cell, "threshold_id": String(exit_record.get("threshold_id", ""))},
		"stream": RUN_STREAM,
	})
	ended = true
	if follower_runtime != null and follower_runtime.get("enabled") != null:
		follower_runtime.set("enabled", false)
	if door_runtime == null and assembly != null and assembly.has_meta("maze_door_runtime"):
		door_runtime = assembly.get_meta("maze_door_runtime")
	if door_runtime != null and door_runtime.get("enabled") != null:
		door_runtime.set("enabled", false)
	counters = _counters()
	var card_value := card()
	if end_card != null:
		end_card.show_card(card_value)
	emit_signal("run_ended", card_value)
	return card_value


func card() -> Dictionary:
	counters = _counters()
	return {
		"schema_version": 1,
		"title": "RUN ENDED",
		"seed": int(counters.get("seed", 0)),
		"map_id": String(counters.get("map_id", "")),
		"rooms_visited": int(counters.get("rooms_visited", 0)),
		"edits": int(counters.get("edits", 0)),
		"rerolls": int(counters.get("rerolls", 0)),
		"run_ended": bool(counters.get("run_ended", false)),
		"ended_at_event": int(counters.get("ended_at_event", 0)),
		"actions": [],
	}


## Capture/test hook: end the run without waiting for a physics crossing.
func force_end(from_cell: String = "") -> Dictionary:
	return end_run(from_cell)


func _sync_edits() -> void:
	if follower_runtime == null:
		return
	var edits: Array = follower_runtime.edit_events
	while _synced_edits < edits.size():
		var source: Dictionary = edits[_synced_edits]
		var record: Dictionary = source.duplicate(true)
		record["record_kind"] = "mutation"
		record["event_type"] = "follower_edit"
		record["follower_event_index"] = int(source.get("event_index", 0))
		record["event_index"] = run_log.size() + 1
		run_log.append(record)
		_synced_edits += 1


func _sync_doors() -> void:
	if door_runtime == null and assembly != null and assembly.has_meta("maze_door_runtime"):
		door_runtime = assembly.get_meta("maze_door_runtime")
	if door_runtime == null:
		return
	var events: Array = door_runtime.door_events
	while _synced_doors < events.size():
		var source: Dictionary = events[_synced_doors]
		var record: Dictionary = source.duplicate(true)
		record["record_kind"] = "mutation"
		record["door_event_index"] = int(source.get("event_index", 0))
		record["event_index"] = run_log.size() + 1
		run_log.append(record)
		_synced_doors += 1


func _counters() -> Dictionary:
	var visited: Array[String] = []
	var edits := 0
	var rerolls := 0
	var ended_at := 0
	for record: Dictionary in run_log:
		var kind := String(record.get("event_type", ""))
		if String(record.get("record_kind", "")) == "trigger":
			if VISIT_TRIGGER_KINDS.has(kind):
				var cell := String(record.get("player_cell", record.get("from_cell", "")))
				if not cell.is_empty() and not visited.has(cell):
					visited.append(cell)
			continue
		if kind == "follower_edit":
			edits += 1
		elif kind == "door_reroll":
			var validation: Variant = record.get("validation")
			if validation is Dictionary and String((validation as Dictionary).get(
					"outcome", "")) == "rejected":
				continue
			rerolls += 1
		elif kind == "run_end" and ended_at == 0:
			ended_at = int(record.get("event_index", 0))
	return {
		"seed": int(assembly.map.get("seed", 0)) if assembly != null else 0,
		"map_id": String(assembly.map.get("map_id", "")) if assembly != null else "",
		"records": run_log.size(),
		"rooms_visited": visited.size(),
		"edits": edits,
		"rerolls": rerolls,
		"run_ended": ended_at > 0,
		"ended_at_event": ended_at,
	}
