extends Node

const GLOBALS := {
	"affine_texture_mapping": [RenderingServer.GLOBAL_VAR_TYPE_BOOL, true],
	"texture_filtering": [RenderingServer.GLOBAL_VAR_TYPE_BOOL, false],
	"texture_lod_halve_distance": [RenderingServer.GLOBAL_VAR_TYPE_FLOAT, 0.0],
	"vertex_snap_intensity": [RenderingServer.GLOBAL_VAR_TYPE_INT, 1],
	"cull_distance": [RenderingServer.GLOBAL_VAR_TYPE_FLOAT, 0.0],
}
var originals: Array[Dictionary] = []
var packaged_enabled := true
static var globals_registered := false


func configure(room: Node3D) -> void:
	name = "LibraryPsxPreset"
	room.add_child(self)
	for argument in OS.get_cmdline_user_args():
		if argument == "--native-baseline":
			packaged_enabled = false
	_register_globals()
	for instance in room.find_children("*", "MeshInstance3D", true, false):
		_convert_instance(instance)
	set_packaged_enabled(packaged_enabled)
	room.set_meta("psx_package", "URSC 1.5 subset / 8cd971d")
	room.set_meta("operator_approved", false)
	room.set_meta("psx_applied", true)


func _register_globals() -> void:
	if globals_registered:
		return
	for parameter: String in GLOBALS:
		if not ProjectSettings.has_setting("shader_globals/" + parameter):
			RenderingServer.global_shader_parameter_add(parameter,
				GLOBALS[parameter][0], GLOBALS[parameter][1])
	globals_registered = true


func _convert_instance(instance: MeshInstance3D) -> void:
	if instance.mesh == null:
		return
	for surface in instance.mesh.get_surface_count():
		var source := instance.get_active_material(surface) as StandardMaterial3D
		if source == null:
			continue
		var material := ShaderMaterial.new()
		var shader_name := "vertex" if source.albedo_texture == null else "textured"
		material.shader = load("res://shaders/library_psx_%s.gdshader" % shader_name)
		material.set_shader_parameter("albedo_color", source.albedo_color)
		if source.albedo_texture != null:
			material.set_shader_parameter("albedo_texture", source.albedo_texture)
			material.set_shader_parameter("uv_scale", Vector2(source.uv1_scale.x, source.uv1_scale.y))
		originals.append({"instance": instance, "surface": surface,
			"override": instance.material_override,
			"surface_material": instance.get_surface_override_material(surface), "psx": material})


func set_packaged_enabled(enabled: bool) -> void:
	packaged_enabled = enabled
	for record in originals:
		var instance: MeshInstance3D = record.instance
		instance.material_override = null if enabled else record.override
		instance.set_surface_override_material(record.surface,
			record.psx if enabled else record.surface_material)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F6:
		set_packaged_enabled(not packaged_enabled)
		print("URSC packaged material effects: ", packaged_enabled)
