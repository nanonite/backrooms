class_name MazeRunSave
extends RefCounted

## Run save, restore and cache-key contract for the M7 overlay slice (#237).
##
## A save is the immutable base identity plus the ordered event log.  It stores
## no candidate pool, no shortlist and no overlay snapshot.  A pending re-roll
## is re-enumerated by ``MazeRewireRuntime.restore_events`` from the accepted
## ``door_lock`` record; once a ``door_reroll`` record exists its stored ``P``
## is the state.
##
## This is the GDScript twin of ``maze_run_save.py``.  The committed map is only
## read; the save file is a separate UTF-8 JSON document.

const SAVE_SCHEMA_VERSION := 1
const SAVE_KIND := "maze-run-save"
const SAVE_VERSION := "maze-run-save-0.1.0"
const CACHE_KEY_VERSION := "maze-room-cache-0.1.0"

const SAVE_FIELDS := ["schema_version", "save_kind", "save_version", "base", "event_log"]
const POOL_FIELDS := ["pool", "pool_hash", "pool_sha256", "candidate_pool",
	"candidate_pool_hash"]


## The stable base block stored in a save; never a pool or overlay hash.
static func base_identity(document: Dictionary, base_map_sha256: String) -> Dictionary:
	var identity := {
		"map_id": String(document.get("map_id", "")),
		"base_map_sha256": base_map_sha256,
		"generator_version": String(document.get("generator_version", "")),
		"seed": int(document.get("seed", 0)),
		"attempt": int(document.get("attempt", 0)),
	}
	var snapshot: Variant = document.get("catalog_snapshot")
	if snapshot is Dictionary and (snapshot as Dictionary).has("sha256"):
		identity["catalog_snapshot_sha256"] = String((snapshot as Dictionary).sha256)
	return identity


## Validate and package a base identity plus an ordered event log.
static func build(base: Dictionary, events: Array) -> Dictionary:
	var normalized: Array = []
	for position in events.size():
		var value: Variant = events[position]
		if not (value is Dictionary):
			return _result(false, "event_not_object", {}, "event %d is not an object" % (position + 1))
		var event: Dictionary = (value as Dictionary).duplicate(true)
		var stored: Variant = event.get("base")
		if stored is Dictionary:
			if not _base_matches(base, stored):
				return _result(false, "base_mismatch", {}, "event %d has another base" % (position + 1))
		else:
			event["base"] = _copy_base(base)
		normalized.append(event)
	var save := {
		"schema_version": SAVE_SCHEMA_VERSION,
		"save_kind": SAVE_KIND,
		"save_version": SAVE_VERSION,
		"base": _copy_base(base),
		"event_log": normalized,
	}
	return validate(save, base)


## Validate a save in memory.  The returned ``save`` is a deep copy on success.
static func validate(save: Variant, base: Dictionary) -> Dictionary:
	if not (save is Dictionary):
		return _result(false, "save_invalid", {}, "save is not an object")
	var document: Dictionary = save
	for key: String in document:
		if not SAVE_FIELDS.has(key):
			var reason := "pool_forbidden" if POOL_FIELDS.has(key) else "save_field_unknown"
			return _result(false, reason, {}, "unexpected save field: %s" % key)
	if int(document.get("schema_version", -1)) != SAVE_SCHEMA_VERSION:
		return _result(false, "schema_version_unsupported", {}, "save schema_version")
	if String(document.get("save_kind", "")) != SAVE_KIND:
		return _result(false, "save_kind_invalid", {}, "save_kind is not maze-run-save")
	if String(document.get("save_version", "")) != SAVE_VERSION:
		return _result(false, "save_version_unsupported", {}, "save_version")
	if not _is_sha256(base.get("base_map_sha256")):
		return _result(false, "base_invalid", {}, "base_map_sha256 is not a file hash")
	var stored_base: Variant = document.get("base")
	if not (stored_base is Dictionary) or not _base_matches(base, stored_base):
		return _result(false, "base_mismatch", {}, "save base does not match the current map")
	var event_log: Variant = document.get("event_log")
	if not (event_log is Array):
		return _result(false, "event_log_invalid", {}, "event_log is not a list")
	var events: Array = event_log
	for position in events.size():
		var reason := _event_error(events[position], base, position + 1)
		if not reason.is_empty():
			return _result(false, reason, {}, "event %d: %s" % [position + 1, reason])
	return _result(true, "", document.duplicate(true), "")


## Read and validate a UTF-8 JSON save file without writing anything.
static func read(path: String, base: Dictionary) -> Dictionary:
	var absolute := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(absolute):
		return _result(false, "save_missing", {}, "save %s does not exist" % path)
	var text := FileAccess.get_file_as_string(absolute)
	if text.is_empty():
		return _result(false, "save_invalid", {}, "save %s is empty" % path)
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		return _result(false, "save_invalid", {}, "save %s is not a JSON object" % path)
	return validate(parsed, base)


## Validate then atomically replace a UTF-8 JSON save file.
static func write(path: String, base: Dictionary, save: Dictionary) -> Dictionary:
	var checked := validate(save, base)
	if not bool(checked.get("ok", false)):
		return checked
	var absolute := ProjectSettings.globalize_path(path)
	if absolute.is_empty():
		return _result(false, "save_invalid", {}, "save path is empty")
	var directory := absolute.get_base_dir()
	if not DirAccess.dir_exists_absolute(directory):
		var made := DirAccess.make_dir_recursive_absolute(directory)
		if made != OK:
			return _result(false, "save_write_failed", {}, "cannot create %s" % directory)
	var temporary := absolute + ".tmp"
	var stream := FileAccess.open(temporary, FileAccess.WRITE)
	if stream == null:
		return _result(false, "save_write_failed", {}, "cannot write %s" % temporary)
	stream.store_string(JSON.stringify(checked.save, "\t", true) + "\n")
	stream.close()
	var renamed := DirAccess.rename_absolute(temporary, absolute)
	if renamed != OK:
		DirAccess.remove_absolute(temporary)
		return _result(false, "save_write_failed", {}, "cannot replace %s" % absolute)
	return _result(true, "", checked.save, "")


static func room_cache_key(base: Dictionary, branch_epoch: int,
		passage_revision: int, content_revision: int, cell_id: String) -> String:
	return "|".join([
		CACHE_KEY_VERSION,
		String(base.get("map_id", "")),
		String(base.get("base_map_sha256", "")),
		str(int(branch_epoch)),
		str(int(passage_revision)),
		str(int(content_revision)),
		cell_id,
	])


static func _event_error(event: Variant, base: Dictionary, expected_index: int) -> String:
	if not (event is Dictionary):
		return "event_not_object"
	var record: Dictionary = event
	if int(record.get("event_index", 0)) != expected_index:
		return "event_order"
	if String(record.get("event_type", "")).is_empty():
		return "event_type_invalid"
	var record_kind := String(record.get("record_kind", ""))
	if record_kind != "trigger" and record_kind != "mutation":
		return "record_kind_invalid"
	var stored: Variant = record.get("base")
	if not (stored is Dictionary) or not _base_matches(base, stored):
		return "base_mismatch"
	if record_kind == "trigger":
		var trigger: Variant = record.get("trigger")
		if not (trigger is Dictionary):
			return "trigger_invalid"
		if not String((trigger as Dictionary).get("kind", "")).is_empty() \
				and String((trigger as Dictionary).kind) != String(record.event_type):
			return "trigger_kind_invalid"
		return ""
	var event_type := String(record.event_type)
	if event_type == "door_reroll":
		var rewire: Variant = record.get("rewire")
		if not (rewire is Dictionary):
			return "rewire_required"
		if String((rewire as Dictionary).get("algorithm_version", "")).is_empty():
			return "rewire_invalid"
	elif event_type == "door_lock" or event_type == "door_unlock":
		var change: Variant = record.get("change")
		if not (change is Dictionary):
			return "change_required"
		if not ("before" in (change as Dictionary)) or not ("after" in (change as Dictionary)):
			return "change_invalid"
	return ""


static func _is_sha256(value: Variant) -> bool:
	if not (value is String):
		return false
	var text: String = value
	return text.length() == 64 and text.is_valid_hex_number()


static func _base_matches(first: Dictionary, second: Dictionary) -> bool:
	for field: String in ["map_id", "base_map_sha256", "generator_version", "seed", "attempt"]:
		if first.get(field) != second.get(field):
			return false
	var snapshot: Variant = second.get("catalog_snapshot_sha256")
	return snapshot == null or snapshot == first.get("catalog_snapshot_sha256")


static func _copy_base(base: Dictionary) -> Dictionary:
	var result := base.duplicate(true)
	return result


static func _result(ok: bool, reason: String, save: Dictionary, message: String) -> Dictionary:
	return {"ok": ok, "reason": reason, "message": message, "save": save}
