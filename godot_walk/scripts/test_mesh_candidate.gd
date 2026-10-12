extends SceneTree

const DEFAULT_SCENE := "res://generated_mesh_scenes/backrooms_mesh_v1/scene.tscn"


func _initialize() -> void:
	var scene_path := DEFAULT_SCENE
	var args := OS.get_cmdline_user_args()
	if not args.is_empty():
		scene_path = args[0]
	var report_path := scene_path.get_base_dir().path_join("scene_report.json")
	var report := _load_report(report_path)
	if report.is_empty():
		_fail("could not load scene report %s" % report_path)
		quit(1)
		return
	var packed := load(scene_path) as PackedScene
	if packed == null:
		_fail("could not load %s" % scene_path)
		quit(1)
		return
	var instance := packed.instantiate()
	root.add_child(instance)
	await process_frame
	await physics_frame
	var ok := _verify_textured_mesh(instance)
	ok = _verify_collision_and_floor(instance, report) and ok
	if ok:
		print("OK: textured mesh scene and collision assessment verified")
	quit(0 if ok else 1)


func _verify_textured_mesh(instance: Node) -> bool:
	var meshes: Array[MeshInstance3D] = []
	_collect_meshes(instance, meshes)
	var textured_surfaces := 0
	for mesh_instance in meshes:
		if mesh_instance.mesh == null:
			continue
		for surface in range(mesh_instance.mesh.get_surface_count()):
			var material := mesh_instance.mesh.surface_get_material(surface) as BaseMaterial3D
			if material != null and material.albedo_texture != null:
				textured_surfaces += 1
	if meshes.is_empty() or textured_surfaces == 0:
		return _fail("scene has no textured MeshInstance3D surfaces")
	print("OK: %d mesh instances, %d textured surfaces" % [meshes.size(), textured_surfaces])
	return true


func _verify_collision_and_floor(instance: Node, report: Dictionary) -> bool:
	var collision := instance.get_node_or_null("GeneratedCollision") as StaticBody3D
	if collision == null:
		return _fail("GeneratedCollision is missing")
	var triangles := int(collision.get("triangle_count"))
	if triangles <= 0:
		return _fail("collision mesh is empty: %s" % str(collision.get("load_error")))
	var shape_node := collision.get_node_or_null("CollisionShape3D") as CollisionShape3D
	if shape_node == null or not shape_node.shape is ConcavePolygonShape3D:
		return _fail("collision did not create a concave triangle shape")
	if not bool(report.get("walkable", false)):
		if instance.get_node_or_null("PlayerSpawn") != null or instance.get_node_or_null("Player") != null:
			return _fail("non-walkable mesh scene must not stage a player")
		var path_hits := _count_camera_path_floor_rays(instance, report)
		var path_poses := int(report.get("camera_path_poses", 0))
		if path_poses == 0 or float(path_hits) / path_poses >= 0.75:
			return _fail("scene report rejects floor, but %d/%d capture poses have collision support" % [path_hits, path_poses])
		print(
			"NEGATIVE: %d collision triangles, %.4f m2 low horizontal support, %d/%d capture poses grounded; " %
			[
				triangles,
				float(report.get("low_horizontal_support_area_m2", 0.0)),
				path_hits,
				path_poses,
			]
			+ "scene intentionally has no player spawn"
		)
		return true
	var player := instance.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		return _fail("walkable scene report has no Player")
	var floor: Variant = _raycast_floor(instance, player)
	if floor == null:
		return _fail("no collision floor under the staged player spawn")
	var spawn := instance.get_node("PlayerSpawn") as Marker3D
	if spawn.global_position.distance_to(player.global_position) > 0.001:
		return _fail("PlayerSpawn and Player transforms differ")
	var spawn_view := str(report.get("spawn_view", ""))
	var heights: Dictionary = report.get("floor_height_by_view", {})
	if not heights.has(spawn_view) or absf(float(floor) - float(heights[spawn_view])) > 0.08:
		return _fail("Godot spawn floor differs from the staged camera-path floor")
	if absf((player.global_position.y - 0.6) - float(floor)) > 0.08:
		return _fail("player capsule does not start on the measured collision floor")
	print("OK: collision has %d triangles; spawn ray hits y=%.3f" % [triangles, floor])
	return true


func _raycast_floor(instance: Node, player: CharacterBody3D) -> Variant:
	var spawn := instance.get_node_or_null("PlayerSpawn") as Marker3D
	if spawn == null:
		return null
	var query := PhysicsRayQueryParameters3D.create(
		spawn.global_position + Vector3.UP,
		spawn.global_position - Vector3.UP
	)
	query.exclude = [player.get_rid()]
	var hit: Dictionary = (instance as Node3D).get_world_3d().direct_space_state.intersect_ray(query)
	return hit.get("position", Vector3.ZERO).y if not hit.is_empty() else null


func _count_camera_path_floor_rays(instance: Node, report: Dictionary) -> int:
	var meshes: Array[MeshInstance3D] = []
	_collect_meshes(instance, meshes)
	if meshes.is_empty() or meshes[0].mesh == null:
		return 0
	var bounds := meshes[0].global_transform * meshes[0].get_aabb()
	var floor_ceiling := bounds.position.y + bounds.size.y * float(report.get("floor_search_height_fraction", 0.35))
	var space := (instance as Node3D).get_world_3d().direct_space_state
	var hits := 0
	var path: Dictionary = report.get("camera_path_positions", {})
	for value in path.values():
		if not value is Array or value.size() != 3:
			continue
		var from := Vector3(float(value[0]), bounds.end.y + 0.1, float(value[2]))
		var to := Vector3(float(value[0]), bounds.position.y - 0.1, float(value[2]))
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(from, to))
		if not hit.is_empty() and hit.normal.y > 0.8 and hit.position.y <= floor_ceiling:
			hits += 1
	return hits


func _load_report(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var value: Variant = JSON.parse_string(file.get_as_text())
	return value if value is Dictionary else {}


func _collect_meshes(node: Node, meshes: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		meshes.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_meshes(child, meshes)


func _fail(message: String) -> bool:
	printerr("FAIL: %s" % message)
	return false
