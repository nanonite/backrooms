extends Node3D

# Issue 271: isolated bench material fallback fixture derived from snow-garden-courtyard-v2.
# ONE script drives both comparison scenes; the only difference between them is the
# exported bench_material_mode property set in the two .tscn files. Geometry and
# collision construction is never branch-dependent, so the statue plinth, all other
# props and every collider stay identical to the reference. Only the bench's stone
# parts move from the shared robe crop to an explicitly authored fallback material.

const PANORAMA_PATH := "res://source_library/sources/video-d92fc1fa764aa3a2/hunyuan/attempt-001-retry-001/panorama/panorama.png"
const TEXTURE_ROOT := "res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/textures/"
const WALL_HEIGHT := 2.4
# Mirrors bench_material_decision_v1.json -> authored_material.parameters.
const AUTHORED_BENCH_COLOR := Color(0.42, 0.44, 0.47, 1.0)
const AUTHORED_BENCH_ROUGHNESS := 1.0
const SOURCE_CROP_ORIGIN := "source_crop:stone_robe"
const AUTHORED_ORIGIN := "project_authored"

@export var bench_material_mode: String = "reference"

const WALL_SEGMENTS := [
	["SouthWall", 0.0, 1.2, -8.15, 20.3, 2.4, 0.3],
	["NorthWall", 0.0, 1.2, 8.15, 20.3, 2.4, 0.3],
	["WestWall", -10.15, 1.2, 0.0, 0.3, 2.4, 16.3],
	["EastWall", 10.15, 1.2, 0.0, 0.3, 2.4, 16.3],
]

const TREE_SPECS := [
	["Tree00", -8.5, -5.8, 7.4, 0.20, "leafy"],
	["Tree01", -6.0, -6.2, 6.8, 0.17, "fine"],
	["Tree02", -3.5, -5.6, 7.2, 0.19, "dense"],
	["Tree03", -1.2, -6.0, 6.2, 0.15, "bare"],
	["Tree04", 1.2, -6.0, 6.6, 0.16, "bare"],
	["Tree05", 3.5, -5.6, 7.6, 0.21, "leafy"],
	["Tree06", 6.0, -6.2, 6.9, 0.18, "dense"],
	["Tree07", 8.5, -5.8, 7.1, 0.19, "fine"],
	["Tree08", -7.5, -2.0, 6.0, 0.16, "bare"],
	["Tree09", -4.0, -2.2, 5.6, 0.14, "fine"],
	["Tree10", 4.0, -2.2, 5.8, 0.15, "dense"],
	["Tree11", 7.5, -2.0, 6.1, 0.16, "bare"],
	["Tree12", -8.5, 2.5, 6.5, 0.17, "leafy"],
	["Tree13", -5.0, 3.4, 5.4, 0.14, "fine"],
	["Tree14", -3.0, 4.5, 5.2, 0.13, "bare"],
	["Tree15", 3.0, 4.5, 5.3, 0.13, "bare"],
	["Tree16", 5.0, 3.4, 5.7, 0.15, "fine"],
	["Tree17", 8.5, 2.5, 6.1, 0.17, "dense"],
]

const DRIFT_SPECS := [
	["Drift00", -7.0, -3.6, 1.7, 0.9, false],
	["Drift01", -5.2, -4.4, 1.2, 0.7, true],
	["Drift02", -2.2, -4.0, 1.4, 0.8, false],
	["Drift03", 2.4, -4.2, 1.5, 0.8, true],
	["Drift04", 6.6, -3.4, 1.8, 1.0, false],
	["Drift05", -8.2, 0.6, 1.1, 1.6, true],
	["Drift06", -6.4, 5.9, 1.6, 0.7, false],
	["Drift07", 6.2, 5.8, 1.5, 0.8, false],
	["Drift08", 8.2, 0.4, 1.0, 1.5, true],
	["Drift09", 0.4, -6.8, 1.9, 0.6, true],
]

const POST_SPECS := [
	["Post00", -6.2, -0.4, 0.46, 0.12],
	["Post01", -4.6, 1.4, 0.34, 0.10],
	["Post02", -2.0, -3.0, 0.42, 0.11],
	["Post03", 1.8, -3.2, 0.38, 0.11],
	["Post04", 4.8, 1.2, 0.44, 0.12],
	["Post05", 6.6, -0.6, 0.32, 0.10],
	["Post06", -7.4, 4.0, 0.40, 0.11],
	["Post07", 7.4, 4.2, 0.36, 0.11],
	["Post08", -1.0, 4.8, 0.30, 0.09],
	["Post09", 1.2, 4.8, 0.33, 0.09],
	["Post10", -5.6, -6.6, 0.48, 0.12],
	["Post11", 5.6, -6.6, 0.45, 0.12],
]

const WALL_POST_X := [-8.0, -4.0, 0.0, 4.0, 8.0]
const WALL_POST_Z := [-6.0, -2.0, 2.0, 6.0]

var materials: Dictionary = {}
var inspection_camera: Camera3D = null


func _ready() -> void:
	_set_candidate_metadata()
	_create_scene_groups()
	if not _build_environment() or not _build_materials():
		return
	_build_floor()
	_build_boundaries()
	_build_wall_details()
	_build_trees()
	_build_stone_bench()
	_build_stone_statue()
	_build_snow_drifts()
	_build_marker_posts()
	_build_safety_net()
	_add_inspection_camera()


func _set_candidate_metadata() -> void:
	set_meta("room_id", "issue_271_bench_material_fallback")
	set_meta("bench_material_mode", bench_material_mode)
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("revision_of", "snow-garden-courtyard-v2")
	set_meta("source_reference", "godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json")
	set_meta("panorama_visual_only", true)
	set_meta("material_decision", "fixture/bench_material_decision_v1.json")


func _create_scene_groups() -> void:
	for group_name in ["AuthoredVisuals", "AuthoredBoundaries", "AuthoredObstacles", "SafetyNet"]:
		var group := Node3D.new()
		group.name = group_name
		add_child(group)


func _build_environment() -> bool:
	var panorama := _load_texture(PANORAMA_PATH)
	if panorama == null:
		return false
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.background_energy_multiplier = 1.12
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.66, 0.76, 0.95)
	environment.ambient_light_energy = 0.85
	var sky_material := PanoramaSkyMaterial.new()
	sky_material.panorama = panorama
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	var world := WorldEnvironment.new()
	world.name = "PanoramaEnvironment"
	world.environment = environment
	add_child(world)
	_add_dusk_lights()
	return true


func _add_dusk_lights() -> void:
	var key_light := DirectionalLight3D.new()
	key_light.name = "WinterSunlight"
	key_light.light_color = Color(1.0, 0.86, 0.72)
	key_light.rotation = Vector3(deg_to_rad(-24.0), deg_to_rad(210.0), 0.0)
	key_light.light_energy = 1.1
	add_child(key_light)
	var fill_light := DirectionalLight3D.new()
	fill_light.name = "WinterSkyFill"
	fill_light.light_color = Color(0.55, 0.68, 0.95)
	fill_light.rotation = Vector3(deg_to_rad(-62.0), deg_to_rad(-30.0), 0.0)
	fill_light.light_energy = 0.35
	add_child(fill_light)


func _build_materials() -> bool:
	var figure := _load_texture(TEXTURE_ROOT + "stone_figure.png")
	var robe := _load_texture(TEXTURE_ROOT + "stone_robe.png")
	var canopy := _load_texture(TEXTURE_ROOT + "branch_canopy.png")
	var fine := _load_texture(TEXTURE_ROOT + "branch_fine.png")
	var foliage := _load_texture(TEXTURE_ROOT + "evergreen_foliage.png")
	if figure == null or robe == null or canopy == null or fine == null or foliage == null:
		return false
	materials.snow = _solid_material(Color(0.80, 0.86, 0.94))
	materials.snow_shade = _solid_material(Color(0.69, 0.77, 0.90))
	materials.hedge = _solid_material(Color(0.17, 0.25, 0.23))
	materials.hedge_base = _solid_material(Color(0.12, 0.18, 0.18))
	materials.snow_cap = _solid_material(Color(0.84, 0.89, 0.96))
	materials.trunk = _solid_material(Color(0.21, 0.25, 0.32))
	materials.branch = _solid_material(Color(0.24, 0.28, 0.35))
	materials.post = _solid_material(Color(0.27, 0.31, 0.36))
	materials.stone = _texture_material(robe, Vector3(1.0, 1.0, 1.0))
	materials.bench_stone = _authored_bench_material()
	materials.figure = _texture_material(figure, Vector3(1.0, 1.0, 1.0))
	materials.canopy = _texture_material(canopy, Vector3(1.0, 1.0, 1.0))
	materials.fine = _texture_material(fine, Vector3(1.0, 1.0, 1.0))
	materials.foliage = _texture_material(foliage, Vector3(1.0, 1.0, 1.0))
	return true


func _authored_bench_material() -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = AUTHORED_BENCH_COLOR
	material.roughness = AUTHORED_BENCH_ROUGHNESS
	material.metallic = 0.0
	material.albedo_texture = null
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.set_meta("origin", AUTHORED_ORIGIN)
	material.set_meta("intended_role", "stone_like_bench_surface")
	return material


func _bench_surface_material() -> Material:
	if bench_material_mode == "candidate":
		return materials.bench_stone
	return materials.stone


func _bench_surface_origin() -> String:
	if bench_material_mode == "candidate":
		return AUTHORED_ORIGIN
	return SOURCE_CROP_ORIGIN


func _build_floor() -> void:
	_add_box("WalkableFloorVisual", Vector3(0.0, -0.12, 0.0), Vector3(20.0, 0.24, 16.0), materials.snow, "AuthoredVisuals")
	_add_collision_box("WalkableFloor", Vector3(0.0, -0.12, 0.0), Vector3(20.0, 0.24, 16.0), "AuthoredBoundaries")


func _build_boundaries() -> void:
	for segment: Array in WALL_SEGMENTS:
		var center := Vector3(segment[1], segment[2], segment[3])
		var size := Vector3(segment[4], segment[5], segment[6])
		_add_box("%sVisual" % segment[0], center, size, materials.hedge, "AuthoredVisuals")
		_add_collision_box(segment[0], center, size, "AuthoredBoundaries")


func _build_wall_details() -> void:
	for sign: float in [-1.0, 1.0]:
		for position_x: float in WALL_POST_X:
			_add_wall_post("WallPostX%s_%s" % [sign, position_x],
				Vector3(position_x, WALL_HEIGHT / 2.0, sign * 8.15))
		for position_z: float in WALL_POST_Z:
			_add_wall_post("WallPostZ%s_%s" % [sign, position_z],
				Vector3(sign * 10.15, WALL_HEIGHT / 2.0, position_z))
	_add_box("SouthWallCap", Vector3(0.0, 2.48, -8.15), Vector3(20.4, 0.16, 0.5), materials.snow_cap, "AuthoredVisuals")
	_add_box("NorthWallCap", Vector3(0.0, 2.48, 8.15), Vector3(20.4, 0.16, 0.5), materials.snow_cap, "AuthoredVisuals")
	_add_box("WestWallCap", Vector3(-10.15, 2.48, 0.0), Vector3(0.5, 0.16, 16.4), materials.snow_cap, "AuthoredVisuals")
	_add_box("EastWallCap", Vector3(10.15, 2.48, 0.0), Vector3(0.5, 0.16, 16.4), materials.snow_cap, "AuthoredVisuals")
	_add_box("SouthHedgeBase", Vector3(0.0, 0.10, -7.85), Vector3(20.0, 0.20, 0.3), materials.hedge_base, "AuthoredVisuals")
	_add_box("NorthHedgeBase", Vector3(0.0, 0.10, 7.85), Vector3(20.0, 0.20, 0.3), materials.hedge_base, "AuthoredVisuals")


func _add_wall_post(label: String, center: Vector3) -> void:
	_add_box(label, center, Vector3(0.36, WALL_HEIGHT + 0.4, 0.36), materials.hedge, "AuthoredVisuals")
	_add_box("%sCap" % label, Vector3(center.x, WALL_HEIGHT + 0.28, center.z),
		Vector3(0.48, 0.14, 0.48), materials.snow_cap, "AuthoredVisuals")


func _build_trees() -> void:
	for spec: Array in TREE_SPECS:
		var name: String = spec[0]
		var tree_x: float = spec[1]
		var tree_z: float = spec[2]
		var height: float = spec[3]
		var radius: float = spec[4]
		var variant: String = spec[5]
		var trunk_center := Vector3(tree_x, height / 2.0, tree_z)
		_add_cylinder("%sTrunk" % name, trunk_center, radius, height, materials.trunk, 6)
		_add_branches(name, tree_x, tree_z, height)
		_add_canopy(name, tree_x, tree_z, height, variant)
		_add_collision_box("%sCollision" % name, trunk_center,
			Vector3(radius * 2.0, height, radius * 2.0), "AuthoredObstacles")


func _add_branches(prefix: String, tree_x: float, tree_z: float, height: float) -> void:
	var base_y := height * 0.74
	for index in 4:
		var angle := TAU * float(index) / 4.0 + (tree_x + tree_z) * 0.11
		var tilt := deg_to_rad(36.0 + float(index % 2) * 8.0)
		var length := 1.3 + float(index % 3) * 0.4
		var direction := Vector3(sin(tilt) * cos(angle), cos(tilt), sin(tilt) * sin(angle))
		var center := Vector3(tree_x, base_y, tree_z) + direction * (length * 0.5)
		var rotation := Vector3(tilt * sin(angle), 0.0, -tilt * cos(angle))
		_add_cylinder("%sBranch%d" % [prefix, index], center, 0.045, length,
			materials.branch, 4, rotation)


func _add_canopy(prefix: String, tree_x: float, tree_z: float, height: float, variant: String) -> void:
	if variant == "bare":
		return
	var material: Material = materials.canopy
	if variant == "fine":
		material = materials.fine
	elif variant == "leafy":
		material = materials.foliage
	for index in 2:
		var angle := TAU * float(index) / 2.0 + tree_x * 0.13
		var center := Vector3(tree_x + cos(angle) * 0.55, height - 0.8 - float(index) * 0.5,
			tree_z + sin(angle) * 0.55)
		if variant == "leafy":
			_add_sphere("%sFoliage%d" % [prefix, index], center, 0.75, 0.9,
				Vector3(1.0, 0.35, 0.8), material)
		else:
			_add_box_rotated("%sPanel%d" % [prefix, index], center,
				Vector3(1.25, 0.85, 0.06), material, Vector3(0.0, angle, 0.0))


func _build_stone_bench() -> void:
	var surface := _bench_surface_material()
	var origin := _bench_surface_origin()
	_add_marked_box("BenchPlinth", Vector3(0.0, 0.15, 0.0), Vector3(3.4, 0.30, 1.6), surface, origin)
	for sign_x: float in [-1.0, 1.0]:
		for sign_z: float in [-1.0, 1.0]:
			_add_marked_box("BenchLeg%s%s" % [sign_x, sign_z],
				Vector3(sign_x * 1.35, 0.45, sign_z * 0.5),
				Vector3(0.32, 0.6, 0.32), surface, origin)
	_add_marked_box("BenchSeat", Vector3(0.0, 0.80, 0.0), Vector3(3.2, 0.18, 1.25), surface, origin)
	for index in 3:
		_add_marked_box("BenchBackPost%d" % index,
			Vector3((float(index) - 1.0) * 1.3, 1.25, -0.55),
			Vector3(0.18, 0.95, 0.18), surface, origin)
	for index in 3:
		_add_marked_box("BenchBackSlat%d" % index,
			Vector3(0.0, 0.95 + float(index) * 0.24, -0.58),
			Vector3(3.0, 0.14, 0.12), surface, origin)
	for sign_x: float in [-1.0, 1.0]:
		for sign_z: float in [-1.0, 1.0]:
			_add_marked_cylinder("BenchBollard%s%s" % [sign_x, sign_z],
				Vector3(sign_x * 2.25, 0.28, sign_z * 1.35), 0.12, 0.56,
				materials.post, "project_authored_solid:post", 6)
	_add_collision_box("StoneBenchCollision", Vector3(0.0, 0.8, -0.1),
		Vector3(3.6, 1.6, 1.9), "AuthoredObstacles")


func _build_stone_statue() -> void:
	var center := Vector3(-4.6, 0.0, 0.8)
	# The plinth keeps the reference's shared stone crop in BOTH scenes; it is
	# deliberately never switched to the authored bench material.
	_add_marked_box("StatuePlinth", center + Vector3(0.0, 0.28, 0.0),
		Vector3(1.2, 0.56, 1.1), materials.stone, SOURCE_CROP_ORIGIN)
	_add_box("StatueFigure", center + Vector3(0.0, 1.35, 0.0),
		Vector3(0.72, 1.55, 0.42), materials.figure, "AuthoredVisuals")
	_add_box_rotated("StatueWing", center + Vector3(-0.35, 1.45, -0.1),
		Vector3(0.95, 1.05, 0.16), materials.figure, Vector3(0.0, 0.0, deg_to_rad(-12.0)))
	_add_sphere("StatueHead", center + Vector3(0.05, 2.25, 0.0), 0.22, 0.42,
		Vector3.ONE, materials.figure)
	_add_collision_box("StatueCollision", center + Vector3(0.0, 1.2, 0.0),
		Vector3(1.2, 2.4, 1.1), "AuthoredObstacles")


func _build_snow_drifts() -> void:
	for spec: Array in DRIFT_SPECS:
		var material: Material = materials.snow
		if spec[5]:
			material = materials.snow_shade
		_add_sphere(spec[0], Vector3(spec[1], 0.06, spec[2]), 1.0, 0.5,
			Vector3(spec[3], 0.28, spec[4]), material)


func _build_marker_posts() -> void:
	for spec: Array in POST_SPECS:
		_add_cylinder(spec[0], Vector3(spec[1], spec[3] * 0.5, spec[2]),
			spec[4], spec[3], materials.post, 5)


func _build_safety_net() -> void:
	_add_collision_box("SafetyNet", Vector3(0.0, -3.1, 0.0), Vector3(22.0, 0.12, 18.0), "SafetyNet")


func _add_inspection_camera() -> void:
	inspection_camera = Camera3D.new()
	inspection_camera.name = "InspectionCamera"
	inspection_camera.fov = 62.0
	inspection_camera.near = 0.05
	inspection_camera.far = 200.0
	add_child(inspection_camera)


func _add_marked_box(label: String, center: Vector3, size: Vector3, material: Material, origin: String) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	_add_mesh(label, center, mesh, material, "AuthoredVisuals", Vector3.ZERO, Vector3.ONE, origin)


func _add_marked_cylinder(label: String, center: Vector3, radius: float, height: float,
		material: Material, origin: String, segments: int) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = segments
	mesh.rings = 1
	_add_mesh(label, center, mesh, material, "AuthoredVisuals", Vector3.ZERO, Vector3.ONE, origin)


func _add_box(label: String, center: Vector3, size: Vector3, material: Material, parent_name: String) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	_add_mesh(label, center, mesh, material, parent_name)


func _add_box_rotated(label: String, center: Vector3, size: Vector3, material: Material, rotation: Vector3) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	_add_mesh(label, center, mesh, material, "AuthoredVisuals", rotation)


func _add_cylinder(label: String, center: Vector3, radius: float, height: float,
		material: Material, segments: int, rotation := Vector3.ZERO) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = segments
	mesh.rings = 1
	_add_mesh(label, center, mesh, material, "AuthoredVisuals", rotation)


func _add_sphere(label: String, center: Vector3, radius: float, height: float,
		scale: Vector3, material: Material) -> void:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = height
	mesh.radial_segments = 8
	mesh.rings = 4
	_add_mesh(label, center, mesh, material, "AuthoredVisuals", Vector3.ZERO, scale)


func _add_mesh(label: String, center: Vector3, mesh: Mesh, material: Material,
		parent_name: String, rotation := Vector3.ZERO, scale := Vector3.ONE,
		origin := "") -> void:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = center
	visual.rotation = rotation
	visual.scale = scale
	visual.mesh = mesh
	visual.material_override = material
	if not origin.is_empty():
		visual.set_meta("material_origin", origin)
	get_node(parent_name).add_child(visual)


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


func _texture_material(texture: Texture2D, uv_scale: Vector3) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.uv1_scale = uv_scale
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _load_texture(resource_path: String) -> Texture2D:
	var image := Image.load_from_file(ProjectSettings.globalize_path(resource_path))
	if image == null or image.is_empty():
		push_error("Could not read candidate image resource: %s" % resource_path)
		return null
	return ImageTexture.create_from_image(image)


func _solid_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material
