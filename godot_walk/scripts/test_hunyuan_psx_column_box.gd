extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run_tests")


func _run_tests() -> void:
	var reference := _load_scene("res://scenes/hunyuan_psx_round3.tscn", "column_face_extrusion")
	var candidate := _load_scene("res://scenes/hunyuan_psx_column_box.tscn", "four_sided_box")
	_expect(_collision_snapshot(reference) == _collision_snapshot(candidate), "collision changed")
	_expect(candidate.get_meta("registration_accepted") == false, "registration changed")
	_expect(candidate.get_meta("scale_calibrated") == false, "scale changed")
	_expect(candidate.get_meta("hunyuan_visual_loaded", false), "Hunyuan room missing")
	var cover := candidate.get_node("AuthoredBoundaries/FourSidedColumnBox")
	_expect(cover.find_children("*", "MeshInstance3D", true, false).size() == 5, "prism must have backing and four faces")
	_expect(cover.find_children("*", "CollisionShape3D", true, false).is_empty(), "cover adds collision")
	_test_accepted_face(reference, cover)
	reference.free()
	candidate.free()
	for failure in failures:
		printerr("FAIL: %s" % failure)
	print("COLUMN_BOX_CHECK: %s" % ("PASS" if failures.is_empty() else "FAIL"))
	quit(0 if failures.is_empty() else 1)


func _test_accepted_face(reference: Node3D, cover: Node3D) -> void:
	var front := cover.get_node("EastSourceFace") as MeshInstance3D
	var old_front := reference.get_node("AuthoredBoundaries/ColumnFaceFrame0152") as MeshInstance3D
	_expect(front.mesh.size == old_front.mesh.size, "accepted face dimensions changed")
	var texture_bytes: PackedByteArray = front.mesh.material.albedo_texture.get_image().get_data()
	var old_texture_bytes: PackedByteArray = old_front.mesh.material.albedo_texture.get_image().get_data()
	_expect(texture_bytes == old_texture_bytes, "accepted texture changed")
	_expect(front.mesh.material.texture_filter == BaseMaterial3D.TEXTURE_FILTER_NEAREST, "texture filter changed")


func _load_scene(path: String, variant: String) -> Node3D:
	var scene := load(path).instantiate() as Node3D
	scene.set("variant_id", variant)
	root.add_child(scene)
	scene.get_node("Player").set_physics_process(false)
	return scene


func _collision_snapshot(scene: Node3D) -> Array[Dictionary]:
	var snapshot: Array[Dictionary] = []
	for collision in scene.find_children("*", "CollisionShape3D", true, false):
		if str(scene.get_path_to(collision)).begins_with("Player/"):
			continue
		snapshot.append({"path": scene.get_path_to(collision), "transform": collision.global_transform,
			"size": collision.shape.size, "disabled": collision.disabled})
	return snapshot


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
