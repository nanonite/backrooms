extends StaticBody3D

## Static collision built at run time from the mesh #84 generated.
##
## The collision GLB is imported by Godot as a `PackedScene` holding an
## `ArrayMesh`; there is no `.tres` `Shape3D` to reference from the scene file
## without committing a binary resource.  Building the trimesh here keeps the
## scene file readable and the geometry reviewable in the pipeline that produced
## it, at the cost of one `create_trimesh_shape()` at load.
##
## The cost of that choice is that a node existing proves nothing: if the GLB is
## missing, unimported or empty, the body silently has no shape.  Every consumer
## therefore checks :func:`triangle_count` and the physics queries themselves --
## `verify_traversal.gd` in particular asserts what the walker stands on rather
## than that a node is present.

## The collision mesh #84's benchmark produced.  Reproduce with
## `scripts/splat_pipeline/generate_collision.py`; the expected triangle count is
## what distinguishes "the mesh is here" from "a shape exists".
const MESH_PATH := "res://assets/corridor_splat/collision/corridor_splat.collision.glb"

## Triangles the recorded run produced.  Only a warning when it does not match:
## a re-voxelised capture legitimately differs, and the walk test's own
## assertions are the real gate.
const EXPECTED_TRIANGLES := 10178

var triangle_count: int = 0
var load_error: String = ""


func _ready() -> void:
	triangle_count = 0
	load_error = ""
	if get_node_or_null("CollisionShape3D") != null:
		return
	var mesh := _load_mesh()
	if mesh == null:
		push_error("GeneratedCollision: %s" % load_error)
		return
	var shape := mesh.create_trimesh_shape()
	if shape == null:
		load_error = "%s produced no triangle mesh" % MESH_PATH
		push_error("GeneratedCollision: %s" % load_error)
		return
	# The generated shell is a boolean difference -- outer surface minus carved
	# cavity -- and #84 measured only 81.8% of its faces winding toward
	# navigable space.  One-sided collision on that mesh would let the player
	# pass through the 18% that face the other way, so collision is two-sided.
	# #84's winding measurement stays the check that the mesh is sane; this is
	# what stops a known-uneven winding from becoming a fall-through.
	shape.backface_collision = true
	var node := CollisionShape3D.new()
	node.name = "CollisionShape3D"
	node.shape = shape
	add_child(node)
	triangle_count = _triangle_count(mesh)
	if triangle_count != EXPECTED_TRIANGLES:
		push_warning(
			"GeneratedCollision: %s has %d triangles, the recorded run produced %d"
			% [MESH_PATH, triangle_count, EXPECTED_TRIANGLES]
		)


func has_collision() -> bool:
	## Whether a triangle shape is actually attached, not merely whether the node is.
	return triangle_count > 0


func _load_mesh() -> ArrayMesh:
	var scene: PackedScene = load(MESH_PATH)
	if scene == null:
		load_error = "could not load %s; run the Godot import pass first" % MESH_PATH
		return null
	var instance := scene.instantiate()
	if instance == null:
		load_error = "could not instantiate %s" % MESH_PATH
		return null
	var mesh := _first_mesh(instance)
	instance.free()
	if mesh == null:
		load_error = "%s contains no MeshInstance3D" % MESH_PATH
	return mesh


func _first_mesh(node: Node) -> ArrayMesh:
	for child in node.get_children():
		if child is MeshInstance3D:
			var mesh: ArrayMesh = (child as MeshInstance3D).mesh
			if mesh != null:
				return mesh
		var found := _first_mesh(child)
		if found != null:
			return found
	return null


func _triangle_count(mesh: ArrayMesh) -> int:
	var total := 0
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		if arrays.size() == 0:
			continue
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		if indices.size() > 0:
			total += indices.size() / 3
		else:
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			total += vertices.size() / 3
	return total
