extends Node3D

# Baseline for issue 269: the current representation described in the issue-255
# report — flattened ellipsoids above a flat floor and box collider, with tree
# trunks as separate colliders and no ground shadows. Authored design units only.
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const RELIEF_SPEC_PATH := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/relief_spec_v1.json"
const SHADOW_SPEC_PATH := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/shadow_spec_v1.json"
const SPAWN := Vector3(0.0, 0.6, 7.5)

var player: CharacterBody3D
var relief_spec: Dictionary = {}
var shadow_spec: Dictionary = {}


func _ready() -> void:
	set_meta("fixture_id", "issue_269_baseline_relief_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "baseline_pending_review")
	set_meta("collision_policy", "flat")
	set_meta("representation", "flat_floor_flattened_ellipsoids_no_shadows")
	_create_groups()
	if not _load_specs():
		return
	_build_floor()
	_build_flattened_ellipsoids()
	_build_trees()
	_build_safety_net()
	_spawn_player()


func _create_groups() -> void:
	for group_name in ["BaselineEllipsoids", "AuthoredTrees", "AuthoredBoundaries", "TreeCollision", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _load_specs() -> bool:
	relief_spec = _read_json(RELIEF_SPEC_PATH)
	shadow_spec = _read_json(SHADOW_SPEC_PATH)
	if relief_spec.is_empty() or shadow_spec.is_empty():
		push_error("Issue 269 baseline: could not read authored specs")
		return false
	return true


func _read_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return {}
	return parsed


func _build_floor() -> void:
	var spec: Dictionary = relief_spec["collision"]
	_add_box("FlatFloorVisual", Vector3(0.0, float(spec["center_y"]), 0.0),
		Vector3(float(spec["size_x"]), float(spec["thickness"]), float(spec["size_z"])),
		_solid(Color(0.62, 0.68, 0.74)), "AuthoredBoundaries")
	var body := StaticBody3D.new()
	body.name = "FlatFloorCollision"
	body.position = Vector3(0.0, float(spec["center_y"]), 0.0)
	body.set_meta("collision_policy", "flat")
	get_node("AuthoredBoundaries").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = Vector3(float(spec["size_x"]), float(spec["thickness"]), float(spec["size_z"]))
	collision.shape = shape
	body.add_child(collision)


func _build_flattened_ellipsoids() -> void:
	for drift: Dictionary in relief_spec["drifts"]:
		var mesh := SphereMesh.new()
		mesh.radius = 1.0
		mesh.height = 2.0
		var scale := Vector3(float(drift["sigma_x"]), 0.10, float(drift["sigma_z"]))
		var visual := MeshInstance3D.new()
		visual.name = drift["id"]
		visual.position = Vector3(float(drift["center_x"]), 0.04, float(drift["center_z"]))
		visual.scale = scale
		visual.mesh = mesh
		visual.material_override = _solid(Color(0.62, 0.68, 0.74))
		visual.set_meta("classification", "authored")
		get_node("BaselineEllipsoids").add_child(visual)


func _build_trees() -> void:
	for spec: Dictionary in shadow_spec["trees"]:
		var x := float(spec["x"])
		var z := float(spec["z"])
		var height := float(spec["trunk_height"])
		var center := Vector3(x, height * 0.5, z)
		var trunk_mesh := CylinderMesh.new()
		trunk_mesh.bottom_radius = 0.16
		trunk_mesh.top_radius = 0.10
		trunk_mesh.height = height
		trunk_mesh.radial_segments = 7
		var trunk := MeshInstance3D.new()
		trunk.name = spec["id"] + "_Trunk"
		trunk.position = center
		trunk.mesh = trunk_mesh
		trunk.material_override = _solid(Color(0.18, 0.15, 0.13))
		get_node("AuthoredTrees").add_child(trunk)
		var canopy_mesh := SphereMesh.new()
		canopy_mesh.radius = float(spec["canopy_radius"])
		canopy_mesh.height = float(spec["canopy_radius"]) * 2.0
		var canopy := MeshInstance3D.new()
		canopy.name = spec["id"] + "_Canopy"
		canopy.position = Vector3(x, height + 0.15, z)
		canopy.mesh = canopy_mesh
		canopy.material_override = _solid(Color(0.22, 0.34, 0.26))
		get_node("AuthoredTrees").add_child(canopy)
		var body := StaticBody3D.new()
		body.name = spec["id"] + "_TrunkCollision"
		body.position = center
		get_node("TreeCollision").add_child(body)
		var collision := CollisionShape3D.new()
		collision.name = "Collision"
		var shape := CylinderShape3D.new()
		shape.radius = 0.20
		shape.height = height
		collision.shape = shape
		body.add_child(collision)


func _build_safety_net() -> void:
	var body := StaticBody3D.new()
	body.name = "SafetyNet"
	body.position = Vector3(0.0, -3.1, 0.0)
	get_node("SafetyNet").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = Vector3(18.0, 0.12, 18.0)
	collision.shape = shape
	body.add_child(collision)


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = SPAWN
	add_child(player)


func _add_box(label: String, center: Vector3, size: Vector3, material: Material,
		parent_name: String) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	visual.mesh = mesh
	visual.material_override = material
	get_node(parent_name).add_child(visual)


func _solid(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material
