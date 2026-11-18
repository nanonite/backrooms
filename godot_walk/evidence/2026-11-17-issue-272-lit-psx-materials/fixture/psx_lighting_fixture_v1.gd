extends Node3D

# Issue 272: isolated, opt-in lit PSX material comparison fixture.
# ONE script drives all four comparison scenes. Geometry, transforms, camera,
# light and fog settings are identical across every scene; only the shader
# assigned to the test surfaces (baseline unshaded vs lit) and the surface path
# (solid vs textured) differ. Lighting can be toggled repeatably with
# set_light_on(), giving a light-on/light-off comparison for each variant.
# Nothing here is admitted, registered, calibrated or approved.

const SHADER_SOLID_BASELINE := "res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/psx_solid_baseline_v1.gdshader"
const SHADER_SOLID_LIT := "res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/psx_solid_lit_v1.gdshader"
const SHADER_TEXTURED_BASELINE := "res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/psx_textured_baseline_v1.gdshader"
const SHADER_TEXTURED_LIT := "res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/psx_textured_lit_v1.gdshader"
const SURFACE_KINDS := ["solid", "textured"]
const LIGHTING_MODES := ["baseline", "lit"]

# Authored, uncalibrated design values. The solid albedo is neutral so any
# response seen in captures comes from lighting, not from a source-derived tint.
const SOLID_ALBEDO := Color(0.62, 0.66, 0.71, 1.0)
const CHECKER_SIZE := 64
const CHECKER_CELLS := 8
const CHECKER_A := Color(0.86, 0.83, 0.75, 1.0)
const CHECKER_B := Color(0.27, 0.32, 0.39, 1.0)
const KEY_LIGHT_ENERGY := 1.7
const KEY_LIGHT_COLOR := Color(1.0, 0.93, 0.82, 1.0)
const KEY_LIGHT_ROTATION := Vector3(-38.0, 28.0, 0.0)
const AMBIENT_ENERGY := 0.4
const AMBIENT_COLOR := Color(0.5, 0.55, 0.62, 1.0)
const BACKGROUND_COLOR := Color(0.05, 0.06, 0.08, 1.0)

@export var surface_kind: String = "solid"
@export var lighting_mode: String = "baseline"
@export var light_on: bool = false

var key_light: DirectionalLight3D = null
var ambient_world: WorldEnvironment = null
var inspection_camera: Camera3D = null
var checker_texture: ImageTexture = null


func _ready() -> void:
	_set_metadata()
	_validate_modes()
	_build_environment()
	_build_surfaces()
	_add_inspection_camera()
	set_light_on(light_on)


func _set_metadata() -> void:
	set_meta("fixture_id", "issue_272_lit_psx_materials")
	set_meta("surface_kind", surface_kind)
	set_meta("lighting_mode", lighting_mode)
	set_meta("shader", _shader_path())
	set_meta("light_on", light_on)
	set_meta("fog_setting", "FOG_DISABLED_unchanged")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "candidate_pending_review")
	set_meta("revision_of", "library_psx_vertex.gdshader+library_psx_textured.gdshader (new opt-in variants)")


func _validate_modes() -> void:
	if not SURFACE_KINDS.has(surface_kind):
		push_error("Unknown surface_kind: %s" % surface_kind)
		surface_kind = "solid"
	if not LIGHTING_MODES.has(lighting_mode):
		push_error("Unknown lighting_mode: %s" % lighting_mode)
		lighting_mode = "baseline"


func _shader_path() -> String:
	if surface_kind == "textured":
		return SHADER_TEXTURED_LIT if lighting_mode == "lit" else SHADER_TEXTURED_BASELINE
	return SHADER_SOLID_LIT if lighting_mode == "lit" else SHADER_SOLID_BASELINE


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = BACKGROUND_COLOR
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = AMBIENT_COLOR
	environment.ambient_light_energy = AMBIENT_ENERGY
	# Fog is deliberately left at the environment default (disabled), matching
	# FOG_DISABLED in all four shader variants. It is NOT part of this comparison.
	world.environment = environment
	add_child(world)
	ambient_world = world

	var light := DirectionalLight3D.new()
	light.name = "KeyLight"
	light.light_color = KEY_LIGHT_COLOR
	light.light_energy = KEY_LIGHT_ENERGY
	light.rotation_degrees = KEY_LIGHT_ROTATION
	light.shadow_enabled = false  # URSC include sets shadows_disabled; no shadow maps here.
	add_child(light)
	key_light = light


func _build_surfaces() -> void:
	var surfaces := Node3D.new()
	surfaces.name = "Surfaces"
	add_child(surfaces)
	_add_box(surfaces, "Floor", Vector3(8.0, 0.2, 8.0), Vector3(0.0, -0.1, 0.0), Vector3.ZERO)
	_add_box(surfaces, "Cuboid", Vector3(1.4, 2.0, 1.0), Vector3(-2.2, 1.0, 0.0), Vector3(0.0, 20.0, 0.0))
	_add_sphere(surfaces, "Sphere", 0.9, Vector3(0.4, 0.9, 0.0))
	_add_cylinder(surfaces, "Cylinder", 0.5, 1.6, Vector3(2.4, 0.8, 0.6))
	_add_box(surfaces, "BackWall", Vector3(8.0, 3.0, 0.2), Vector3(0.0, 1.5, -3.5), Vector3.ZERO)


func _add_box(parent: Node3D, name: String, size: Vector3, position: Vector3,
		rotation_degrees: Vector3) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	_add_surface(parent, name, mesh, position, rotation_degrees)


func _add_sphere(parent: Node3D, name: String, radius: float, position: Vector3) -> void:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	_add_surface(parent, name, mesh, position, Vector3.ZERO)


func _add_cylinder(parent: Node3D, name: String, radius: float, height: float,
		position: Vector3) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	_add_surface(parent, name, mesh, position, Vector3.ZERO)


func _add_surface(parent: Node3D, name: String, mesh: Mesh, position: Vector3,
		rotation_degrees: Vector3) -> void:
	var instance := MeshInstance3D.new()
	instance.name = name
	instance.mesh = mesh
	instance.position = position
	instance.rotation_degrees = rotation_degrees
	var material := _surface_material()
	if material == null:
		return
	instance.material_override = material
	instance.set_meta("material_origin", "%s:%s" % [surface_kind, lighting_mode])
	instance.set_meta("shader", _shader_path())
	parent.add_child(instance)


func _surface_material() -> ShaderMaterial:
	var shader := load(_shader_path()) as Shader
	if shader == null:
		push_error("Could not load shader: %s" % _shader_path())
		return null
	var material := ShaderMaterial.new()
	material.shader = shader
	if surface_kind == "textured":
		material.set_shader_parameter("albedo_color", Color.WHITE)
		material.set_shader_parameter("albedo_texture", _checker_texture())
		material.set_shader_parameter("uv_scale", Vector2(3.0, 3.0))
	else:
		material.set_shader_parameter("albedo_color", SOLID_ALBEDO)
	return material


func _checker_texture() -> ImageTexture:
	if checker_texture != null:
		return checker_texture
	var image := Image.create(CHECKER_SIZE, CHECKER_SIZE, false, Image.FORMAT_RGBA8)
	var cell: int = CHECKER_SIZE / CHECKER_CELLS
	for y in CHECKER_SIZE:
		for x in CHECKER_SIZE:
			var column: int = x / cell
			var row: int = y / cell
			var even: bool = (column + row) % 2 == 0
			image.set_pixel(x, y, CHECKER_A if even else CHECKER_B)
	checker_texture = ImageTexture.create_from_image(image)
	return checker_texture


func _add_inspection_camera() -> void:
	var camera := Camera3D.new()
	camera.name = "InspectionCamera"
	camera.fov = 62.0
	camera.near = 0.05
	camera.far = 200.0
	add_child(camera)
	camera.position = Vector3(0.0, 3.2, 8.5)
	camera.look_at(Vector3(0.0, 1.0, -0.5), Vector3.UP)
	inspection_camera = camera


func set_light_on(on: bool) -> void:
	light_on = on
	if key_light != null:
		key_light.visible = on
	if ambient_world != null and ambient_world.environment != null:
		ambient_world.environment.ambient_light_energy = AMBIENT_ENERGY if on else 0.0
	set_meta("light_on", on)
