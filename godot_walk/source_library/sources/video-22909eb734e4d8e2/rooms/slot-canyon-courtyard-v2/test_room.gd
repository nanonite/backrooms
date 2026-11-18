extends SceneTree

# Headless mechanical acceptance for the v2 visual-only depth variant.
# The baseline v1 scene is instantiated beside the variant so footprint,
# spawn and the complete collidable body set can be compared directly.

const VARIANT_SCENE := preload("res://source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v2/room.tscn")
const BASELINE_SCENE := preload("res://source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/room.tscn")
const SPAWN := Vector3(0.0, 0.6, -7.0)
const BOUNDARY_NAMES := [
	"SouthWall", "LowerEastWall", "BendSouthWall",
	"FarEastWall", "NorthWall", "WestWall",
]

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var variant := VARIANT_SCENE.instantiate() as Node3D
	root.add_child(variant)
	await _physics_steps(12)
	var player := variant.get_node("Player") as CharacterBody3D
	_assert(player.is_on_floor(), "variant player did not settle onto the authored floor")
	_assert(_ray_hits(variant, Vector3(0.0, 3.0, -5.0), Vector3(0.0, -1.0, -5.0)), "floor ray missed")
	_assert(_ray_hits(variant, Vector3(0.0, 1.0, 6.0), Vector3(0.0, 1.0, 10.0)), "north boundary ray missed")
	_assert(_ray_hits(variant, Vector3(-1.8, 0.3, -5.0), Vector3(-1.8, 0.3, -2.0)), "rock obstacle ray missed")

	var baseline := BASELINE_SCENE.instantiate() as Node3D
	root.add_child(baseline)
	await _physics_steps(2)
	var baseline_data := {
		"collision": _collision_signature(baseline),
		"envelope": baseline.get_meta("walk_envelope"),
		"spawn": baseline.get_meta("safe_spawn"),
		"floor_y": baseline.get_meta("walk_floor_y"),
		"visual_count": _visual_names(baseline).size(),
		"obstacle_count": baseline.get_node("AuthoredObstacles").get_child_count(),
	}
	# Both rooms would otherwise share one physics world and keep baseline
	# colliders alive during the variant's negative-control ray checks.
	root.remove_child(baseline)
	baseline.queue_free()
	await _physics_steps(12)

	_check_unchanged_contract(variant, baseline_data)
	_check_visual_only_relief(variant, baseline_data)
	await _walk_and_backtrack(player, variant)
	_check_floor_negative(variant)
	_check_boundary_negative(variant)
	_check_reset(variant, player)

	if not _failed:
		print("SLOT_CANYON_V2_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_unchanged_contract(variant: Node3D, baseline: Dictionary) -> void:
	_assert(variant.get_meta("walk_envelope") == baseline["envelope"], "declared walk envelope changed")
	_assert(variant.get_meta("safe_spawn") == baseline["spawn"], "safe spawn changed")
	_assert(variant.get_meta("walk_floor_y") == baseline["floor_y"], "floor elevation changed")
	_assert(_collision_signature(variant) == baseline["collision"], "collidable body set changed between v1 and v2")
	_assert(variant.get_node("AuthoredObstacles").get_child_count() == baseline["obstacle_count"], "new collidable obstacle added")
	_assert(not variant.get_meta("registration_accepted") and not variant.get_meta("scale_calibrated"), "calibration flags must stay false")


func _check_visual_only_relief(variant: Node3D, baseline: Dictionary) -> void:
	var expected := int(variant.get_meta("visual_relief_node_count"))
	_assert(expected == 23, "unexpected declared relief node count")
	var added := _visual_names(variant).size() - int(baseline["visual_count"])
	_assert(added == expected, "relief visual nodes were not added as declared")
	_assert(variant.get_meta("visual_relief_visual_only"), "relief is not declared visual-only")
	for child in variant.get_node("AuthoredObstacles").get_children():
		_assert(not String(child.name).begins_with("Relief"), "relief leaked into the obstacle collider group")
	for child in variant.get_node("AuthoredVisuals").get_children():
		if String(child.name).begins_with("Relief"):
			_assert(child.get_child_count() == 0, "relief visual carries a collider child")


func _collision_signature(room: Node3D) -> Dictionary:
	var result := {}
	for group_name in ["AuthoredBoundaries", "AuthoredObstacles"]:
		var group := room.get_node(group_name)
		var entries := {}
		for child in group.get_children():
			if not child is StaticBody3D:
				continue
			var shape := child.get_node("Collision") as CollisionShape3D
			var size := Vector3.ZERO
			if shape != null and shape.shape is BoxShape3D:
				size = (shape.shape as BoxShape3D).size
			entries[child.name] = "%s|%s" % [str(child.position), str(size)]
		result[group_name] = entries
	return result


func _visual_names(room: Node3D) -> Dictionary:
	var result := {}
	for child in room.get_node("AuthoredVisuals").get_children():
		if child is MeshInstance3D:
			result[child.name] = str((child as MeshInstance3D).mesh)
	return result


func _walk_and_backtrack(player: CharacterBody3D, room: Node3D) -> void:
	var start := player.global_position
	Input.action_press("move_right")
	await _physics_steps(55)
	Input.action_release("move_right")
	_assert(player.global_position.x > start.x + 1.5, "player did not walk across the courtyard")
	_assert(player.is_on_floor(), "player lost floor support during traversal")
	Input.action_press("move_left")
	await _physics_steps(55)
	Input.action_release("move_left")
	_assert(absf(player.global_position.x - start.x) < 0.8, "player could not backtrack to the spawn lane")
	_assert(_inside_room(player.global_position), "walked player crossed an exposed boundary")


func _check_floor_negative(room: Node3D) -> void:
	var floor_body := room.get_node("AuthoredBoundaries/MainFloorCollision") as StaticBody3D
	floor_body.collision_layer = 0
	_assert(not _ray_hits(room, Vector3(0.0, 3.0, -5.0), Vector3(0.0, -1.0, -5.0)), "missing-floor negative control unexpectedly hit")
	floor_body.collision_layer = 1
	_assert(_ray_hits(room, Vector3(0.0, 3.0, -5.0), Vector3(0.0, -1.0, -5.0)), "floor ray did not recover after reset")


func _check_boundary_negative(room: Node3D) -> void:
	var north := room.get_node("AuthoredBoundaries/NorthWall") as StaticBody3D
	var probe_start := Vector3(0.0, 1.0, 6.0)
	var probe_end := Vector3(0.0, 1.0, 10.0)
	_assert(_ray_hits(room, probe_start, probe_end), "north boundary absent before negative control")
	north.collision_layer = 0
	_assert(not _ray_hits(room, probe_start, probe_end), "escape negative control did not detect an open boundary")
	north.collision_layer = 1
	_assert(_ray_hits(room, probe_start, probe_end), "boundary ray did not recover after reset")
	var walls: Array[StaticBody3D] = []
	for name in BOUNDARY_NAMES:
		var wall := room.get_node("AuthoredBoundaries/%s" % name) as StaticBody3D
		walls.append(wall)
		wall.collision_layer = 0
	_assert(not _ray_hits(room, probe_start, probe_end), "missing-boundary negative control did not detect all walls removed")
	for wall in walls:
		wall.collision_layer = 1
	_assert(_ray_hits(room, probe_start, probe_end), "boundary rays did not recover after restoring all walls")


func _check_reset(room: Node3D, player: CharacterBody3D) -> void:
	player.global_position = Vector3(0.0, -5.0, 0.0)
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	room.call("_unhandled_key_input", event)
	_assert(player.global_position.distance_to(SPAWN) < 0.01, "R reset did not return to safe spawn")


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _inside_room(position: Vector3) -> bool:
	return position.x > -3.8 and position.x < 10.8 and position.z > -9.8 and position.z < 7.8


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("SLOT_CANYON_V2_TEST_FAILURE: ", message)
