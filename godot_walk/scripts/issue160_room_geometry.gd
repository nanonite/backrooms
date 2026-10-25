class_name Issue160RoomGeometry
extends RefCounted


static func add_box(parent: Node3D, label: String, center: Vector3, size: Vector3,
		material: Material, visible: bool = true, collidable: bool = true) -> Node3D:
	var body := StaticBody3D.new() if collidable else Node3D.new()
	body.name = label
	body.position = center
	parent.add_child(body)
	if collidable:
		var collision := CollisionShape3D.new()
		collision.name = "CollisionShape3D"
		var shape := BoxShape3D.new()
		shape.size = size
		collision.shape = shape
		body.add_child(collision)
	if visible:
		var mesh := MeshInstance3D.new()
		mesh.name = "%sVisual" % label
		var box := BoxMesh.new()
		box.size = size
		mesh.mesh = box
		mesh.material_override = material
		body.add_child(mesh)
	return body


static func add_wall_segment(parent: Node3D, label: String, start: Vector2, end: Vector2,
		floor_y: float, height: float, thickness: float, material: Material) -> StaticBody3D:
	var direction := end - start
	var length := direction.length()
	var wall := add_box(parent, label,
		Vector3((start.x + end.x) * 0.5, floor_y + height * 0.5, (start.y + end.y) * 0.5),
		Vector3(length + 0.02, height, thickness), material)
	wall.rotation.y = atan2(-direction.y, direction.x)
	return wall as StaticBody3D


static func add_polygon_slab(parent: Node3D, label: String, polygon: PackedVector2Array,
		y: float, material: Material, faces_up: bool) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	parent.add_child(body)
	var mesh := ArrayMesh.new()
	var vertices := PackedVector3Array()
	var uvs := PackedVector2Array()
	var collision_faces := PackedVector3Array()
	for index in range(1, polygon.size() - 1):
		var points := [polygon[0], polygon[index], polygon[index + 1]]
		if faces_up:
			points.reverse()
		for point: Vector2 in points:
			var vertex := Vector3(point.x, y, point.y)
			vertices.append(vertex)
			uvs.append(Vector2(point.x, point.y))
			collision_faces.append(vertex)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	var visual := MeshInstance3D.new()
	visual.name = "%sVisual" % label
	visual.mesh = mesh
	body.add_child(visual)
	var collision := CollisionShape3D.new()
	collision.name = "CollisionShape3D"
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(collision_faces)
	shape.backface_collision = true
	collision.shape = shape
	body.add_child(collision)
	return body


static func interpolate(start: Vector2, end: Vector2, amount: float) -> Vector2:
	return start.lerp(end, amount)
