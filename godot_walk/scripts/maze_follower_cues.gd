class_name MazeFollowerCues
extends Node

## The M9 follower presence cue driver (#239).
##
## The follower is heard, never seen.  This driver listens to the follower's
## cell/edit signals and the M4 door signals, applies the §8 pacing rules and
## hands one cue plan at a time to ``MazeFollowerAudio``.  It records an inert
## ``follower_cue`` event for every played cue so the run log and the replay
## audit can show what was heard and why.
##
## Rules owned here:
## * no optional cue before the fifth distinct room;
## * one optional cue per edit, and only when the player is still;
## * an 8-15 second deterministic gap between optional cues;
## * ``door_close`` and ``lock_click`` are mandatory on an eligible door;
## * ``door_reopen`` is the same latch plus one low room-tone tail.

const AUDIO := preload("res://scripts/maze_follower_audio.gd")

const STREAM := "follower-cues:gmap-0.13.0"
const FOLLOWER_STEP := "follower_step"
const DOOR_CLOSE := "door_close"
const LOCK_CLICK := "lock_click"
const DOOR_REOPEN := "door_reopen"

const FIRST_CUE_VISIT := 5
const MIN_GAP_SECONDS := 8
const MAX_GAP_SECONDS := 15
const MIN_STEPS := 1
const MAX_STEPS := 3
const STEP_SPACING_S := 0.35
const LOCK_DELAY_S := 0.12
const REOPEN_TAIL_DELAY_S := 0.28
const QUIET_SPEED_MPS := 0.25
const QUIET_WAIT_SECONDS := 4.0

const REFERENCE_DISTANCE_M := 1.0
const STEP_BASE_VOLUME_DB := -12.0
const DOOR_BASE_VOLUME_DB := -8.0
const ROLLOFF_DB_PER_DOUBLING := 6.0
const STEP_MIN_VOLUME_DB := -45.0
const DOOR_MIN_VOLUME_DB := -35.0
const MAX_DISTANCE_M := 40.0
const SOURCE_HEIGHT_M := 1.0

const STEP_CHECKS := [
	"after_four_rooms", "graph_distance_one_to_two", "one_cue_per_edit",
	"volume_by_distance", "audio_only", "inert_cue",
]
const CLOSE_CHECKS := [
	"mandatory_door_contract", "door_close_before_latch",
	"volume_by_distance", "audio_only", "inert_cue",
]
const LATCH_CHECKS := [
	"mandatory_door_contract", "lock_click_after_close",
	"volume_by_distance", "audio_only", "inert_cue",
]
const REOPEN_CHECKS := [
	"mandatory_door_contract", "same_latch_as_lock_click", "room_tone_tail",
	"volume_by_distance", "audio_only", "inert_cue",
]

signal cue_played(event: Dictionary)

var enabled := true
var assembly: Node3D
var player: CharacterBody3D
var follower: Node
var door_runtime: Node
var audio: Node
var map: Dictionary = {}
var cells_by_id: Dictionary = {}
var seed_value := 0
var attempt := 0
var spawn_cell := ""
var exit_cell := ""
var current_cell := ""
var visit_count := 0
var clock_s := 0.0
var next_allowed_s := 0.0
var cue_index := 0
var cue_events: Array[Dictionary] = []
var pending_step: Dictionary = {}


func setup(assembly_node: Node3D, player_node: CharacterBody3D,
		follower_node: Node, door_node: Node) -> void:
	assembly = assembly_node
	player = player_node
	follower = follower_node
	door_runtime = door_node
	apply_map(assembly.map)
	exit_cell = String(assembly.get_meta("maze_exit_cell", ""))
	audio = AUDIO.new()
	audio.name = "FollowerAudio"
	add_child(audio)
	audio.ensure_bus()
	audio.ensure_pool()
	audio.set_process(false)
	if follower != null:
		follower.cell_entered.connect(_on_cell_entered)
		follower.edit_applied.connect(_on_edit_applied)
		current_cell = String(follower.current_cell)
		visit_count = (follower.visited as Array).size()
	if door_runtime != null:
		door_runtime.door_latched.connect(_on_door_latched)
		door_runtime.door_rerolled.connect(_on_door_rerolled)


func apply_map(runtime_map: Dictionary) -> void:
	map = runtime_map
	seed_value = int(map.get("seed", 0))
	attempt = int(map.get("attempt", 0))
	cells_by_id = {}
	for cell: Dictionary in map.get("cells", []):
		cells_by_id[String(cell.get("cell_id", ""))] = cell
	if not map.get("cells", []).is_empty():
		spawn_cell = String(map.cells[0].cell_id)


func _process(delta: float) -> void:
	if not enabled:
		return
	tick(delta)


## Advance the cue clock.  The audio layer is driven from this one clock so a
## headless check can advance time without waiting on a real frame.
func tick(delta: float) -> void:
	clock_s += maxf(0.0, delta)
	if audio != null:
		audio.tick(delta)
	_drain_pending_step()


func _on_cell_entered(cell_id: String, count: int, _is_new: bool) -> void:
	current_cell = cell_id
	visit_count = count


func _on_edit_applied(event: Dictionary) -> void:
	if not enabled:
		return
	request_step_cue(int(event.get("event_index", 0)))


## One optional presence cue for one edit.  Returns the logged event or an
## empty dictionary when the beat is silent.
func request_step_cue(event_index: int) -> Dictionary:
	if not enabled or visit_count < FIRST_CUE_VISIT:
		return {}
	if clock_s < next_allowed_s:
		return {}
	if not player_is_quiet():
		pending_step = {
			"event_index": event_index,
			"deadline_s": clock_s + QUIET_WAIT_SECONDS,
		}
		return {}
	return _play_step_cue(event_index)


func _drain_pending_step() -> void:
	if pending_step.is_empty():
		return
	if clock_s > float(pending_step.get("deadline_s", 0.0)):
		pending_step.clear()
		return
	if clock_s < next_allowed_s or not player_is_quiet():
		return
	var event_index := int(pending_step.get("event_index", 0))
	pending_step.clear()
	_play_step_cue(event_index)


func player_is_quiet() -> bool:
	if player == null:
		return true
	return Vector2(player.velocity.x, player.velocity.z).length() <= QUIET_SPEED_MPS


func _play_step_cue(event_index: int) -> Dictionary:
	var source := _select_step_source(event_index)
	if source.is_empty():
		return {}
	var position := cell_position(cells_by_id[source])
	var measured := player.global_position.distance_to(position)
	if measured > MAX_DISTANCE_M:
		return {}
	var hops := int(_graph_distances(current_cell, 2).get(source, 0))
	if hops not in [1, 2]:
		return {}
	var steps := MIN_STEPS + _mod_hex(_draw_hex(source, "step-count", event_index),
		MAX_STEPS - MIN_STEPS + 1)
	var volume_db := volume_at_distance(measured, STEP_BASE_VOLUME_DB,
		STEP_MIN_VOLUME_DB)
	var cooldown := _cooldown_seconds(event_index)
	audio.play_follower_step(position, volume_db, steps, STEP_SPACING_S)
	next_allowed_s = clock_s + float(cooldown)
	return _record_cue(FOLLOWER_STEP, {"cell_id": source}, event_index,
		position, hops, measured, volume_db, steps, 0.0, 0.0,
		AUDIO.STEP_TRANSIENT_SAMPLE, AUDIO.STEP_SAMPLE, cooldown, STEP_CHECKS)


func _on_door_latched(threshold: String) -> void:
	if not enabled:
		return
	var door := _door(threshold)
	if door.is_empty():
		return
	var position := _door_position(door)
	var measured := player.global_position.distance_to(position)
	var volume_db := volume_at_distance(measured, DOOR_BASE_VOLUME_DB,
		DOOR_MIN_VOLUME_DB)
	var source_index := cue_index + 1
	if door_runtime != null:
		source_index = int(door_runtime.event_index)
	var cooldown := _cooldown_seconds(source_index)
	audio.play_door_close(position, volume_db)
	_record_cue(DOOR_CLOSE, {"threshold_id": threshold}, source_index,
		position, 0, measured, volume_db, 0, 0.0, 0.0,
		AUDIO.DOOR_CLOSE_SAMPLE, "", cooldown, CLOSE_CHECKS)
	audio.play_lock_click(position, volume_db, LOCK_DELAY_S)
	_record_cue(LOCK_CLICK, {"threshold_id": threshold}, source_index,
		position, 0, measured, volume_db, 0, LOCK_DELAY_S, 0.0,
		AUDIO.LOCK_CLICK_SAMPLE, "", cooldown, LATCH_CHECKS)
	next_allowed_s = clock_s + float(cooldown)


func _on_door_rerolled(threshold: String) -> void:
	if not enabled:
		return
	var door := _door(threshold)
	if door.is_empty():
		return
	var position := _door_position(door)
	var measured := player.global_position.distance_to(position)
	var volume_db := volume_at_distance(measured, DOOR_BASE_VOLUME_DB,
		DOOR_MIN_VOLUME_DB)
	var source_index := cue_index + 1
	if door_runtime != null:
		source_index = int(door_runtime.event_index)
	var cooldown := _cooldown_seconds(source_index)
	audio.play_door_reopen(position, volume_db, REOPEN_TAIL_DELAY_S)
	_record_cue(DOOR_REOPEN, {"threshold_id": threshold}, source_index,
		position, 0, measured, volume_db, 0, 0.0, REOPEN_TAIL_DELAY_S,
		AUDIO.LOCK_CLICK_SAMPLE, AUDIO.ROOM_TONE_SAMPLE, cooldown,
		REOPEN_CHECKS)
	next_allowed_s = clock_s + float(cooldown)


func _record_cue(kind: String, target: Dictionary, source_event_index: int,
		position: Vector3, graph_distance: int, measured: float, volume_db: float,
		steps: int, delay_s: float, tail_delay_s: float, latch_sample: String,
		tail_sample: String, cooldown: int, checks: Array) -> Dictionary:
	cue_index += 1
	var event := {
		"event_index": cue_index,
		"event_type": "follower_cue",
		"record_kind": "mutation",
		"source_event_index": source_event_index,
		"target": target.duplicate(true),
		"stream": STREAM,
		"cue": {
			"kind": kind,
			"target": target.duplicate(true),
			"position": [position.x, position.y, position.z],
			"graph_distance": graph_distance,
			"distance_m": measured,
			"volume_db": volume_db,
			"steps": steps,
			"step_spacing_s": STEP_SPACING_S if kind == FOLLOWER_STEP else 0.0,
			"delay_s": delay_s,
			"tail_delay_s": tail_delay_s,
			"latch_sample": latch_sample,
			"tail_sample": tail_sample,
			"cooldown_s": cooldown,
			"visible_nodes": audio.visible_node_count() if audio != null else 0,
			"player_cell": current_cell,
		},
		"validation": {"outcome": "accepted", "checks": checks},
	}
	cue_events.append(event)
	cue_played.emit(event)
	return event


func _select_step_source(event_index: int) -> String:
	var distances := _graph_distances(current_cell, 2)
	var candidates: Array[String] = []
	var distant: Array[String] = []
	for cell_id: String in distances:
		var hops := int(distances[cell_id])
		if hops not in [1, 2] or cell_id == current_cell or cell_id == exit_cell:
			continue
		if not cells_by_id.has(cell_id) or not assembly.has_room(cell_id):
			continue
		if String((cells_by_id[cell_id] as Dictionary).get("role", "")) == "void":
			continue
		candidates.append(cell_id)
		if hops == 2:
			distant.append(cell_id)
	var pool := distant if not distant.is_empty() else candidates
	if pool.is_empty():
		return ""
	var best := ""
	var best_rank := ""
	for cell_id: String in pool:
		var rank := _draw_hex(cell_id, "step-source", event_index)
		if best.is_empty() or rank < best_rank:
			best = cell_id
			best_rank = rank
	return best


func _graph_distances(start: String, max_depth: int) -> Dictionary:
	var adjacency := {}
	for cell: Dictionary in map.get("cells", []):
		if String(cell.get("role", "")) != "void":
			adjacency[String(cell.cell_id)] = []
	for edge: Dictionary in map.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var left := String(edge.get("from", "")).get_slice(":", 0)
		var right := String(edge.get("to", "")).get_slice(":", 0)
		if left == right or not adjacency.has(left) or not adjacency.has(right):
			continue
		(adjacency[left] as Array).append(right)
		(adjacency[right] as Array).append(left)
	if not adjacency.has(start):
		return {}
	var distances := {start: 0}
	var frontier: Array[String] = [start]
	for depth in range(1, max_depth + 1):
		var next_frontier: Array[String] = []
		for current: String in frontier:
			var neighbors: Array = adjacency[current]
			neighbors.sort()
			for neighbor: String in neighbors:
				if distances.has(neighbor):
					continue
				distances[neighbor] = depth
				next_frontier.append(neighbor)
		frontier = next_frontier
		if frontier.is_empty():
			break
	return distances


func cell_position(cell: Dictionary) -> Vector3:
	var points: Array = cell.get("envelope_xz", [])
	var total := Vector2.ZERO
	for point: Array in points:
		total += Vector2(float(point[0]), float(point[1]))
	var center := total / float(maxi(points.size(), 1))
	return Vector3(center.x, float(cell.get("floor_y", 0.0)) + SOURCE_HEIGHT_M,
		center.y)


func _port_position(port_id: String) -> Vector3:
	var cell_id := port_id.get_slice(":", 0)
	if not cells_by_id.has(cell_id):
		return Vector3.ZERO
	var cell: Dictionary = cells_by_id[cell_id]
	for port: Dictionary in cell.get("required_ports", []):
		if String(port.get("port_id", "")) != port_id:
			continue
		var pos: Array = port.get("pos_xz", [])
		if pos.size() >= 2:
			return Vector3(float(pos[0]),
				float(cell.get("floor_y", 0.0)) + SOURCE_HEIGHT_M, float(pos[1]))
	return cell_position(cell)


func _door_position(door: Dictionary) -> Vector3:
	var threshold := String(door.get("threshold_id", ""))
	if door_runtime != null and not threshold.is_empty():
		var leaf: Node3D = door_runtime.leaf_node(threshold)
		if leaf != null:
			return leaf.global_position
	var first := _port_position(String(door.get("port_a", "")))
	var second := _port_position(String(door.get("port_b", "")))
	if first.is_zero_approx() and second.is_zero_approx():
		return player.global_position
	if first.is_zero_approx():
		return second
	if second.is_zero_approx():
		return first
	return (first + second) * 0.5


func _door(threshold: String) -> Dictionary:
	if door_runtime == null:
		return {}
	for door: Dictionary in (door_runtime.plan as Dictionary).get("doors", []):
		if String(door.get("threshold_id", "")) == threshold:
			return door
	return {}


func _cooldown_seconds(event_index: int) -> int:
	var value := _mod_hex(_draw_hex("cue", "cooldown", event_index),
		MAX_GAP_SECONDS - MIN_GAP_SECONDS + 1)
	return MIN_GAP_SECONDS + value


func _draw_hex(target: String, purpose: String, event_index: int) -> String:
	var key := "%d:%d:%d:%s:%s:%s" % [
		seed_value, attempt, event_index, STREAM, target, purpose,
	]
	return key.sha256_text()


static func _mod_hex(hex: String, modulus: int) -> int:
	if modulus <= 0:
		return 0
	var remainder := 0
	for offset in range(0, hex.length(), 2):
		remainder = (remainder * 256 + hex.substr(offset, 2).hex_to_int()) % modulus
	return remainder


static func volume_at_distance(distance: float, base_db: float,
		minimum_db: float) -> float:
	var effective := maxf(distance, REFERENCE_DISTANCE_M)
	var value := base_db - ROLLOFF_DB_PER_DOUBLING * (
		log(effective / REFERENCE_DISTANCE_M) / log(2.0))
	return maxf(value, minimum_db)


func disable() -> void:
	enabled = false
	pending_step.clear()
	if audio != null:
		audio.stop_all()


func snapshot() -> Dictionary:
	var kinds := {}
	for event: Dictionary in cue_events:
		var kind := String((event.get("cue", {}) as Dictionary).get("kind", ""))
		kinds[kind] = int(kinds.get(kind, 0)) + 1
	return {
		"enabled": enabled,
		"visit_count": visit_count,
		"cue_count": cue_events.size(),
		"kind_counts": kinds,
		"current_cell": current_cell,
		"clock_s": clock_s,
		"next_allowed_s": next_allowed_s,
		"visible_nodes": audio.visible_node_count() if audio != null else 0,
		"audio": audio.snapshot() if audio != null else {},
		"events": cue_events.duplicate(true),
	}


func export_events() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for event: Dictionary in cue_events:
		result.append(event.duplicate(true))
	return result
