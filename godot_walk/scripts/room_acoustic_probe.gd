class_name RoomAcousticProbe
extends Node

## Ray-cast room-acoustics probe for the generated walkthrough (#205).
##
## Casts a horizontal fan of `RAY_COUNT` rays plus one up ray from the listener's
## head. The rays use the same physics world and collision layer as the footstep
## floor ray (layer 1), so walls, floors and any collidable ceiling or library
## geometry answer them. Metrics only; audible output is the reverb bus's job.
##
## The query object and direction table are created once. A probe therefore
## allocates no query resources at its roughly 4 Hz cadence, and it never runs
## per frame.

const RAY_COUNT := 12
const RAY_LENGTH_M := 20.0
const COLLISION_MASK := 1
const SPEED_OF_SOUND_MPS := 343.0
const MIN_PREDELAY_MSEC := 1.0
const MAX_PREDELAY_MSEC := 50.0
const ROOM_SIZE_REFERENCE_M := 10.0
const CEILING_LOW_M := 2.2
const CEILING_HIGH_M := 6.0

## Latest measured enclosure metrics, replaced on every sample.
var metrics: Dictionary = {
	"mean_distance_m": 0.0,
	"max_distance_m": 0.0,
	"ceiling_height_m": 0.0,
	"openness": 0.0,
}
## Latest mapping result; the reverb bus consumes this dictionary.
var parameters: Dictionary = {
	"room_size": 0.0,
	"damping": 0.0,
	"wet": 0.0,
	"predelay_msec": MIN_PREDELAY_MSEC,
}

var _query := PhysicsRayQueryParameters3D.new()
var _directions: Array[Vector3] = []


func _init() -> void:
	_query.collision_mask = COLLISION_MASK
	_query.collide_with_areas = false
	_query.collide_with_bodies = true
	for index in RAY_COUNT:
		var angle := TAU * float(index) / float(RAY_COUNT)
		_directions.append(Vector3(cos(angle), 0.0, sin(angle)))


## Measure the room around `head_origin` and update `metrics` / `parameters`.
## `floor_y` turns the up-ray clearance into a ceiling height; `exclude` should
## contain the listener's own body RID so the fan does not hit the player.
## `ceiling_hint_m` caps a missed up ray at the authored ceiling, because
## generated room ceilings are rendered without collision.
func sample(
	space_state: PhysicsDirectSpaceState3D,
	head_origin: Vector3,
	floor_y: float,
	exclude: Array[RID],
	ceiling_hint_m: float = 0.0
) -> Dictionary:
	_query.exclude = exclude
	var fan := _horizontal_fan(space_state, head_origin)
	metrics = {
		"mean_distance_m": fan.mean,
		"max_distance_m": fan.maximum,
		"ceiling_height_m": _ceiling_height(space_state, head_origin, floor_y, ceiling_hint_m),
		"openness": fan.openness,
	}
	parameters = map_metrics(metrics)
	return parameters


func _horizontal_fan(space_state: PhysicsDirectSpaceState3D, head_origin: Vector3) -> Dictionary:
	var total := 0.0
	var maximum := 0.0
	var misses := 0
	for direction: Vector3 in _directions:
		var distance := _cast(space_state, head_origin, head_origin + direction * RAY_LENGTH_M)
		if distance < 0.0:
			distance = RAY_LENGTH_M
			misses += 1
		total += distance
		maximum = maxf(maximum, distance)
	return {
		"mean": total / float(RAY_COUNT),
		"maximum": maximum,
		"openness": float(misses) / float(RAY_COUNT),
	}


func _ceiling_height(
	space_state: PhysicsDirectSpaceState3D,
	head_origin: Vector3,
	floor_y: float,
	ceiling_hint_m: float
) -> float:
	var up_distance := _cast(space_state, head_origin, head_origin + Vector3.UP * RAY_LENGTH_M)
	if up_distance < 0.0:
		up_distance = RAY_LENGTH_M
	var height := maxf(head_origin.y - floor_y, 0.0) + up_distance
	if ceiling_hint_m > 0.0:
		height = minf(height, ceiling_hint_m)
	return height


## Pure enclosure-to-reverb mapping. Larger and taller enclosed spaces get a
## larger room, a longer pre-delay and a somewhat wetter, duller tail. Open
## space keeps some size but loses wet level, so a doorway does not turn the
## world into a cathedral.
static func map_metrics(enclosure: Dictionary) -> Dictionary:
	var mean_distance := clampf(float(enclosure.get("mean_distance_m", 0.0)), 0.0, RAY_LENGTH_M)
	var ceiling_height := clampf(float(enclosure.get("ceiling_height_m", CEILING_LOW_M)), 0.0, RAY_LENGTH_M)
	var openness := clampf(float(enclosure.get("openness", 0.0)), 0.0, 1.0)
	var wall_size := clampf(mean_distance / ROOM_SIZE_REFERENCE_M, 0.0, 1.0)
	var height_size := clampf(
		(ceiling_height - CEILING_LOW_M) / (CEILING_HIGH_M - CEILING_LOW_M), 0.0, 1.0)
	var room_size := clampf(0.10 + 0.78 * wall_size + 0.12 * height_size, 0.0, 1.0)
	var damping := clampf(
		0.22 + 0.48 * wall_size + 0.18 * height_size + 0.12 * openness, 0.0, 1.0)
	var wet := clampf(
		(0.18 + 0.48 * wall_size + 0.14 * height_size) * (1.0 - 0.35 * openness),
		0.0, 0.75)
	var predelay := clampf(
		mean_distance / SPEED_OF_SOUND_MPS * 1000.0, MIN_PREDELAY_MSEC, MAX_PREDELAY_MSEC)
	return {
		"room_size": room_size,
		"damping": damping,
		"wet": wet,
		"predelay_msec": predelay,
	}


func _cast(space_state: PhysicsDirectSpaceState3D, from: Vector3, to: Vector3) -> float:
	_query.from = from
	_query.to = to
	var hit := space_state.intersect_ray(_query)
	if hit.is_empty():
		return -1.0
	var position: Vector3 = hit.position
	return (position - from).length()
