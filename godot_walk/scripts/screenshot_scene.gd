extends SceneTree

const DEFAULT_SCENE_PATH := "res://scenes/corridor.tscn"
const SCREENSHOT_DIR := "res://screenshots"
const CAPTURE_FRAME_COUNT := 5
const PLAYER_SPAWN := Vector3(0.116, 0.9, 0.041)

var target_scene_path := DEFAULT_SCENE_PATH


func _init() -> void:
	target_scene_path = _target_scene_path()
	var instance: Node = _load_scene(target_scene_path)
	if instance == null:
		quit(1)
		return

	root.add_child(instance)
	await process_frame
	if not _ensure_screenshot_dir():
		quit(1)
		return

	_print_splat_aabbs(instance)

	var bounds := _scene_bounds(instance)
	var center := bounds.get_center()
	var size := bounds.size
	var radius = max(size.x, max(size.y, size.z))
	radius = max(radius, 4.0)

	# Recreate the original video camera path: travel THROUGH the corridor from
	# inside. Y is up/height (PLY header: Vertical axis = y); the corridor LENGTH
	# is whichever of X/Z has the larger extent. Derive the interior POV from the
	# splat AABB at runtime instead of the dead-mesh PLAYER_SPAWN.
	var length_is_z := size.z >= size.x
	var pov_eye: Vector3
	var pov_target: Vector3
	var pov_eye_reverse: Vector3
	var pov_target_reverse: Vector3
	if length_is_z:
		var near_z := bounds.position.z + size.z * 0.05
		var far_z := bounds.position.z + size.z * 0.95
		pov_eye = Vector3(center.x, center.y, near_z)
		pov_target = Vector3(center.x, center.y, far_z)
		pov_eye_reverse = Vector3(center.x, center.y, far_z)
		pov_target_reverse = Vector3(center.x, center.y, near_z)
	else:
		var near_x := bounds.position.x + size.x * 0.05
		var far_x := bounds.position.x + size.x * 0.95
		pov_eye = Vector3(near_x, center.y, center.z)
		pov_target = Vector3(far_x, center.y, center.z)
		pov_eye_reverse = Vector3(far_x, center.y, center.z)
		pov_target_reverse = Vector3(near_x, center.y, center.z)

	var cameras := [
		_create_perspective_camera("overhead_orbit", center + Vector3(radius, radius * 0.7, radius), center, 60.0),
		_create_perspective_camera("player_pov", pov_eye, pov_target, 75.0),
		_create_perspective_camera("player_pov_reverse", pov_eye_reverse, pov_target_reverse, 75.0),
		_create_top_down_camera("top_down", center + Vector3(0.0, radius * 1.6, 0.0), center, radius * 1.5),
	]

	for camera in cameras:
		instance.add_child(camera)

	for camera in cameras:
		var ok := await _capture(camera)
		if not ok:
			quit(1)
			return

	print("OK: wrote %d screenshots for %s" % [cameras.size(), target_scene_path])
	quit(0)


func _target_scene_path() -> String:
	var args := OS.get_cmdline_user_args()
	if args.size() == 0 or args[0].strip_edges() == "":
		return DEFAULT_SCENE_PATH
	return args[0]


func _load_scene(scene_path: String) -> Node:
	var scene: PackedScene = load(scene_path) as PackedScene
	if scene == null:
		printerr("FAIL: could not load %s" % scene_path)
		return null

	var instance: Node = scene.instantiate()
	if instance == null:
		printerr("FAIL: could not instantiate %s" % scene_path)
		return null
	return instance


func _ensure_screenshot_dir() -> bool:
	var absolute_dir := ProjectSettings.globalize_path(SCREENSHOT_DIR)
	var error := DirAccess.make_dir_recursive_absolute(absolute_dir)
	if error != OK:
		printerr("FAIL: could not create %s (error %d)" % [SCREENSHOT_DIR, error])
		return false
	return true


func _scene_bounds(node: Node) -> AABB:
	# Collect every VisualInstance3D, not just MeshInstance3D, so camera framing
	# works for Gaussian-splat scenes (GaussianSplatNode is a VisualInstance3D
	# that exposes a valid AABB via _get_aabb()), not only textured meshes.
	var visuals: Array[VisualInstance3D] = []
	_collect_visuals(node, visuals)

	var bounds := AABB()
	var have_bounds := false
	for visual in visuals:
		var visual_aabb := _visual_bounds(visual)
		# Skip degenerate/unpopulated AABBs so they don't drag bounds to origin.
		if visual_aabb.size == Vector3.ZERO:
			continue
		if not have_bounds:
			bounds = visual_aabb
			have_bounds = true
		else:
			bounds = bounds.merge(visual_aabb)
	if not have_bounds:
		return AABB(Vector3(-2.0, 0.0, -2.0), Vector3(4.0, 2.0, 4.0))
	return bounds


func _print_splat_aabbs(node: Node) -> void:
	# Print the world-space AABB of every VisualInstance3D so the operator can
	# read the splat's true orientation + metric scale straight off stdout/log.
	# Format is machine-greppable: SPLAT_AABB: name=<node> pos=(x,y,z) size=(x,y,z)
	var visuals: Array[VisualInstance3D] = []
	_collect_visuals(node, visuals)
	for visual in visuals:
		var aabb := _visual_bounds(visual)
		print("SPLAT_AABB: name=%s pos=(%.4f, %.4f, %.4f) size=(%.4f, %.4f, %.4f)" % [
			visual.name,
			aabb.position.x, aabb.position.y, aabb.position.z,
			aabb.size.x, aabb.size.y, aabb.size.z,
		])


func _collect_visuals(node: Node, visuals: Array[VisualInstance3D]) -> void:
	if node is VisualInstance3D:
		visuals.append(node as VisualInstance3D)
	for child in node.get_children():
		_collect_visuals(child, visuals)


func _visual_bounds(visual: VisualInstance3D) -> AABB:
	var local_bounds := visual.get_aabb()
	var first_point := visual.global_transform * local_bounds.get_endpoint(0)
	var bounds := AABB(first_point, Vector3.ZERO)
	for index in range(1, 8):
		bounds = bounds.expand(visual.global_transform * local_bounds.get_endpoint(index))
	return bounds


func _create_perspective_camera(name: String, position: Vector3, target: Vector3, fov: float) -> Camera3D:
	var camera := Camera3D.new()
	camera.name = name
	camera.fov = fov
	camera.look_at_from_position(position, target, Vector3.UP)
	return camera


func _create_top_down_camera(name: String, position: Vector3, target: Vector3, size: float) -> Camera3D:
	var camera := Camera3D.new()
	camera.name = name
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = size
	camera.look_at_from_position(position, target, Vector3.FORWARD)
	return camera


func _capture(camera: Camera3D) -> bool:
	camera.current = true
	for _frame in range(CAPTURE_FRAME_COUNT):
		await process_frame
	await RenderingServer.frame_post_draw

	var image := root.get_texture().get_image()
	if image == null or image.is_empty():
		printerr("FAIL: empty screenshot for %s" % camera.name)
		return false

	var path := "%s/%s.png" % [SCREENSHOT_DIR, camera.name]
	var error := image.save_png(path)
	if error != OK:
		printerr("FAIL: could not save %s (error %d)" % [path, error])
		return false

	print("WROTE: %s" % path)
	return true
