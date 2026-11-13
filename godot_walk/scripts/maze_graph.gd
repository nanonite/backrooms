class_name MazeGraph
extends RefCounted

## Runtime F0-F2 fairness check for the maze overlay (#236).
##
## The graph is the current traversal graph: level and ramp passages go both
## ways, a drop goes upper -> lower only. Doors in v1 are openable from either
## side, so a latched leaf never removes an edge. The passage state is the base
## map's direct passages plus every accepted ``door_reroll`` event, keyed by the
## same sorted cell pair the M5 enumerator uses.
##
## This is the GDScript runtime port of the reference checks in
## ``gmap_elevation.py`` (``directed_edges`` / ``strongly_connected``) and
## ``maze_rewire.py``. It reads no files and never edits a map.

const VOID_ROLE := "void"


static func walkable_ids(document: Dictionary) -> Array[String]:
	var result: Array[String] = []
	for cell: Dictionary in document.get("cells", []):
		if String(cell.get("role", "")) != VOID_ROLE:
			result.append(String(cell.get("cell_id", "")))
	result.sort()
	return result


static func pair_cells(key: String) -> Array:
	var parts := key.split("|")
	if parts.size() != 2:
		return []
	return [parts[0], parts[1]]


## Directed edges from the current passage state. A drop record carries its
## upper/lower cells; every other passage is bidirectional.
static func directed_edges(state: Dictionary) -> Array:
	var edges: Array = []
	var keys: Array = state.keys()
	keys.sort()
	for key: String in keys:
		var record: Dictionary = state[key]
		var pair := pair_cells(key)
		if pair.size() != 2:
			continue
		var left := String(pair[0])
		var right := String(pair[1])
		if String(record.get("vertical", "level")) == "drop":
			var upper := String(record.get("upper", left))
			var lower := String(record.get("lower", right))
			edges.append([upper, lower])
		else:
			edges.append([left, right])
			edges.append([right, left])
	return edges


static func adjacency(state: Dictionary) -> Dictionary:
	var graph := {}
	for key: String in state.keys():
		var pair := pair_cells(key)
		if pair.size() != 2:
			continue
		var left := String(pair[0])
		var right := String(pair[1])
		if not graph.has(left):
			graph[left] = [] as Array[String]
		if not graph.has(right):
			graph[right] = [] as Array[String]
		if String((state[key] as Dictionary).get("vertical", "level")) == "drop":
			var upper := String((state[key] as Dictionary).get("upper", left))
			var lower := String((state[key] as Dictionary).get("lower", right))
			_append_unique(graph, upper, lower)
			continue
		_append_unique(graph, left, right)
		_append_unique(graph, right, left)
	for cell_id: String in graph:
		(graph[cell_id] as Array[String]).sort()
	return graph


static func _append_unique(graph: Dictionary, from_cell: String, to_cell: String) -> void:
	if not graph.has(from_cell):
		graph[from_cell] = [] as Array[String]
	var neighbours: Array[String] = graph[from_cell]
	if not neighbours.has(to_cell):
		neighbours.append(to_cell)


static func reachable(state: Dictionary, start: String) -> Dictionary:
	var graph := adjacency(state)
	var seen := {}
	if start.is_empty() or not graph.has(start):
		return seen
	seen[start] = true
	var queue: Array[String] = [start]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		for neighbour: String in graph[current]:
			if seen.has(neighbour):
				continue
			seen[neighbour] = true
			queue.append(neighbour)
	return seen


static func strongly_connected(document: Dictionary, state: Dictionary) -> bool:
	var ids := walkable_ids(document)
	if ids.is_empty():
		return false
	var graph := adjacency(state)
	for cell_id: String in ids:
		if not graph.has(cell_id):
			return false
		var seen := {cell_id: true}
		var queue: Array[String] = [cell_id]
		var head := 0
		while head < queue.size():
			var current := queue[head]
			head += 1
			for neighbour: String in graph[current]:
				if seen.has(neighbour):
					continue
				seen[neighbour] = true
				queue.append(neighbour)
		if seen.size() != ids.size():
			return false
	return true


## F0: the whole walkable graph is strongly connected. F1: the exit is
## reachable from the player's cell. F2: every cell reachable from the player
## can still reach the exit. Returns the checks and the failing identifiers.
static func f0_f1_f2(document: Dictionary, state: Dictionary, player_cell: String,
		exit_cell: String) -> Dictionary:
	var failures: Array[String] = []
	var f0 := strongly_connected(document, state)
	if not f0:
		failures.append("F0")
	var from_player := reachable(state, player_cell)
	var f1 := not exit_cell.is_empty() and from_player.has(exit_cell)
	if not f1:
		failures.append("F1")
	var f2 := true
	for cell_id: String in from_player:
		var reached := reachable(state, cell_id)
		if not reached.has(exit_cell):
			f2 = false
			break
	if not f2:
		failures.append("F2")
	return {
		"F0": f0,
		"F1": f1,
		"F2": f2,
		"failures": failures,
		"reachable_from_player": from_player.keys(),
	}
