extends Node3D

# Isolated one-tree prototype for issue 268. Visual experiment only.
# The trunk is explicitly authored (no usable bark crop exists in the source frames);
# the canopy cards reuse three traceable source-backed crops. All placement, geometry,
# floor, lighting and collision are authored in uncalibrated design units.
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const TEXTURE_ROOT := "res://evidence/2026-11-17-issue-268-tree-prototype/fixture/textures/"
const CARD_SPECS_PATH := "res://evidence/2026-11-17-issue-268-tree-prototype/fixture/card_specs_v1.json"

const TREE_CENTER := Vector3(0.0, 0.0, 0.0)
const TRUNK_HEIGHT := 5.6
const TRUNK_BASE_RADIUS := 0.24
const TRUNK_TOP_RADIUS := 0.13
const TRUNK_COLLISION_RADIUS := 0.26
const GROUND_SIZE := Vector3(14.0, 0.24, 14.0)
const SPAWN := Vector3(0.0, 0.6, 4.5)

var player: CharacterBody3D
var materials: Dictionary = {}


func _ready() -> void:
	set_meta("fixture_id", "issue_268_tree_trunk_canopy_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("trunk_representation", "authored_taper_no_bark_crop")
	set_meta("canopy_representation", "source_backed_layered_cards")
	set_meta("source_frame", "frame_4347; direct decode from source video d92fc1fa764aa3a2")
	set_meta("provenance", "res://evidence/2026-11-17-issue-268-tree-prototype/fixture/crop_provenance_v1.json")
	_create_groups()
	if not _build_materials():
		return
	_build_floor()
	_build_tree()
	_build_safety_net()
	_spawn_player()


func _create_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredCanopy", "TreeCollision", "AuthoredBoundaries", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _build_materials() -> bool:
	for crop_name in ["branch_canopy", "branch_fine", "evergreen_foliage"]:
		var texture := _load_texture(TEXTURE_ROOT + crop_name + ".png")
		if texture == null:
			return false
		materials[crop_name] = _texture_material(texture)
	materials.trunk = _solid_material(Color(0.17, 0.14, 0.13))
	materials.branch = _solid_material(Color(0.20, 0.17, 0.16))
	materials.ground = _solid_material(Color(0.62, 0.68, 0.74))
	materials.ground_shade = _solid_material(Color(0.54, 0.61, 0.68))
	return true


func _build_floor() -> void:
	_add_box("InspectionFloorVisual", Vector3(0.0, -0.12, 0.0), GROUND_SIZE, materials.ground, "AuthoredVisuals")
	_add_box("FloorAccent", Vector3(0.0, -0.115, 0.0), Vector3(3.0, 0.02, 14.0), materials.ground_shade, "AuthoredVisuals")
	_add_collision_box("WalkableFloor", Vector3(0.0, -0.12, 0.0), GROUND_SIZE, "AuthoredBoundaries")


func _build_tree() -> void:
	var trunk_center := TREE_CENTER + Vector3(0.0, TRUNK_HEIGHT / 2.0, 0.0)
	var trunk := _add_tapered_cylinder("AuthoredTrunk", trunk_center, TRUNK_BASE_RADIUS,
		TRUNK_TOP_RADIUS, TRUNK_HEIGHT, materials.trunk, 7)
	trunk.set_meta("classification", "authored")
	trunk.set_meta("bark_source_crop", "none")
	_add_root_flare()
	_add_authored_branches()
	_add_canopy_cards()
	_add_trunk_collision(trunk_center)


func _add_root_flare() -> void:
	var flare := _add_tapered_cylinder("AuthoredRootFlare", TREE_CENTER + Vector3(0.0, 0.22, 0.0),
		TRUNK_BASE_RADIUS * 1.35, TRUNK_BASE_RADIUS, 0.44, materials.trunk, 7)
	flare.set_meta("classification", "authored")


func _add_authored_branches() -> void:
	for index in 5:
		var angle := TAU * float(index) / 5.0 + deg_to_rad(12.0)
		var tilt := deg_to_rad(42.0 + float(index % 2) * 9.0)
		var length := 1.6 + float(index % 3) * 0.25
		var direction := Vector3(sin(tilt) * cos(angle), cos(tilt), sin(tilt) * sin(angle))
		var center := TREE_CENTER + Vector3(0.0, 3.9 + float(index % 2) * 0.35, 0.0) + direction * (length * 0.5)
		var rotation := Vector3(tilt * sin(angle), 0.0, -tilt * cos(angle))
		var branch := _add_tapered_cylinder("AuthoredBranch%d" % index, center, 0.05, 0.09,
			length, materials.branch, 5, rotation)
		branch.set_meta("classification", "authored")


func _add_canopy_cards() -> void:
	var file := FileAccess.open(CARD_SPECS_PATH, FileAccess.READ)
	if file == null:
		push_error("Could not read canopy card specs: %s" % CARD_SPECS_PATH)
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary or not parsed.has("cards"):
		push_error("Canopy card specs are not a valid dictionary with cards")
		return
	for spec: Dictionary in parsed["cards"]:
		var azimuth := deg_to_rad(float(spec["azimuth_deg"]))
		var radial := float(spec["radial_offset"])
		var center := TREE_CENTER + Vector3(cos(azimuth) * radial, float(spec["center_y"]), sin(azimuth) * radial)
		# A thin box faces +Z at zero yaw; rotate so its normal follows the authored radial direction.
		var yaw := deg_to_rad(90.0 - float(spec["azimuth_deg"]))
		var rotation := Vector3(deg_to_rad(float(spec["tilt_deg"])), yaw, 0.0)
		var card := _add_box(spec["id"], center,
			Vector3(float(spec["size_x"]), float(spec["size_y"]), 0.05),
			materials[spec["crop"]], "AuthoredCanopy", rotation)
		card.set_meta("classification", "source_backed_crop")
		card.set_meta("crop", spec["crop"])
		card.set_meta("azimuth_deg", float(spec["azimuth_deg"]))
		card.set_meta("radial_offset", radial)
		card.set_meta("center_y", float(spec["center_y"]))


func _add_trunk_collision(center: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = "TrunkCollision"
	body.position = center
	body.set_meta("classification", "authored")
	body.set_meta("independent_of_visual", true)
	get_node("TreeCollision").add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := CylinderShape3D.new()
	shape.radius = TRUNK_COLLISION_RADIUS
	shape.height = TRUNK_HEIGHT
	collision.shape = shape
	body.add_child(collision)


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(0.0, -3.1, 0.0), Vector3(16.0, 0.12, 16.0), "SafetyNet")


func _spawn_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = SPAWN
	add_child(player)


func _add_box(label: String, center: Vector3, size: Vector3, material: Material,
		parent_name: String, rotation := Vector3.ZERO) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	return _add_mesh(label, center, mesh, material, parent_name, rotation)


func _add_tapered_cylinder(label: String, center: Vector3, base_radius: float, top_radius: float,
		height: float, material: Material, segments: int,
		rotation := Vector3.ZERO) -> MeshInstance3D:
	var mesh := CylinderMesh.new()
	mesh.bottom_radius = base_radius
	mesh.top_radius = top_radius
	mesh.height = height
	mesh.radial_segments = segments
	mesh.rings = 1
	return _add_mesh(label, center, mesh, material, "AuthoredVisuals", rotation)


func _add_mesh(label: String, center: Vector3, mesh: Mesh, material: Material,
		parent_name: String, rotation := Vector3.ZERO) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	visual.rotation = rotation
	visual.mesh = mesh
	visual.material_override = material
	get_node(parent_name).add_child(visual)
	return visual


func _add_collision_box(label: String, center: Vector3, size: Vector3, parent_name: String) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	get_node(parent_name).add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)


func _texture_material(texture: Texture2D) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _load_texture(resource_path: String) -> Texture2D:
	var image := Image.load_from_file(ProjectSettings.globalize_path(resource_path))
	if image == null or image.is_empty():
		push_error("Could not read fixture texture: %s" % resource_path)
		return null
	return ImageTexture.create_from_image(image)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		player.global_position = SPAWN
		player.velocity = Vector3.ZERO
		player.rotation = Vector3.ZERO
		player.get_node("Head").rotation = Vector3.ZERO
		print("Issue 268 tree prototype reset to safe spawn")
