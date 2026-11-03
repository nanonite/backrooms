class_name DoorwaySizes
extends RefCounted

## Doorway clear size per connector compatibility type. Same table as
## scripts/doorway_sizes.py (a Python test compares the two). Value: Vector2(width_m, height_m).

const DEFAULT_TYPE := "level_doorway_2m_v1"
const SIZES := {
	"level_doorway_2m_v1": Vector2(2.0, 2.1),
	"authored_direct_doorway_2.4x2.2_v1": Vector2(2.4, 2.2),
}


## Clear size of a doorway record; specs without a compatibility_type use the default type.
static func size_of(doorway: Dictionary) -> Vector2:
	var type := String(doorway.get("compatibility_type", DEFAULT_TYPE))
	if not SIZES.has(type):
		push_error("No doorway size for compatibility type %s" % type)
		return SIZES[DEFAULT_TYPE]
	return SIZES[type]
