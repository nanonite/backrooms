class_name MazeRewire
extends RefCounted

## Derived-spec rebuild contract for the M6 re-roll runtime (#236).
##
## The M5 enumerator chooses a passage set ``P`` on the existing footprint.
## This module turns the stored event into runtime room specs:
##
## * remove only the doorway records for passages in ``E_T \ P``;
## * add an open doorway record for every passage in ``P \ E_T`` at the stored
##   center, reusing the room's envelope and builder;
## * copy every other field unchanged and bump ``passage_revision``;
## * reject a doorway that does not fit its wall, overlaps a kept opening or
##   cuts a content-pinned cell.
##
## No committed map, shape-room file, library scene or generator output is
## touched. The derived spec is an in-memory copy; the committed spec stays the
## base for replay.

const REROLL := preload("res://scripts/maze_reroll.gd")

const ALGORITHM_VERSION := "rewire-1"
const RUNTIME_LAYER_VERSION := "maze-rewire-runtime-0.1.0"
const STATE_HASH_PREFIX := "maze-rewire-state-0.1.0"
const PORT_PREFIX := "rw_"
const DOOR_WIDTH_M := 1.4
const DOOR_HEIGHT_M := 2.2
const DOORWAY_MARGIN_M := 0.2
const DOORWAY_COMPATIBILITY_TYPE := "maze_rewire_1_4m_v1"
const INTERNAL_FLAG := "rewire_internal"
const MIN_CEILING_CLEARANCE_M := 0.05
const EPSILON := 0.000000001

## Only these fields may differ between a base spec and its derived copy.
const ALLOWED_SPEC_FIELDS := ["doorways", "features", "degenerate_port_ids",
	"passage_revision"]


static func port_id(cell_id: String, other_cell_id: String) -> String:
	return "%s:%s%s" % [cell_id, PORT_PREFIX, other_cell_id]


static func pair_key(left: String, right: String) -> String:
	return left + "|" + right if left < right else right + "|" + left


static func pair_cells(key: String) -> Array:
	var parts := key.split("|")
	if parts.size() != 2:
		return []
	return [parts[0], parts[1]]


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


## The outward normal of ``cell`` on the shared wall towards ``other``.
static func wall_normal(cell: Dictionary, other: Dictionary,
		wall: Dictionary) -> Array:
	var rect_cell: Variant = _rect(cell)
	var rect_other: Variant = _rect(other)
	if rect_cell == null or rect_other == null:
		return []
	var ax0 := float(rect_cell[0])
	var az0 := float(rect_cell[1])
	var ax1 := float(rect_cell[2])
	var az1 := float(rect_cell[3])
	var bx0 := float(rect_other[0])
	var bz0 := float(rect_other[1])
	var bx1 := float(rect_other[2])
	var bz1 := float(rect_other[3])
	if String(wall.get("axis", "")) == "x":
		if absf(ax1 - bx0) <= EPSILON:
			return [1.0, 0.0]
		if absf(bx1 - ax0) <= EPSILON:
			return [-1.0, 0.0]
		return []
	if absf(az1 - bz0) <= EPSILON:
		return [0.0, 1.0]
	if absf(bz1 - az0) <= EPSILON:
		return [0.0, -1.0]
	return []


static func _doorway_record(cell_id: String, other_cell_id: String,
		event_record: Dictionary, cells: Dictionary) -> Dictionary:
	var cell: Dictionary = cells.get(cell_id, {})
	var other: Dictionary = cells.get(other_cell_id, {})
	if cell.is_empty() or other.is_empty():
		return {}
	var wall: Dictionary = REROLL.shared_wall(cell, other)
	if wall.is_empty():
		return {}
	var normal := wall_normal(cell, other, wall)
	if normal.is_empty():
		return {}
	var center: Variant = event_record.get("center_xz", [])
	if not (center is Array) or (center as Array).size() != 2:
		return {}
	return {
		"port_id": port_id(cell_id, other_cell_id),
		"to_port_id": port_id(other_cell_id, cell_id),
		"to_cell_id": other_cell_id,
		"pos_xz": [float(center[0]), float(center[1])],
		"normal": normal,
		"width_m": float(event_record.get("width_m", DOOR_WIDTH_M)),
		"height_m": float(event_record.get("height_m", DOOR_HEIGHT_M)),
		"sill_height_m": 0.0,
		"kind": "open",
		"vertical": "level",
		"compatibility_type": DOORWAY_COMPATIBILITY_TYPE,
		INTERNAL_FLAG: true,
	}


static func _copy_spec(base: Dictionary) -> Dictionary:
	return base.duplicate(true)


static func _remove_doorway(spec: Dictionary, other_cell_id: String) -> Array:
	var removed: Array = []
	var kept: Array = []
	for doorway: Dictionary in spec.get("doorways", []):
		if String(doorway.get("to_cell_id", "")) == other_cell_id:
			removed.append(String(doorway.get("port_id", "")))
			continue
		kept.append(doorway)
	spec["doorways"] = kept
	if removed.is_empty():
		return removed
	var features: Array = []
	for feature: Dictionary in spec.get("features", []):
		if String(feature.get("kind", "")) == "doorway" \
				and removed.has(String(feature.get("feature_id", "")).trim_prefix("doorway:")):
			continue
		features.append(feature)
	spec["features"] = features
	var degenerate: Array = []
	for port: String in spec.get("degenerate_port_ids", []):
		if not removed.has(port):
			degenerate.append(port)
	spec["degenerate_port_ids"] = degenerate
	return removed


static func _add_doorway(spec: Dictionary, other_cell_id: String,
		record: Dictionary) -> bool:
	for doorway: Dictionary in spec.get("doorways", []):
		if String(doorway.get("to_cell_id", "")) == other_cell_id:
			return false
	(spec["doorways"] as Array).append(record)
	var features: Array = spec.get("features", [])
	features.append({
		"feature_id": "doorway:" + String(record.port_id),
		"kind": "doorway",
		"sign": "symbol",
	})
	spec["features"] = features
	return true


static func _content_pinned(cell: Dictionary) -> bool:
	return cell.get("module") != null or cell.get("landmark") != null \
		or cell.get("diagonal_passage") != null


static func changed_pairs(event: Dictionary) -> Dictionary:
	var rewire: Variant = event.get("rewire")
	if not (rewire is Dictionary):
		return {}
	var before := {}
	for pair: Variant in (rewire as Dictionary).get("passages_before", []):
		if pair is Array and (pair as Array).size() == 2:
			before[pair_key(String(pair[0]), String(pair[1]))] = true
	var after := {}
	for pair: Variant in (rewire as Dictionary).get("passages_after", []):
		if pair is Array and (pair as Array).size() == 2:
			after[pair_key(String(pair[0]), String(pair[1]))] = true
	return {"before": before, "after": after}


## Build the derived spec copy for every cell whose doorway set changes.
## Returns ``{"ok": bool, "reason": String, "specs": {...}, "changed_cells": []}``.
static func derive_specs(document: Dictionary, base_specs: Dictionary,
		event: Dictionary) -> Dictionary:
	var pairs := changed_pairs(event)
	if pairs.is_empty():
		return {"ok": false, "reason": "rewire_invalid", "specs": {}, "changed_cells": []}
	var rewire: Dictionary = event.get("rewire", {})
	var before: Dictionary = pairs.before
	var after: Dictionary = pairs.after
	var record_by_pair := {}
	for record: Dictionary in rewire.get("doorways", []):
		if String(record.get("action", "")) != "opened":
			continue
		record_by_pair[pair_key(String(record.get("cell_a", "")),
			String(record.get("cell_b", "")))] = record
	var cells := REROLL.cells_by_id(document)
	var working := {}
	var changed := {}
	var removed_pairs: Array = []
	var added_pairs: Array = []
	for key: String in before:
		if not after.has(key):
			removed_pairs.append(key)
	for key: String in after:
		if not before.has(key):
			added_pairs.append(key)
	removed_pairs.sort()
	added_pairs.sort()
	for key: String in removed_pairs:
		var pair := pair_cells(key)
		if pair.size() != 2:
			continue
		var left := String(pair[0])
		var right := String(pair[1])
		for side: Array in [[left, right], [right, left]]:
			var cell_id := String(side[0])
			var other := String(side[1])
			if not base_specs.has(cell_id):
				if cells.has(cell_id) and _content_pinned(cells[cell_id]):
					return {"ok": false, "reason": "content_pinned_change",
						"specs": {}, "changed_cells": []}
				return {"ok": false, "reason": "missing_spec", "specs": {},
					"changed_cells": []}
			if not working.has(cell_id):
				working[cell_id] = _copy_spec(base_specs[cell_id])
			var removed := _remove_doorway(working[cell_id], other)
			if removed.is_empty():
				return {"ok": false, "reason": "missing_doorway", "specs": {},
					"changed_cells": []}
			changed[cell_id] = true
	for key: String in added_pairs:
		var pair := pair_cells(key)
		if pair.size() != 2:
			continue
		var left := String(pair[0])
		var right := String(pair[1])
		var event_record: Dictionary = record_by_pair.get(key, {})
		if event_record.is_empty():
			return {"ok": false, "reason": "missing_doorway", "specs": {},
				"changed_cells": []}
		for cell_id: String in [left, right]:
			if not base_specs.has(cell_id):
				if cells.has(cell_id) and _content_pinned(cells[cell_id]):
					return {"ok": false, "reason": "content_pinned_change",
						"specs": {}, "changed_cells": []}
				return {"ok": false, "reason": "missing_spec", "specs": {},
					"changed_cells": []}
			if cells.has(cell_id) and _content_pinned(cells[cell_id]):
				return {"ok": false, "reason": "content_pinned_change",
					"specs": {}, "changed_cells": []}
		for side: Array in [[left, right], [right, left]]:
			var cell_id := String(side[0])
			var other := String(side[1])
			if not working.has(cell_id):
				working[cell_id] = _copy_spec(base_specs[cell_id])
			var record := _doorway_record(cell_id, other, event_record, cells)
			if record.is_empty():
				return {"ok": false, "reason": "geometry_conflict", "specs": {},
					"changed_cells": []}
			if not _add_doorway(working[cell_id], other, record):
				return {"ok": false, "reason": "doorway_conflict", "specs": {},
					"changed_cells": []}
			changed[cell_id] = true
	var result := {}
	var changed_cells: Array = []
	for cell_id: String in working:
		var spec: Dictionary = working[cell_id]
		spec["passage_revision"] = int(base_specs[cell_id].get("passage_revision", 0)) + 1
		result[cell_id] = spec
		changed_cells.append(cell_id)
	changed_cells.sort()
	return {"ok": true, "reason": "", "specs": result, "changed_cells": changed_cells}


## Fields that must not change between the base spec and the derived copy.
static func identity_issues(base: Dictionary, derived: Dictionary) -> Array:
	var issues: Array = []
	var keys := {}
	for key: Variant in base:
		keys[key] = true
	for key: Variant in derived:
		keys[key] = true
	for key: String in keys:
		if ALLOWED_SPEC_FIELDS.has(key):
			continue
		if base.get(key) != derived.get(key):
			issues.append("%s:%s" % [String(derived.get("cell_id", "")), key])
	var base_features: Array = []
	for feature: Dictionary in base.get("features", []):
		if String(feature.get("kind", "")) != "doorway":
			base_features.append(feature)
	var derived_features: Array = []
	for feature: Dictionary in derived.get("features", []):
		if String(feature.get("kind", "")) != "doorway":
			derived_features.append(feature)
	if base_features != derived_features:
		issues.append("%s:features" % String(derived.get("cell_id", "")))
	var base_ports := {}
	for port: String in base.get("degenerate_port_ids", []):
		base_ports[port] = true
	for port: String in derived.get("degenerate_port_ids", []):
		if not base_ports.has(port):
			issues.append("%s:degenerate_port_ids" % String(derived.get("cell_id", "")))
			break
	if int(derived.get("passage_revision", 0)) != \
			int(base.get("passage_revision", 0)) + 1:
		issues.append("%s:passage_revision" % String(derived.get("cell_id", "")))
	return issues


static func _ceiling_height(cell: Dictionary, specs: Dictionary,
		cell_id: String) -> float:
	if specs.has(cell_id):
		var value := float((specs[cell_id] as Dictionary).get("ceiling_height_m", 0.0))
		if value > 0.0:
			return value
	var range_value: Variant = cell.get("ceiling_range_m")
	if range_value is Array and not (range_value as Array).is_empty():
		return float((range_value as Array)[(range_value as Array).size() - 1])
	return 0.0


static func _interval_on_wall(doorway: Dictionary, wall: Dictionary) -> Array:
	var position: Array = doorway.get("pos_xz", [])
	if position.size() != 2:
		return []
	var half := float(doorway.get("width_m", 0.0)) / 2.0
	if String(wall.get("axis", "")) == "x":
		return [float(position[1]) - half, float(position[1]) + half]
	return [float(position[0]) - half, float(position[0]) + half]


static func _overlaps_kept(doorway: Dictionary, cell_id: String,
		other_cell_id: String, specs: Dictionary, wall: Dictionary) -> bool:
	var interval := _interval_on_wall(doorway, wall)
	if interval.is_empty():
		return true
	for spec_cell: String in [cell_id, other_cell_id]:
		if not specs.has(spec_cell):
			continue
		for kept: Dictionary in (specs[spec_cell] as Dictionary).get("doorways", []):
			# Both sides of the new opening belong to the new pair, not to the
			# kept set it has to fit beside.
			var to_cell := String(kept.get("to_cell_id", ""))
			if (spec_cell == cell_id and to_cell == other_cell_id) \
					or (spec_cell == other_cell_id and to_cell == cell_id):
				continue
			var kept_interval := _interval_on_wall(kept, wall)
			if kept_interval.is_empty():
				continue
			var position: Array = kept.get("pos_xz", [])
			if position.size() != 2:
				continue
			var line := float(position[0]) if String(wall.get("axis", "")) == "x" \
				else float(position[1])
			if absf(line - float(wall.get("line", 0.0))) > 0.000001:
				continue
			var separated := float(interval[1]) + DOORWAY_MARGIN_M \
				<= float(kept_interval[0]) or float(kept_interval[1]) \
				+ DOORWAY_MARGIN_M <= float(interval[0])
			if not separated:
				return true
	return false


## Geometry and identity checks for one accepted event. An empty result is a
## valid rebuild; every entry is a named failing check.
static func geometry_issues(document: Dictionary, base_specs: Dictionary,
		derived_specs: Dictionary, event: Dictionary) -> Array:
	var issues: Array = []
	var rewire: Dictionary = event.get("rewire", {})
	var cells := REROLL.cells_by_id(document)
	for cell_id: String in derived_specs:
		issues.append_array(identity_issues(base_specs.get(cell_id, {}),
			derived_specs[cell_id]))
	for record: Dictionary in rewire.get("doorways", []):
		if String(record.get("action", "")) != "opened":
			continue
		var cell_a := String(record.get("cell_a", ""))
		var cell_b := String(record.get("cell_b", ""))
		if not cells.has(cell_a) or not cells.has(cell_b):
			issues.append("missing_cell")
			continue
		var wall: Dictionary = REROLL.shared_wall(cells[cell_a], cells[cell_b])
		if wall.is_empty() or float(wall.length_m) + EPSILON < REROLL.MIN_SHARED_WALL_M:
			issues.append("wall_too_short:%s|%s" % [cell_a, cell_b])
			continue
		if _content_pinned(cells[cell_a]) or _content_pinned(cells[cell_b]):
			issues.append("content_pinned_change:%s|%s" % [cell_a, cell_b])
			continue
		var width := float(record.get("width_m", DOOR_WIDTH_M))
		var center: Array = record.get("center_xz", [])
		if center.size() != 2 or width <= 0.0:
			issues.append("doorway_invalid:%s|%s" % [cell_a, cell_b])
			continue
		var low := float(wall.start) + DOORWAY_MARGIN_M + width / 2.0
		var high := float(wall.end) - DOORWAY_MARGIN_M - width / 2.0
		var along := float(center[1]) if String(wall.axis) == "x" else float(center[0])
		if low > high + EPSILON or along < low - EPSILON or along > high + EPSILON:
			issues.append("doorway_outside_wall:%s|%s" % [cell_a, cell_b])
			continue
		var height := float(record.get("height_m", DOOR_HEIGHT_M))
		for cell_id: String in [cell_a, cell_b]:
			var ceiling := _ceiling_height(cells[cell_id], derived_specs, cell_id)
			if ceiling > 0.0 and height + MIN_CEILING_CLEARANCE_M > ceiling:
				issues.append("doorway_too_tall:%s|%s" % [cell_a, cell_b])
				break
		for cell_id: String in [cell_a, cell_b]:
			if not derived_specs.has(cell_id):
				issues.append("missing_spec:%s" % cell_id)
				continue
			var other := cell_b if cell_id == cell_a else cell_a
			var normal := wall_normal(cells[cell_id], cells[other], wall)
			if normal.is_empty():
				issues.append("missing_normal:%s" % cell_id)
				continue
			var found := false
			for doorway: Dictionary in (derived_specs[cell_id] as Dictionary).get("doorways", []):
				if String(doorway.get("port_id", "")) != port_id(cell_id, other):
					continue
				found = true
				if _overlaps_kept(doorway, cell_id, other, derived_specs, wall):
					issues.append("doorway_overlap:%s|%s" % [cell_a, cell_b])
			if not found:
				issues.append("missing_doorway:%s" % cell_id)
	return issues


## Refuse a stale event and apply its stored passage delta in order.
static func apply_event_to_state(state: Dictionary, event: Dictionary) -> Dictionary:
	var rewire: Variant = event.get("rewire")
	if not (rewire is Dictionary):
		return {"ok": false, "reason": "rewire_invalid", "state": state}
	var block: Dictionary = rewire
	if String(block.get("algorithm_version", "")) != ALGORITHM_VERSION:
		return {"ok": false, "reason": "unsupported_algorithm", "state": state}
	var target := {}
	for cell_id: String in block.get("target_cells", []):
		target[cell_id] = true
	var before := {}
	for pair: Variant in block.get("passages_before", []):
		if pair is Array and (pair as Array).size() == 2:
			before[pair_key(String(pair[0]), String(pair[1]))] = true
	var after := {}
	for pair: Variant in block.get("passages_after", []):
		if pair is Array and (pair as Array).size() == 2:
			after[pair_key(String(pair[0]), String(pair[1]))] = true
	var current := {}
	for key: String in state:
		var pair := pair_cells(key)
		if pair.size() == 2 and target.has(String(pair[0])) and target.has(String(pair[1])):
			current[key] = true
	if current != before:
		return {"ok": false, "reason": "passages_before_mismatch", "state": state}
	var result := state.duplicate(true)
	for key: String in before:
		if not after.has(key):
			result.erase(key)
	for key: String in after:
		if not before.has(key):
			result[key] = {"vertical": "level"}
	return {"ok": true, "reason": "", "state": result}


static func state_hash(state: Dictionary, revisions: Dictionary, branch_epoch: int,
		reroll_serial: int) -> String:
	var keys: Array = state.keys()
	keys.sort()
	var payload := STATE_HASH_PREFIX + "\n"
	payload += "branch_epoch=%d\n" % branch_epoch
	payload += "reroll_serial=%d\n" % reroll_serial
	for key: String in keys:
		payload += "%s=%s\n" % [key, String((state[key] as Dictionary).get(
			"vertical", "level"))]
	var cells: Array = revisions.keys()
	cells.sort()
	for cell_id: String in cells:
		payload += "%s=%d\n" % [cell_id, int(revisions[cell_id])]
	return payload.sha256_text()


## Compact doorway projection for fixtures and evidence (same shape as the
## Python reference).
static func spec_projection(spec: Dictionary) -> Dictionary:
	var doorways: Array = []
	var sorted_doorways: Array = (spec.get("doorways", []) as Array).duplicate()
	sorted_doorways.sort_custom(func(first: Dictionary, second: Dictionary) -> bool:
		return String(first.get("port_id", "")) < String(second.get("port_id", "")))
	for doorway: Dictionary in sorted_doorways:
		var position: Array = []
		for value: Variant in doorway.get("pos_xz", []):
			position.append(float(value))
		var normal: Array = []
		for value: Variant in doorway.get("normal", []):
			normal.append(float(value))
		doorways.append({
			"port_id": String(doorway.get("port_id", "")),
			"to_cell_id": String(doorway.get("to_cell_id", "")),
			"pos_xz": position,
			"normal": normal,
			"width_m": float(doorway.get("width_m", 0.0)),
			"height_m": float(doorway.get("height_m", 0.0)),
			"kind": String(doorway.get("kind", "")),
			"sill_height_m": float(doorway.get("sill_height_m", 0.0)),
			INTERNAL_FLAG: bool(doorway.get(INTERNAL_FLAG, false)),
		})
	return {
		"cell_id": String(spec.get("cell_id", "")),
		"passage_revision": int(spec.get("passage_revision", 0)),
		"doorways": doorways,
	}


static func revision_map(base_specs: Dictionary, derived_specs: Dictionary,
		previous: Dictionary) -> Dictionary:
	var result := previous.duplicate(true)
	for cell_id: String in derived_specs:
		result[cell_id] = int((derived_specs[cell_id] as Dictionary).get(
			"passage_revision", 0))
	return result
