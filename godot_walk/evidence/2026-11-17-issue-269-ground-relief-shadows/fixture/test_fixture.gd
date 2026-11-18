extends SceneTree

# Headless structural checks for issue 269. Verifies deterministic relief bounds,
# one shadow per tree on a common direction, a flat (non-following) collider, a
# usable flat traversal route, and the baseline's flattened-ellipsoid scheme.
const VARIANT_SCENE := preload("res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/relief_shadows_v1.tscn")
const BASELINE_SCENE := preload("res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/baseline_relief_v1.tscn")
const SHADOW_SPEC_PATH := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/shadow_spec_v1.json"
const SPAWN := Vector3(0.0, 0.6, 7.5)

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var variant := VARIANT_SCENE.instantiate() as Node3D
	root.add_child(variant)
	await _physics_steps(12)
	var player := variant.get_node("Player") as CharacterBody3D
	_assert(player.is_on_floor(), "player did not settle on the flat floor")
	_assert(not bool(variant.get_meta("registration_accepted")), "variant registration_accepted must be false")
	_assert(not bool(variant.get_meta("scale_calibrated")), "variant scale_calibrated must be false")
	_assert(variant.get_meta("collision_policy") == "flat", "variant collision policy must be flat")
	_check_relief(variant)
	_check_shadows(variant)
	_check_flat_collision(variant)
	await _check_walk(variant, player)
	_check_baseline()
	if not _failed:
		print("ISSUE_269_FIXTURE_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_relief(room: Node3D) -> void:
	var relief := room.get_node("AuthoredRelief/AuthoredReliefMesh") as MeshInstance3D
	_assert(relief != null, "authored relief mesh is missing")
	var aabb := relief.mesh.get_aabb()
	var bound := 0.35
	_assert(aabb.position.y >= -bound - 0.001, "relief dips below the declared height bound")
	_assert(aabb.position.y + aabb.size.y <= bound + 0.001, "relief rises above the declared height bound")
	_assert(aabb.size.y >= 0.15, "relief variation is too small to read as non-ellipsoid relief")
	var material := relief.material_override as StandardMaterial3D
	_assert(material != null and material.vertex_color_use_as_albedo,
		"relief shading must be baked into vertex colours")
	_assert(relief.get_meta("collision_policy") == "flat", "relief visual is not marked flat-collision")


func _check_shadows(room: Node3D) -> void:
	var file := FileAccess.open(SHADOW_SPEC_PATH, FileAccess.READ)
	_assert(file != null, "could not read shadow spec")
	if file == null:
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	var spec: Dictionary = parsed
	var expected: Array = spec["shadow_direction_xz"]
	var expected_direction := Vector2(float(expected[0]), float(expected[1])).normalized()
	var shadows := room.get_node("AuthoredShadows").get_children()
	var trees := room.get_node("AuthoredTrees").get_children()
	_assert(shadows.size() == trees.size() / 2, "there must be one shadow per tree")
	_assert(shadows.size() >= 4, "fixture needs at least four tree shadows")
	var paired: Dictionary = {}
	for tree in trees:
		var tree_id: String = tree.get_meta("tree_id")
		if not paired.has(tree_id):
			paired[tree_id] = []
		paired[tree_id].append(tree)
	for shadow_node in shadows:
		var shadow := shadow_node as MeshInstance3D
		var tree_id: String = shadow.get_meta("tree_id")
		_assert(paired.has(tree_id), "shadow %s has no matching tree" % shadow.name)
		_assert(shadow.get_meta("direction_xz").distance_to(expected_direction) < 0.0001,
			"shadow %s does not share the documented direction" % shadow.name)
		_assert(float(shadow.get_meta("length")) >= 5.0, "shadow %s is not long" % shadow.name)
		var candidates: Array = paired.get(tree_id, [])
		_assert(candidates.size() >= 2, "tree visual %s is missing" % tree_id)
		if candidates.size() >= 2:
			var tree_visual := candidates[0] as Node3D
			var origin: Vector2 = shadow.get_meta("origin")
			var tree_xz := Vector2(tree_visual.global_position.x, tree_visual.global_position.z)
			_assert(origin.distance_to(tree_xz) < 0.001,
				"shadow %s does not originate at its tree" % shadow.name)


func _check_flat_collision(room: Node3D) -> void:
	var body := room.get_node("AuthoredBoundaries/FlatFloorCollision") as StaticBody3D
	_assert(body != null, "flat floor collision is missing")
	_assert(body.get_meta("collision_policy") == "flat", "floor collision is not declared flat")
	var shape := (body.get_node("Collision") as CollisionShape3D).shape
	_assert(shape is BoxShape3D, "flat floor collision must be a box, not a heightfield")
	var top := body.global_position.y + (shape as BoxShape3D).size.y * 0.5
	_assert(absf(top) < 0.001, "flat floor top must sit at y=0")
	_assert(_ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -0.5, 0.0)),
		"downward ray missed the flat floor")
	body.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 3.0, 0.0), Vector3(0.0, -0.5, 0.0)),
		"flat floor negative control unexpectedly hit")
	body.collision_layer = 1


func _check_walk(room: Node3D, player: CharacterBody3D) -> void:
	var start_z := player.global_position.z
	Input.action_press("move_forward")
	await _physics_steps(80)
	Input.action_release("move_forward")
	var forward_z := player.global_position.z
	_assert(forward_z < start_z - 1.0, "player could not traverse the plot")
	_assert(player.is_on_floor(), "player lost floor support while traversing relief")
	_assert(absf(player.global_position.y - SPAWN.y) < 0.4, "player did not stay on the flat plane")
	player.global_position = SPAWN
	player.velocity = Vector3.ZERO
	Input.action_press("move_right")
	await _physics_steps(40)
	Input.action_release("move_right")
	_assert(player.global_position.x > SPAWN.x + 1.5, "side inspection route is blocked")
	_assert(player.is_on_floor(), "player lost floor support on the side route")
	print("ISSUE_269_WALK: forward_z=%.3f side_x=%.3f" % [forward_z, player.global_position.x])


func _check_baseline() -> void:
	var baseline := BASELINE_SCENE.instantiate() as Node3D
	root.add_child(baseline)
	await _physics_steps(12)
	_assert(baseline.get_node("BaselineEllipsoids").get_child_count() >= 4,
		"baseline must keep its flattened ellipsoids")
	_assert(baseline.get_node_or_null("AuthoredShadows") == null,
		"baseline must not contain shadow polygons")
	_assert(baseline.get_node("AuthoredBoundaries/FlatFloorCollision") != null,
		"baseline must keep its flat box collider")
	_assert(not bool(baseline.get_meta("registration_accepted")), "baseline registration_accepted must be false")
	_assert(not bool(baseline.get_meta("scale_calibrated")), "baseline scale_calibrated must be false")


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("ISSUE_269_TEST_FAILURE: ", message)
