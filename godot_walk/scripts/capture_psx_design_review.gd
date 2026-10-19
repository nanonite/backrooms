extends SceneTree

const CATALOG := preload("res://scripts/psx_design_variant_catalog.gd")
const SCENE_PATH := "res://scenes/corridor_psx_design_candidate.tscn"
const FOV_DEGREES := 75.0
const RESOLUTION := Vector2i(1280, 720)
const HEADINGS := {
	"e": Vector3(1.0, 0.0, 0.0),
	"n": Vector3(0.0, 0.0, 1.0),
	"w": Vector3(-1.0, 0.0, 0.0),
	"s": Vector3(0.0, 0.0, -1.0),
}
const VIEW_PLAN := [
	{"station": "patch_anchor", "route_id": "route_2", "headings": ["e", "w"]},
	{"station": "transition", "route_id": "route_3", "headings": ["e", "w"]},
	{"station": "column", "route_id": "route_5", "headings": ["e", "n", "w", "s"]},
	{"station": "far_room", "route_id": "route_6", "headings": ["e", "w"]},
]

var variant_id := "v2_control"
var out_dir := "res://evidence/psx_design_review/captures/v2_control/repeat_1"
var positions_path := ""
var settle_frames := 200
var views: Array[Dictionary] = []


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--variant="):
			variant_id = argument.trim_prefix("--variant=")
		elif argument.begins_with("--out-dir="):
			out_dir = argument.trim_prefix("--out-dir=")
		elif argument.begins_with("--positions-json="):
			positions_path = argument.trim_prefix("--positions-json=")
		elif argument.begins_with("--settle="):
			if not _set_settle(argument.trim_prefix("--settle=")):
				printerr("FAIL: --settle must be an integer from 0 through 1000")
				quit(1)
				return
	if not CATALOG.variant_ids().has(variant_id) or positions_path.is_empty():
		printerr("FAIL: provide a catalog variant and --positions-json")
		quit(1)
		return
	call_deferred("_capture_all")


func _capture_all() -> void:
	var spec := CATALOG.load_variant(variant_id)
	var positions := _load_route_positions()
	var scene := await _load_candidate_scene()
	if spec.is_empty() or positions.is_empty() or scene == null:
		quit(1)
		return
	await _capture_scene(scene, positions, spec)


func _load_candidate_scene() -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		printerr("FAIL: could not load %s" % SCENE_PATH)
		return null
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await process_frame
	if str(scene.get_meta("design_candidate_id", "")) != variant_id:
		printerr("FAIL: candidate scene did not activate %s" % variant_id)
		return null
	return scene


func _capture_scene(scene: Node3D, positions: Dictionary, spec: Dictionary) -> void:
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		printerr("FAIL: candidate scene has no Player")
		quit(1)
		return
	player.set_physics_process(false)
	var camera := Camera3D.new()
	camera.name = "DesignReviewCamera"
	camera.fov = FOV_DEGREES
	scene.add_child(camera)
	camera.current = true
	if not await _capture_plan(player, camera, positions):
		quit(1)
		return
	if not _write_metadata(spec):
		quit(1)
		return
	print("OK: wrote %d matched design-review views for %s" % [views.size(), variant_id])
	quit(0)


func _capture_plan(player: CharacterBody3D, camera: Camera3D, positions: Dictionary) -> bool:
	var directory := ProjectSettings.globalize_path(out_dir.path_join("spawn_headings"))
	if DirAccess.make_dir_recursive_absolute(directory) != OK:
		printerr("FAIL: could not create capture directory %s" % directory)
		return false
	for station: Dictionary in VIEW_PLAN:
		if not await _capture_station(player, camera, station, positions):
			return false
	return true


func _capture_station(player: CharacterBody3D, camera: Camera3D,
		station: Dictionary, positions: Dictionary) -> bool:
	var route_id: String = station.route_id
	if not positions.has(route_id):
		printerr("FAIL: route positions do not contain %s" % route_id)
		return false
	var eye: Vector3 = positions[route_id]
	var head := player.get_node_or_null("Head") as Node3D
	if head == null:
		printerr("FAIL: player has no Head node")
		return false
	player.global_position += eye - head.global_position
	player.velocity = Vector3.ZERO
	for heading in station.headings:
		camera.look_at_from_position(eye, eye + HEADINGS[heading], Vector3.UP)
		var filename := "spawn_%s_%s.png" % [station.station, heading]
		if not await _save_view(camera, filename):
			return false
		views.append({"filename": filename, "station": station.station,
			"route_id": route_id, "heading": heading, "eye": _coordinates(eye),
			"fov_degrees": camera.fov})
	return true


func _save_view(camera: Camera3D, filename: String) -> bool:
	for frame in range(settle_frames):
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image == null or image.is_empty() or image.get_size() != RESOLUTION:
		printerr("FAIL: expected a %s capture for %s" % [RESOLUTION, filename])
		return false
	var path := ProjectSettings.globalize_path(out_dir.path_join("spawn_headings").path_join(filename))
	var error := image.save_png(path)
	if error != OK:
		printerr("FAIL: could not save %s (error %d)" % [path, error])
		return false
	print("WROTE: %s" % path)
	return true


func _load_route_positions() -> Dictionary:
	var file := FileAccess.open(positions_path, FileAccess.READ)
	if file == null:
		printerr("FAIL: cannot open route positions %s" % positions_path)
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Array:
		printerr("FAIL: route positions must be a JSON array")
		return {}
	var positions := {}
	for entry: Variant in parsed:
		if not entry is Dictionary or not entry.get("eye", null) is Array:
			printerr("FAIL: malformed route position entry")
			return {}
		var eye: Array = entry.eye
		if eye.size() != 3 or not _numeric_triplet(eye):
			printerr("FAIL: route eye must contain three finite numbers")
			return {}
		positions[str(entry.get("id", ""))] = Vector3(float(eye[0]), float(eye[1]), float(eye[2]))
	return positions


func _numeric_triplet(values: Array) -> bool:
	for value in values:
		if typeof(value) != TYPE_FLOAT and typeof(value) != TYPE_INT:
			return false
		if not is_finite(float(value)):
			return false
	return true


func _set_settle(value: String) -> bool:
	if not value.is_valid_int():
		return false
	settle_frames = int(value)
	return settle_frames >= 0 and settle_frames <= 1000


func _write_metadata(spec: Dictionary) -> bool:
	var metadata := {"scene": SCENE_PATH, "variant": variant_id,
		"hypothesis": spec.hypothesis, "capture_path": "root.get_texture().get_image()",
		"resolution": [RESOLUTION.x, RESOLUTION.y], "fov_degrees": FOV_DEGREES,
		"settle_frames": settle_frames, "views": views}
	var path := ProjectSettings.globalize_path(out_dir.path_join("frames.json"))
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		printerr("FAIL: cannot write capture metadata %s" % path)
		return false
	file.store_string(JSON.stringify(metadata, "\t") + "\n")
	return true


func _coordinates(value: Vector3) -> Array:
	return [value.x, value.y, value.z]
