class_name ShapeRoomDiagonalPassage
extends RefCounted

## Mitered boundary surfaces for a 0.6.0 diagonal passage; no overlapping end faces.

const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const DIAGONAL := preload("res://scripts/shape_room_diagonal.gd")
const WALL_THICKNESS := 0.16
## The floors of a room and of the passage are thin planes that meet on the doorway line; a sliver of the void shows
## through that seam as black dots. A strip just under the floor, across the seam, fills it with floor material.
const SEAM_STRIP_DEPTH := 0.3
const SEAM_STRIP_DROP := 0.004
const SEAM_STRIP_THICKNESS := 0.05


static func add_visuals(parent: Node3D, context: Dictionary) -> void:
	var ring: Array[Vector2] = context.ring
	var inner := _offset_ring(ring, WALL_THICKNESS)
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var tile := MATERIALS.tile_m(context.materials, "wallpaper")
	for index in ring.size():
		var start := ring[index]
		var finish := ring[(index + 1) % ring.size()]
		var inner_start := inner[index]
		var inner_finish := inner[(index + 1) % inner.size()]
		var length := start.distance_to(finish)
		var gaps := _passage_gaps(start, finish, context.doorways)
		var cursor := 0.0
		for gap: Vector2 in gaps:
			if gap.x > cursor + 0.001:
				_add_segment(surface, start, finish, inner_start, inner_finish, length, cursor, gap.x, context.height, tile)
			cursor = gap.y
		if cursor < length - 0.001:
			_add_segment(surface, start, finish, inner_start, inner_finish, length, cursor, length, context.height, tile)
	var instance := MeshInstance3D.new()
	instance.name = "Wall_PassageMesh"
	instance.mesh = surface.commit()
	instance.material_override = MATERIALS.planar(context.materials, "wallpaper")
	parent.add_child(instance)
	for doorway: Dictionary in context.doorways:
		_add_seam_strip(parent, context, doorway)


static func _add_seam_strip(parent: Node3D, context: Dictionary, doorway: Dictionary) -> void:
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
	var along := float(doorway.width_m) + 2.0 * WALL_THICKNESS
	var instance := MeshInstance3D.new()
	instance.name = "SeamStrip_" + String(doorway.port_id)
	instance.position = Vector3(float(doorway.pos_xz[0]), -SEAM_STRIP_DROP - SEAM_STRIP_THICKNESS / 2.0, float(doorway.pos_xz[1]))
	instance.rotation.y = DIAGONAL.yaw_of(Vector2(-normal.y, normal.x))
	var mesh := BoxMesh.new()
	mesh.size = Vector3(along, SEAM_STRIP_THICKNESS, SEAM_STRIP_DEPTH)
	instance.mesh = mesh
	instance.material_override = MATERIALS.scaled(context.materials, "floor", along, SEAM_STRIP_DEPTH)
	parent.add_child(instance)


static func _offset_ring(ring: Array[Vector2], thickness: float) -> Array[Vector2]:
	var result: Array[Vector2] = []
	for index in ring.size():
		var previous := (ring[index] - ring[(index - 1 + ring.size()) % ring.size()]).normalized()
		var next := (ring[(index + 1) % ring.size()] - ring[index]).normalized()
		var previous_inward := Vector2(-previous.y, previous.x)
		var next_inward := Vector2(-next.y, next.x)
		var p := ring[index] + previous_inward * thickness
		var q := ring[index] + next_inward * thickness
		var distance := (q - p).cross(next) / previous.cross(next)
		result.append(p + previous * distance)
	return result


static func _passage_gaps(start: Vector2, finish: Vector2, doorways: Array[Dictionary]) -> Array[Vector2]:
	var direction := (finish - start).normalized()
	var gaps: Array[Vector2] = []
	for doorway: Dictionary in doorways:
		var position := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		var offset := position - start
		if absf(offset.cross(direction)) > 0.001:
			continue
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		if normal.distance_to(Vector2(direction.y, -direction.x)) > 0.001:
			continue
		var along := offset.dot(direction)
		var half := float(doorway.width_m) / 2.0
		gaps.append(Vector2(maxf(0.0, along - half), minf(start.distance_to(finish), along + half)))
	gaps.sort_custom(func(a: Vector2, b: Vector2) -> bool: return a.x < b.x)
	return gaps


static func _add_segment(surface: SurfaceTool, start: Vector2, finish: Vector2,
		inner_start: Vector2, inner_finish: Vector2, length: float, low: float, high: float,
		height: float, tile: float) -> void:
	var outer_a := start.lerp(finish, low / length)
	var outer_b := start.lerp(finish, high / length)
	var inner_a := inner_start.lerp(inner_finish, low / length)
	var inner_b := inner_start.lerp(inner_finish, high / length)
	var direction := (finish - start).normalized()
	var inward := Vector3(-direction.y, 0.0, direction.x)
	_add_wall_quad(surface, outer_a, outer_b, 0.0, height, low, high, tile, -inward)
	_add_wall_quad(surface, inner_a, inner_b, 0.0, height, low, high, tile, inward)
	_add_top_quad(surface, outer_a, outer_b, inner_b, inner_a, height, tile)


static func _add_wall_quad(surface: SurfaceTool, start: Vector2, finish: Vector2, low_y: float,
		high_y: float, low_u: float, high_u: float, tile: float, normal: Vector3) -> void:
	var points: Array[Vector3] = [Vector3(start.x, low_y, start.y), Vector3(finish.x, low_y, finish.y),
		Vector3(finish.x, high_y, finish.y), Vector3(start.x, high_y, start.y)]
	var uvs: Array[Vector2] = [Vector2(low_u, low_y) / tile, Vector2(high_u, low_y) / tile,
		Vector2(high_u, high_y) / tile, Vector2(low_u, high_y) / tile]
	_add_quad(surface, points, uvs, normal)


static func _add_top_quad(surface: SurfaceTool, outer_a: Vector2, outer_b: Vector2,
		inner_b: Vector2, inner_a: Vector2, y: float, tile: float) -> void:
	var points: Array[Vector3] = [Vector3(outer_a.x, y, outer_a.y), Vector3(outer_b.x, y, outer_b.y),
		Vector3(inner_b.x, y, inner_b.y), Vector3(inner_a.x, y, inner_a.y)]
	var uvs: Array[Vector2] = [Vector2(outer_a.x, outer_a.y) / tile, Vector2(outer_b.x, outer_b.y) / tile,
		Vector2(inner_b.x, inner_b.y) / tile, Vector2(inner_a.x, inner_a.y) / tile]
	_add_quad(surface, points, uvs, Vector3.UP)


static func _add_quad(surface: SurfaceTool, points: Array[Vector3], uvs: Array[Vector2], normal: Vector3) -> void:
	for index in [0, 1, 2, 0, 2, 3]:
		surface.set_normal(normal)
		surface.set_uv(uvs[index])
		surface.add_vertex(points[index])
