class_name MazeRoomCache
extends RefCounted

## Revision-aware room cache for the M7 overlay slice (#237).
##
## The key includes the base identity, ``branch_epoch``, ``passage_revision``,
## ``content_revision`` and the stable cell ID.  A cell whose passage revision
## changed is a cache miss even though its ID and every non-doorway field are
## unchanged.  This is the contract #162's streamer will use; the current
## runtime fills it while replaying a re-roll and never serves a stale revision.

const VERSION := "maze-room-cache-0.1.0"

var entries: Dictionary = {}
var hits := 0
var misses := 0


static func key_for(base: Dictionary, branch_epoch: int,
		passage_revision: int, content_revision: int, cell_id: String) -> String:
	return "|".join([
		VERSION,
		String(base.get("map_id", "")),
		String(base.get("base_map_sha256", "")),
		str(int(branch_epoch)),
		str(int(passage_revision)),
		str(int(content_revision)),
		cell_id,
	])


func get_value(key: String) -> Variant:
	if not entries.has(key):
		misses += 1
		return null
	hits += 1
	return entries[key]


func put(key: String, value: Variant) -> void:
	entries[key] = value


func has(key: String) -> bool:
	return entries.has(key)


func clear() -> void:
	entries.clear()


func stats() -> Dictionary:
	return {
		"version": VERSION,
		"entries": entries.size(),
		"hits": hits,
		"misses": misses,
	}
