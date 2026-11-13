extends SceneTree

## Headless M5 ``rewire-1`` golden-fixture and parity test (#235).
## godot4 --headless --path godot_walk --script res://scripts/test_issue235_reroll.gd \
##   [--out=res://evidence/<dir>/parity.json]

const REROLL := preload("res://scripts/maze_reroll.gd")
const FIXTURE_PATH := "res://fixtures/maze_reroll_v1.json"

var failures: Array[String] = []
var fixture: Dictionary = {}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	fixture = _load_json(FIXTURE_PATH)
	if fixture.is_empty():
		_fail("cannot load the shared re-roll fixture")
		_finish()
		return
	var report := {
		"algorithm_version": String(fixture.get("algorithm_version", "")),
		"parity": _check_parity_cases(),
		"directions": _check_directions(),
		"worked_example": _check_worked_example(),
		"failures": failures,
	}
	report["summary"] = _summary()
	_write_report(report)
	_finish()


func _check_parity_cases() -> Array:
	var results: Array = []
	for case: Dictionary in fixture.get("parity_cases", []):
		var document := _load_map(String(case.map_id))
		if document.is_empty():
			continue
		var actual := REROLL.projection(REROLL.plan(
			document, String(case.from_cell), String(case.to_cell), int(case.event_index)))
		var expected: Dictionary = case.expected
		_expect(_normalized_text(actual) == _normalized_text(expected),
			"parity case %s differs from the Python projection" % String(case.name))
		if _normalized_text(actual) != _normalized_text(expected):
			printerr("EXPECTED: " + _normalized_text(expected))
			printerr("ACTUAL:   " + _normalized_text(actual))
		results.append({
			"name": String(case.name),
			"ok": bool(actual.get("ok", false)),
			"candidate_count": int(actual.get("candidate_count", 0)),
			"shortlist_size": int(actual.get("shortlist_size", 0)),
			"chosen_rank": int(actual.get("chosen_rank", 0)),
		})
	return results


func _check_directions() -> Array:
	var results: Array = []
	for seed_key: String in fixture.get("maps", {}).keys():
		var expected_map: Dictionary = fixture.maps[seed_key]
		var document := _load_map(String(expected_map.map_id))
		if document.is_empty():
			continue
		var actual_directions: Array = []
		for expected: Dictionary in expected_map.get("directions", []):
			var actual := REROLL.direction_report(document,
				String(expected.from_cell), String(expected.to_cell))
			actual_directions.append(actual)
			_expect(_normalized_text(actual) == _normalized_text(expected),
				"seed %s direction %s->%s differs from the fixture" % [
					seed_key, String(expected.from_cell), String(expected.to_cell)])
		var pools := 0
		var spawn_pinned_pools := 0
		for direction: Dictionary in actual_directions:
			if int(direction.in_tolerance) >= REROLL.MIN_REROLL_ALTERNATIVES:
				pools += 1
				if not bool(direction.spawn_in_target):
					spawn_pinned_pools += 1
		_expect(actual_directions.size() == int(expected_map.direction_count),
			"seed %s direction count differs" % seed_key)
		_expect(pools == int(expected_map.directions_with_pool),
			"seed %s pool count differs" % seed_key)
		_expect(spawn_pinned_pools == int(expected_map.spawn_pinned_pool_directions),
			"seed %s spawn-pinned pool count differs" % seed_key)
		results.append({
			"seed": int(seed_key),
			"directions": actual_directions.size(),
			"directions_with_pool": pools,
			"spawn_pinned_pool_directions": spawn_pinned_pools,
		})
	return results


func _check_worked_example() -> Dictionary:
	var expected: Dictionary = fixture.worked_example
	var document := _load_map("gmap-32-gmap-0.13.0")
	var plan := REROLL.plan(document, String(expected.from_cell), String(expected.to_cell),
		int(expected.event_index))
	var hard := 0
	for candidate: Dictionary in plan.get("candidates", []):
		hard += 1
	_expect(hard == (expected.candidates as Array).size(),
		"the seed 32 hard candidate count differs")
	_expect((plan.get("shortlist", []) as Array).size() == (expected.shortlist as Array).size(),
		"the seed 32 shortlist size differs")
	_expect(int(plan.get("chosen_rank", 0)) == int(expected.chosen_rank),
		"the seed 32 chosen rank differs")
	var names := _candidate_names(plan)
	var shortlist_names: Array = []
	for candidate: Dictionary in plan.get("shortlist", []):
		shortlist_names.append(String(names.get(String(candidate.key), "")))
	_expect(shortlist_names == expected.shortlist,
		"the seed 32 shortlist names differ: %s" % str(shortlist_names))
	var chosen_name := String(names.get(String((plan.get("chosen", {}) as Dictionary).get("key", "")), ""))
	_expect(chosen_name == String(expected.chosen),
		"the seed 32 chosen candidate differs: %s" % chosen_name)
	return {
		"hard_valid": hard,
		"shortlist": shortlist_names,
		"chosen": chosen_name,
		"chosen_rank": int(plan.get("chosen_rank", 0)),
	}


func _candidate_names(plan: Dictionary) -> Dictionary:
	var names := {}
	var index := 0
	for candidate: Dictionary in plan.get("candidates", []):
		index += 1
		names[String(candidate.key)] = "C%d" % index
	return names


func _summary() -> Dictionary:
	var directions := 0
	var pools := 0
	var spawn_pinned := 0
	for seed_key: String in fixture.get("maps", {}).keys():
		var record: Dictionary = fixture.maps[seed_key]
		directions += int(record.direction_count)
		pools += int(record.directions_with_pool)
		spawn_pinned += int(record.spawn_pinned_pool_directions)
	return {
		"directions": directions,
		"directions_with_pool": pools,
		"spawn_pinned_pool_directions": spawn_pinned,
		"seed_3_directions": int(fixture.maps["3"].direction_count),
		"seed_279_rich_hard": int(fixture.summary.seed_279_rich_hard),
		"seed_279_rich_in_tolerance": int(fixture.summary.seed_279_rich_in_tolerance),
		"seed_32_chosen": String(fixture.worked_example.chosen),
	}


func _finish() -> void:
	var summary: Dictionary = _summary()
	print("ISSUE235_REROLL: %s directions=%d pool=%d spawn_pinned=%d seed279_hard=%d seed279_shortlist=%d seed32_chosen=%s" % [
		"PASS" if failures.is_empty() else "FAIL",
		int(summary.directions), int(summary.directions_with_pool),
		int(summary.spawn_pinned_pool_directions), int(summary.seed_279_rich_hard),
		int(fixture.seed_279_rich.shortlist_size), String(summary.seed_32_chosen)])
	quit(0 if failures.is_empty() else 1)


func _load_map(map_id: String) -> Dictionary:
	return _load_json("res://room_catalog/generative_maps/%s.json" % map_id)


func _load_json(path: String) -> Dictionary:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		_fail("cannot read " + path)
		return {}
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		_fail("not a JSON object: " + path)
		return {}
	return parsed


func _normalized_text(value: Variant) -> String:
	return JSON.stringify(_normalize_numbers(value), "", true)


func _normalize_numbers(value: Variant) -> Variant:
	if value is float:
		var number := float(value)
		return int(number) if number == floorf(number) else number
	if value is Array:
		var items: Array = []
		for item: Variant in value:
			items.append(_normalize_numbers(item))
		return items
	if value is Dictionary:
		var result := {}
		for key: Variant in value:
			result[key] = _normalize_numbers(value[key])
		return result
	return value


func _write_report(report: Dictionary) -> void:
	var out := ""
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			out = argument.trim_prefix("--out=")
	if out.is_empty():
		return
	var text := JSON.stringify(report, "\t", true) + "\n"
	var absolute := ProjectSettings.globalize_path(out)
	if FileAccess.file_exists(absolute) and FileAccess.get_file_as_string(absolute) != text:
		_fail("refusing to overwrite a different parity report: " + out)
		return
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	var file := FileAccess.open(absolute, FileAccess.WRITE)
	if file == null:
		_fail("cannot write parity report: " + out)
		return
	file.store_string(text)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE235_REROLL: " + message)
