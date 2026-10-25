extends SceneTree

const EVIDENCE := "res://evidence/2026-10-21-issue-155-godot-library"
var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_verify")


func _verify() -> void:
	var reference := load("res://scenes/hunyuan_psx_column_box.tscn").instantiate() as Node3D
	reference.variant_id = "four_sided_box"
	root.add_child(reference)
	var column := _room("column")
	_expect(_snapshot(reference) == _snapshot(column), "Column room collision changed")
	_check_accepted_face(reference, column)
	await physics_frame
	var query := PhysicsRayQueryParameters3D.create(Vector3(3.3, 0, 0.3), Vector3(-3, 0, 0.3))
	var hit := column.get_world_3d().direct_space_state.intersect_ray(query)
	_expect(not hit.is_empty() and hit.collider.name == "ColumnObstacle", "Missing column obstacle")
	reference.free()
	column.free()
	var pocket := _room("pocket")
	_check_pocket_collision(pocket)
	_check_pocket_materials(pocket)
	pocket.free()
	for failure in failures:
		printerr(failure)
	print("LIBRARY_ROOM_CONTRACT: ", "PASS" if failures.is_empty() else "FAIL")
	quit(0 if failures.is_empty() else 1)


func _room(label: String) -> Node3D:
	var room := load("res://scenes/library_%s_room.tscn" % label).instantiate() as Node3D
	root.add_child(room)
	room.get_node("Player").set_physics_process(false)
	_expect(not room.get_meta("registration_accepted"), "Registration changed")
	_expect(not room.get_meta("scale_calibrated"), "Scale changed")
	_expect(not room.get_meta("operator_approved"), "Whole room promoted")
	var preset := room.get_node("LibraryPsxPreset")
	_expect(not preset.originals.is_empty(), "No packaged PSX materials")
	preset.set_packaged_enabled(false)
	for record in preset.originals:
		_expect(record.instance.material_override == record.override, "Native toggle mismatch")
	preset.set_packaged_enabled(true)
	return room


func _check_accepted_face(reference: Node3D, column: Node3D) -> void:
	var path := "AuthoredBoundaries/FourSidedColumnBox/EastSourceFace"
	var original := reference.get_node(path) as MeshInstance3D
	var candidate := column.get_node(path) as MeshInstance3D
	_expect(original.transform == candidate.transform, "Accepted face transform changed")
	_expect(original.mesh.size == candidate.mesh.size, "Accepted face dimensions changed")
	var material := candidate.get_active_material(0) as ShaderMaterial
	_expect(material != null, "Accepted face does not use packaged shader")
	if material == null:
		return
	var texture: Texture2D = material.get_shader_parameter("albedo_texture")
	_expect(texture.get_image().get_data() == original.mesh.material.albedo_texture.get_image().get_data(),
		"Accepted face texture changed")
	_expect(material.get_shader_parameter("uv_scale") == Vector2.ONE, "Accepted face UV changed")


func _check_pocket_collision(pocket: Node3D) -> void:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var path := "res://evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_collision.glb"
	_expect(document.append_from_file(path, state) == OK, "Cannot read protected collision")
	var source := document.generate_scene(state) as Node3D
	root.add_child(source)
	var triangles := 0
	for instance in source.find_children("*", "MeshInstance3D", true, false):
		var collision: CollisionShape3D = pocket.find_child(str(instance.name), true, false).get_node("CollisionShape3D")
		_expect(collision.global_transform == instance.global_transform, "Imported collision transform changed")
		_expect(collision.shape.get_faces() == instance.mesh.get_faces(), "Imported collision triangles changed")
		triangles += collision.shape.get_faces().size() / 3
	_expect(triangles == 50, "Expected original 50 pocket collision triangles")
	source.free()


func _snapshot(scene: Node3D) -> Array[Dictionary]:
	var snapshot: Array[Dictionary] = []
	for collision in scene.find_children("*", "CollisionShape3D", true, false):
		if str(scene.get_path_to(collision)).begins_with("Player/"):
			continue
		snapshot.append({"path": str(scene.get_path_to(collision)),
			"transform": str(collision.global_transform), "size": str(collision.shape.size)})
	var file := FileAccess.open(EVIDENCE + "/collision_snapshot.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(snapshot, "\t") + "\n")
	return snapshot


func _check_pocket_materials(pocket: Node3D) -> void:
	var preset := pocket.get_node("LibraryPsxPreset")
	preset.set_packaged_enabled(false)
	for instance in pocket.get_node("AuthoredPocketVisual").find_children("*", "MeshInstance3D", true, false):
		var material := instance.get_active_material(0) as StandardMaterial3D
		_expect(material != null and material.cull_mode == BaseMaterial3D.CULL_DISABLED,
			"Pocket native floor/ceiling must render from both sides")
	preset.set_packaged_enabled(true)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
