extends SceneTree

# Headless verification for issue 268. Checks that both fixtures load, the source
# crops resolve as textures, canopy card transforms differ, the trunk collision is
# independently defined and blocks the player, and the inspection route stays usable.
# Negative controls disable collision to prove the ray test is not a false positive.
const BASELINE_SCENE := preload("res://evidence/2026-11-17-issue-268-tree-prototype/fixture/baseline_tree_v1.tscn")
const VARIANT_SCENE := preload("res://evidence/2026-11-17-issue-268-tree-prototype/fixture/tree_trunk_canopy_v1.tscn")
const SPAWN := Vector3(0.0, 0.6, 4.5)

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var variant := VARIANT_SCENE.instantiate() as Node3D
	root.add_child(variant)
	await _physics_steps(12)
	_assert(variant != null, "variant scene did not instantiate")
	var player := variant.get_node("Player") as CharacterBody3D
	_assert(player.is_on_floor(), "player did not settle onto the inspection floor")
	_assert(not bool(variant.get_meta("registration_accepted")), "variant registration_accepted must be false")
	_assert(not bool(variant.get_meta("scale_calibrated")), "variant scale_calibrated must be false")
	_assert(not bool(variant.get_meta("operator_approved")), "variant operator_approved must be false")

	_check_trunk_collision(variant)
	_check_canopy_cards(variant)
	await _check_walk(variant, player)
	_check_baseline()

	if not _failed:
		print("ISSUE_268_FIXTURE_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_trunk_collision(room: Node3D) -> void:
	var trunk_body := room.get_node("TreeCollision/TrunkCollision") as StaticBody3D
	_assert(trunk_body != null, "independently defined trunk collision is missing")
	_assert(bool(trunk_body.get_meta("independent_of_visual")), "trunk collision is not marked independent")
	var shape := (trunk_body.get_node("Collision") as CollisionShape3D).shape
	_assert(shape is CylinderShape3D, "trunk collision shape is not an authored cylinder")
	var start := Vector3(0.0, 2.0, 2.0)
	var end := Vector3(0.0, 2.0, -2.0)
	_assert(_ray_hits(room, start, end), "trunk collision ray missed; player could pass through the trunk")
	trunk_body.collision_layer = 0
	_assert(not _ray_hits(room, start, end), "trunk negative control unexpectedly hit")
	trunk_body.collision_layer = 1
	_assert(_ray_hits(room, start, end), "trunk collision did not restore after negative control")


func _check_canopy_cards(room: Node3D) -> void:
	var cards := room.get_node("AuthoredCanopy").get_children()
	_assert(cards.size() >= 6, "layered canopy needs at least six cards; found %d" % cards.size())
	var yaws: Array[float] = []
	var radials: Array[float] = []
	var heights: Array[float] = []
	var crops: Array[String] = []
	for node in cards:
		var card := node as MeshInstance3D
		_assert(card != null, "canopy child is not a MeshInstance3D")
		_assert(card.has_meta("crop"), "canopy card %s has no crop provenance" % card.name)
		var crop: String = card.get_meta("crop")
		_assert(crop in ["branch_canopy", "branch_fine", "evergreen_foliage"],
			"canopy card uses an unrecorded crop: %s" % crop)
		crops.append(crop)
		var material := card.material_override as StandardMaterial3D
		_assert(material != null and material.albedo_texture != null,
			"canopy card %s has no source-backed texture" % card.name)
		yaws.append(card.rotation.y)
		radials.append(float(card.get_meta("radial_offset")))
		heights.append(float(card.get_meta("center_y")))
	_assert(_all_distinct(yaws), "canopy card yaw rotations are not all different")
	_assert(_all_distinct(radials), "canopy card radial depth offsets are not all different")
	_assert(_all_distinct(heights), "canopy card height offsets are not all different")
	for crop_name in ["branch_canopy", "branch_fine", "evergreen_foliage"]:
		_assert(crop_name in crops, "crop %s is not used by any canopy card" % crop_name)
	var trunk_visual := room.get_node("AuthoredVisuals/AuthoredTrunk")
	_assert(trunk_visual != null, "authored trunk visual is missing")
	_assert(trunk_visual.get_meta("classification") == "authored",
		"trunk must be labelled authored, not source-backed")
	_assert(trunk_visual.get_meta("bark_source_crop") == "none",
		"trunk must not claim a bark crop")


func _check_walk(room: Node3D, player: CharacterBody3D) -> void:
	Input.action_press("move_forward")
	await _physics_steps(100)
	Input.action_release("move_forward")
	_assert(player.global_position.z > 0.40,
		"player passed through or too close to the trunk centre (z=%.3f)" % player.global_position.z)
	_assert(player.is_on_floor(), "player lost floor support approaching the trunk")
	var approach_z := player.global_position.z
	player.global_position = SPAWN
	player.velocity = Vector3.ZERO
	Input.action_press("move_right")
	await _physics_steps(40)
	Input.action_release("move_right")
	_assert(player.global_position.x > SPAWN.x + 1.5, "inspection route to the side is blocked")
	_assert(player.is_on_floor(), "player lost floor support on the inspection route")
	_assert(absf(player.global_position.z - SPAWN.z) < 0.8, "inspection route drifted off its lane")
	print("ISSUE_268_WALK: approach_stopped_z=%.3f side_x=%.3f" % [approach_z, player.global_position.x])


func _check_baseline() -> void:
	var baseline := BASELINE_SCENE.instantiate() as Node3D
	root.add_child(baseline)
	await _physics_steps(12)
	_assert(baseline.get_node("AuthoredCanopy").get_child_count() == 2,
		"baseline must keep its two thin textured canopy boxes")
	_assert(baseline.get_node("TreeCollision/TrunkCollision") != null,
		"baseline must keep a separate trunk box collision")
	_assert(_ray_hits(baseline, Vector3(0.0, 2.0, 2.0), Vector3(0.0, 2.0, -2.0)),
		"baseline trunk collision ray missed")
	_assert(not bool(baseline.get_meta("registration_accepted")), "baseline registration_accepted must be false")
	_assert(not bool(baseline.get_meta("scale_calibrated")), "baseline scale_calibrated must be false")


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _all_distinct(values: Array[float]) -> bool:
	for index in values.size():
		for other in range(index + 1, values.size()):
			if absf(values[index] - values[other]) < 0.0001:
				return false
	return true


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("ISSUE_268_TEST_FAILURE: ", message)
