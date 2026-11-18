extends Node3D

# Visual-only experiment for issue 270: a finite, world-fixed silhouette ring
# against a static sky. No collision, no floor, no traversal and no implied
# route. All placement is authored in uncalibrated design units.
const HORIZON_SPEC_PATH := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/horizon_spec_v1.json"

var ring_spec: Dictionary = {}


func _ready() -> void:
	set_meta("fixture_id", "issue_270_horizon_ring_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("representation", "finite_authored_world_fixed_silhouette_ring")
	set_meta("collision_policy", "none")
	set_meta("horizon_enabled", true)
	var horizon := Node3D.new()
	horizon.name = "AuthoredHorizonRing"
	horizon.set_meta("classification", "authored")
	horizon.set_meta("visual_only", true)
	add_child(horizon)
	if not _load_spec():
		return
	_build_ring()
	_build_camera()


func _load_spec() -> bool:
	var file := FileAccess.open(HORIZON_SPEC_PATH, FileAccess.READ)
	if file == null:
		push_error("Issue 270: could not read horizon spec")
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		push_error("Issue 270: horizon spec is not a dictionary")
		return false
	ring_spec = parsed
	return true


func _build_ring() -> void:
	var ring: Dictionary = ring_spec["ring"]
	var heights: Array = ring_spec["panel_heights"]
	var color: Array = ring_spec["silhouette"]["color"]
	var count := int(ring["segment_count"])
	var material := _silhouette_material(Color(color[0], color[1], color[2], 1.0))
	for index in count:
		var height := float(heights[index])
		var theta := TAU * float(index) / float(count)
		var x := float(ring["center_x"]) + float(ring["radius"]) * cos(theta)
		var z := float(ring["center_z"]) + float(ring["radius"]) * sin(theta)
		var mesh := BoxMesh.new()
		mesh.size = Vector3(float(ring["panel_width"]), height, float(ring["panel_thickness"]))
		var panel := MeshInstance3D.new()
		panel.name = "RingPanel_%02d" % index
		panel.position = Vector3(x, float(ring["panel_base_y"]) + height * 0.5, z)
		panel.rotation.y = PI * 0.5 - theta
		panel.mesh = mesh
		panel.material_override = material
		panel.set_meta("classification", "authored")
		panel.set_meta("panel_index", index)
		get_node("AuthoredHorizonRing").add_child(panel)


func _build_camera() -> void:
	var camera := Camera3D.new()
	camera.name = "InspectionCamera"
	camera.current = true
	add_child(camera)


func _silhouette_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material
