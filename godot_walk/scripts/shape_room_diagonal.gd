class_name ShapeRoomDiagonal
extends RefCounted

## 45-degree rooms and gmap-0.6.0 diagonal passages: triangulated floor/ceiling and rotated wall boxes.
##
## Joints. Every wall box has square ends and stands inside the outline, thickness inward. At a convex
## joint (135 degrees at a chamfer, 45 degrees at a wedge tip) each box end lies inside the neighbouring
## box, so the wall band is covered with no gap and no end face is visible; no two visible faces are
## coplanar. A reflex joint would extend by the wall thickness (axis-aligned stage-1 code), but a chamfer
## only ever cuts convex corners. `pullback` shortens a diagonal box at both ends and exists only for the
## "unmitred joint" negative control.

const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const MIN_TRIANGLE_AREA := 0.000001
const FLOOR_OVERLAP_M := 0.02
const MITRE_LIMIT := 4.0
const DIAGONAL_MIN := 0.01


static func is_chamfered(spec: Dictionary) -> bool:
	return (spec.has("chamfers") and not spec.chamfers.is_empty()) or spec.has("diagonal_passage")


## True when the unit direction is neither horizontal nor vertical.
static func is_diagonal(direction: Vector2) -> bool:
	return minf(absf(direction.x), absf(direction.y)) > DIAGONAL_MIN


## Yaw that turns a box's local +X onto the xz direction.
static func yaw_of(direction: Vector2) -> float:
	return atan2(-direction.y, direction.x)


## Triangles of the outline as arrays of three Vector2 (empty when the outline cannot be triangulated).
static func triangles(ring: Array[Vector2]) -> Array[PackedVector2Array]:
	var found: Array[PackedVector2Array] = []
	var indices := Geometry2D.triangulate_polygon(PackedVector2Array(ring))
	for first in range(0, indices.size(), 3):
		var tri := PackedVector2Array([ring[indices[first]], ring[indices[first + 1]], ring[indices[first + 2]]])
		if absf((tri[1] - tri[0]).cross(tri[2] - tri[0])) * 0.5 > MIN_TRIANGLE_AREA:
			found.append(tri)
	return found


## Floor collision: one convex prism per triangle, each grown FLOOR_OVERLAP_M in plane. Triangles that
## only share an edge leave a slit that a ray or a foot exactly on the edge slips through (a triangle
## mesh does too: a headless run of the dense floor check missed 41 of 43831 samples). With the overlap
## every interior point lies inside at least one prism; the outer boundary grows by 2 cm, which lies
## under a wall or outside the room, never in walkable space.
static func add_floor(floor_visual: Node3D, body: StaticBody3D, context: Dictionary, thickness: float) -> void:
	var tris := triangles(context.ring)
	_add_plane(floor_visual, "FloorPolygon", tris, 0.0, Vector3.UP, MATERIALS.planar(context.materials, "floor"), MATERIALS.tile_m(context.materials, "floor"))
	for index in tris.size():
		var grown := _grown(tris[index])
		var points := PackedVector3Array()
		for corner in grown:
			points.append(Vector3(corner.x, 0.0, corner.y))
			points.append(Vector3(corner.x, -thickness, corner.y))
		var shape := ConvexPolygonShape3D.new()
		shape.points = points
		var collision := CollisionShape3D.new()
		collision.name = "FloorTriangleShape_%03d" % index
		collision.shape = shape
		body.add_child(collision)


## The triangle with every edge moved FLOOR_OVERLAP_M outward (exact mitre; a sharp corner is capped at
## MITRE_LIMIT times the offset). Geometry2D.offset_polygon is not used: its integer rounding moves
## vertices by about 1 cm, as much as the overlap itself.
static func _grown(tri: PackedVector2Array) -> PackedVector2Array:
	var orient := signf((tri[1] - tri[0]).cross(tri[2] - tri[0]))
	var normals: Array[Vector2] = []
	for index in 3:
		var edge := (tri[(index + 1) % 3] - tri[index]).normalized()
		normals.append(Vector2(edge.y, -edge.x) * orient)
	var grown := PackedVector2Array()
	for index in 3:
		var before := normals[(index + 2) % 3]
		var after := normals[index]
		var shift := (before + after) * FLOOR_OVERLAP_M / maxf(1.0 + before.dot(after), 0.0001)
		if shift.length() > FLOOR_OVERLAP_M * MITRE_LIMIT:
			shift = shift.normalized() * FLOOR_OVERLAP_M * MITRE_LIMIT
		grown.append(tri[index] + shift)
	return grown


static func add_ceiling(ceiling: Node3D, context: Dictionary) -> void:
	_add_plane(ceiling, "CeilingPolygon", triangles(context.ring), context.height, Vector3.DOWN,
		MATERIALS.planar(context.materials, "ceiling"), MATERIALS.tile_m(context.materials, "ceiling"))


## One mesh of horizontal triangles at height `y`, wound so the front face looks along `facing`
## (Godot front faces are clockwise); UVs are world metres / tile so the texel density matches boxes.
static func _add_plane(parent: Node3D, label: String, tris: Array[PackedVector2Array], y: float,
		facing: Vector3, material: Material, tile: float) -> void:
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	surface.set_normal(facing)
	for tri in tris:
		var a := Vector3(tri[0].x, y, tri[0].y)
		var b := Vector3(tri[1].x, y, tri[1].y)
		var c := Vector3(tri[2].x, y, tri[2].y)
		if (c - a).cross(b - a).dot(facing) < 0.0:
			var swap := b
			b = c
			c = swap
		for corner in [a, b, c]:
			surface.set_uv(Vector2(corner.x, corner.z) / tile)
			surface.add_vertex(corner)
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.mesh = surface.commit()
	instance.material_override = material
	parent.add_child(instance)
