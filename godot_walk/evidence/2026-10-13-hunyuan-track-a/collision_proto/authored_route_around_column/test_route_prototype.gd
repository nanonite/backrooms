extends SceneTree

const SCENE_PATH := "res://evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/route_prototype.tscn"
const REPORT_PATH := "res://evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/route_report.json"


func _initialize() -> void:
	call_deferred("_verify_scene")


func _verify_scene() -> void:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		_fail("Godot route scene could not be loaded")
		return
	var instance := packed.instantiate()
	root.add_child(instance)
	await process_frame
	var floor_shape := instance.find_child("AuthoredPlanarFloorShape", true, false) as CollisionShape3D
	var column_shape := instance.find_child("ColumnObstacleBoxShape", true, false) as CollisionShape3D
	var inner_shape := instance.find_child("AuthoredEdgeBoundaryInnerShape", true, false) as CollisionShape3D
	var outer_shape := instance.find_child("AuthoredEdgeBoundaryOuterShape", true, false) as CollisionShape3D
	var inner_mesh := instance.find_child("authored_edge_boundary_inner", true, false) as MeshInstance3D
	var outer_mesh := instance.find_child("authored_edge_boundary_outer", true, false) as MeshInstance3D
	var start_marker := instance.find_child("AuthoredRouteStartEndMarker", true, false) as MeshInstance3D
	if floor_shape == null or not floor_shape.shape is ConcavePolygonShape3D:
		_fail("authored route did not create a concave floor collider")
		return
	if column_shape == null or not column_shape.shape is BoxShape3D:
		_fail("reviewed column did not create a box obstacle collider")
		return
	if not _boundary_is_valid(inner_shape, inner_mesh, "inner"):
		return
	if not _boundary_is_valid(outer_shape, outer_mesh, "outer"):
		return
	if not _marker_matches_report(start_marker):
		_fail("route start/end marker is missing or misplaced")
		return
	if floor_shape.shape.get_faces().size() < 3:
		_fail("authored floor collider has no triangle faces")
		return
	print("OK: Godot imported the route GLB and created floor, column and authored edge colliders")
	quit(0)


func _boundary_is_valid(shape: CollisionShape3D, mesh: MeshInstance3D, side: String) -> bool:
	if shape == null or not shape.shape is ConcavePolygonShape3D or mesh == null or mesh.mesh == null:
		_fail("authored %s edge boundary did not create a triangle collider" % side)
		return false
	if mesh.global_transform != Transform3D.IDENTITY:
		_fail("authored %s edge boundary GLB transform is not identity" % side)
		return false
	var report: Variant = JSON.parse_string(FileAccess.get_file_as_string(REPORT_PATH))
	if not report is Dictionary:
		_fail("route provenance report is invalid")
		return false
	var expected_height := float(report.get("edge_boundaries", {}).get("height_m", 0.0))
	if not is_equal_approx(mesh.mesh.get_aabb().size.y, expected_height):
		_fail("authored %s boundary height differs from report" % side)
		return false
	var body := shape.get_parent() as StaticBody3D
	if body == null or body.get_meta("origin", "") != "authored_not_reconstructed":
		_fail("authored %s boundary is missing its authored provenance label" % side)
		return false
	return true


func _marker_matches_report(marker: MeshInstance3D) -> bool:
	if marker == null or marker.mesh == null:
		return false
	var report: Variant = JSON.parse_string(FileAccess.get_file_as_string(REPORT_PATH))
	if not report is Dictionary:
		return false
	var start_xz: Array = report.get("route", {}).get("start_xz_m", [])
	if start_xz.size() != 2:
		return false
	var floor_y := float(report.get("plane", {}).get("height_m", 0.0))
	var expected := Vector3(float(start_xz[0]), floor_y + 0.013, float(start_xz[1]))
	return marker.position.is_equal_approx(expected)


func _fail(message: String) -> void:
	printerr("FAIL: %s" % message)
	quit(1)
