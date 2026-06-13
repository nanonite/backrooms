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
	if not _ensure_screenshot_dir():
		quit(1)
		return

	var cameras := [
		_create_perspective_camera("overhead_orbit", Vector3(4.0, 3.0, 4.0), Vector3(0.0, 0.8, 0.0), 60.0),
		_create_perspective_camera("player_pov", PLAYER_SPAWN + Vector3(0.0, 1.45, 0.0), PLAYER_SPAWN + Vector3(0.0, 1.2, -5.0), 70.0),
		_create_top_down_camera("top_down", Vector3(0.0, 8.0, 0.0), 10.0),
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


func _create_perspective_camera(name: String, position: Vector3, target: Vector3, fov: float) -> Camera3D:
	var camera := Camera3D.new()
	camera.name = name
	camera.position = position
	camera.fov = fov
	camera.look_at(target, Vector3.UP)
	return camera


func _create_top_down_camera(name: String, position: Vector3, size: float) -> Camera3D:
	var camera := Camera3D.new()
	camera.name = name
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = size
	camera.position = position
	camera.look_at(Vector3.ZERO, Vector3.FORWARD)
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
