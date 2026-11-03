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


static func blockers(space: PhysicsDirectSpaceState3D, x: float, z: float) -> Array[String]:
	var shape := CapsuleShape3D.new()
	shape.radius = RADIUS
	shape.height = HEIGHT
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, Vector3(x, CENTER_Y, z))
	query.collision_mask = 1
	var names: Array[String] = []
	for result in space.intersect_shape(query, 32):
		var collider := result.get("collider") as Node
		if collider != null and not is_floor_body(collider):
			names.append(collider.name)
	return names


static func is_floor_body(collider: Node) -> bool:
	return collider.name == FLOOR_BODY or MODULE_FLOOR_BODIES.has(String(collider.name))


static func floor_supported(space: PhysicsDirectSpaceState3D, x: float, z: float) -> bool:
	var query := PhysicsRayQueryParameters3D.create(Vector3(x, 0.45, z), Vector3(x, -0.12, z))
	query.collision_mask = 1
	var result := space.intersect_ray(query)
	return not result.is_empty() and is_floor_body(result.collider as Node)


static func clear_and_supported(space: PhysicsDirectSpaceState3D, x: float, z: float) -> bool:
	return blockers(space, x, z).is_empty() and floor_supported(space, x, z)


## Capsule sweep sampled every 0.1 m: every sample must be unblocked and floor-supported.
static func sweep(space: PhysicsDirectSpaceState3D, from: Vector2, to: Vector2) -> Dictionary:
	var steps := int(ceilf(from.distance_to(to) / SWEEP_STEP))
	for step in steps + 1:
		var point := from.lerp(to, float(step) / float(steps))
		var hits := blockers(space, point.x, point.y)
		if not hits.is_empty():
			return {"passable": false, "at": point, "reason": "blocked by %s" % hits[0]}
		if not floor_supported(space, point.x, point.y):
			return {"passable": false, "at": point, "reason": "no floor support"}
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
