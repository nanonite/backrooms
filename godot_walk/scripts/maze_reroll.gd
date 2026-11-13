class_name MazeReroll
extends RefCounted

## Headless ``rewire-1`` passage-graph enumerator for the M5 overlay slice (#235).
##
## This is the GDScript twin of ``maze_reroll.py``.  It reads the committed map,
## freezes a 3-8 cell departed component, builds ``H_T`` and the mandatory pins,
## enumerates every passage graph on the same footprint, applies R0-R11, ranks
## the survivors by shape consistency and draws from the shortlist.
##
## The slice creates no runtime geometry.  ``projection`` is the cross-language
## contract exercised by ``test_issue235_reroll.gd`` and the Python suite.

const EXIT := preload("res://scripts/maze_exit.gd")

const ALGORITHM_VERSION := "rewire-1"
const EVENT_STREAM := "door-reroll:gmap-0.13.0"
const DOORWAY_STREAM := "doorway:rewire-1"

const DOOR_WIDTH_M := 1.4
const DOOR_HEIGHT_M := 2.2
const DOORWAY_MARGIN_M := 0.2
const MIN_REROLL_CELLS := 3
const MAX_REROLL_CELLS := 8
const MAX_DEGREE := 4
const MIN_SHARED_WALL_M := 1.8
const MIN_RETAINED := 0.5
const CANDIDATE_SHORTLIST := 8
const MIN_REROLL_ALTERNATIVES := 2
const MAX_REROLLS_PER_RUN := 3
const MAX_REROLLS_PER_DOOR := 1
const MAX_H_UNIVERSE := 16

const TIERS := {
	1: [1, 2],
	2: [2, 4],
	3: [3, 6],
}
const SHAPE_TOLERANCES := {
	1: {"leaves": 1, "loops": 1, "max_depth": 1, "mean_depth": 0.75,
		"degree_histogram": 2, "door_count": 2},
	2: {"leaves": 1, "loops": 1, "max_depth": 2, "mean_depth": 1.0,
		"degree_histogram": 3, "door_count": 3},
	3: {"leaves": 2, "loops": 2, "max_depth": 3, "mean_depth": 1.5,
		"degree_histogram": 4, "door_count": 4},
}
const SHAPE_WEIGHTS := {
	"leaves": 2,
	"loops": 3,
	"max_depth": 1,
	"mean_depth": 2,
	"degree_histogram": 2,
	"door_count": 1,
	"retained": 2,
}
const HARD_CHECKS := [
	"R0_same_footprint",
	"R1_connected",
	"R2_strongly_connected",
	"R3_degree_limit",
	"R4_pins",
	"R5_retained_fraction",
	"R6_edit_bounds",
	"R7_no_content_change",
	"R8_geometry",
	"R9_visibility",
	"R10_exit_reachable",
	"R11_change_is_real",
]


static func cells_by_id(document: Dictionary) -> Dictionary:
	var result := {}
	for cell: Dictionary in document.get("cells", []):
		var cell_id := String(cell.get("cell_id", ""))
		if not cell_id.is_empty():
			result[cell_id] = cell
	return result


static func spawn_cell_id(document: Dictionary) -> String:
	var cells: Array = document.get("cells", [])
	return String((cells[0] as Dictionary).get("cell_id", "")) if not cells.is_empty() else ""


static func cell_of(port_id: String) -> String:
	return port_id.get_slice(":", 0)


static func pair_key(first: String, second: String) -> String:
	return "%s|%s" % [first, second] if first < second else "%s|%s" % [second, first]


static func pair_cells(key: String) -> Array:
	var parts := key.split("|")
	return [String(parts[0]), String(parts[1])]


static func base_passage_state(document: Dictionary) -> Dictionary:
	var cells := cells_by_id(document)
	var state := {}
	for edge: Dictionary in document.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var left := cell_of(String(edge.get("from", "")))
		var right := cell_of(String(edge.get("to", "")))
		if left == right or not cells.has(left) or not cells.has(right):
			continue
		if String((cells[left] as Dictionary).get("role", "")) == "void":
			continue
		if String((cells[right] as Dictionary).get("role", "")) == "void":
			continue
		var record := {"vertical": String(edge.get("vertical", "level"))}
		if String(record.vertical) == "drop":
			var drop: Dictionary = edge.get("drop", {}) if edge.get("drop") is Dictionary else {}
			record["upper"] = String(drop.get("upper_cell_id", left))
			record["lower"] = String(drop.get("lower_cell_id", right))
		state[pair_key(left, right)] = record
	return state


static func target_component(state: Dictionary, from_cell: String, to_cell: String) -> Variant:
	var graph := _undirected_graph(state)
	if not graph.has(from_cell):
		return null
	var seen := {from_cell: true}
	var queue: Array[String] = [from_cell]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		for neighbour: String in graph.get(current, {}):
			if current == from_cell and neighbour == to_cell:
				continue
			if not seen.has(neighbour):
				seen[neighbour] = true
				queue.append(neighbour)
	if seen.has(to_cell):
		return null
	var result: Array[String] = []
	for cell: String in seen.keys():
		result.append(cell)
	result.sort()
	return result


static func _undirected_graph(state: Dictionary, include_drops: bool = false) -> Dictionary:
	var graph := {}
	for key: String in state.keys():
		var record: Dictionary = state[key]
		if String(record.get("vertical", "level")) == "drop" and not include_drops:
			continue
		var pair := pair_cells(key)
		var left := String(pair[0])
		var right := String(pair[1])
		if not graph.has(left):
			graph[left] = {}
		if not graph.has(right):
			graph[right] = {}
		(graph[left] as Dictionary)[right] = true
		(graph[right] as Dictionary)[left] = true
	return graph


static func _rect(cell: Dictionary) -> Variant:
	var envelope: Variant = cell.get("envelope_xz")
	if not (envelope is Array) or (envelope as Array).size() != 4:
		return null
	var xs := {}
	var zs := {}
	var points: Array = []
	for point: Variant in envelope:
		if not (point is Array) or (point as Array).size() != 2:
			return null
		var x := float(point[0])
		var z := float(point[1])
		xs[x] = true
		zs[z] = true
		points.append([x, z])
	if xs.size() != 2 or zs.size() != 2:
		return null
	var x_keys: Array = xs.keys()
	var z_keys: Array = zs.keys()
	x_keys.sort()
	z_keys.sort()
	var x0 := float(x_keys[0])
	var x1 := float(x_keys[1])
	var z0 := float(z_keys[0])
	var z1 := float(z_keys[1])
	for point: Array in points:
		var x := float(point[0])
		var z := float(point[1])
		var corner := (is_equal_approx(x, x0) or is_equal_approx(x, x1)) \
			and (is_equal_approx(z, z0) or is_equal_approx(z, z1))
		if not corner:
			return null
	return [x0, z0, x1, z1]


static func shared_wall(first: Dictionary, second: Dictionary) -> Dictionary:
	var rect_a: Variant = _rect(first)
	var rect_b: Variant = _rect(second)
	if rect_a == null or rect_b == null:
		return {}
	var ax0 := float(rect_a[0])
	var az0 := float(rect_a[1])
	var ax1 := float(rect_a[2])
	var az1 := float(rect_a[3])
	var bx0 := float(rect_b[0])
	var bz0 := float(rect_b[1])
	var bx1 := float(rect_b[2])
	var bz1 := float(rect_b[3])
	var walls: Array = []
	if is_equal_approx(ax1, bx0) or is_equal_approx(bx1, ax0):
		var line := ax1 if is_equal_approx(ax1, bx0) else ax0
		var start := maxf(az0, bz0)
		var end := minf(az1, bz1)
		if end > start:
			walls.append({"axis": "x", "line": line, "start": start, "end": end,
				"length_m": end - start})
	if is_equal_approx(az1, bz0) or is_equal_approx(bz1, az0):
		var line := az1 if is_equal_approx(az1, bz0) else az0
		var start := maxf(ax0, bx0)
		var end := minf(ax1, bx1)
		if end > start:
			walls.append({"axis": "z", "line": line, "start": start, "end": end,
				"length_m": end - start})
	if walls.is_empty():
		return {}
	var best: Dictionary = walls[0]
	for wall: Dictionary in walls:
		if float(wall.length_m) > float(best.length_m):
			best = wall
	return best


static func is_content_pinned(cell: Dictionary) -> bool:
	return cell.get("module") != null or cell.get("landmark") != null \
		or cell.get("diagonal_passage") != null


static func build_universe(document: Dictionary, target_cells: Array, root_cell: String,
		state: Dictionary) -> Dictionary:
	var cells := cells_by_id(document)
	var target_set := {}
	for cell: String in target_cells:
		target_set[cell] = true
	var edges := {}
	for key: String in state.keys():
		var pair := pair_cells(key)
		if target_set.has(String(pair[0])) and target_set.has(String(pair[1])):
			edges[key] = true
	var mandatory := {}
	for key: String in edges.keys():
		var record: Dictionary = state[key]
		var pair := pair_cells(key)
		if String(record.get("vertical", "level")) == "ramp" \
				or String(record.get("vertical", "level")) == "drop":
			mandatory[key] = true
		if is_content_pinned(cells[String(pair[0])]) or is_content_pinned(cells[String(pair[1])]):
			mandatory[key] = true
	var universe := edges.duplicate()
	var ordered: Array = target_cells.duplicate()
	ordered.sort()
	for first_index in range(ordered.size()):
		for second_index in range(first_index + 1, ordered.size()):
			var left := String(ordered[first_index])
			var right := String(ordered[second_index])
			var key := pair_key(left, right)
			if universe.has(key):
				continue
			if is_content_pinned(cells[left]) or is_content_pinned(cells[right]):
				continue
			if not is_equal_approx(float(cells[left].get("floor_y", 0.0)),
					float(cells[right].get("floor_y", 0.0))):
				continue
			var wall := shared_wall(cells[left], cells[right])
			if not wall.is_empty() and float(wall.length_m) + 0.000000001 >= MIN_SHARED_WALL_M:
				universe[key] = true
	if universe.size() > MAX_H_UNIVERSE:
		return {"error": "target_too_large", "message": "|H_T| exceeds %d" % MAX_H_UNIVERSE}
	var variable: Array = []
	for key: String in universe.keys():
		if not mandatory.has(key):
			variable.append(key)
	variable.sort()
	return {
		"target_cells": ordered,
		"root_cell_id": root_cell,
		"edges_before": edges,
		"universe": universe,
		"mandatory": mandatory,
		"variable": variable,
	}


static func _degree(passages: Dictionary, root_cell: String) -> Dictionary:
	var degree := {}
	for key: String in passages.keys():
		var pair := pair_cells(key)
		var left := String(pair[0])
		var right := String(pair[1])
		degree[left] = int(degree.get(left, 0)) + 1
		degree[right] = int(degree.get(right, 0)) + 1
	degree[root_cell] = int(degree.get(root_cell, 0)) + 1
	return degree


static func _connected(passages: Dictionary, target_cells: Array, root_cell: String) -> bool:
	var graph := {}
	for cell: String in target_cells:
		graph[cell] = {}
	for key: String in passages.keys():
		var pair := pair_cells(key)
		var left := String(pair[0])
		var right := String(pair[1])
		(graph[left] as Dictionary)[right] = true
		(graph[right] as Dictionary)[left] = true
	var seen := {root_cell: true}
	var queue: Array[String] = [root_cell]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		for neighbour: String in graph[current]:
			if not seen.has(neighbour):
				seen[neighbour] = true
				queue.append(neighbour)
	return seen.size() == target_cells.size()


static func _strongly_connected(passages: Dictionary, target_cells: Array,
		state: Dictionary) -> bool:
	var directed := {}
	for cell: String in target_cells:
		directed[cell] = {}
	for key: String in passages.keys():
		var record: Dictionary = state.get(key, {"vertical": "level"})
		var pair := pair_cells(key)
		var left := String(pair[0])
		var right := String(pair[1])
		if String(record.get("vertical", "level")) == "drop":
			var upper := String(record.get("upper", left))
			var lower := String(record.get("lower", right))
			if directed.has(upper) and directed.has(lower):
				(directed[upper] as Dictionary)[lower] = true
		else:
			if directed.has(left) and directed.has(right):
				(directed[left] as Dictionary)[right] = true
				(directed[right] as Dictionary)[left] = true
	for start: String in target_cells:
		var seen := {start: true}
		var queue: Array[String] = [start]
		var head := 0
		while head < queue.size():
			var current := queue[head]
			head += 1
			for neighbour: String in directed[current]:
				if not seen.has(neighbour):
					seen[neighbour] = true
					queue.append(neighbour)
		if seen.size() != target_cells.size():
			return false
	return true


static func _depths(passages: Dictionary, target_cells: Array, root_cell: String) -> Dictionary:
	var graph := {}
	for cell: String in target_cells:
		graph[cell] = {}
	for key: String in passages.keys():
		var pair := pair_cells(key)
		var left := String(pair[0])
		var right := String(pair[1])
		(graph[left] as Dictionary)[right] = true
		(graph[right] as Dictionary)[left] = true
	var depth := {root_cell: 0}
	var queue: Array[String] = [root_cell]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		var neighbours: Array = (graph[current] as Dictionary).keys()
		neighbours.sort()
		for neighbour: String in neighbours:
			if not depth.has(neighbour):
				depth[neighbour] = int(depth[current]) + 1
				queue.append(neighbour)
	return depth


static func shape_metrics(passages: Dictionary, target_cells: Array,
		root_cell: String) -> Dictionary:
	var degree := _degree(passages, root_cell)
	var depth := _depths(passages, target_cells, root_cell)
	var leaves := 0
	var histogram := {}
	var sum_depth := 0
	for cell: String in target_cells:
		var value := int(degree.get(cell, 0))
		if value == 1:
			leaves += 1
		histogram[value] = int(histogram.get(value, 0)) + 1
		sum_depth += int(depth.get(cell, 0))
	return {
		"leaves": leaves,
		"loops": passages.size() - (target_cells.size() - 1),
		"degree_histogram": histogram,
		"max_depth": int(depth.values().max()),
		"mean_depth": float(sum_depth) / float(target_cells.size()),
		"door_count": passages.size() + 1,
	}


static func _histogram_l1(first: Dictionary, second: Dictionary) -> int:
	var keys := {}
	for key: Variant in first.keys():
		keys[key] = true
	for key: Variant in second.keys():
		keys[key] = true
	var total := 0
	for key: Variant in keys.keys():
		total += abs(int(first.get(key, 0)) - int(second.get(key, 0)))
	return total


static func shape_violations(shape: Dictionary, baseline: Dictionary, tier: int) -> int:
	var tolerance: Dictionary = SHAPE_TOLERANCES[tier]
	var violations := 0
	for field: String in ["leaves", "loops", "max_depth", "door_count"]:
		if abs(int(shape[field]) - int(baseline[field])) > int(tolerance[field]):
			violations += 1
	if absf(float(shape.mean_depth) - float(baseline.mean_depth)) > float(tolerance.mean_depth):
		violations += 1
	if _histogram_l1(shape.degree_histogram, baseline.degree_histogram) > int(tolerance.degree_histogram):
		violations += 1
	return violations


static func shape_score(shape: Dictionary, baseline: Dictionary, retained_fraction: float) -> float:
	var score: float = (
		int(SHAPE_WEIGHTS.leaves) * abs(int(shape.leaves) - int(baseline.leaves))
		+ int(SHAPE_WEIGHTS.loops) * abs(int(shape.loops) - int(baseline.loops))
		+ int(SHAPE_WEIGHTS.max_depth) * abs(int(shape.max_depth) - int(baseline.max_depth))
		+ float(SHAPE_WEIGHTS.mean_depth) * absf(float(shape.mean_depth) - float(baseline.mean_depth))
		+ int(SHAPE_WEIGHTS.degree_histogram) * _histogram_l1(shape.degree_histogram, baseline.degree_histogram)
		+ int(SHAPE_WEIGHTS.door_count) * abs(int(shape.door_count) - int(baseline.door_count))
		+ float(SHAPE_WEIGHTS.retained) * (1.0 - retained_fraction)
	)
	return round(score * 1000000.0) / 1000000.0


static func passage_key(passages: Dictionary) -> String:
	var keys: Array = passages.keys()
	keys.sort()
	var parts: Array = []
	for key: String in keys:
		var pair := pair_cells(key)
		parts.append("%s-%s" % [String(pair[0]), String(pair[1])])
	return ";".join(parts)


static func keyed_candidate_rank(seed: int, attempt: int, passages: Dictionary) -> String:
	var key := "%d:%d:%s:%s:%s" % [seed, attempt, EVENT_STREAM, ALGORITHM_VERSION,
		passage_key(passages)]
	return key.sha256_text()


static func candidate_set_hash(candidates: Array) -> String:
	var keys: Array = []
	for candidate: Dictionary in candidates:
		keys.append(String(candidate.key))
	keys.sort()
	return "\n".join(keys).sha256_text()


static func _candidate(passages: Dictionary, edges_before: Dictionary,
		mandatory: Dictionary, target_cells: Array, root_cell: String, state: Dictionary,
		baseline: Dictionary, tier: int, seed: int, attempt: int) -> Dictionary:
	var edit_distance := _symmetric_difference_size(passages, edges_before)
	var retained := float(_intersection_size(passages, edges_before)) / float(edges_before.size()) \
		if not edges_before.is_empty() else 0.0
	var shape := shape_metrics(passages, target_cells, root_cell)
	return {
		"passages": passages,
		"key": passage_key(passages),
		"edit_distance": edit_distance,
		"retained_fraction": retained,
		"shape": shape,
		"shape_violations": shape_violations(shape, baseline, tier),
		"shape_score": shape_score(shape, baseline, retained),
		"keyed_rank": keyed_candidate_rank(seed, attempt, passages),
		"pinned_passages": mandatory.duplicate(),
	}


static func _intersection_size(first: Dictionary, second: Dictionary) -> int:
	var total := 0
	for key: String in first.keys():
		if second.has(key):
			total += 1
	return total


static func _symmetric_difference_size(first: Dictionary, second: Dictionary) -> int:
	return first.size() + second.size() - 2 * _intersection_size(first, second)


static func _passes_hard_invariants(passages: Dictionary, candidate: Dictionary,
		edges_before: Dictionary, mandatory: Dictionary, target_cells: Array,
		root_cell: String, state: Dictionary, tier: int, exit_cell: String,
		reachable_from: String) -> bool:
	var bounds: Array = TIERS[tier]
	for key: String in mandatory.keys():
		if not passages.has(key):
			return false
	if _same_keys(passages, edges_before):
		return false
	if int(candidate.edit_distance) < int(bounds[0]) or int(candidate.edit_distance) > int(bounds[1]):
		return false
	if float(candidate.retained_fraction) < MIN_RETAINED:
		return false
	if not _connected(passages, target_cells, root_cell):
		return false
	if not _strongly_connected(passages, target_cells, state):
		return false
	var degree := _degree(passages, root_cell)
	if int(degree.values().max()) > MAX_DEGREE:
		return false
	if not exit_cell.is_empty() and not target_cells.has(exit_cell):
		var graph := _graph_after(state, passages, target_cells)
		if not _reachable(graph, reachable_from, exit_cell):
			return false
	return true


static func _same_keys(first: Dictionary, second: Dictionary) -> bool:
	if first.size() != second.size():
		return false
	for key: String in first.keys():
		if not second.has(key):
			return false
	return true


static func _graph_after(state: Dictionary, passages: Dictionary, target_cells: Array) -> Dictionary:
	var graph := _undirected_graph(state)
	for key: String in state.keys():
		var pair := pair_cells(key)
		if target_cells.has(String(pair[0])) and target_cells.has(String(pair[1])):
			(graph[String(pair[0])] as Dictionary).erase(String(pair[1]))
			(graph[String(pair[1])] as Dictionary).erase(String(pair[0]))
	for key: String in passages.keys():
		var pair := pair_cells(key)
		var left := String(pair[0])
		var right := String(pair[1])
		if not graph.has(left):
			graph[left] = {}
		if not graph.has(right):
			graph[right] = {}
		(graph[left] as Dictionary)[right] = true
		(graph[right] as Dictionary)[left] = true
	return graph


static func _reachable(graph: Dictionary, start: String, goal: String) -> bool:
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
		for neighbour: String in graph.get(current, {}):
			if not seen.has(neighbour):
				seen[neighbour] = true
				queue.append(neighbour)
	return seen.has(goal)


static func _sort_candidates(candidates: Array) -> void:
	candidates.sort_custom(func(first: Dictionary, second: Dictionary) -> bool:
		if int(first.shape_violations) != int(second.shape_violations):
			return int(first.shape_violations) < int(second.shape_violations)
		if int(first.edit_distance) != int(second.edit_distance):
			return int(first.edit_distance) < int(second.edit_distance)
		if float(first.shape_score) != float(second.shape_score):
			return float(first.shape_score) < float(second.shape_score)
		return String(first.keyed_rank) < String(second.keyed_rank))


static func shortlist_for(candidates: Array) -> Array:
	var in_tolerance: Array = []
	for candidate: Dictionary in candidates:
		if int(candidate.shape_violations) == 0:
			in_tolerance.append(candidate)
	if in_tolerance.size() >= MIN_REROLL_ALTERNATIVES:
		return [in_tolerance.slice(0, CANDIDATE_SHORTLIST), false]
	var limit := maxi(MIN_REROLL_ALTERNATIVES, mini(CANDIDATE_SHORTLIST, candidates.size()))
	return [candidates.slice(0, limit), true]


static func threshold_port(document: Dictionary, from_cell: String, to_cell: String) -> String:
	for edge: Dictionary in document.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var left := cell_of(String(edge.get("from", "")))
		var right := cell_of(String(edge.get("to", "")))
		if left == from_cell and right == to_cell:
			return String(edge.get("to", ""))
		if right == from_cell and left == to_cell:
			return String(edge.get("from", ""))
	return ""


static func door_threshold_id(from_cell: String, to_cell: String) -> String:
	return EXIT.threshold_id(from_cell, to_cell)


static func _pair_list(passages: Dictionary) -> Array:
	var keys: Array = passages.keys()
	keys.sort()
	var result: Array = []
	for key: String in keys:
		result.append(pair_cells(key))
	return result


static func _rejected(code: String, from_cell: String, to_cell: String,
		target_cells: Array = []) -> Dictionary:
	return {
		"ok": false,
		"reason": code,
		"algorithm_version": ALGORITHM_VERSION,
		"from_cell": from_cell,
		"to_cell": to_cell,
		"target_cells": target_cells.duplicate(),
		"target_size": target_cells.size(),
		"candidates": [],
		"shortlist": [],
		"consistency_relaxed": false,
		"candidate_set_hash": candidate_set_hash([]),
		"checks": [],
		"edges_before": {},
		"universe": {},
		"mandatory": {},
		"variable": [],
	}


static func analyze_target(document: Dictionary, from_cell: String, to_cell: String,
		options: Dictionary = {}) -> Dictionary:
	var algorithm_version := String(options.get("algorithm_version", ALGORITHM_VERSION))
	if algorithm_version != ALGORITHM_VERSION:
		return _rejected("unsupported_algorithm", from_cell, to_cell)
	var tier := int(options.get("reroll_index", 1))
	if not TIERS.has(tier):
		return _rejected("unsupported_algorithm", from_cell, to_cell)
	var exit_cell := String(options.get("exit_cell", ""))
	var visible_cells: Array = options.get("visible_cells", [])
	var cells := cells_by_id(document)
	if not cells.has(from_cell) or not cells.has(to_cell):
		return _rejected("not_bridge", from_cell, to_cell)
	var state: Dictionary = options.get("state", {})
	if state.is_empty():
		state = base_passage_state(document)
	var crossing: Variant = state.get(pair_key(from_cell, to_cell))
	if crossing == null:
		return _rejected("not_bridge", from_cell, to_cell)
	if String((crossing as Dictionary).get("vertical", "level")) == "drop":
		return _rejected("drop_door", from_cell, to_cell)
	var target: Variant = target_component(state, from_cell, to_cell)
	if target == null:
		return _rejected("not_bridge", from_cell, to_cell)
	var target_cells: Array = target
	if target_cells.size() < MIN_REROLL_CELLS:
		return _rejected("target_too_small", from_cell, to_cell, target_cells)
	if target_cells.size() > MAX_REROLL_CELLS:
		return _rejected("target_too_large", from_cell, to_cell, target_cells)
	if not exit_cell.is_empty() and target_cells.has(exit_cell):
		return _rejected("exit_inside", from_cell, to_cell, target_cells)
	if not visible_cells.is_empty():
		for cell: String in target_cells:
			if visible_cells.has(cell):
				return _rejected("visible_target", from_cell, to_cell, target_cells)
	var universe := build_universe(document, target_cells, from_cell, state)
	if universe.has("error"):
		return _rejected(String(universe.error), from_cell, to_cell, target_cells)
	var seed := int(document.get("seed", 0))
	var attempt := int(document.get("attempt", 0))
	var baseline := shape_metrics(universe.edges_before, target_cells, from_cell)
	var candidates: Array = []
	var raw_count := 0
	var variable: Array = universe.variable
	for bits in range(1 << variable.size()):
		var passages: Dictionary = (universe.mandatory as Dictionary).duplicate()
		for index in range(variable.size()):
			if bits & (1 << index):
				passages[String(variable[index])] = true
		if _same_keys(passages, universe.edges_before):
			continue
		raw_count += 1
		var candidate := _candidate(passages, universe.edges_before, universe.mandatory,
			target_cells, from_cell, state, baseline, tier, seed, attempt)
		if not _passes_hard_invariants(passages, candidate, universe.edges_before,
				universe.mandatory, target_cells, from_cell, state, tier, exit_cell, to_cell):
			continue
		candidates.append(candidate)
	_sort_candidates(candidates)
	var reason := ""
	var shortlist: Array = []
	var relaxed := false
	var checks: Array = []
	for name: String in HARD_CHECKS:
		if name != "R9_visibility" or not visible_cells.is_empty():
			checks.append(name)
	if candidates.is_empty():
		reason = "no_candidate_in_tier" if raw_count > 0 else "no_candidate"
	elif candidates.size() < MIN_REROLL_ALTERNATIVES:
		reason = "below_min_alternatives"
	else:
		var short := shortlist_for(candidates)
		shortlist = short[0]
		relaxed = bool(short[1])
	return {
		"ok": reason.is_empty(),
		"reason": reason,
		"algorithm_version": algorithm_version,
		"from_cell": from_cell,
		"to_cell": to_cell,
		"threshold_id": threshold_port(document, from_cell, to_cell),
		"door_threshold_id": door_threshold_id(from_cell, to_cell),
		"root_cell_id": from_cell,
		"target_cells": target_cells,
		"target_size": target_cells.size(),
		"spawn_cell_id": spawn_cell_id(document),
		"spawn_in_target": target_cells.has(spawn_cell_id(document)),
		"edges_before": universe.edges_before,
		"universe": universe.universe,
		"mandatory": universe.mandatory,
		"variable": universe.variable,
		"shape_before": baseline,
		"candidates": candidates,
		"shortlist": shortlist,
		"consistency_relaxed": relaxed,
		"candidate_set_hash": candidate_set_hash(candidates),
		"checks": checks,
		"reroll_index": tier,
	}


static func _hash_mod(hex_digest: String, modulus: int) -> int:
	var value := 0
	for index in range(hex_digest.length()):
		value = (value * 16 + hex_digest.substr(index, 1).hex_to_int()) % modulus
	return value


static func choose_candidate(analysis: Dictionary, event_index: int) -> Dictionary:
	if not bool(analysis.get("ok", false)) or (analysis.get("shortlist", []) as Array).is_empty():
		return {}
	var threshold := String(analysis.threshold_id)
	var seed := int(analysis.get("seed", 0))
	var attempt := int(analysis.get("attempt", 0))
	var key := "%d:%d:%d:%s:%s:%s:choose" % [seed, attempt, event_index,
		EVENT_STREAM, threshold, ALGORITHM_VERSION]
	var index := _hash_mod(key.sha256_text(), (analysis.shortlist as Array).size())
	return {
		"index": index,
		"chosen_rank": index + 1,
		"chosen": (analysis.shortlist as Array)[index],
		"purpose": "%s:choose" % ALGORITHM_VERSION,
	}


static func plan(document: Dictionary, from_cell: String, to_cell: String,
		event_index: int, options: Dictionary = {}) -> Dictionary:
	var analysis := analyze_target(document, from_cell, to_cell, options)
	if not bool(analysis.get("ok", false)):
		return analysis
	analysis["seed"] = int(document.get("seed", 0))
	analysis["attempt"] = int(document.get("attempt", 0))
	var draw := choose_candidate(analysis, event_index)
	analysis["draw"] = draw
	analysis["chosen"] = draw.get("chosen")
	analysis["chosen_rank"] = int(draw.get("chosen_rank", 0))
	return analysis


## Keyed doorway placement (§4.5.7). The digest prefix and divisor match the
## Python reference bit for bit.
static func _keyed_uniform(seed: int, attempt: int, event_index: int,
		threshold: String, cell_a: String, cell_b: String) -> float:
	var key := "%d:%d:%d:%s:%s:%s:%s" % [seed, attempt, event_index,
		DOORWAY_STREAM, threshold, cell_a, cell_b]
	var digest := key.sha256_text()
	return float(digest.substr(0, 13).hex_to_int()) / 4503599627370496.0


## Pure doorway metadata for every changed shared wall; no runtime geometry.
static func doorway_records(document: Dictionary, analysis: Dictionary,
		event_index: int) -> Array:
	var cells := cells_by_id(document)
	var before: Dictionary = analysis.get("edges_before", {})
	var chosen: Variant = analysis.get("chosen")
	if not (chosen is Dictionary):
		return []
	var after: Dictionary = (chosen as Dictionary).get("passages", {})
	var seed := int(document.get("seed", 0))
	var attempt := int(document.get("attempt", 0))
	var threshold := String(analysis.get("threshold_id", ""))
	var records: Array = []
	var changed: Array = []
	for key: String in before:
		if not after.has(key):
			changed.append(key)
	for key: String in after:
		if not before.has(key):
			changed.append(key)
	changed.sort()
	for key: String in changed:
		var pair := pair_cells(key)
		if pair.size() != 2:
			continue
		var cell_a := String(pair[0])
		var cell_b := String(pair[1])
		if before.has(key):
			records.append({"cell_a": cell_a, "cell_b": cell_b, "action": "closed"})
			continue
		if not cells.has(cell_a) or not cells.has(cell_b):
			continue
		var wall := shared_wall(cells[cell_a], cells[cell_b])
		if wall.is_empty() or float(wall.length_m) + 0.000000001 < MIN_SHARED_WALL_M:
			continue
		var low := float(wall.start) + DOORWAY_MARGIN_M + DOOR_WIDTH_M / 2.0
		var high := float(wall.end) - DOORWAY_MARGIN_M - DOOR_WIDTH_M / 2.0
		if low > high + 0.000000001:
			continue
		var along := _keyed_uniform(seed, attempt, event_index, threshold,
			cell_a, cell_b)
		var center := clampf(float(wall.start) + along * float(wall.length_m),
			low, high)
		var center_xz := [round(float(wall.line) * 1000000.0) / 1000000.0,
			round(center * 1000000.0) / 1000000.0]
		if String(wall.axis) == "z":
			center_xz = [round(center * 1000000.0) / 1000000.0,
				round(float(wall.line) * 1000000.0) / 1000000.0]
		records.append({
			"cell_a": cell_a,
			"cell_b": cell_b,
			"action": "opened",
			"center_xz": center_xz,
			"width_m": DOOR_WIDTH_M,
			"height_m": DOOR_HEIGHT_M,
		})
	return records


## The §4.5.8 event payload for one accepted re-roll.
static func rewire_block(document: Dictionary, analysis: Dictionary,
		event_index: int) -> Dictionary:
	var chosen: Dictionary = analysis.get("chosen", {})
	return {
		"algorithm_version": ALGORITHM_VERSION,
		"target_cells": (analysis.get("target_cells", []) as Array).duplicate(),
		"root_cell_id": String(analysis.get("root_cell_id", "")),
		"threshold_id": String(analysis.get("threshold_id", "")),
		"passages_before": _pair_list(analysis.get("edges_before", {})),
		"passages_after": _pair_list(chosen.get("passages", {})),
		"pinned_passages": _pair_list(analysis.get("mandatory", {})),
		"doorways": doorway_records(document, analysis, event_index),
		"edit_distance": int(chosen.get("edit_distance", 0)),
		"retained_fraction": float(chosen.get("retained_fraction", 0.0)),
		"shape_before": _shape_projection(analysis.get("shape_before", {})),
		"shape_after": _shape_projection(chosen.get("shape", {})),
		"shape_score": float(chosen.get("shape_score", 0.0)),
		"candidate_count": (analysis.get("candidates", []) as Array).size(),
		"shortlist_size": (analysis.get("shortlist", []) as Array).size(),
		"chosen_rank": int(analysis.get("chosen_rank", 0)),
		"consistency_relaxed": bool(analysis.get("consistency_relaxed", false)),
		"candidate_set_hash": String(analysis.get("candidate_set_hash", "")),
	}


static func _shape_projection(shape: Dictionary) -> Dictionary:
	var histogram: Array = []
	var keys: Array = (shape.degree_histogram as Dictionary).keys()
	keys.sort()
	for degree: Variant in keys:
		histogram.append([int(degree), int(shape.degree_histogram[degree])])
	return {
		"leaves": int(shape.leaves),
		"loops": int(shape.loops),
		"max_depth": int(shape.max_depth),
		"mean_depth_milli": int(round(float(shape.mean_depth) * 1000.0)),
		"door_count": int(shape.door_count),
		"degree_histogram": histogram,
	}


static func _candidate_projection(candidate: Dictionary) -> Dictionary:
	return {
		"passages_after": _pair_list(candidate.passages),
		"edit_distance": int(candidate.edit_distance),
		"retained_milli": int(round(float(candidate.retained_fraction) * 1000.0)),
		"shape": _shape_projection(candidate.shape),
		"shape_violations": int(candidate.shape_violations),
		"shape_score_micro": int(round(float(candidate.shape_score) * 1000000.0)),
	}


static func projection(plan_data: Dictionary) -> Dictionary:
	var shortlist: Array = []
	for candidate: Dictionary in plan_data.get("shortlist", []):
		shortlist.append(_candidate_projection(candidate))
	var in_tolerance := 0
	for candidate: Dictionary in plan_data.get("candidates", []):
		if int(candidate.shape_violations) == 0:
			in_tolerance += 1
	var chosen: Variant = null
	if plan_data.get("chosen") != null:
		chosen = _candidate_projection(plan_data.chosen)
	var shape_before: Dictionary = {}
	if plan_data.has("shape_before"):
		shape_before = _shape_projection(plan_data.shape_before)
	return {
		"ok": bool(plan_data.get("ok", false)),
		"reason": String(plan_data.get("reason", "")),
		"target_cells": plan_data.get("target_cells", []),
		"root_cell_id": String(plan_data.get("root_cell_id", "")),
		"threshold_id": String(plan_data.get("threshold_id", "")),
		"door_threshold_id": String(plan_data.get("door_threshold_id", "")),
		"h_universe": _pair_list(plan_data.get("universe", {})),
		"mandatory_passages": _pair_list(plan_data.get("mandatory", {})),
		"variable_count": (plan_data.get("variable", []) as Array).size(),
		"passages_before": _pair_list(plan_data.get("edges_before", {})),
		"pinned_passages": _pair_list(plan_data.get("mandatory", {})),
		"candidate_count": (plan_data.get("candidates", []) as Array).size(),
		"in_tolerance_count": in_tolerance,
		"shortlist_size": shortlist.size(),
		"consistency_relaxed": bool(plan_data.get("consistency_relaxed", false)),
		"shape_before": shape_before,
		"shortlist": shortlist,
		"chosen": chosen,
		"chosen_rank": int(plan_data.get("chosen_rank", 0)),
		"candidate_set_hash": String(plan_data.get("candidate_set_hash", "")),
	}


static func direction_report(document: Dictionary, from_cell: String, to_cell: String,
		options: Dictionary = {}) -> Dictionary:
	var analysis := analyze_target(document, from_cell, to_cell, options)
	var edits: Array = []
	for candidate: Dictionary in analysis.get("candidates", []):
		edits.append(int(candidate.edit_distance))
	edits.sort()
	var in_tolerance := 0
	for candidate: Dictionary in analysis.get("candidates", []):
		if int(candidate.shape_violations) == 0:
			in_tolerance += 1
	return {
		"threshold_id": String(analysis.get("threshold_id", "")),
		"door_threshold_id": String(analysis.get("door_threshold_id", "")),
		"from_cell": from_cell,
		"to_cell": to_cell,
		"target_cells": analysis.get("target_cells", []),
		"target_size": int(analysis.get("target_size", 0)),
		"spawn_in_target": bool(analysis.get("spawn_in_target", false)),
		"h_universe": _pair_list(analysis.get("universe", {})),
		"mandatory_passages": _pair_list(analysis.get("mandatory", {})),
		"variable_count": (analysis.get("variable", []) as Array).size(),
		"hard_valid": (analysis.get("candidates", []) as Array).size(),
		"in_tolerance": in_tolerance,
		"shortlist_size": (analysis.get("shortlist", []) as Array).size(),
		"consistency_relaxed": bool(analysis.get("consistency_relaxed", false)),
		"edit_range": [edits[0], edits[-1]] if not edits.is_empty() else [],
		"reason": String(analysis.get("reason", "")),
	}
