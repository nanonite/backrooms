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
	var start_marker := instance.find_child("AuthoredRouteStartEndMarker", true, false) as MeshInstance3D
	if floor_shape == null or not floor_shape.shape is ConcavePolygonShape3D:
		_fail("authored route did not create a concave floor collider")
		return
	if column_shape == null or not column_shape.shape is BoxShape3D:
		_fail("reviewed column did not create a box obstacle collider")
		return
	if not _marker_matches_report(start_marker):
		_fail("route start/end marker is missing or misplaced")
		return
	if floor_shape.shape.get_faces().size() < 3:
		_fail("authored floor collider has no triangle faces")
		return
	print("OK: Godot imported the experimental route GLB and created separate floor and column colliders")
	quit(0)


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
