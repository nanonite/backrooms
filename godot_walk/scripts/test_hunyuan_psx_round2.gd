extends SceneTree

const SCENE_PATH := "res://scenes/hunyuan_psx_round2.tscn"
const VARIANTS := ["preserve_hunyuan", "column_box_source_face"]

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run_tests")


func _run_tests() -> void:
	for variant_id in VARIANTS:
		await _test_variant(variant_id)
	if failures.is_empty():
		print("OK: round 2 isolates a textured column box and preserves shared collision")
		quit()
		return
	for failure in failures:
		printerr("FAIL: %s" % failure)
	quit(1)


func _test_variant(variant_id: String) -> void:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		failures.append("round 2 scene did not load")
		return
	var scene := packed.instantiate()
	scene.set("variant_id", variant_id)
	root.add_child(scene)
	await process_frame
	_expect(scene.has_meta("hunyuan_visual_loaded"), "Hunyuan GLB missing")
	_expect(scene.get_meta("registration_accepted") == false, "registration flag changed")
	_expect(scene.get_meta("scale_calibrated") == false, "scale flag changed")
	_test_shared_collision(scene)
	_test_column_variant(scene, variant_id)
	scene.queue_free()
	await process_frame


func _test_shared_collision(scene: Node) -> void:
	var floor := scene.get_node_or_null("AuthoredFloor") as StaticBody3D
	var column := scene.get_node_or_null("AuthoredBoundaries/ColumnObstacle") as StaticBody3D
	_expect(floor != null and floor.get_node_or_null("CollisionShape3D") != null,
		"shared authored floor collider missing")
	_expect(column != null and column.get_node_or_null("CollisionShape3D") != null,
		"shared column obstacle collider missing")
	var visual := scene.get_node_or_null("HunyuanVisualOnly")
	_expect(visual != null and visual.find_children("*", "StaticBody3D", true, false).is_empty(),
		"Hunyuan layer must remain visual-only")


func _test_column_variant(scene: Node, variant_id: String) -> void:
	var column_box := scene.get_node_or_null("AuthoredBoundaries/ColumnBoxSourceFace") as StaticBody3D
	if variant_id == "preserve_hunyuan":
		_expect(column_box == null, "baseline unexpectedly contains a column cover")
		return
	_expect(column_box != null, "source-face column box missing")
	if column_box == null:
		return
	_expect(column_box.get_node_or_null("CollisionShape3D") == null,
		"visual column cover must not add a duplicate collider")
	var mesh := column_box.get_node_or_null("ColumnBoxSourceFaceVisual") as MeshInstance3D
	_expect(mesh != null and mesh.mesh is BoxMesh, "column cover must be a box mesh")
	if mesh != null and mesh.mesh is BoxMesh:
		_expect(mesh.material_override != null, "column box texture material missing")
		_expect(mesh.mesh.size == Vector3(1.8587826, 2.4, 2.3700817),
			"column box dimensions differ from the shared obstacle")
	_expect(scene.get_node_or_null("AuthoredBoundaries/SourceCeiling") == null,
		"round 2 must leave the ceiling untouched")
	_expect(scene.get_node_or_null("AuthoredBoundaries/SourceEastWall") == null,
		"round 2 must leave the walls untouched")


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
