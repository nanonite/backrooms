extends SceneTree

const CATALOG := preload("res://scripts/psx_design_variant_catalog.gd")
const CANDIDATE_SCENE := "res://scenes/corridor_psx_design_candidate.tscn"
const VARIANT_IDS := [
	"v2_control", "door_flush", "door_removed", "wall_endcap",
	"north_wall_smooth", "north_wall_source_texture", "clean_ceiling",
	"source_texture_cleanup", "source_floor_single_column",
	"source_floor_ceiling_single_column",
]
const BASE_DOOR_X := 3.875
const BASE_FRAME_X := 3.9
const FLUSH_SHIFT_M := 0.0155


func _initialize() -> void:
	var ok := _test_catalog_validation()
	for variant_id: String in VARIANT_IDS:
		var scene_ok := await _test_variant_scene(variant_id)
		ok = scene_ok and ok
	if ok:
		print("OK: bounded PSX design variants preserve v2 traversal metadata")
	quit(0 if ok else 1)


func _test_catalog_validation() -> bool:
	var control := CATALOG.load_variant("v2_control")
	if control.is_empty():
		return _fail("v2 control config did not load")
	var invalid_extents: Dictionary = control.duplicate(true)
	invalid_extents["design"]["collision"]["bounds_m"]["east"] = 5.0
	var rejects_extents := not CATALOG.validate_variant(invalid_extents, "v2_control").is_empty()
	var invalid_material: Dictionary = control.duplicate(true)
	invalid_material["design"]["materials"]["wall"] = "unreviewed_material"
	var rejects_material := not CATALOG.validate_variant(invalid_material, "v2_control").is_empty()
	var invalid_treatment: Dictionary = control.duplicate(true)
	invalid_treatment["design"]["surface_treatment"] = "arbitrary_geometry"
	var rejects_treatment := not CATALOG.validate_variant(invalid_treatment, "v2_control").is_empty()
	var rejects_unknown := not CATALOG.validate_variant(control, "not_a_variant").is_empty()
	return _check(rejects_extents and rejects_material and rejects_treatment and rejects_unknown,
		"catalog accepted an unsafe bound, material, surface treatment, or candidate ID")


func _test_variant_scene(variant_id: String) -> bool:
	var packed := load(CANDIDATE_SCENE) as PackedScene
	if packed == null:
		return _fail("could not load %s" % CANDIDATE_SCENE)
	var room := packed.instantiate() as Node3D
	var driver := room.get_node_or_null("VariantDriver")
	if driver == null:
		return _fail("candidate scene has no VariantDriver")
	driver.set("variant_id", variant_id)
	root.add_child(room)
	await process_frame
	await process_frame
	var ok := _verify_candidate_metadata(room, variant_id)
	ok = _verify_door_policy(room, variant_id) and ok
	ok = _verify_surface_treatment(room, variant_id) and ok
	room.queue_free()
	await process_frame
	return ok


func _verify_candidate_metadata(room: Node3D, variant_id: String) -> bool:
	var ok := _check(room.get_meta("design_candidate_id", "") == variant_id,
		"candidate ID was not applied: %s" % variant_id)
	var route_value: Variant = room.get_meta("walk_route", null)
	if not route_value is PackedVector2Array:
		return _fail("v2 route metadata is missing for %s" % variant_id) and ok
	var route: PackedVector2Array = route_value
	ok = _check(_matches_expected_route(route), "v2 route changed for %s" % variant_id) and ok
	var envelope_value: Variant = room.get_meta("walk_envelope", null)
	if not envelope_value is Rect2:
		return _fail("v2 walk envelope is missing for %s" % variant_id) and ok
	var envelope: Rect2 = envelope_value
	ok = _check(envelope == Rect2(-1.35, -2.8, 5.35, 6.2),
		"v2 walk envelope changed for %s" % variant_id) and ok
	ok = _check(room.has_node("AuthoredBoundaries/EastBoundary"),
		"v2 east boundary is missing for %s" % variant_id) and ok
	return ok


func _matches_expected_route(route: PackedVector2Array) -> bool:
	var expected := PackedVector2Array([
		Vector2(-0.65, 2.9), Vector2(0.5, 2.9), Vector2(0.5, 1.7),
		Vector2(1.25, 1.7), Vector2(2.6, 1.7), Vector2(2.6, 0.2),
		Vector2(3.5, 0.2),
	])
	if route.size() != expected.size():
		return false
	for index in range(route.size()):
		if route[index].distance_to(expected[index]) > 0.0001:
			return false
	return true


func _verify_door_policy(room: Node3D, variant_id: String) -> bool:
	var door := room.get_node_or_null("AuthoredBoundaries/EastServiceDoor") as MeshInstance3D
	if door == null:
		return _fail("service door mesh is missing for %s" % variant_id)
	if variant_id == "door_removed" or variant_id == "wall_endcap":
		var hidden := _check(not door.visible, "%s left the door visible" % variant_id)
		if variant_id == "wall_endcap":
			return _verify_wall_endcap(room) and hidden
		return hidden
	var frame := room.get_node_or_null("AuthoredBoundaries/EastServiceDoorFrame") as MeshInstance3D
	if frame == null:
		return _fail("service door frame is missing for %s" % variant_id)
	if variant_id in ["door_flush", "north_wall_smooth", "north_wall_source_texture",
		"clean_ceiling", "source_texture_cleanup", "source_floor_single_column",
		"source_floor_ceiling_single_column"]:
		var frame_ok := _check(is_equal_approx(frame.position.x, BASE_FRAME_X),
			"door_flush moved the existing frame")
		return _check(is_equal_approx(door.position.x, BASE_DOOR_X + FLUSH_SHIFT_M),
			"door_flush did not align the leaf to the fixed frame") and frame_ok
	return _check(door.visible, "v2 control unexpectedly hid its door") and _check(
		is_equal_approx(door.position.x, BASE_DOOR_X),
		"v2 control changed the service door position")


func _verify_wall_endcap(room: Node3D) -> bool:
	for node_name in ["DesignEndcapWallpaper", "DesignEndcapWainscot", "DesignEndcapRail"]:
		var panel := room.get_node_or_null(node_name) as MeshInstance3D
		if panel == null or not panel.visible or panel.get_child_count() != 0:
			return _fail("wall_endcap has a missing or non-visual-only panel: %s" % node_name)
	return true


func _verify_surface_treatment(room: Node3D, variant_id: String) -> bool:
	if variant_id == "north_wall_smooth":
		var north_wall := _first_mesh(room.get_node_or_null("AuthoredBoundaries/NorthBoundary"))
		if north_wall == null or north_wall.material_override == null:
			return _fail("north_wall_smooth did not apply a clean north-wall material")
		for index in range(4):
			var stile := room.get_node_or_null("DesignNorthWallStile%d" % index)
			if not stile is MeshInstance3D or stile.get_child_count() != 0:
				return _fail("north_wall_smooth is missing a visual-only wall stile")
		return true
	if variant_id == "north_wall_source_texture":
		var north_wall := _first_mesh(room.get_node_or_null("AuthoredBoundaries/NorthBoundary"))
		var material := north_wall.material_override as StandardMaterial3D if north_wall != null else null
		if material == null or material.albedo_texture == null:
			return _fail("north_wall_source_texture did not apply its source image")
		if not material.albedo_texture.resource_path.ends_with("wallpaper_source_video.png"):
			return _fail("north_wall_source_texture used an unexpected image")
		for index in range(4):
			if not room.get_node_or_null("DesignNorthWallStile%d" % index) is MeshInstance3D:
				return _fail("north_wall_source_texture changed the smooth-wall geometry")
		return true
	if variant_id == "clean_ceiling":
		var ceiling := room.get_node_or_null(
			"AuthoredBoundaries/CeilingBackstop") as MeshInstance3D
		if ceiling == null or ceiling.material_override == null:
			return _fail("clean_ceiling did not apply a clean ceiling material")
		if not is_equal_approx(ceiling.position.y, 1.435):
			return _fail("clean_ceiling did not lower the visual ceiling")
		for label in ["DesignCeilingGridX1", "DesignCeilingGridZ1"]:
			var rail := room.get_node_or_null(label)
			if not rail is MeshInstance3D or rail.get_child_count() != 0:
				return _fail("clean_ceiling is missing a visual-only grid rail: %s" % label)
	if variant_id == "source_floor_single_column":
		return _verify_aligned_source_floor_and_column(room)
	if variant_id == "source_floor_ceiling_single_column":
		return _verify_source_ceiling_column(room)
	if variant_id == "source_texture_cleanup":
		return _verify_source_texture_cleanup(room)
	return true


func _verify_source_texture_cleanup(room: Node3D) -> bool:
	var north := _first_mesh(room.get_node_or_null("AuthoredBoundaries/NorthBoundary"))
	var east := _first_mesh(room.get_node_or_null("AuthoredBoundaries/EastBoundary"))
	var ceiling := room.get_node_or_null("AuthoredBoundaries/CeilingBackstop") as MeshInstance3D
	if not _uses_texture(north, "wallpaper_source_video.png"):
		return _fail("source_texture_cleanup did not texture the north wall")
	if not _uses_texture(ceiling, "ceiling_source_video.png"):
		return _fail("source_texture_cleanup did not texture the ceiling")
	if east == null or not is_zero_approx(east.position.x):
		return _fail("source_texture_cleanup shifted the far wall and could hide the door")
	if not is_equal_approx(north.position.z, -0.08):
		return _fail("source north-wall face was not brought forward to cover artifacts")
	if not is_equal_approx(ceiling.position.y, 1.55):
		return _fail("source-textured ceiling did not cover the noisy ceiling layer")
	return _verify_source_floor_and_column(room)


func _verify_source_floor_and_column(room: Node3D) -> bool:
	var floor := room.get_node_or_null("DesignSourceFloor") as MeshInstance3D
	var column := room.get_node_or_null("DesignSourceColumn") as MeshInstance3D
	if not _uses_texture(floor, "floor_source_video.png"):
		return _fail("source_texture_cleanup did not add the source floor cover")
	if not _uses_texture(column, "column_source_video.png"):
		return _fail("source_texture_cleanup did not wrap the column")
	if floor.get_child_count() != 0 or column.get_child_count() != 0:
		return _fail("source surface cleanup added collision beneath visual-only meshes")
	return true


func _verify_aligned_source_floor_and_column(room: Node3D) -> bool:
	var floor := room.get_node_or_null("DesignSourceFloor") as MeshInstance3D
	var column := room.get_node_or_null("DesignAlignedSourceColumn") as MeshInstance3D
	if not _uses_texture(floor, "floor_source_video.png"):
		return _fail("source floor-column variant is missing its floor texture")
	if not _uses_texture(column, "column_source_video.png"):
		return _fail("source floor-column variant is missing its column texture")
	if room.has_node("DesignSourceColumn"):
		return _fail("source floor-column variant kept the offset second column")
	var expected := Vector3(1.25, 0.3285, 0.2)
	if column.position.distance_to(expected) > 0.0001:
		return _fail("aligned source column is not on the existing centerline")
	return _check(floor.get_child_count() == 0 and column.get_child_count() == 0,
		"source floor-column variant added collision to visual-only meshes")


func _verify_source_ceiling_column(room: Node3D) -> bool:
	if not _verify_aligned_source_floor_and_column(room):
		return false
	var ceiling := room.get_node_or_null("AuthoredBoundaries/CeilingBackstop") as MeshInstance3D
	if not _uses_texture(ceiling, "ceiling_source_video.png"):
		return _fail("source ceiling-column variant is missing its ceiling texture")
	if not is_equal_approx(ceiling.position.y, 1.0):
		return _fail("source ceiling was not lowered to cover the artifact layer")
	for boundary_name in ["WestBoundary", "EastBoundary", "NorthBoundary", "SouthBoundary"]:
		if not _wall_mesh_meets_source_ceiling(room, boundary_name):
			return false
	return _verify_source_ceiling_trim(room)


func _wall_mesh_meets_source_ceiling(room: Node3D, boundary_name: String) -> bool:
	var boundary := room.get_node_or_null("AuthoredBoundaries/" + boundary_name) as Node3D
	var mesh := _first_mesh(boundary)
	if boundary == null or mesh == null:
		return _fail("source ceiling variant is missing wall mesh %s" % boundary_name)
	var visible_top := boundary.position.y + mesh.position.y \
		+ (mesh.scale.y * 2.943) * 0.5
	return _check(is_equal_approx(visible_top, 1.035),
		"%s visual wall does not meet the lowered ceiling" % boundary_name)


func _verify_source_ceiling_trim(room: Node3D) -> bool:
	for label in ["DesignCeilingTrimNorth", "DesignCeilingTrimSouth",
		"DesignCeilingTrimWest", "DesignCeilingTrimEast"]:
		var trim := room.get_node_or_null(label) as MeshInstance3D
		if trim == null or trim.get_child_count() != 0:
			return _fail("source ceiling variant is missing visual-only trim %s" % label)
	return true


func _uses_texture(mesh: MeshInstance3D, filename: String) -> bool:
	if mesh == null or mesh.material_override == null:
		return false
	var material := mesh.material_override as StandardMaterial3D
	return material != null and material.albedo_texture != null \
		and material.albedo_texture.resource_path.ends_with(filename)


func _first_mesh(parent: Node) -> MeshInstance3D:
	if parent == null:
		return null
	for child in parent.get_children():
		if child is MeshInstance3D:
			return child
	return null


func _check(condition: bool, message: String) -> bool:
	return true if condition else _fail(message)


func _fail(message: String) -> bool:
	printerr("FAIL: %s" % message)
	return false
