extends SceneTree

# Deterministic headless checks for issue 271. Verifies that the reference and
# candidate scenes are geometrically identical node by node, that only the 12
# bench stone parts change material origin, that the statue plinth keeps the
# shared robe crop, that the authored parameters match the decision record, that
# declared geometry/collision matches the instantiated scenes, and that every
# comparison view is reproducible from its recorded transform.
const REFERENCE_SCENE := preload("res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/bench_reference_v1.tscn")
const CANDIDATE_SCENE := preload("res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/bench_candidate_v1.tscn")
const DECISION_PATH := "res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/bench_material_decision_v1.json"
const GEOMETRY_PATH := "res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/bench_geometry_v1.json"
const VIEWS_PATH := "res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/views_v1.json"

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var decision := _read(DECISION_PATH)
	var geometry := _read(GEOMETRY_PATH)
	var views := _read(VIEWS_PATH)
	_assert(not decision.is_empty(), "could not read material decision")
	_assert(not geometry.is_empty(), "could not read geometry record")
	_assert(not views.is_empty(), "could not read views record")
	var reference := REFERENCE_SCENE.instantiate() as Node3D
	root.add_child(reference)
	var candidate := CANDIDATE_SCENE.instantiate() as Node3D
	root.add_child(candidate)
	await _frames(2)

	_check_flags(reference, candidate)
	_check_geometry_equality(reference, candidate)
	_check_origins(reference, candidate, decision)
	_check_authored_material(candidate, decision)
	_check_declarations(candidate, geometry)
	_check_views(candidate, views)
	if not _failed:
		print("ISSUE_271_FIXTURE_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_flags(reference: Node3D, candidate: Node3D) -> void:
	for room: Node3D in [reference, candidate]:
		for flag in ["registration_accepted", "scale_calibrated", "operator_approved"]:
			_assert(not bool(room.get_meta(flag)), "%s %s must be false" % [room.name, flag])
	_assert(reference.get_meta("bench_material_mode") == "reference", "reference mode missing")
	_assert(candidate.get_meta("bench_material_mode") == "candidate", "candidate mode missing")


func _check_geometry_equality(reference: Node3D, candidate: Node3D) -> void:
	var reference_geometry: Array[String] = []
	var candidate_geometry: Array[String] = []
	var reference_origins: Dictionary = {}
	var candidate_origins: Dictionary = {}
	_collect(reference, "", reference_geometry, reference_origins)
	_collect(candidate, "", candidate_geometry, candidate_origins)
	reference_geometry.sort()
	candidate_geometry.sort()
	_assert(reference_geometry.size() == candidate_geometry.size(),
		"scene node counts differ")
	_assert(reference_geometry == candidate_geometry,
		"candidate geometry, transforms or collision differ from the reference")


func _collect(node: Node, prefix: String, geometry: Array[String], origins: Dictionary) -> void:
	for child: Node in node.get_children():
		var key := prefix + "/" + child.name
		var parts: Array[String] = [key, child.get_class()]
		if child is Node3D:
			parts.append("pos=" + str(child.position))
			parts.append("rot=" + str(child.rotation))
			parts.append("scale=" + str(child.scale))
		if child is MeshInstance3D:
			var mesh: Mesh = (child as MeshInstance3D).mesh
			if mesh is BoxMesh:
				parts.append("mesh=BoxMesh size=" + str(mesh.size))
			elif mesh is CylinderMesh:
				parts.append("mesh=CylinderMesh r=%s h=%s seg=%s" % [str(mesh.top_radius), str(mesh.height), str(mesh.radial_segments)])
			elif mesh is SphereMesh:
				parts.append("mesh=SphereMesh r=%s h=%s" % [str(mesh.radius), str(mesh.height)])
		if child is CollisionShape3D and child.shape is BoxShape3D:
			parts.append("shape=BoxShape3D size=" + str(child.shape.size))
		geometry.append("|".join(parts))
		if child.has_meta("material_origin"):
			origins[key] = String(child.get_meta("material_origin"))
		_collect(child, key, geometry, origins)


func _check_origins(reference: Node3D, candidate: Node3D, decision: Dictionary) -> void:
	var reference_origins: Dictionary = {}
	var candidate_origins: Dictionary = {}
	var throwaway: Array[String] = []
	_collect(reference, "", throwaway, reference_origins)
	throwaway.clear()
	_collect(candidate, "", throwaway, candidate_origins)
	var changed: Dictionary = {}
	for assignment: Dictionary in decision["bench_assignments"]:
		var key := "/AuthoredVisuals/" + String(assignment["part"])
		if assignment["candidate_material_key"] == "bench_stone":
			changed[key] = true
			_assert(reference_origins.get(key) == "source_crop:stone_robe",
				"%s reference must use the robe crop" % key)
			_assert(candidate_origins.get(key) == "project_authored",
				"%s candidate must use the authored fallback" % key)
		else:
			_assert(not changed.has(key), "%s must not be in the changed set" % key)
			_assert(reference_origins.get(key) == "project_authored_solid:post" and candidate_origins.get(key) == "project_authored_solid:post",
				"%s bollard material must be unchanged" % key)
	_assert(changed.size() == 12, "exactly 12 stone bench parts must change")
	var plinth_key := "/AuthoredVisuals/StatuePlinth"
	_assert(reference_origins.get(plinth_key) == "source_crop:stone_robe", "reference plinth keeps the robe crop")
	_assert(candidate_origins.get(plinth_key) == "source_crop:stone_robe", "candidate plinth must not silently change")
	var keys: Dictionary = {}
	for key: String in reference_origins:
		keys[key] = true
	for key: String in candidate_origins:
		keys[key] = true
	for key: String in keys:
		if not changed.has(key):
			_assert(reference_origins.get(key) == candidate_origins.get(key),
				"%s changed outside the bench stone parts" % key)


func _check_authored_material(candidate: Node3D, decision: Dictionary) -> void:
	var authored: Dictionary = decision["authored_material"]
	var parameters: Dictionary = authored["parameters"]
	var expected_color: Array = parameters["albedo_color_rgba"]
	var bench := candidate.get_node("AuthoredVisuals/BenchSeat") as MeshInstance3D
	_assert(bench != null, "bench seat is missing")
	if bench == null:
		return
	var material := bench.material_override as StandardMaterial3D
	_assert(material != null, "bench seat has no material override")
	if material == null:
		return
	_assert(material.albedo_texture == null, "authored fallback must not carry a texture")
	_assert(absf(material.albedo_color.r - float(expected_color[0])) < 0.0001, "authored red mismatch")
	_assert(absf(material.albedo_color.g - float(expected_color[1])) < 0.0001, "authored green mismatch")
	_assert(absf(material.albedo_color.b - float(expected_color[2])) < 0.0001, "authored blue mismatch")
	_assert(absf(material.albedo_color.a - float(expected_color[3])) < 0.0001, "authored alpha mismatch")
	_assert(is_equal_approx(material.roughness, float(parameters["roughness"])), "authored roughness mismatch")
	_assert(material.metallic == 0.0, "authored metallic must be zero")
	_assert(material.get_meta("origin") == "project_authored", "authored material origin meta missing")
	var plinth := candidate.get_node("AuthoredVisuals/StatuePlinth") as MeshInstance3D
	_assert(plinth != null, "statue plinth is missing")
	if plinth != null:
		var plinth_material := plinth.material_override as StandardMaterial3D
		_assert(plinth_material != null and plinth_material.albedo_texture != null,
			"candidate plinth must keep the reference robe crop")


func _check_declarations(room: Node3D, geometry: Dictionary) -> void:
	for entry: Dictionary in geometry["bench_parts"]:
		var node := room.get_node_or_null("AuthoredVisuals/%s" % entry["part"]) as MeshInstance3D
		_assert(node != null, "declared bench part missing: %s" % entry["part"])
		if node == null:
			continue
		_assert(_vector_equal(node.position, entry["center"]), "%s center differs" % entry["part"])
		if entry["kind"] == "box":
			var mesh := node.mesh as BoxMesh
			_assert(mesh != null and _vector_equal(mesh.size, entry["size"]), "%s size differs" % entry["part"])
		else:
			var mesh := node.mesh as CylinderMesh
			_assert(mesh != null
				and is_equal_approx(mesh.top_radius, float(entry["radius"]))
				and is_equal_approx(mesh.height, float(entry["height"])),
				"%s cylinder differs" % entry["part"])
	for entry: Dictionary in geometry["colliders"]:
		var name: String = entry["name"]
		var parent_name: String = entry["parent"]
		var body := room.get_node_or_null("%s/%s" % [parent_name, name]) as StaticBody3D
		_assert(body != null, "declared collider missing: %s" % name)
		if body == null:
			continue
		_assert(_vector_equal(body.position, entry["center"]), "%s center differs" % name)
		var collision := body.get_node("Collision") as CollisionShape3D
		var shape: BoxShape3D = null
		if collision != null:
			shape = collision.shape as BoxShape3D
		_assert(shape != null and _vector_equal(shape.size, entry["size"]), "%s size differs" % name)


func _check_views(room: Node3D, views: Dictionary) -> void:
	var camera := room.get_node("InspectionCamera") as Camera3D
	_assert(camera != null, "inspection camera missing")
	if camera == null:
		return
	for required in ["bench_close", "bench_oblique", "wider_scene", "plinth_check"]:
		var view := _find_view(views["views"], required)
		_assert(view != null, "required view missing: %s" % required)
		if view == null:
			continue
		var position_array: Array = view["position"]
		var target_array: Array = view["target"]
		var position := Vector3(position_array[0], position_array[1], position_array[2])
		var target := Vector3(target_array[0], target_array[1], target_array[2])
		camera.position = position
		camera.look_at(target, Vector3.UP)
		var orientation := -(camera.global_transform.basis.z)
		var expected := (target - position).normalized()
		_assert(orientation.distance_to(expected) < 0.0001, "camera orientation not reproducible: %s" % required)


func _find_view(entries: Array, id: String) -> Dictionary:
	for entry: Dictionary in entries:
		if entry["id"] == id:
			return entry
	return {}


func _vector_equal(actual: Vector3, declared: Array) -> bool:
	_assert(declared is Array and declared.size() == 3, "invalid declared vector")
	if not declared is Array or declared.size() != 3:
		return false
	return absf(actual.x - float(declared[0])) < 0.0001 \
		and absf(actual.y - float(declared[1])) < 0.0001 \
		and absf(actual.z - float(declared[2])) < 0.0001


func _read(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("Could not read record: %s" % path)
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		push_error("Invalid record: %s" % path)
		return {}
	return parsed


func _frames(count: int) -> void:
	for _index in count:
		await process_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("ISSUE_271_ASSERT: ", message)
