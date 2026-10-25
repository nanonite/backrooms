extends Node3D

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const FLOOR_TEXTURE := "floor_source_video.png"
const CEILING_TEXTURE := "ceiling_source_video.png"
const BASELINE_SCALE := Vector2(4.0, 4.0)
const CANDIDATE_SCALE := Vector2(16.0, 16.0)
const CEILING_BRIDGE_UV_SCALE := Vector2(1.3, 1.18)
const FLOOR_Y := -1.27099049
const CEILING_Y := FLOOR_Y + 2.4
const CEILING_PATCH_DROP := 0.06

var _walkthrough: Node3D
var _label: Label
var _candidate_enabled := false
var _ceiling_candidate_enabled := false
var _pocket_instance_id := 0
var _floor_materials: Array[Dictionary] = []
var _ceiling_patch: MeshInstance3D


func _ready() -> void:
	_walkthrough = WALKTHROUGH.instantiate() as Node3D
	if _walkthrough == null:
		push_error("#157 cannot instantiate the accepted #156 walkthrough")
		get_tree().quit(2)
		return
	add_child(_walkthrough)
	_create_ceiling_patch()
	_add_status_label()


func _process(_delta: float) -> void:
	if not _walkthrough.get_meta("walkthrough_ready", false):
		return
	_refresh_pocket_materials()


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo \
			and event.keycode == KEY_F8:
		_candidate_enabled = not _candidate_enabled
		_apply_floor_scale()
		_update_label()
		get_viewport().set_input_as_handled()


func set_ceiling_candidate_enabled(enabled: bool) -> void:
	if _ceiling_patch == null:
		return
	_ceiling_candidate_enabled = enabled
	_ceiling_patch.visible = enabled
	_update_label()


func _refresh_pocket_materials() -> void:
	var pocket := _walkthrough.find_child("R001", true, false) as Node3D
	var instance_id := pocket.get_instance_id() if pocket != null else 0
	if instance_id == _pocket_instance_id:
		return
	_pocket_instance_id = instance_id
	_floor_materials.clear()
	if pocket != null:
		_collect_floor_materials(pocket)
	_apply_floor_scale()
	print("ISSUE157_FLOOR_REVIEW pocket_loaded=%s matching_surfaces=%d" % [
		pocket != null, _floor_materials.size()])
	_update_label()


func _collect_floor_materials(pocket: Node3D) -> void:
	for child: Node in pocket.find_children("*", "MeshInstance3D", true, false):
		var instance := child as MeshInstance3D
		if instance.mesh == null:
			continue
		for surface in instance.mesh.get_surface_count():
			_collect_floor_surface(instance, surface)


func _collect_floor_surface(instance: MeshInstance3D, surface: int) -> void:
	var original := instance.get_surface_override_material(surface) as ShaderMaterial
	if original == null:
		original = instance.get_active_material(surface) as ShaderMaterial
	if original == null or not _uses_floor_texture(original):
		return
	var candidate := original.duplicate() as ShaderMaterial
	candidate.set_shader_parameter("uv_scale", CANDIDATE_SCALE)
	_floor_materials.append({"instance": instance, "surface": surface,
		"original": original, "candidate": candidate})


func _uses_floor_texture(material: ShaderMaterial) -> bool:
	var texture := material.get_shader_parameter("albedo_texture") as Texture2D
	return texture != null and texture.resource_path.ends_with(FLOOR_TEXTURE)


func _apply_floor_scale() -> void:
	for entry: Dictionary in _floor_materials:
		var instance: MeshInstance3D = entry.instance
		if not is_instance_valid(instance):
			continue
		var material: ShaderMaterial = entry.candidate if _candidate_enabled else entry.original
		instance.set_surface_override_material(entry.surface, material)


func _add_status_label() -> void:
	var canvas := CanvasLayer.new()
	canvas.layer = 100
	_label = Label.new()
	_label.position = Vector2(18.0, 18.0)
	_label.add_theme_font_size_override("font_size", 20)
	_label.add_theme_color_override("font_color", Color.WHITE)
	_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(_label)
	add_child(canvas)
	_update_label()


func _create_ceiling_patch() -> void:
	var texture := load("res://assets/psx_extension/textures/%s" % CEILING_TEXTURE) as Texture2D
	var shader := load("res://shaders/library_psx_textured.gdshader") as Shader
	if texture == null or shader == null:
		push_error("#157 cannot load the source-textured ceiling bridge resources")
		return
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("albedo_texture", texture)
	material.set_shader_parameter("albedo_color", Color.WHITE)
	material.set_shader_parameter("uv_scale", CEILING_BRIDGE_UV_SCALE)
	var plane := PlaneMesh.new()
	plane.size = Vector2(2.6, 2.0)
	plane.material = material
	_ceiling_patch = MeshInstance3D.new()
	_ceiling_patch.name = "Issue157SourceTexturedCeilingBridge"
	_ceiling_patch.mesh = plane
	_ceiling_patch.position = Vector3(3.5, CEILING_Y - CEILING_PATCH_DROP, 3.1)
	_ceiling_patch.visible = false
	add_child(_ceiling_patch)


func _update_label() -> void:
	var factor := "16x preview" if _candidate_enabled else "4x selected"
	var ceiling := "preview enabled" if _ceiling_candidate_enabled else "off (operator choice)"
	_label.text = "F8 floor UV: %s | F9 ceiling bridge: %s | %d pocket floor surfaces" % [
		factor, ceiling, _floor_materials.size()]
