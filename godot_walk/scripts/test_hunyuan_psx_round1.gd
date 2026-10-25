extends SceneTree

const SCENE_PATH := "res://scenes/hunyuan_psx_round1.tscn"
const VARIANTS := ["preserve_hunyuan", "source_surface_cleanup"]

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run_tests")


func _run_tests() -> void:
	for variant_id in VARIANTS:
		await _test_variant(variant_id)
	if failures.is_empty():
		print("OK: Hunyuan round variants keep visual and collision roles separate")
		quit()
		return
	for failure in failures:
		printerr("FAIL: %s" % failure)
	quit(1)


func _test_variant(variant_id: String) -> void:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		failures.append("candidate scene did not load")
		return
	var scene := packed.instantiate()
	scene.set("variant_id", variant_id)
	root.add_child(scene)
	await process_frame
	_expect(scene.has_meta("hunyuan_visual_loaded"), "%s Hunyuan GLB missing" % variant_id)
	_expect(scene.get_meta("registration_accepted") == false, "registration flag changed")
	_expect(scene.get_meta("scale_calibrated") == false, "scale flag changed")
	_expect(scene.get_node_or_null("Player") is CharacterBody3D, "%s player missing" % variant_id)
	_test_collision_roles(scene)
	_test_variant_surfaces(scene, variant_id)
	scene.queue_free()
	await process_frame


func _test_collision_roles(scene: Node) -> void:
	var floor := scene.get_node_or_null("AuthoredFloor") as StaticBody3D
	_expect(floor != null and floor.get_node_or_null("CollisionShape3D") != null,
		"authored floor collider missing")
	var boundaries := scene.get_node_or_null("AuthoredBoundaries")
	for name in ["WestBoundary", "EastBoundary", "NorthBoundary", "SouthBoundary", "ColumnObstacle"]:
		var body := boundaries.get_node_or_null(name) as StaticBody3D if boundaries != null else null
		_expect(body != null and body.get_node_or_null("CollisionShape3D") != null,
			"authored collision missing: %s" % name)
	var visual := scene.get_node_or_null("HunyuanVisualOnly")
	_expect(visual != null and visual.find_children("*", "StaticBody3D", true, false).is_empty(),
		"Hunyuan mesh must remain visual-only")


func _test_variant_surfaces(scene: Node, variant_id: String) -> void:
	var clean_surface := scene.get_node_or_null("AuthoredBoundaries/SourceCeiling")
	var column_cover := scene.get_node_or_null("AuthoredBoundaries/SourceColumnCover")
	if variant_id == "preserve_hunyuan":
		_expect(clean_surface == null and column_cover == null,
			"preserve variant unexpectedly contains cleanup surfaces")
		return
	_expect(clean_surface is StaticBody3D, "cleanup ceiling surface missing")
	_expect(column_cover is StaticBody3D, "cleanup column cover missing")
	if clean_surface is StaticBody3D:
		_expect(clean_surface.get_node_or_null("CollisionShape3D") == null,
			"cleanup ceiling must be visual-only")
	if column_cover is StaticBody3D:
		_expect(column_cover.get_node_or_null("CollisionShape3D") == null,
			"cleanup column cover must be visual-only")


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
