class_name MazeVisibility
extends RefCounted

## Bounded graph visibility for the maze mutation gate (#232, proposal §5.3/§9.6).
##
## The camera check is a later backstop. This proxy walks through open and
## ``closed_visible`` openings up to a small depth and never enters a void cell.
## It is deliberately simple so the Python reference and the runtime measure the
## same thing.

const DEFAULT_DEPTH := 2
const VISIBLE_CONNECTORS := ["direct", "closed_visible"]
const VISIBLE_DOOR_STATES := ["open", "closed_visible"]
const VOID_ROLE := "void"


static func visible_cells(map: Dictionary, player_cell: String, depth: int = DEFAULT_DEPTH,
		door_states: Dictionary = {}) -> PackedStringArray:
	var result := PackedStringArray()
	if player_cell.is_empty() or depth < 0:
		return result
	var cells := _cells_by_id(map)
	if not cells.has(player_cell) or _role(cells[player_cell]) == VOID_ROLE:
		return result
	var graph := _visible_graph(map, cells, door_states)
	var seen := {player_cell: true}
	result.append(player_cell)
	var frontier: Array[String] = [player_cell]
	for _step in depth:
		var following: Array[String] = []
		for current: String in frontier:
			var neighbors: Array = graph.get(current, [])
			for neighbor: String in neighbors:
				if seen.has(neighbor):
					continue
				seen[neighbor] = true
				result.append(neighbor)
				following.append(neighbor)
		frontier = following
		if frontier.is_empty():
			break
	result.sort()
	return result


static func cell_is_hidden(map: Dictionary, player_cell: String, target_cell: String,
		depth: int = DEFAULT_DEPTH, door_states: Dictionary = {}) -> bool:
	if target_cell.is_empty() or target_cell == player_cell:
		return false
	return not visible_cells(map, player_cell, depth, door_states).has(target_cell)


static func _cells_by_id(map: Dictionary) -> Dictionary:
	var result := {}
	for cell: Dictionary in map.get("cells", []):
		var cell_id := String(cell.get("cell_id", ""))
		if not cell_id.is_empty():
			result[cell_id] = cell
	return result


static func _visible_graph(map: Dictionary, cells: Dictionary, door_states: Dictionary) -> Dictionary:
	var graph := {}
	for cell_id: String in cells:
		if _role(cells[cell_id]) != VOID_ROLE:
			graph[cell_id] = []
	for edge: Dictionary in map.get("edges", []):
		var connector := String(edge.get("connector", ""))
		if not VISIBLE_CONNECTORS.has(connector):
			continue
		var from_port := String(edge.get("from", ""))
		var to_port := String(edge.get("to", ""))
		var left := from_port.get_slice(":", 0)
		var right := to_port.get_slice(":", 0)
		if left == right or not graph.has(left) or not graph.has(right):
			continue
		if not _door_visible(cells[left], from_port, door_states):
			continue
		if not _door_visible(cells[right], to_port, door_states):
			continue
		(graph[left] as Array).append(right)
		(graph[right] as Array).append(left)
	for cell_id: String in graph:
		(graph[cell_id] as Array).sort()
	return graph


static func _door_visible(cell: Dictionary, port_id: String, door_states: Dictionary) -> bool:
	var state := ""
	if door_states.has(port_id):
		state = String(door_states[port_id])
	else:
		state = "open"
		for door: Dictionary in cell.get("doors", []):
			if String(door.get("port_id", "")) == port_id:
				state = String(door.get("state", "open"))
				break
	return VISIBLE_DOOR_STATES.has(state)


static func _role(cell: Dictionary) -> String:
	return String(cell.get("role", "ground"))
