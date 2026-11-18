extends SceneTree

# Deterministic headless checks for issue 270. Verifies a finite world-fixed
# ring, a static sky at infinity, no collision or implied route, the bounded
# camera path, the disabled baseline, and a threshold angular parallax shift
# between the two separated same-orientation views.
const VARIANT_SCENE := preload("res://evidence/2026-11-17-issue-270-horizon-ring/fixture/horizon_ring_v1.tscn")
const BASELINE_SCENE := preload("res://evidence/2026-11-17-issue-270-horizon-ring/fixture/baseline_sky_v1.tscn")
const HORIZON_SPEC_PATH := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/horizon_spec_v1.json"
const VIEWS_PATH := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/views_v1.json"

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var spec := _read(HORIZON_SPEC_PATH)
	var views := _read(VIEWS_PATH)
	_assert(not spec.is_empty(), "could not read horizon spec")
	_assert(not views.is_empty(), "could not read views record")
	var variant := VARIANT_SCENE.instantiate() as Node3D
	root.add_child(variant)
	var baseline := BASELINE_SCENE.instantiate() as Node3D
	root.add_child(baseline)
	await _frames(2)
	_check_flags(variant, baseline)
	_check_sky(variant, baseline)
	_check_ring(variant, spec)
	_check_no_collision(variant, baseline)
	_check_baseline_disabled(baseline)
	_check_parallax(variant, baseline, spec, views)
	if not _failed:
		print("ISSUE_270_FIXTURE_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_flags(variant: Node3D, baseline: Node3D) -> void:
	for room: Node3D in [variant, baseline]:
		for flag in ["registration_accepted", "scale_calibrated", "operator_approved"]:
			_assert(not bool(room.get_meta(flag)), "%s %s must be false" % [room.name, flag])
	_assert(bool(variant.get_meta("horizon_enabled")), "variant horizon must be enabled")
	_assert(not bool(baseline.get_meta("horizon_enabled")), "baseline horizon must be disabled")
	_assert(variant.get_meta("collision_policy") == "none", "variant collision policy must be none")


func _check_sky(variant: Node3D, baseline: Node3D) -> void:
	for room: Node3D in [variant, baseline]:
		var world := room.get_node_or_null("StaticSkyBackground/WorldEnvironment") as WorldEnvironment
		_assert(world != null, "%s has no static sky WorldEnvironment" % room.name)
		if world == null:
			continue
		var environment: Environment = world.environment
		_assert(environment != null and environment.background_mode == Environment.BG_SKY,
			"%s sky must be BG_SKY (rendered at infinity)" % room.name)
		_assert(environment.sky != null
			and environment.sky.sky_material is ProceduralSkyMaterial,
			"%s sky material must be a static procedural gradient" % room.name)
		_assert(world.get_meta("rendered_at") == "infinity", "%s sky must be marked infinity" % room.name)


func _check_ring(variant: Node3D, spec: Dictionary) -> void:
	var ring: Dictionary = spec["ring"]
	var heights: Array = spec["panel_heights"]
	var count := int(ring["segment_count"])
	var radius := float(ring["radius"])
	var group := variant.get_node_or_null("AuthoredHorizonRing") as Node3D
	_assert(group != null, "variant has no authored horizon group")
	if group == null:
		return
	_assert(group.get_child_count() == count, "ring panel count does not match the authored spec")
	var seen: Dictionary = {}
	for index in count:
		var panel := group.get_node("RingPanel_%02d" % index) as MeshInstance3D
		_assert(panel != null, "ring panel %d is missing" % index)
		if panel == null:
			continue
		_assert(panel.get_meta("classification") == "authored", "panel %d is not authored" % index)
		var distance := Vector2(panel.global_position.x, panel.global_position.z).length()
		_assert(absf(distance - radius) < 0.01, "panel %d is not on the fixed ring radius" % index)
		var expected_height := float(heights[index])
		var mesh := panel.mesh as BoxMesh
		_assert(mesh != null and absf(mesh.size.y - expected_height) < 0.001,
			"panel %d height does not match the authored array" % index)
		_assert(absf(panel.global_position.y - float(ring["panel_base_y"]) - expected_height * 0.5) < 0.01,
			"panel %d base is not at the authored y" % index)
		var key := "%d" % index
		_assert(not seen.has(key), "panel %d is duplicated" % index)
		seen[key] = true
	_assert(seen.size() == count, "ring panel positions are not distinct")


func _check_no_collision(variant: Node3D, baseline: Node3D) -> void:
	_assert(not _has_collision(variant), "variant horizon has collision or an implied route")
	_assert(not _has_collision(baseline), "baseline has collision or an implied route")


func _check_baseline_disabled(baseline: Node3D) -> void:
	var group := baseline.get_node_or_null("AuthoredHorizonRing") as Node3D
	_assert(group != null, "baseline must declare the disabled horizon group")
	if group != null:
		_assert(group.get_child_count() == 0, "baseline must have zero finite horizon panels")
	_assert(_mesh_count(baseline) == 0, "baseline must contain no finite silhouette geometry")


func _check_parallax(variant: Node3D, baseline: Node3D, spec: Dictionary, views: Dictionary) -> void:
	var path: Dictionary = spec["camera_path"]
	var parallax: Dictionary = spec["parallax"]
	var a := _find_view(views["views"], "translate_a")
	var b := _find_view(views["views"], "translate_b")
	var rotated := _find_view(views["views"], "rotated")
	_assert(a != null and b != null and rotated != null, "required comparison views are missing")
	if a == null or b == null or rotated == null:
		return
	var dir_a := _direction(a)
	var dir_b := _direction(b)
	_assert(dir_a.distance_to(dir_b) < 0.0001, "translate_a and translate_b must share one orientation")
	var pos_a := _position(a)
	var pos_b := _position(b)
	_assert(absf(pos_b.x - pos_a.x) >= 5.0, "the two camera positions must be clearly separated")
	_assert(rotated["position"][0] == a["position"][0]
		and rotated["position"][1] == a["position"][1]
		and rotated["position"][2] == a["position"][2],
		"rotated view must hold the translate_a position in place")
	_assert(_direction(rotated).distance_to(dir_a) > 0.5, "rotated view must change orientation")
	for entry: Dictionary in views["views"] + views["movement_sequence"]["steps"]:
		if entry.has("on_path") and not bool(entry["on_path"]):
			continue
		var p := _position(entry)
		_assert(p.x >= float(path["min_x"]) - 0.0001 and p.x <= float(path["max_x"]) + 0.0001,
			"view %s leaves the bounded path" % entry["id"])
		_assert(absf(p.y - float(path["y"])) < 0.0001 and absf(p.z - float(path["z"])) < 0.0001,
			"view %s leaves the authored path height/z" % entry["id"])

	var index := int(parallax["sampled_panel_index"])
	var panel := variant.get_node("AuthoredHorizonRing/RingPanel_%02d" % index) as MeshInstance3D
	_assert(panel != null, "sampled parallax panel is missing")
	if panel != null:
		var world_point := panel.global_position
		var angle_a := _horizontal_angle(pos_a, dir_a, world_point)
		var angle_b := _horizontal_angle(pos_b, dir_b, world_point)
		var shift := absf(angle_a - angle_b)
		var minimum := float(parallax["min_angular_shift_deg"])
		_assert(shift >= minimum, "finite horizon parallax shift %.3f deg is below %.3f" % [shift, minimum])
		print("ISSUE_270_PARALLAX: panel=%d shift_deg=%.3f (sky shift=0 by construction, BG_SKY at infinity)" % [index, shift])

	# The captured cameras must be reproducible: look_at yields the authored direction.
	var camera := variant.get_node("InspectionCamera") as Camera3D
	var baseline_camera := baseline.get_node("InspectionCamera") as Camera3D
	_assert(camera != null and baseline_camera != null, "inspection cameras are missing")
	for entry: Dictionary in views["views"]:
		for cam: Camera3D in [camera, baseline_camera]:
			if cam == null:
				continue
			cam.position = _position(entry)
			cam.look_at(_target(entry), Vector3.UP)
			_assert(-cam.global_transform.basis.z.dot(_direction(entry)) > 0.999,
				"camera orientation is not reproducible for %s" % entry["id"])


func _position(view: Dictionary) -> Vector3:
	var v: Array = view["position"]
	return Vector3(v[0], v[1], v[2])


func _target(view: Dictionary) -> Vector3:
	var v: Array = view["target"]
	return Vector3(v[0], v[1], v[2])


func _direction(view: Dictionary) -> Vector3:
	return (_target(view) - _position(view)).normalized()


func _horizontal_angle(position: Vector3, forward: Vector3, point: Vector3) -> float:
	var right := forward.cross(Vector3.UP).normalized()
	var delta := point - position
	return rad_to_deg(atan2(delta.dot(right), delta.dot(forward)))


func _find_view(entries: Array, view_id: String) -> Dictionary:
	for entry: Dictionary in entries:
		if entry["id"] == view_id:
			return entry
	return {}


func _read(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return {}
	return parsed


func _has_collision(node: Node) -> bool:
	if node is CollisionObject3D or node is CollisionShape3D:
		return true
	for child in node.get_children():
		if _has_collision(child):
			return true
	return false


func _mesh_count(node: Node) -> int:
	var count := 0
	if node is MeshInstance3D:
		count += 1
	for child in node.get_children():
		count += _mesh_count(child)
	return count


func _frames(count: int) -> void:
	for _index in count:
		await process_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("ISSUE_270_TEST_FAILURE: ", message)
