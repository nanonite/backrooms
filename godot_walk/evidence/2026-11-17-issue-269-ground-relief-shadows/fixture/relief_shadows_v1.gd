extends Node3D

# Isolated authored-relief + static-shadow variant for issue 269. Visual experiment
# only. All geometry, colours, light direction and placement are authored in
# uncalibrated design units. Collision stays flat; the relief is visual only.
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const RELIEF_SPEC_PATH := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/relief_spec_v1.json"
const SHADOW_SPEC_PATH := "res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/shadow_spec_v1.json"
const SPAWN := Vector3(0.0, 0.6, 7.5)

var player: CharacterBody3D
var relief_spec: Dictionary = {}
var shadow_spec: Dictionary = {}
var drifts: Array = []
var materials: Dictionary = {}


func _ready() -> void:
	set_meta("fixture_id", "issue_269_ground_relief_shadows_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("collision_policy", "flat")
	set_meta("representation", "authored_irregular_relief_plus_static_shadows")
	_create_groups()
	if not _load_specs():
		return
	_build_materials()
	_build_relief_mesh()
	_build_flat_collision()
	_build_shadows()
	_build_trees()
	_build_safety_net()
	_spawn_player()


func _create_groups() -> void:
	for group_name in ["AuthoredRelief", "AuthoredShadows", "AuthoredTrees", "AuthoredBoundaries", "TreeCollision", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _load_specs() -> bool:
	relief_spec = _read_json(RELIEF_SPEC_PATH)
	shadow_spec = _read_json(SHADOW_SPEC_PATH)
	if relief_spec.is_empty() or shadow_spec.is_empty():
		push_error("Issue 269: could not read authored relief/shadow specs")
		return false
	for drift: Dictionary in relief_spec["drifts"]:
		drifts.append(drift)
	return true


func _read_json(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return {}
	return parsed


func _build_materials() -> void:
	materials.relief = _vertex_color_material()
	materials.shadow = _solid_material(Color(0.10, 0.12, 0.16, 0.55), true)
	materials.trunk = _solid_material(Color(0.18, 0.15, 0.13))
	materials.canopy = _solid_material(Color(0.22, 0.34, 0.26))


func _height(x: float, z: float) -> float:
	var height := float(relief_spec["base_height"])
	for drift: Dictionary in drifts:
		var dx := x - float(drift["center_x"])
		var dz := z - float(drift["center_z"])
		var sigma_x := float(drift["sigma_x"])
		var sigma_z := float(drift["sigma_z"])
		var exponent := -(dx * dx / (2.0 * sigma_x * sigma_x) + dz * dz / (2.0 * sigma_z * sigma_z))
		height += float(drift["amplitude"]) * exp(exponent)
	return height


func _relief_color(height: float) -> Color:
	var bound := maxf(absf(float(relief_spec["visible_height_bound"])), 0.0001)
	var lift := clampf(height / bound, -1.0, 1.0)
	return Color(0.55 + 0.16 * lift, 0.62 + 0.16 * lift, 0.70 + 0.12 * lift, 1.0)


func _build_relief_mesh() -> void:
	var grid: Dictionary = relief_spec["grid"]
	var step := float(grid["step"])
	var columns := int(round((float(grid["max_x"]) - float(grid["min_x"])) / step)) + 1
	var rows := int(round((float(grid["max_z"]) - float(grid["min_z"])) / step)) + 1
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for row in rows - 1:
		for column in columns - 1:
			var x0 := float(grid["min_x"]) + float(column) * step
			var x1 := x0 + step
			var z0 := float(grid["min_z"]) + float(row) * step
			var z1 := z0 + step
			_add_relief_vertex(surface, x0, z0)
			_add_relief_vertex(surface, x0, z1)
			_add_relief_vertex(surface, x1, z0)
			_add_relief_vertex(surface, x1, z0)
			_add_relief_vertex(surface, x0, z1)
			_add_relief_vertex(surface, x1, z1)
	surface.generate_normals()
	var visual := MeshInstance3D.new()
	visual.name = "AuthoredReliefMesh"
	visual.mesh = surface.commit()
	visual.material_override = materials.relief
	visual.set_meta("classification", "authored")
	visual.set_meta("collision_policy", "flat")
	get_node("AuthoredRelief").add_child(visual)


func _add_relief_vertex(surface: SurfaceTool, x: float, z: float) -> void:
	var height := _height(x, z)
	surface.set_color(_relief_color(height))
	surface.add_vertex(Vector3(x, height, z))


func _build_flat_collision() -> void:
	var spec: Dictionary = relief_spec["collision"]
	var body := StaticBody3D.new()
	body.name = "FlatFloorCollision"
	body.position = Vector3(0.0, float(spec["center_y"]), 0.0)
	body.set_meta("classification", "authored")
	body.set_meta("collision_policy", "flat")
	body.set_meta("visual_collision_height_bound", float(spec["visual_collision_height_bound"]))
	get_node("AuthoredBoundaries").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = Vector3(float(spec["size_x"]), float(spec["thickness"]), float(spec["size_z"]))
	collision.shape = shape
	body.add_child(collision)


func _build_shadows() -> void:
	var lift := float(shadow_spec["shadow_lift"])
	for spec: Dictionary in shadow_spec["shadows"]:
		var surface := SurfaceTool.new()
		surface.begin(Mesh.PRIMITIVE_TRIANGLES)
		var origin := Vector2(float(spec["origin_x"]), float(spec["origin_z"]))
		var direction := Vector2(float(spec["direction_xz"][0]), float(spec["direction_xz"][1])).normalized()
		var side := Vector2(-direction.y, direction.x)
		var length := float(spec["length"])
		for index in 8:
			_append_shadow_segment(surface, origin, direction, side, length,
				float(spec["width_start"]), float(spec["width_end"]), lift,
				float(index) / 8.0, float(index + 1) / 8.0)
		var visual := MeshInstance3D.new()
		visual.name = spec["id"]
		visual.mesh = surface.commit()
		visual.material_override = materials.shadow
		visual.set_meta("classification", "authored")
		visual.set_meta("tree_id", spec["tree_id"])
		visual.set_meta("origin", origin)
		visual.set_meta("direction_xz", direction)
		visual.set_meta("length", length)
		get_node("AuthoredShadows").add_child(visual)


func _append_shadow_segment(surface: SurfaceTool, origin: Vector2, direction: Vector2,
		side: Vector2, length: float, width_start: float, width_end: float,
		lift: float, begin: float, finish: float) -> void:
	var near := origin + direction * (length * begin)
	var far := origin + direction * (length * finish)
	var near_width := lerpf(width_start, width_end, begin) * 0.5
	var far_width := lerpf(width_start, width_end, finish) * 0.5
	var near_left := near - side * near_width
	var near_right := near + side * near_width
	var far_left := far - side * far_width
	var far_right := far + side * far_width
	_add_shadow_vertex(surface, near_left, lift)
	_add_shadow_vertex(surface, far_left, lift)
	_add_shadow_vertex(surface, near_right, lift)
	_add_shadow_vertex(surface, near_right, lift)
	_add_shadow_vertex(surface, far_left, lift)
	_add_shadow_vertex(surface, far_right, lift)


func _add_shadow_vertex(surface: SurfaceTool, point: Vector2, lift: float) -> void:
	surface.add_vertex(Vector3(point.x, _height(point.x, point.y) + lift, point.y))


func _build_trees() -> void:
	for spec: Dictionary in shadow_spec["trees"]:
		var x := float(spec["x"])
		var z := float(spec["z"])
		var base := _height(x, z)
		var trunk_height := float(spec["trunk_height"])
		var trunk_center := Vector3(x, base + trunk_height * 0.5 - 0.15, z)
		var trunk := _add_cylinder(spec["id"] + "_Trunk", trunk_center, 0.16, 0.10,
			trunk_height, materials.trunk)
		trunk.set_meta("classification", "authored")
		trunk.set_meta("tree_id", spec["id"])
		var canopy := _add_sphere(spec["id"] + "_Canopy",
			Vector3(x, base + trunk_height + 0.15, z), float(spec["canopy_radius"]), materials.canopy)
		canopy.set_meta("classification", "authored")
		canopy.set_meta("tree_id", spec["id"])
		_add_trunk_collision(spec["id"], trunk_center, trunk_height)


func _add_trunk_collision(tree_id: String, center: Vector3, height: float) -> void:
	var body := StaticBody3D.new()
	body.name = tree_id + "_TrunkCollision"
	body.position = center
	body.set_meta("tree_id", tree_id)
	body.set_meta("classification", "authored")
	get_node("TreeCollision").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := CylinderShape3D.new()
	shape.radius = 0.20
	shape.height = height
	collision.shape = shape
	body.add_child(collision)


func _add_cylinder(label: String, center: Vector3, bottom: float, top: float,
		height: float, material: Material) -> MeshInstance3D:
	var mesh := CylinderMesh.new()
	mesh.bottom_radius = bottom
	mesh.top_radius = top
	mesh.height = height
	mesh.radial_segments = 7
	return _add_mesh(label, center, mesh, material, "AuthoredTrees")


func _add_sphere(label: String, center: Vector3, radius: float,
		material: Material) -> MeshInstance3D:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	return _add_mesh(label, center, mesh, material, "AuthoredTrees")


func _add_mesh(label: String, center: Vector3, mesh: Mesh, material: Material,
		parent_name: String) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	visual.mesh = mesh
	visual.material_override = material
	get_node(parent_name).add_child(visual)
	return visual


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


func _vertex_color_material() -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.roughness = 1.0
	return material


func _solid_material(color: Color, transparent := false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	if transparent:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		player.global_position = SPAWN
		player.velocity = Vector3.ZERO
		player.rotation = Vector3.ZERO
		player.get_node("Head").rotation = Vector3.ZERO
		print("Issue 269 relief fixture reset to safe spawn")
