extends SceneTree

const CORRIDOR_SCENE := "res://scenes/corridor.tscn"
const IMPORT_TEST_SCENE := "res://scenes/import_test.tscn"
const PLAYER_SCENE := "res://scenes/player.tscn"

## Static bodies corridor.tscn must carry. `GeneratedCollision` is the mesh #84
## produced and is the only body that supports the player; `SafetyNet` is a
## diagnostic failsafe that must never be stood on.
const REQUIRED_BODIES := ["GeneratedCollision", "SafetyNet"]

## How far the spawn ray reaches before "there is no floor" is the answer.  Long
## enough to pass through the capsule and the clearance under it, short enough not
## to find the safety net below and mistake it for floor.
const SPAWN_RAY_REACH := 1.5

## Slack on "the capsule bottom is above the floor".  Godot resolves an initial
## overlap by pushing the body out, so a millimetre of float error is not a
## defect; 0.1 m of overlap is the failure this is here to catch.
const OVERLAP_TOLERANCE := 0.02

## Largest drop the spawn may have onto the generated floor, in metres.  The
## contract's marker is 0.5 m above its own floor plane; a generated surface far
## below that would mean the collision and the contract describe different rooms.
const MAX_SPAWN_DROP := 1.0

## Uses `_initialize`, not `_init`: nodes only get valid `global_transform` values
## once the tree is running. Reading them during construction returns identity while
## printing engine errors, which silently turns a world-space measurement into a
## local one.
func _initialize() -> void:
	var ok := _verify_import_test()
	ok = await _verify_corridor_collider() and ok
	quit(0 if ok else 1)


func _verify_import_test() -> bool:
	var instance := _instantiate_scene(IMPORT_TEST_SCENE)
	if instance == null:
		return false

	var walker := instance.get_node_or_null("TestWalker")
	var room := instance.get_node_or_null("Room")
	if walker == null:
		printerr("FAIL: TestWalker node not found")
		return false
	if room == null:
		printerr("FAIL: Room node not found")
		return false

	root.add_child(instance)
	var counts := _count_recursive(instance)
	var ok := _require_count(counts, "mesh", "no MeshInstance3D found in Room")
	ok = _require_count(counts, "static", "no StaticBody3D found -- collision not generated") and ok
	ok = _require_count(counts, "shape", "no CollisionShape3D found -- collision shapes missing") and ok
	if ok:
		print("OK: import_test mesh=%d static=%d shape=%d" % [counts["mesh"], counts["static"], counts["shape"]])
	return ok


func _verify_corridor_collider() -> bool:
	var instance := _instantiate_scene(CORRIDOR_SCENE)
	if instance == null:
		return false

	# Capture the authored spawn/player positions *before* the scene enters the
	# tree. Once inside, the player is a CharacterBody3D under gravity and has
	# already fallen a few millimetres by the time anything is read, so any later
	# comparison measures gravity rather than the scene's authoring.
	var authored_spawn := _authored_origin(instance, "PlayerSpawn")
	var authored_player := _authored_origin(instance, "Player")

	root.add_child(instance)
	# Await a frame so nodes are actually inside the tree; reading
	# global_transform before that returns identity and prints engine errors.
	await process_frame
	var ok := _verify_bodies(instance)
	ok = _verify_collision_has_geometry(instance) and ok
	ok = _verify_player_capsule_matches_disk(instance) and ok
	ok = _verify_spawn_placement(instance, authored_spawn, authored_player) and ok
	if ok:
		print("OK: corridor collision bodies=%s spawn=%s"
			% [str(REQUIRED_BODIES), str(authored_spawn)])
	return ok


func _verify_bodies(instance: Node) -> bool:
	var ok := true
	for body_name: String in REQUIRED_BODIES:
		var body := instance.get_node_or_null(body_name)
		if body == null or not body is StaticBody3D:
			printerr("FAIL: corridor body missing or not static: %s" % body_name)
			ok = false
	return ok


func _verify_collision_has_geometry(instance: Node) -> bool:
	## The node existing is not collision existing.
	##
	## `GeneratedCollision` builds its trimesh from the imported GLB at run time,
	## so a missing mesh, a stale import cache or an empty file all leave a node
	## with no shape at all -- a walker falls straight through while every check
	## that only counts nodes still passes.
	var body := instance.get_node_or_null("GeneratedCollision")
	if body == null:
		return false
	var triangles: Variant = body.get("triangle_count")
	if typeof(triangles) != TYPE_INT or int(triangles) <= 0:
		printerr("FAIL: GeneratedCollision built no triangles (%s); the mesh is missing"
			% str(body.get("load_error")))
		return false
	var shape_node := body.get_node_or_null("CollisionShape3D")
	if shape_node == null or not shape_node is CollisionShape3D:
		printerr("FAIL: GeneratedCollision has no CollisionShape3D")
		return false
	var shape: Shape3D = (shape_node as CollisionShape3D).shape
	if not shape is ConcavePolygonShape3D:
		printerr("FAIL: GeneratedCollision shape is %s, expected ConcavePolygonShape3D"
			% (shape.get_class() if shape != null else "null"))
		return false
	var faces: PackedVector3Array = (shape as ConcavePolygonShape3D).get_faces()
	if faces.size() < 3:
		printerr("FAIL: GeneratedCollision trimesh has %d face vertices" % faces.size())
		return false
	print("OK: GeneratedCollision %d triangles, trimesh %d face vertices"
		% [int(triangles), faces.size()])
	return true


func _verify_player_capsule_matches_disk(instance: Node) -> bool:
	## Read the production capsule from player.tscn, not from a constant here.
	##
	## Every clearance this project asserts is the capsule's, so a copy of the
	## numbers inside a verifier is a second source of truth that drifts.
	var disk := _capsule_from_disk(PLAYER_SCENE)
	var scene_player := instance.get_node_or_null("Player")
	var placed := _capsule(scene_player)
	if disk == null or placed == null:
		printerr("FAIL: Player has no CapsuleShape3D")
		return false
	if not _close(disk.radius, placed.radius) or not _close(disk.height, placed.height):
		printerr("FAIL: Player capsule r=%.3f h=%.3f differs from player.tscn r=%.3f h=%.3f"
			% [placed.radius, placed.height, disk.radius, disk.height])
		return false
	print("OK: Player capsule radius %.2f m height %.2f m (matches player.tscn)"
		% [placed.radius, placed.height])
	return true


func _verify_spawn_placement(instance: Node, spawn_origin: Vector3, player_origin: Vector3) -> bool:
	## The marker is a drop-in reference; the body belongs on the collision's floor.
	##
	## The contract places PlayerSpawn `spawn_clearance_m` above the *contract's*
	## floor plane, which is a measured sheet plane rather than the surface the
	## generated collision actually has. A `CharacterBody3D`'s origin is its
	## capsule's centre, so neither of the two heights is a standable height by
	## itself. What has to hold is physical: the capsule's lower hemisphere must
	## not be inside the collision it will be dropped onto. So the floor is
	## measured here with the engine's own ray cast against the generated trimesh
	## and compared with the authored capsule bottom -- which is also a check no
	## amount of marker arithmetic can fake.
	var capsule := _capsule_from_disk(PLAYER_SCENE)
	if capsule == null:
		printerr("FAIL: could not read the production capsule")
		return false
	if absf(spawn_origin.x - player_origin.x) > 0.001 or absf(spawn_origin.z - player_origin.z) > 0.001:
		printerr("FAIL: PlayerSpawn %s and Player %s must share an x/z position"
			% [str(spawn_origin), str(player_origin)])
		return false

	var floor_y: Variant = _floor_below(
		instance,
		Vector3(player_origin.x, player_origin.y, player_origin.z),
		capsule.height + SPAWN_RAY_REACH
	)
	if floor_y == null:
		printerr("FAIL: no collision surface below PlayerSpawn at %s; the player would fall"
			% str(Vector3(player_origin.x, 0.0, player_origin.z)))
		return false
	var bottom := player_origin.y - 0.5 * capsule.height
	if bottom < float(floor_y) - OVERLAP_TOLERANCE:
		printerr("FAIL: PlayerSpawn capsule bottom %.4f m is %.4f m inside the generated floor %.4f m"
			% [bottom, float(floor_y) - bottom, float(floor_y)])
		return false
	var drop := float(floor_y) - bottom
	if drop > MAX_SPAWN_DROP:
		printerr("FAIL: PlayerSpawn would fall %.3f m onto the generated floor; the limit is %.2f m"
			% [drop, MAX_SPAWN_DROP])
		return false
	print("OK: PlayerSpawn capsule bottom %.4f m clears the generated floor %.4f m by %.4f m"
		% [bottom, float(floor_y), drop])
	print("    marker is the contract's spawn %s, %.4f m above the floor surface"
		% [str(spawn_origin), spawn_origin.y - float(floor_y)])
	return true


func _floor_below(instance: Node, from: Vector3, distance: float) -> Variant:
	## Cast down for the collision surface under a point, in the scene's own space.
	var space := (instance as Node3D).get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(from, from + Vector3.DOWN * distance)
	query.collide_with_areas = false
	var hit: Dictionary = space.intersect_ray(query)
	if hit.is_empty():
		return null
	return float(hit["position"].y)


func _close(left: float, right: float) -> bool:
	return absf(left - right) <= 0.0001


func _capsule(body: Node) -> CapsuleShape3D:
	if body == null:
		return null
	for child in body.get_children():
		if child is CollisionShape3D:
			var shape: Shape3D = (child as CollisionShape3D).shape
			if shape is CapsuleShape3D:
				return shape
	return null


func _capsule_from_disk(scene_path: String) -> CapsuleShape3D:
	var scene: PackedScene = load(scene_path)
	if scene == null:
		return null
	var instance := scene.instantiate()
	if instance == null:
		return null
	var capsule := _capsule(instance)
	instance.free()
	return capsule


func _authored_origin(instance: Node, node_name: String) -> Vector3:
	## Return a node's transform origin as authored in the scene file.
	var node := instance.get_node_or_null(node_name)
	if node is Node3D:
		return (node as Node3D).transform.origin
	return Vector3.ZERO


func _instantiate_scene(scene_path: String) -> Node:
	var scene: PackedScene = load(scene_path)
	if scene == null:
		printerr("FAIL: could not load %s" % scene_path)
		return null
	var instance: Node = scene.instantiate()
	if instance == null:
		printerr("FAIL: could not instantiate %s" % scene_path)
	return instance


func _require_count(counts: Dictionary, key: String, message: String) -> bool:
	if counts[key] == 0:
		printerr("FAIL: %s" % message)
		return false
	return true


func _count_recursive(root_node: Node) -> Dictionary:
	var counts := {"mesh": 0, "static": 0, "shape": 0}
	_do_count(root_node, counts)
	return counts


func _do_count(node: Node, counts: Dictionary) -> void:
	for child in node.get_children():
		if child is MeshInstance3D:
			counts["mesh"] += 1
		if child is StaticBody3D:
			counts["static"] += 1
		if child is CollisionShape3D:
			counts["shape"] += 1
		_do_count(child, counts)
