extends SceneTree

func _init() -> void:
	var scene = load("res://scenes/import_test.tscn")
	if scene == null:
		printerr("FAIL: could not load import_test.tscn")
		quit(1)
		return

	var instance = scene.instantiate()
	if instance == null:
		printerr("FAIL: could not instantiate import_test.tscn")
		quit(1)
		return

	var walker = instance.get_node_or_null("TestWalker")
	if walker == null:
		printerr("FAIL: TestWalker node not found")
		quit(1)
		return

	var room = instance.get_node_or_null("Room")
	if room == null:
		printerr("FAIL: Room node not found")
		quit(1)
		return

	root.add_child(instance)

	var counts = _count_recursive(instance)

	var ok = true
	if counts["mesh"] == 0:
		printerr("FAIL: no MeshInstance3D found in Room")
		ok = false
	if counts["static"] == 0:
		printerr("FAIL: no StaticBody3D found — collision not generated")
		ok = false
	if counts["shape"] == 0:
		printerr("FAIL: no CollisionShape3D found — collision shapes missing")
		ok = false

	if ok:
		print("OK: mesh=%d static=%d shape=%d" % [counts["mesh"], counts["static"], counts["shape"]])
		quit(0)
	else:
		quit(1)


func _count_recursive(root: Node) -> Dictionary:
	var counts = {"mesh": 0, "static": 0, "shape": 0}
	_do_count(root, counts)
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
