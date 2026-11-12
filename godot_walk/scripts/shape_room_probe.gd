class_name ShapeRoomProbe
extends RefCounted

## Physics probes with the player's capsule (radius 0.3, height 1.2, as in player.tscn
## and test_issue165_transfer_room.gd). Floor support is a ray onto a "WalkableFloor" body.

const RADIUS := 0.3
const HEIGHT := 1.2
const CENTER_Y := 0.64
const FLOOR_BODY := "WalkableFloor"
## Floor colliders of library modules placed in a generated map (#188): the source-video
## rooms name theirs "WalkableFloor"; the kit rooms use these.
const MODULE_FLOOR_BODIES := ["AuthoredFloor", "AuthoredPlanarRouteFloor", "ConnectorThreshold"]
const SWEEP_STEP := 0.1


static func cell_floor_y(map_data: Dictionary, cell_id: String) -> float:
	for cell: Dictionary in map_data.cells:
		if String(cell.cell_id) == cell_id:
			return float(cell.get("floor_y", 0.0))
	return 0.0


static func blockers(space: PhysicsDirectSpaceState3D, x: float, z: float, floor_y: float = 0.0) -> Array[String]:
	var shape := CapsuleShape3D.new()
	shape.radius = RADIUS
	shape.height = HEIGHT
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, Vector3(x, floor_y + CENTER_Y, z))
	query.collision_mask = 1
	var names: Array[String] = []
	for result in space.intersect_shape(query, 32):
		var collider := result.get("collider") as Node
		if collider != null and not is_floor_body(collider):
			names.append(collider.name)
	return names


static func is_floor_body(collider: Node) -> bool:
	return collider.name == FLOOR_BODY or String(collider.name).begins_with("Ramp_") or MODULE_FLOOR_BODIES.has(String(collider.name))


static func floor_supported(space: PhysicsDirectSpaceState3D, x: float, z: float, floor_y: float = 0.0) -> bool:
	var query := PhysicsRayQueryParameters3D.create(Vector3(x, floor_y + 0.45, z), Vector3(x, floor_y - 0.12, z))
	query.collision_mask = 1
	var result := space.intersect_ray(query)
	return not result.is_empty() and is_floor_body(result.collider as Node)


static func clear_and_supported(space: PhysicsDirectSpaceState3D, x: float, z: float, floor_y: float = 0.0) -> bool:
	return blockers(space, x, z, floor_y).is_empty() and floor_supported(space, x, z, floor_y)


## Capsule sweep sampled every 0.1 m: every sample must be unblocked and floor-supported.
static func sweep(space: PhysicsDirectSpaceState3D, from: Vector2, to: Vector2,
		from_floor_y: float = 0.0, to_floor_y: float = 0.0) -> Dictionary:
	var steps := int(ceilf(from.distance_to(to) / SWEEP_STEP))
	for step in steps + 1:
		var fraction := float(step) / float(steps)
		var point := from.lerp(to, fraction)
		var floor_y := lerpf(from_floor_y, to_floor_y, fraction)
		var hits := blockers(space, point.x, point.y, floor_y)
		if not hits.is_empty():
			return {"passable": false, "at": point, "reason": "blocked by %s" % hits[0]}
		if not floor_supported(space, point.x, point.y, floor_y):
			return {"passable": false, "at": point, "reason": "no floor support"}
	return {"passable": true}


static func sweep_ramp(space: PhysicsDirectSpaceState3D, from: Vector2, to: Vector2,
		lower_door: Vector2, inward: Vector2, lower_floor: float, upper_floor: float,
		run: float, rise: float) -> Dictionary:
	var steps := int(ceilf(from.distance_to(to) / SWEEP_STEP))
	for step in steps + 1:
		var fraction := float(step) / float(steps)
		var point := from.lerp(to, fraction)
		var distance := (point - lower_door).dot(inward)
		var floor_y := upper_floor
		if distance >= 0.0:
			floor_y = lower_floor + rise * (1.0 - clampf(distance / run, 0.0, 1.0))
		var hits := blockers(space, point.x, point.y, floor_y)
		if not hits.is_empty():
			return {"passable": false, "at": point, "reason": "blocked by %s" % hits[0]}
		if not floor_supported(space, point.x, point.y, floor_y):
			return {"passable": false, "at": point, "reason": "no floor support"}
	return {"passable": true}


## A ledge drop crosses the opening at the upper floor before the capsule falls and lands.
static func sweep_drop(space: PhysicsDirectSpaceState3D, from: Vector2, to: Vector2,
		upper_floor: float, lower_floor: float) -> Dictionary:
	var steps := int(ceilf(from.distance_to(to) / SWEEP_STEP))
	for step in steps + 1:
		var point := from.lerp(to, float(step) / float(steps))
		var hits := blockers(space, point.x, point.y, upper_floor)
		if not hits.is_empty():
			return {"passable": false, "at": point, "reason": "blocked by %s" % hits[0]}
	var landing_hits := blockers(space, to.x, to.y, lower_floor)
	if not landing_hits.is_empty():
		return {"passable": false, "at": to, "reason": "blocked by %s" % landing_hits[0]}
	if not floor_supported(space, to.x, to.y, lower_floor):
		return {"passable": false, "at": to, "reason": "no floor support"}
	return {"passable": true}


static func inside_polygon(point: Vector2, polygon: Array[Vector2]) -> bool:
	var inside := false
	var previous := polygon.size() - 1
	for index in polygon.size():
		var a := polygon[index]
		var b := polygon[previous]
		if (a.y > point.y) != (b.y > point.y):
			if point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x:
				inside = not inside
		previous = index
	return inside
