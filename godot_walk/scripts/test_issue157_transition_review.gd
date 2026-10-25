extends SceneTree

const REVIEW_SCENE := preload("res://scenes/issue157_transition_review.tscn")


func _initialize() -> void:
	call_deferred("_verify_toggle")


func _verify_toggle() -> void:
	var review := REVIEW_SCENE.instantiate() as Node3D
	root.add_child(review)
	for frame in 180:
		if review.get("_floor_materials").size() == 1:
			break
		await process_frame
	var materials: Array[Dictionary] = review.get("_floor_materials")
	if materials.size() != 1:
		push_error("#157 expected one pocket floor material")
		quit(1)
		return
	var ceiling_patch := review.get("_ceiling_patch") as MeshInstance3D
	if ceiling_patch == null or ceiling_patch.visible:
		push_error("#157 ceiling candidate should be loaded and hidden by default")
		quit(1)
		return
	review.call("set_ceiling_candidate_enabled", true)
	if not ceiling_patch.visible:
		push_error("#157 ceiling candidate could not be enabled")
		quit(1)
		return
	review.call("set_ceiling_candidate_enabled", false)
	if ceiling_patch.visible:
		push_error("#157 ceiling candidate could not be hidden")
		quit(1)
		return
	var entry := materials[0]
	var instance: MeshInstance3D = entry.instance
	var surface: int = entry.surface
	var original: ShaderMaterial = entry.original
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_F8
	review.call("_input", event)
	var candidate := instance.get_surface_override_material(surface) as ShaderMaterial
	if candidate.get_shader_parameter("uv_scale") != Vector2(16.0, 16.0):
		push_error("#157 F8 did not apply the UV candidate")
		quit(1)
		return
	review.call("_input", event)
	if instance.get_surface_override_material(surface) != original:
		push_error("#157 F8 did not restore the current material")
		quit(1)
		return
	print("ISSUE157_TRANSITION_TOGGLE: PASS")
	quit()
