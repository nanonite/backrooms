extends SceneTree

## M3 exit-threshold captures (#233). The output folder must exist.
## godot4 --path godot_walk --script res://scripts/capture_issue233_exit_threshold.gd -- \
##   --map=res://...json --rooms=res://.../index.json --out=<existing directory>

const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const SETTLE_FRAMES := 5

var scene: Node3D
var player: CharacterBody3D
var head: Node3D
var camera: Camera3D


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var out := GenerativeMapAssembly.argument("--out=")
	var absolute_out := ProjectSettings.globalize_path(out)
	if out.is_empty() or not DirAccess.dir_exists_absolute(absolute_out):
		push_error("Pass --out=<existing directory>")
		quit(2)
		return
	scene = load(WALK_SCENE).instantiate() as Node3D
	root.add_child(scene)
	await process_frame
	await process_frame
	player = scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		push_error("Walkthrough did not start")
		quit(2)
		return
	player.set_physics_process(false)
	player.set_process_unhandled_input(false)
	head = player.get_node("Head") as Node3D
	camera = head.get_node("Camera3D") as Camera3D
	var exit_cell := String(scene.exit_cell_id())
	var record: Dictionary = scene.exit_record_data()
	var spec: Dictionary = scene.specs.get(exit_cell, {})
	if exit_cell.is_empty() or spec.is_empty() or record.is_empty():
		push_error("The walkthrough has no static exit")
		quit(2)
		return
	var doorway := _doorway(spec, String(record.get("port_id", "")))
	if doorway.is_empty():
		push_error("The exit threshold doorway is missing")
		quit(2)
		return
	var point := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1])).normalized()
	var inside := -normal
	var floor_y := float(_cell_floor_y(exit_cell))
	var approach_floor_y := float(_cell_floor_y(String(record.get("from_cell", ""))))
	var rect := _largest_rect(spec)
	var center := Vector2((float(rect[0]) + float(rect[2])) / 2.0,
		(float(rect[1]) + float(rect[3])) / 2.0)
	var room_min_side := minf(float(rect[2]) - float(rect[0]), float(rect[3]) - float(rect[1]))
	var inside_distance := clampf(center.distance_to(point) + 0.4 * room_min_side, 1.5, 4.8)
	var manifest := {
		"map_id": String(scene.map.map_id),
		"seed": int(scene.map.seed),
		"exit_cell": exit_cell,
		"exit_port": String(record.get("port_id", "")),
		"threshold_id": String(record.get("threshold_id", "")),
		"from_cell": String(record.get("from_cell", "")),
		"views": [] as Array[String],
		"end_card": {},
	}

	_set_view(point + normal * 3.2, point - normal * 0.1, approach_floor_y, 0.02, 68.0)
	await _save(absolute_out, "exit_approach.png")
	manifest.views.append("exit_approach.png")

	_set_view(point + inside * inside_distance, point, floor_y, 0.30, 70.0)
	await _save(absolute_out, "exit_threshold_inside.png")
	manifest.views.append("exit_threshold_inside.png")

	_set_view(point + inside * maxf(1.0, inside_distance * 0.55), center, floor_y, 0.02, 78.0)
	await _save(absolute_out, "exit_room_wide.png")
	manifest.views.append("exit_room_wide.png")

	var exit_runtime: Node = scene.get_meta("maze_exit_runtime", null)
	if exit_runtime != null:
		var card: Dictionary = exit_runtime.force_end(String(record.get("from_cell", "")))
		manifest.end_card = card
		await _save(absolute_out, "run_end_card.png")
		manifest.views.append("run_end_card.png")
	else:
		push_error("The walkthrough has no exit runtime for the end-card capture")

	_write_manifest(absolute_out, manifest)
	print("ISSUE233_CAPTURE: exit=%s port=%s views=%s card_seed=%d rooms=%d edits=%d rerolls=%d" % [
		exit_cell, String(record.get("port_id", "")), str(manifest.views),
		int(manifest.end_card.get("seed", -1)), int(manifest.end_card.get("rooms_visited", -1)),
		int(manifest.end_card.get("edits", -1)), int(manifest.end_card.get("rerolls", -1))])
	quit(0)


func _doorway(spec: Dictionary, port_id: String) -> Dictionary:
	for doorway: Dictionary in spec.get("doorways", []):
		if String(doorway.get("port_id", "")) == port_id:
			return doorway
	return {}


func _cell_floor_y(cell_id: String) -> float:
	for cell: Dictionary in scene.map.cells:
		if String(cell.cell_id) == cell_id:
			return float(cell.get("floor_y", 0.0))
	return 0.0


func _largest_rect(spec: Dictionary) -> Array:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _rect_area(rect) > _rect_area(largest):
			largest = rect
	return largest


func _rect_area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _set_view(position: Vector2, target: Vector2, floor_y: float, pitch: float, fov: float) -> void:
	var direction := target - position
	if direction.length_squared() < 0.0001:
		direction = Vector2.RIGHT
	player.global_position = Vector3(position.x, floor_y + 0.6, position.y)
	player.rotation = Vector3(0.0, atan2(-direction.x, -direction.y), 0.0)
	head.rotation.x = pitch
	camera.fov = fov


func _save(out: String, filename: String) -> void:
	for _frame in SETTLE_FRAMES:
		await process_frame
	var path := out.path_join(filename)
	if FileAccess.file_exists(path):
		push_error("Refusing to overwrite capture %s" % filename)
		return
	var image := root.get_viewport().get_texture().get_image()
	var result := image.save_png(path)
	if result != OK:
		push_error("Failed to save %s: %s" % [filename, error_string(result)])


func _write_manifest(out: String, manifest: Dictionary) -> void:
	var path := out.path_join("manifest.json")
	if FileAccess.file_exists(path):
		push_error("Refusing to overwrite manifest %s" % path)
		return
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(manifest, "\t", true) + "\n")
