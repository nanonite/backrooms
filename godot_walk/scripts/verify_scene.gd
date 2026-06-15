extends SceneTree

const CORRIDOR_SCENE := "res://scenes/corridor.tscn"
const IMPORT_TEST_SCENE := "res://scenes/import_test.tscn"
const FITTED_COLLIDER_BODIES := ["Floor", "LeftWall", "RightWall", "Ceiling", "SafetyNet"]

func _init() -> void:
	var ok := _verify_import_test()
	ok = _verify_corridor_collider() and ok
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

	root.add_child(instance)
	var fitted := instance.get_node_or_null("FittedCollider")
	var spawn := instance.get_node_or_null("PlayerSpawn")
	var player := instance.get_node_or_null("Player")
	var ok := true
	if fitted == null:
		printerr("FAIL: FittedCollider node not found")
		ok = false
	if spawn == null or not spawn is Marker3D:
		printerr("FAIL: PlayerSpawn Marker3D not found")
		ok = false
	if player == null or not player is CharacterBody3D:
		printerr("FAIL: Player CharacterBody3D not found")
		ok = false
	if fitted != null:
		ok = _verify_fitted_bodies(fitted) and ok
		if spawn != null and player != null:
			ok = _verify_spawn_clearance(fitted, spawn, player) and ok
	if ok:
		print("OK: corridor fitted collider bodies=%d spawn=%s" % [FITTED_COLLIDER_BODIES.size(), spawn.position])
	return ok


func _verify_fitted_bodies(fitted: Node) -> bool:
	var ok := true
	for body_name: String in FITTED_COLLIDER_BODIES:
		var body := fitted.get_node_or_null(body_name)
		if body == null or not body is StaticBody3D:
			printerr("FAIL: fitted collider body missing: %s" % body_name)
			ok = false
			continue
		var shape := body.get_node_or_null("CollisionShape3D")
		if shape == null or not shape is CollisionShape3D:
			printerr("FAIL: CollisionShape3D missing for %s" % body_name)
			ok = false
	return ok


func _verify_spawn_clearance(fitted: Node, spawn: Marker3D, player: CharacterBody3D) -> bool:
	var floor := fitted.get_node("Floor") as StaticBody3D
	var floor_shape := floor.get_node("CollisionShape3D") as CollisionShape3D
	var box := floor_shape.shape as BoxShape3D
	var floor_top := floor.position.y + (box.size.y * 0.5)
	var clearance := spawn.position.y - floor_top
	if abs(clearance - 0.5) > 0.01:
		printerr("FAIL: PlayerSpawn must be 0.5m above floor, got %.3f" % clearance)
		return false
	if player.position.distance_to(spawn.position) > 0.001:
		printerr("FAIL: Player transform does not match PlayerSpawn marker")
		return false
	return true


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
