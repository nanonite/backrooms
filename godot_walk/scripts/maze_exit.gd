class_name MazeExit
extends RefCounted

## Runtime static-exit selection for the M3 overlay slice (#233).
##
## This is the GDScript twin of ``maze_exit.py``. It mirrors the same
## level/ramp passage graph, the same 3-8 re-roll targets, the same placement
## tiers and the same per-cell keyed draw
## ``sha256("<seed>:<attempt>:exit:gmap-0.13.0:<cell_id>")``. The committed maps
## carry no exit layer, so both implementations derive the choice from the seed;
## a map regenerated with an ``exit`` layer keeps its recorded cell.
##
## The selection is made before ``reroll_eligibility``: the pre-exit target map
## is the only input, so the exit never hides the direction it removes.

const LAYER_VERSION := "exit:gmap-0.13.0"
const LAYER_FIELD := "exit"
const DRAW_PURPOSE := "exit-cell"
const MIN_REROLL_CELLS := 3
const MAX_REROLL_CELLS := 8
const SCHEMA_VERSION := 1
const GENERATED_ROLES := ["ground", "figure"]


static func walkable_ids(document: Dictionary) -> Array[String]:
	var result: Array[String] = []
	for cell: Dictionary in document.get("cells", []):
		if String(cell.get("role", "")) != "void":
			result.append(String(cell.cell_id))
	return result


static func passage_pairs(document: Dictionary) -> Array:
	var walkable := {}
	for cell_id: String in walkable_ids(document):
		walkable[cell_id] = true
	var seen := {}
	var pairs: Array = []
	for edge: Dictionary in document.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		if String(edge.get("vertical", "")) == "drop":
			continue
		var left := String(edge.get("from", "")).get_slice(":", 0)
		var right := String(edge.get("to", "")).get_slice(":", 0)
		if left == right or not walkable.has(left) or not walkable.has(right):
			continue
		var key := left + "|" + right if left < right else right + "|" + left
		if seen.has(key):
			continue
		seen[key] = true
		pairs.append([left, right] if left < right else [right, left])
	pairs.sort_custom(func(first: Array, second: Array) -> bool:
		if first[0] != second[0]:
			return first[0] < second[0]
		return first[1] < second[1])
	return pairs


static func adjacency(document: Dictionary) -> Dictionary:
	var graph := {}
	for cell_id: String in walkable_ids(document):
		graph[cell_id] = [] as Array[String]
	for pair: Array in passage_pairs(document):
		var left := String(pair[0])
		var right := String(pair[1])
		if not graph.has(left) or not graph.has(right):
			continue
		(graph[left] as Array[String]).append(right)
		(graph[right] as Array[String]).append(left)
	for cell_id: String in graph:
		var neighbours: Array[String] = graph[cell_id]
		neighbours.sort()
	return graph


static func threshold_id(left: String, right: String) -> String:
	return left + "|" + right if left < right else right + "|" + left


## The component of ``start`` after removing the direct edge start-blocked.
## Returns ``null`` when the edge is not a bridge, or the sorted cell list.
static func component_without(graph: Dictionary, start: String, blocked: String) -> Variant:
	if not graph.has(start):
		return null
	var seen := {start: true}
	var order: Array[String] = [start]
	var queue: Array[String] = [start]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		for neighbour: String in graph[current]:
			if current == start and neighbour == blocked:
				continue
			if seen.has(neighbour):
				continue
			seen[neighbour] = true
			order.append(neighbour)
			queue.append(neighbour)
	if seen.has(blocked):
		return null
	order.sort()
	return order


static func reroll_targets(document: Dictionary) -> Array[Dictionary]:
	var graph := adjacency(document)
	var targets: Array[Dictionary] = []
	for pair: Array in passage_pairs(document):
		var left := String(pair[0])
		var right := String(pair[1])
		for direction: Array in [[left, right], [right, left]]:
			var from_cell := String(direction[0])
			var to_cell := String(direction[1])
			var component: Variant = component_without(graph, to_cell, from_cell)
			if component == null:
				continue
			var target_cells: Array[String] = component
			var size := target_cells.size()
			if size < MIN_REROLL_CELLS or size > MAX_REROLL_CELLS:
				continue
			targets.append({
				"passage": [left, right],
				"threshold_id": threshold_id(left, right),
				"from_cell": from_cell,
				"to_cell": to_cell,
				"target_cells": target_cells,
				"target_size": size,
			})
	targets.sort_custom(func(first: Dictionary, second: Dictionary) -> bool:
		if first.from_cell != second.from_cell:
			return first.from_cell < second.from_cell
		return first.to_cell < second.to_cell)
	return targets


static func is_generated_cell(cell: Dictionary) -> bool:
	if cell.get("module") != null:
		return false
	if cell.get("landmark") != null:
		return false
	if cell.get("diagonal_passage") != null:
		return false
	return GENERATED_ROLES.has(String(cell.get("role", "")))


static func exit_port(document: Dictionary, cell_id: String) -> Dictionary:
	var walkable := {}
	for walkable_id: String in walkable_ids(document):
		walkable[walkable_id] = true
	if not walkable.has(cell_id):
		return {}
	var candidates: Array[Dictionary] = []
	for edge: Dictionary in document.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var left := String(edge.get("from", "")).get_slice(":", 0)
		var right := String(edge.get("to", "")).get_slice(":", 0)
		var port_id := ""
		var to_port_id := ""
		var other := ""
		if left == cell_id and walkable.has(right):
			port_id = String(edge.get("from", ""))
			to_port_id = String(edge.get("to", ""))
			other = right
		elif right == cell_id and walkable.has(left):
			port_id = String(edge.get("to", ""))
			to_port_id = String(edge.get("from", ""))
			other = left
		else:
			continue
		candidates.append({
			"port_id": port_id,
			"to_port_id": to_port_id,
			"from_cell": other,
			"threshold_id": threshold_id(cell_id, other),
			"vertical": String(edge.get("vertical", "level")),
			"connector": String(edge.get("connector", "direct")),
		})
	if candidates.is_empty():
		return {}
	candidates.sort_custom(func(first: Dictionary, second: Dictionary) -> bool:
		var first_drop := String(first.vertical) == "drop"
		var second_drop := String(second.vertical) == "drop"
		if first_drop != second_drop:
			return not first_drop
		var first_closed := String(first.connector) == "closed_visible"
		var second_closed := String(second.connector) == "closed_visible"
		if first_closed != second_closed:
			return not first_closed
		return String(first.port_id) < String(second.port_id))
	return candidates[0]


static func keyed_rank(seed: int, attempt: int, cell_id: String) -> String:
	return ("%d:%d:%s:%s" % [seed, attempt, LAYER_VERSION, cell_id]).sha256_text()


static func _target_hits(targets: Array[Dictionary], cell_id: String) -> Array[Dictionary]:
	var hits: Array[Dictionary] = []
	for target: Dictionary in targets:
		if (target.target_cells as Array).has(cell_id):
			hits.append({
				"from_cell": target.from_cell,
				"to_cell": target.to_cell,
				"target_size": target.target_size,
			})
	return hits


static func _seed_record(document: Dictionary, cell_id: String,
		targets: Array[Dictionary], graph: Dictionary) -> Dictionary:
	var port := exit_port(document, cell_id)
	if port.is_empty():
		return {}
	var hits := _target_hits(targets, cell_id)
	var removed := 0
	for hit: Dictionary in hits:
		removed += int(hit.target_size)
	var seed_value := int(document.get("seed", 0))
	var attempt := int(document.get("attempt", 0))
	return {
		"schema_version": SCHEMA_VERSION,
		"layer_version": LAYER_VERSION,
		"source": "seed",
		"cell_id": cell_id,
		"port_id": String(port.port_id),
		"to_port_id": String(port.to_port_id),
		"from_cell": String(port.from_cell),
		"threshold_id": String(port.threshold_id),
		"vertical": String(port.vertical),
		"leaf": (graph.get(cell_id, []) as Array).size() == 1,
		"outside_targets": hits.is_empty(),
		"targets_hit": hits,
		"removed_cells": removed,
		"draw": {
			"stream": LAYER_VERSION,
			"purpose": DRAW_PURPOSE,
			"rank": keyed_rank(seed_value, attempt, cell_id),
		},
	}


static func recorded_exit(document: Dictionary) -> Dictionary:
	var layer: Variant = document.get(LAYER_FIELD, null)
	if not layer is Dictionary:
		return {}
	if String((layer as Dictionary).get("layer_version", "")) != LAYER_VERSION:
		return {}
	var cell_id := String((layer as Dictionary).get("cell_id", ""))
	if cell_id.is_empty() or not walkable_ids(document).has(cell_id):
		return {}
	var record := _seed_record(document, cell_id, reroll_targets(document), adjacency(document))
	if record.is_empty():
		return {}
	var recorded_port := String((layer as Dictionary).get("port_id", ""))
	if not recorded_port.is_empty():
		record["port_id"] = recorded_port
	var recorded_threshold := String((layer as Dictionary).get("threshold_id", ""))
	if not recorded_threshold.is_empty():
		record["threshold_id"] = recorded_threshold
	record["source"] = "layer"
	return record


static func select_exit(document: Dictionary) -> Dictionary:
	var recorded := recorded_exit(document)
	if not recorded.is_empty():
		return recorded
	var targets := reroll_targets(document)
	var graph := adjacency(document)
	var cells := {}
	for cell: Dictionary in document.get("cells", []):
		cells[String(cell.cell_id)] = cell
	if cells.is_empty():
		return {}
	var spawn := String((document["cells"] as Array)[0].cell_id)
	var seed_value := int(document.get("seed", 0))
	var attempt := int(document.get("attempt", 0))
	var candidates: Array[String] = []
	for cell_id: String in walkable_ids(document):
		if cell_id == spawn or not cells.has(cell_id) or not graph.has(cell_id):
			continue
		var cell: Dictionary = cells[cell_id]
		if cell.get("landmark") != null:
			continue
		candidates.append(cell_id)
	if candidates.is_empty():
		return {}
	var rank_keys := {}
	for cell_id: String in candidates:
		rank_keys[cell_id] = _rank_key(document, targets, graph, cells, seed_value, attempt, cell_id)
	candidates.sort_custom(func(first: String, second: String) -> bool:
		return _rank_key_less(rank_keys[first], rank_keys[second]))
	var chosen := candidates[0]
	return _seed_record(document, chosen, targets, graph)


static func _rank_key_less(first: Array, second: Array) -> bool:
	for index in mini(first.size(), second.size()):
		if first[index] == second[index]:
			continue
		return first[index] < second[index]
	return first.size() < second.size()


static func _rank_key(document: Dictionary, targets: Array[Dictionary], graph: Dictionary,
		cells: Dictionary, seed_value: int, attempt: int, cell_id: String) -> Array:
	var cell: Dictionary = cells[cell_id]
	var hits := _target_hits(targets, cell_id)
	var leaf := 0 if (graph.get(cell_id, []) as Array).size() == 1 \
		and not exit_port(document, cell_id).is_empty() else 1
	var generated := 0 if is_generated_cell(cell) else 1
	var removed := 0
	for hit: Dictionary in hits:
		removed += int(hit.target_size)
	return [hits.size(), leaf, removed, generated, keyed_rank(seed_value, attempt, cell_id), cell_id]


static func reroll_eligibility(document: Dictionary, exit_record: Dictionary) -> Array[Dictionary]:
	var exit_cell := String(exit_record.get("cell_id", ""))
	var exit_threshold := String(exit_record.get("threshold_id", ""))
	if exit_threshold.is_empty() and not exit_cell.is_empty():
		exit_threshold = String(exit_port(document, exit_cell).get("threshold_id", ""))
	var result: Array[Dictionary] = []
	for target: Dictionary in reroll_targets(document):
		var reasons: Array[String] = []
		if not exit_threshold.is_empty() and String(target.threshold_id) == exit_threshold:
			reasons.append("exit_threshold_door")
		if not exit_cell.is_empty() and (target.target_cells as Array).has(exit_cell):
			reasons.append("exit_inside")
		var record := target.duplicate(true)
		record["eligible"] = reasons.is_empty()
		record["reasons"] = reasons
		record["reason"] = "" if reasons.is_empty() else reasons[0]
		result.append(record)
	return result


static func plan_run(document: Dictionary) -> Dictionary:
	var exit_record := select_exit(document)
	var eligibility := reroll_eligibility(document, exit_record)
	var eligible: Array[Dictionary] = []
	var rejected: Array[Dictionary] = []
	for item: Dictionary in eligibility:
		if bool(item.eligible):
			eligible.append(item)
		else:
			rejected.append(item)
	return {
		"seed": int(document.get("seed", 0)),
		"map_id": String(document.get("map_id", "")),
		"exit": exit_record,
		"eligibility": eligibility,
		"eligible_directions": eligible,
		"rejected_directions": rejected,
	}
