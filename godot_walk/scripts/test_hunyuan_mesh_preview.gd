extends SceneTree

const PREVIEW_SCENE_PATH := "res://scenes/hunyuan_mesh_preview.tscn"
const MESH_SCENE_PATH := "res://generated_mesh_scenes/hunyuan_track_a_full_run/hunyuan_layers.glb"
const CAMERA_METADATA_PATH := "res://evidence/2026-10-13-hunyuan-track-a/source_selection.json"


func _initialize() -> void:
	call_deferred("_verify_candidate")


func _verify_candidate() -> void:
	if not FileAccess.file_exists(MESH_SCENE_PATH):
		print("SKIP: local Hunyuan GLB has not been generated")
		quit(0)
		return
	var packed := load(PREVIEW_SCENE_PATH) as PackedScene
	if packed == null:
		_fail("preview scene could not be loaded")
		return
	var instance := packed.instantiate()
	root.add_child(instance)
	await process_frame
	var meshes: Array[MeshInstance3D] = []
	_collect_meshes(instance, meshes)
	var ok := _verify_render_meshes(meshes)
	ok = _verify_alignment(instance) and ok
	ok = _verify_no_walk_collision(instance) and ok
	if ok:
		print("OK: imported Hunyuan mesh is aligned for viewing and remains non-walkable")
	quit(0 if ok else 1)


func _verify_render_meshes(meshes: Array[MeshInstance3D]) -> bool:
	if meshes.size() < 2:
		return _fail("expected separate foreground and background mesh instances")
	for mesh_instance in meshes:
		if mesh_instance.mesh == null or mesh_instance.mesh.get_surface_count() == 0:
			return _fail("an imported mesh instance has no surfaces")
		if mesh_instance.mesh.get_aabb().size.length_squared() <= 0.0:
			return _fail("an imported mesh instance has empty bounds")
	print("OK: %d imported mesh instances" % meshes.size())
	return true


func _verify_alignment(instance: Node) -> bool:
	var mesh_root := instance.get_node_or_null("MeshRoot/HunyuanLayers") as Node3D
	var camera := instance.get_node_or_null("PreviewCamera") as Camera3D
	var camera_data := _load_camera_metadata()
	if mesh_root == null or camera == null or camera_data.is_empty():
		return _fail("registered camera or imported mesh root is missing")
	var forward := _vector3(camera_data["forward_godot_world"]).normalized()
	var up := _vector3(camera_data["up_godot_world"]).normalized()
	var right := forward.cross(up).normalized()
	var basis := mesh_root.transform.basis
	if not basis.x.is_equal_approx(-forward) or not basis.y.is_equal_approx(right):
		return _fail("mesh basis does not map Hunyuan forward/right into the registered camera")
	var expected_origin := _vector3(camera_data["camera_center_godot_world_m"])
	if not mesh_root.position.is_equal_approx(expected_origin):
		return _fail("mesh origin differs from the registered camera center")
	return true


func _verify_no_walk_collision(instance: Node) -> bool:
	if not instance.find_children("*", "CollisionObject3D", true, false).is_empty():
		return _fail("unvalidated Hunyuan candidate must not contain collision objects")
	if instance.find_child("Player", true, false) != null:
		return _fail("unvalidated Hunyuan candidate must not stage a player")
	return true


func _load_camera_metadata() -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(CAMERA_METADATA_PATH))
	if not parsed is Dictionary or not parsed.get("camera", {}) is Dictionary:
		return {}
	return parsed["camera"]


func _vector3(values: Array) -> Vector3:
	return Vector3(float(values[0]), float(values[1]), float(values[2])) if values.size() == 3 else Vector3.ZERO


func _collect_meshes(node: Node, output: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		output.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_meshes(child, output)


func _fail(message: String) -> bool:
	printerr("FAIL: %s" % message)
	quit(1)
	return false
