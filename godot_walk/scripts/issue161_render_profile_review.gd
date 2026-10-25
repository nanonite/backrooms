extends Node3D

const WALKTHROUGH := preload("res://scenes/issue156_streamed_walkthrough.tscn")
const PROFILE_NAME := "affine_texture_mapping"

var _walkthrough: Node3D
var _affine_enabled := false
var _profile_label: Label


func _ready() -> void:
	_walkthrough = WALKTHROUGH.instantiate() as Node3D
	if _walkthrough == null:
		push_error("#161 cannot instantiate the #156 walkthrough")
		get_tree().quit(2)
		return
	add_child(_walkthrough)
	_add_profile_label()
	call_deferred("_apply_after_walkthrough_ready")


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo \
			and event.keycode == KEY_F7:
		_affine_enabled = not _affine_enabled
		_apply_profile()
		get_viewport().set_input_as_handled()


func _apply_after_walkthrough_ready() -> void:
	for frame in 180:
		if _walkthrough.get_meta("walkthrough_ready", false):
			_apply_profile()
			return
		await get_tree().process_frame
	push_error("#161 walkthrough did not finish loading")
	get_tree().quit(2)


func _apply_profile() -> void:
	RenderingServer.global_shader_parameter_set(PROFILE_NAME, _affine_enabled)
	_profile_label.text = "F7 toggles profile | %s" % _profile_name()
	print("ISSUE161_PROFILE affine_texture_mapping=%s" % _affine_enabled)


func _profile_name() -> String:
	return "A / affine on" if _affine_enabled else "B / affine off"


func _add_profile_label() -> void:
	var canvas := CanvasLayer.new()
	canvas.layer = 100
	_profile_label = Label.new()
	_profile_label.position = Vector2(18.0, 18.0)
	_profile_label.add_theme_font_size_override("font_size", 20)
	_profile_label.add_theme_color_override("font_color", Color.WHITE)
	_profile_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(_profile_label)
	add_child(canvas)
