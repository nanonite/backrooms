extends SceneTree

## Capture the bounded walk envelope from the central spawn in 8 headings.
##
## Renders the true first-person view (player eye height) from the contract's
## PlayerSpawn toward 8 compass headings at 1280x720, so the reviewer can see
## exactly what the player sees at every reachable heading inside the walkable
## envelope.
##
## Requires a real GPU context (DISPLAY + --rendering-driver vulkan): the
## headless dummy driver never emits RenderingServer.frame_post_draw, which the
## capture awaits.
##
## Usage:
##   DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
##       --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx.tscn --out=res://evidence/walk_envelope
##
## Optional arguments:
##   --settle=N                 frames to wait before each capture (default 5).
##                              The GDGS splat render converges over ~150 frames
##                              (#103 measured it: frame 5 differs from frame 150
##                              on 27% of pixels, frame 150 == frame 300), so
##                              splat evidence must pass a larger value.
##   --camera-position=x,y,z    explicit world-space eye position; permits
##                              matched captures in scenes without PlayerSpawn.
##   --camera-yaw-deg=N          rotate the 8-heading compass around world up.
##   --splat=res://path.ply     swap the scene's splat resource for an ablation
##   --splat-translation=x,y,z  candidate; both are required together, because
##                              GDGS re-centres each PLY at import and only the
##                              matching origin keeps the world fixed.

const DEFAULT_SCENE := "res://scenes/corridor_psx.tscn"
const OUT_DIR := "res://evidence/walk_envelope"
const SETTLE_FRAMES := 5
const MAX_CAMERA_COORDINATE_METERS := 100000.0
const MAX_CAMERA_YAW_DEGREES := 360000.0
## Node that carries the splat resource in every corridor scene.
const SPLAT_NODE_NAME := "CorridorSplatNode"

var scene_path := DEFAULT_SCENE
var out_dir := OUT_DIR
var settle_frames := SETTLE_FRAMES
var camera_position := Vector3.ZERO
var has_camera_position := false
var camera_yaw_degrees := 0.0
var hide_node_path := ""
## Optional #103 ablation override: swap the scene's splat resource (and the
## node origin that keeps the world fixed) without authoring another scene.
var splat_override_path := ""
var splat_override_origin := Vector3.ZERO
var has_splat_override_origin := false


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	for arg in args:
		if arg.begins_with("--scene="):
			scene_path = arg.split("=")[1]
		elif arg.begins_with("--out="):
			out_dir = arg.split("=")[1]
		elif arg.begins_with("--settle="):
			settle_frames = maxi(0, int(arg.split("=")[1]))
		elif arg.begins_with("--camera-position="):
			if not _parse_camera_position(arg.get_slice("=", 1)):
				printerr("FAIL: --camera-position expects finite x,y,z coordinates")
				quit(1)
				return
		elif arg.begins_with("--camera-yaw-deg="):
			var yaw_text := arg.get_slice("=", 1)
			if not yaw_text.is_valid_float():
				printerr("FAIL: --camera-yaw-deg expects a finite number")
				quit(1)
				return
			camera_yaw_degrees = float(yaw_text)
			if not absf(camera_yaw_degrees) <= MAX_CAMERA_YAW_DEGREES:
				printerr("FAIL: --camera-yaw-deg is outside the supported range")
				quit(1)
				return
		elif arg.begins_with("--hide-node="):
			hide_node_path = arg.get_slice("=", 1)
		elif arg.begins_with("--splat="):
			splat_override_path = arg.split("=")[1]
		elif arg.begins_with("--splat-translation="):
			var parts := arg.split("=")[1].split(",")
			if parts.size() == 3:
				splat_override_origin = Vector3(
					float(parts[0]), float(parts[1]), float(parts[2]))
				has_splat_override_origin = true
			else:
				printerr("FAIL: --splat-translation expects x,y,z")
				quit(1)
				return

	var scene: PackedScene = load(scene_path)
	if scene == null:
		printerr("FAIL: could not load %s" % scene_path)
		quit(1)
		return
	var instance: Node = scene.instantiate()
	if instance == null:
		printerr("FAIL: could not instantiate %s" % scene_path)
		quit(1)
		return
	root.add_child(instance)
	await process_frame
	if not _hide_requested_node(instance):
		quit(1)
		return

	var spawn := instance.get_node_or_null("PlayerSpawn") as Node3D
	if spawn == null and not has_camera_position:
		printerr("FAIL: no PlayerSpawn in %s; pass --camera-position for a matched view" % scene_path)
		quit(1)
		return

	if splat_override_path != "" and not _apply_splat_override(instance):
		quit(1)
		return

	# Player eye height (#101): read the production Head node, so the capture
	# always renders what the player actually sees. The Head offset lives in
	# player.tscn (0.5 m above the capsule centre); hardcoding it here drifted
	# once already (the legacy 1.6 m value put the camera inside the ceiling).
	var eye := camera_position
	if not has_camera_position:
		var player := instance.get_node_or_null("Player") as Node3D
		var eye_height := spawn.global_position.y + 0.5
		if player != null:
			var head := player.get_node_or_null("Head") as Node3D
			if head != null:
				eye_height = head.global_position.y
			else:
				eye_height = player.global_position.y + 0.5
		eye = Vector3(spawn.global_position.x, eye_height, spawn.global_position.z)
	else:
		var player := instance.get_node_or_null("Player") as CharacterBody3D
		if player != null:
			var head := player.get_node_or_null("Head") as Node3D
			if head != null:
				player.global_position += eye - head.global_position
				player.velocity = Vector3.ZERO

	var headings := [
		["e", Vector3(1.0, 0.0, 0.0)],
		["ne", Vector3(1.0, 0.0, 1.0).normalized()],
		["n", Vector3(0.0, 0.0, 1.0)],
		["nw", Vector3(-1.0, 0.0, 1.0).normalized()],
		["w", Vector3(-1.0, 0.0, 0.0)],
		["sw", Vector3(-1.0, 0.0, -1.0).normalized()],
		["s", Vector3(0.0, 0.0, -1.0)],
		["se", Vector3(1.0, 0.0, -1.0).normalized()],
	]

	var dir_path := out_dir + "/spawn_headings"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir_path))

	for heading in headings:
		var name: String = heading[0]
		var direction: Vector3 = heading[1]
		direction = direction.rotated(Vector3.UP, deg_to_rad(camera_yaw_degrees))
		var camera := Camera3D.new()
		camera.name = "pov_%s" % name
		camera.fov = 75.0
		camera.look_at_from_position(eye, eye + direction, Vector3.UP)
		instance.add_child(camera)
		await _capture(camera, dir_path + "/spawn_%s.png" % name)
		instance.remove_child(camera)
		camera.free()

	print("OK: wrote %d heading captures to %s" % [headings.size(), dir_path])
	quit(0)


func _parse_camera_position(value: String) -> bool:
	var parts := value.split(",", false)
	if parts.size() != 3:
		return false
	var coordinates: Array[float] = []
	for part in parts:
		var coordinate_text := part.strip_edges()
		if not coordinate_text.is_valid_float():
			return false
		var coordinate := float(coordinate_text)
		if not absf(coordinate) <= MAX_CAMERA_COORDINATE_METERS:
			return false
		coordinates.append(coordinate)
	camera_position = Vector3(coordinates[0], coordinates[1], coordinates[2])
	has_camera_position = true
	return true


func _apply_splat_override(instance: Node) -> bool:
	## Swap the scene's splat for an ablation candidate, keeping the world fixed.
	##
	## GDGS re-centres the loaded PLY at import, so every candidate carries its
	## own node origin (`node_translation_world` in its report). Swapping only
	## the resource would silently slide the room, which is exactly the trap
	## `corridor_psx.tscn` documents; the origin must be passed with the PLY.
	if not has_splat_override_origin:
		printerr("FAIL: --splat requires --splat-translation=x,y,z")
		return false
	var node := instance.get_node_or_null(SPLAT_NODE_NAME) as GaussianSplatNode
	if node == null:
		printerr("FAIL: no %s in %s" % [SPLAT_NODE_NAME, scene_path])
		return false
	var resource := load(splat_override_path)
	if resource == null:
		printerr("FAIL: could not load %s" % splat_override_path)
		return false
	node.gaussian = resource
	var node_transform := node.transform
	node_transform.origin = splat_override_origin
	node.transform = node_transform
	print("OVERRIDE: splat=%s origin=%s" % [splat_override_path, splat_override_origin])
	return true


func _hide_requested_node(instance: Node) -> bool:
	if hide_node_path == "":
		return true
	var target := instance.get_node_or_null(hide_node_path)
	if target == null:
		printerr("FAIL: cannot find hidden node %s" % hide_node_path)
		return false
	var visuals := []
	if target is VisualInstance3D:
		visuals.append(target)
	visuals.append_array(target.find_children("*", "VisualInstance3D", true, false))
	if visuals.is_empty():
		printerr("FAIL: hidden node has no VisualInstance3D descendants")
		return false
	for visual in visuals:
		visual.visible = false
	return true


func _capture(camera: Camera3D, path: String) -> void:
	camera.current = true
	for _frame in range(settle_frames):
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image == null or image.is_empty():
		printerr("FAIL: empty screenshot for %s" % camera.name)
		quit(1)
		return
	var error := image.save_png(ProjectSettings.globalize_path(path))
	if error != OK:
		printerr("FAIL: could not save %s (error %d)" % [path, error])
		quit(1)
		return
	print("WROTE: %s" % path)
