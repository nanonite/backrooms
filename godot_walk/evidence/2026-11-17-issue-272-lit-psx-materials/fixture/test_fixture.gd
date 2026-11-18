extends SceneTree

# Deterministic headless checks for issue 272. Verifies that all four opt-in
# scenes load with independent surface/lighting selection, identical geometry,
# camera, light and fog, the correct shader assignment, a repeatable light toggle,
# and reproducible comparison views. Renders nothing and approves nothing.
const BASE := "res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/"
const SCENES := {
	"baseline_solid": BASE + "psx_baseline_solid_v1.tscn",
	"lit_solid": BASE + "psx_lit_solid_v1.tscn",
	"baseline_textured": BASE + "psx_baseline_textured_v1.tscn",
	"lit_textured": BASE + "psx_lit_textured_v1.tscn",
}
const VIEWS_PATH := BASE + "views_v1.json"
const FLAGS := ["registration_accepted", "scale_calibrated", "operator_approved"]

var _failed := false


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_shader_defines()
	_check_geometry_identical()
	_check_shader_selection()
	_check_light_toggle()
	_check_views()
	if not _failed:
		print("ISSUE_272_FIXTURE_TESTS_PASSED")
		quit(0)
	else:
		quit(1)


func _check_shader_defines() -> void:
	var cases := {
		"psx_solid_baseline_v1.gdshader": {"unshaded": true, "fog": true, "texture": "TEXTURE_DISABLED"},
		"psx_solid_lit_v1.gdshader": {"unshaded": false, "fog": true, "texture": "TEXTURE_DISABLED"},
		"psx_textured_baseline_v1.gdshader": {"unshaded": true, "fog": true, "texture": "TEXTURE_REPEAT"},
		"psx_textured_lit_v1.gdshader": {"unshaded": false, "fog": true, "texture": "TEXTURE_REPEAT"},
	}
	for file_name: String in cases:
		var file := FileAccess.open(BASE + file_name, FileAccess.READ)
		_assert(file != null, "cannot read shader %s" % file_name)
		if file == null:
			continue
		var text := file.get_as_text()
		var expected: Dictionary = cases[file_name]
		_assert(text.contains("#define UNSHADED") == bool(expected["unshaded"]),
			"UNSHADED define mismatch in %s" % file_name)
		_assert(text.contains("#define FOG_DISABLED") == bool(expected["fog"]),
			"FOG_DISABLED must be set in %s" % file_name)
		_assert(text.contains("#define %s" % expected["texture"]),
			"texture path %s missing in %s" % [expected["texture"], file_name])
		_assert(text.contains("#include \"res://vendor/ursc/common.gdshaderinc\""),
			"shared PSX include missing in %s" % file_name)
		_assert(text.contains("shader_type spatial;"), "not a spatial shader: %s" % file_name)


func _check_geometry_identical() -> void:
	var baseline: Array[String] = []
	var first := true
	for key: String in SCENES:
		var packed := load(SCENES[key]) as PackedScene
		_assert(packed != null, "cannot load scene %s" % key)
		if packed == null:
			continue
		var room := packed.instantiate() as Node3D
		root.add_child(room)
		await _frames(2)
		for flag in FLAGS:
			_assert(not bool(room.get_meta(flag)), "%s %s must be false" % [key, flag])
		_assert(not bool(room.get_meta("light_on")), "%s must start light-off" % key)
		var geometry: Array[String] = []
		_collect(room, "", geometry)
		geometry.sort()
		if first:
			baseline = geometry
			first = false
		else:
			_assert(geometry == baseline, "%s geometry/camera/light differs from baseline" % key)
		room.free()


func _collect(node: Node, prefix: String, geometry: Array[String]) -> void:
	for child: Node in node.get_children():
		var key := prefix + "/" + child.name
		var parts: Array[String] = [key, child.get_class()]
		if child is Node3D:
			parts.append("pos=" + str(child.position))
			parts.append("rot=" + str(child.rotation_degrees))
			parts.append("scale=" + str(child.scale))
		if child is Camera3D:
			parts.append("fov=%s near=%s far=%s" % [str(child.fov), str(child.near), str(child.far)])
		if child is DirectionalLight3D:
			parts.append("light_energy=%s light_color=%s rot=%s shadow=%s" % [
				str(child.light_energy), str(child.light_color), str(child.rotation_degrees), str(child.shadow_enabled)])
		if child is WorldEnvironment and child.environment != null:
			parts.append("ambient_src=%s ambient_color=%s fog_enabled=%s" % [
				str(child.environment.ambient_light_source), str(child.environment.ambient_light_color),
				str(child.environment.fog_enabled)])
		if child is MeshInstance3D:
			var mesh: Mesh = (child as MeshInstance3D).mesh
			if mesh is BoxMesh:
				parts.append("mesh=BoxMesh size=" + str(mesh.size))
			elif mesh is SphereMesh:
				parts.append("mesh=SphereMesh r=%s h=%s" % [str(mesh.radius), str(mesh.height)])
			elif mesh is CylinderMesh:
				parts.append("mesh=CylinderMesh r=%s h=%s" % [str(mesh.top_radius), str(mesh.height)])
		geometry.append("|".join(parts))
		_collect(child, key, geometry)


func _check_shader_selection() -> void:
	var expected_paths := {
		"baseline_solid": "psx_solid_baseline_v1.gdshader",
		"lit_solid": "psx_solid_lit_v1.gdshader",
		"baseline_textured": "psx_textured_baseline_v1.gdshader",
		"lit_textured": "psx_textured_lit_v1.gdshader",
	}
	for key: String in SCENES:
		var packed := load(SCENES[key]) as PackedScene
		if packed == null:
			continue
		var room := packed.instantiate() as Node3D
		root.add_child(room)
		await _frames(1)
		var expected: String = expected_paths[key]
		_assert(String(room.get_meta("shader")).ends_with(expected),
			"%s shader meta mismatch: %s" % [key, room.get_meta("shader")])
		var surface := room.get_node_or_null("Surfaces/Sphere") as MeshInstance3D
		_assert(surface != null, "%s sphere is missing" % key)
		var material: ShaderMaterial = null
		if surface != null:
			material = surface.material_override as ShaderMaterial
			_assert(String(surface.get_meta("shader")).ends_with(expected),
				"%s surface shader meta mismatch" % key)
		_assert(material != null and material.shader != null, "%s has no shader material" % key)
		if material != null and material.shader != null:
			_assert(material.shader.resource_path.ends_with(expected),
				"%s assigned shader mismatch: %s" % [key, material.shader.resource_path])
			var texture = material.get_shader_parameter("albedo_texture")
			if key.ends_with("textured"):
				_assert(texture != null, "%s textured path needs an albedo texture" % key)
			else:
				_assert(texture == null, "%s solid path must not have an albedo texture" % key)
		room.free()


func _check_light_toggle() -> void:
	var packed := load(SCENES["lit_solid"]) as PackedScene
	if packed == null:
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	await _frames(1)
	var light := room.get_node("KeyLight") as DirectionalLight3D
	var world := room.get_node("WorldEnvironment") as WorldEnvironment
	room.call("set_light_on", true)
	_assert(light.visible, "set_light_on(true) must show the key light")
	_assert(world.environment.ambient_light_energy > 0.0, "set_light_on(true) must enable ambient")
	room.call("set_light_on", false)
	_assert(not light.visible, "set_light_on(false) must hide the key light")
	_assert(is_equal_approx(world.environment.ambient_light_energy, 0.0),
		"set_light_on(false) must disable ambient")
	room.call("set_light_on", true)
	_assert(light.visible, "light toggle must be repeatable")
	room.free()


func _check_views() -> void:
	var file := FileAccess.open(VIEWS_PATH, FileAccess.READ)
	_assert(file != null, "cannot read views record")
	if file == null:
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	_assert(parsed is Dictionary and parsed.has("views"), "invalid views record")
	if not parsed is Dictionary or not parsed.has("views"):
		return
	var packed := load(SCENES["baseline_solid"]) as PackedScene
	if packed == null:
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	var camera := room.get_node("InspectionCamera") as Camera3D
	_assert(camera != null, "inspection camera missing")
	if camera == null:
		return
	for view: Dictionary in parsed["views"]:
		var position_array: Array = view["position"]
		var target_array: Array = view["target"]
		var position := Vector3(position_array[0], position_array[1], position_array[2])
		var target := Vector3(target_array[0], target_array[1], target_array[2])
		camera.position = position
		camera.look_at(target, Vector3.UP)
		var orientation := -(camera.global_transform.basis.z)
		var expected := (target - position).normalized()
		_assert(orientation.distance_to(expected) < 0.0001,
			"camera orientation not reproducible: %s" % view["id"])
	room.free()


func _frames(count: int) -> void:
	for _index in count:
		await process_frame


func _assert(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	printerr("ISSUE_272_ASSERT: ", message)
