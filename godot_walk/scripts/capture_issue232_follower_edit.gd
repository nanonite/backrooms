extends SceneTree

## M2 follower lamp before/after captures (#232). The output folder must exist.
## godot4 --path godot_walk --script res://scripts/capture_issue232_follower_edit.gd -- \
##   --map=res://...json --rooms=res://.../index.json --out=<existing directory> \
##   [--cell=c04] [--lamp=0]

const VISIBILITY := preload("res://scripts/maze_visibility.gd")
const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const SETTLE_FRAMES := 5
const DEPTH := 2

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
	var target := String(GenerativeMapAssembly.argument("--cell="))
	var lamp_index := int(GenerativeMapAssembly.argument("--lamp=").to_int())
	if target.is_empty():
		target = _default_target()
	if target.is_empty() or not scene.specs.has(target):
		push_error("No generated room with a lamp is available for capture")
		quit(2)
		return
	var spec: Dictionary = scene.specs[target]
	if lamp_index < 0 or lamp_index >= spec.light.lamps.size():
		lamp_index = _first_on_lamp(target)
	if lamp_index < 0:
		lamp_index = 0
	var point := Vector2(float(spec.lamps_xz[lamp_index][0]), float(spec.lamps_xz[lamp_index][1]))
	var distance := 2.5
	var pitch := 0.75
	if not GenerativeMapAssembly.argument("--distance=").is_empty():
		distance = GenerativeMapAssembly.argument("--distance=").to_float()
	if not GenerativeMapAssembly.argument("--pitch=").is_empty():
		pitch = GenerativeMapAssembly.argument("--pitch=").to_float()
	var center := _center(spec)
	var offset := (center - point).normalized() * distance
	if offset.length_squared() < 0.0001:
		offset = Vector2(0.0, distance)
	_set_view(point + offset, point, pitch, 70.0)
	var before := String(scene.cell_light_state(target, lamp_index))
	await _save(absolute_out, "before_%s_%02d_%s.png" % [target, lamp_index, before])
	var manifest := {"map_id": String(scene.map.map_id), "cell_id": target,
		"lamp_index": lamp_index, "before": before, "captures": [] as Array[String]}
	var dead_capture := "after_%s_%02d_dead.png" % [target, lamp_index]
	scene.set_cell_light(target, lamp_index, "dead")
	await _save(absolute_out, dead_capture)
	manifest.captures.append(dead_capture)
	var on_capture := "after_%s_%02d_on.png" % [target, lamp_index]
	scene.set_cell_light(target, lamp_index, "on")
	await _save(absolute_out, on_capture)
	manifest.captures.append(on_capture)
	var flicker_capture := "after_%s_%02d_flicker.png" % [target, lamp_index]
	scene.set_cell_light(target, lamp_index, "flicker", 424242)
	for _frame in 4:
		await process_frame
	await _save(absolute_out, flicker_capture)
	manifest.captures.append(flicker_capture)
	scene.set_cell_light(target, lamp_index, before)
	manifest["after"] = "flicker"
	_write_manifest(absolute_out, manifest)
	print("ISSUE232_CAPTURE: target=%s lamp=%d before=%s captures=%s" % [
		target, lamp_index, before, str(manifest.captures)])
	quit(0)


func _default_target() -> String:
	var visited: Array[String] = []
	var order := _bfs_order(String(scene.origin_cell))
	for cell_id: String in order:
		visited.append(cell_id)
		if visited.size() < 5:
			continue
		for candidate: String in visited:
			if candidate == cell_id or not scene.specs.has(candidate):
				continue
			var spec: Dictionary = scene.specs[candidate]
			if (spec.has("landmark") and spec["landmark"] != null) or not spec.has("light"):
				continue
			if VISIBILITY.cell_is_hidden(scene.map, cell_id, candidate, DEPTH):
				return candidate
	for cell_id: String in scene.specs:
		var spec: Dictionary = scene.specs[cell_id]
		if not (spec.has("landmark") and spec["landmark"] != null) and spec.has("light") and not spec.light.lamps.is_empty():
			return cell_id
	return ""


func _bfs_order(start: String) -> Array[String]:
	var graph := {}
	for cell: Dictionary in scene.map.cells:
		if String(cell.role) != "void":
			graph[String(cell.cell_id)] = []
	for edge: Dictionary in scene.map.get("edges", []):
		if not ["direct", "closed_visible"].has(String(edge.get("connector", ""))):
			continue
		var left := String(edge.get("from", "")).get_slice(":", 0)
		var right := String(edge.get("to", "")).get_slice(":", 0)
		if left != right and graph.has(left) and graph.has(right):
			(graph[left] as Array).append(right)
			(graph[right] as Array).append(left)
	for cell_id: String in graph:
		(graph[cell_id] as Array).sort()
	var order: Array[String] = []
	if not graph.has(start):
		return order
	var seen := {start: true}
	var queue: Array[String] = [start]
	var head := 0
	while head < queue.size():
		var current := queue[head]
		head += 1
		order.append(current)
		for neighbor: String in graph[current]:
			if seen.has(neighbor):
				continue
			seen[neighbor] = true
			queue.append(neighbor)
	return order


func _first_on_lamp(cell_id: String) -> int:
	for entry: Dictionary in scene.cell_light_states(cell_id):
		if String(entry.state) == "on":
			return int(entry.lamp_index)
	return -1


func _center(spec: Dictionary) -> Vector2:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _rect_area(rect) > _rect_area(largest):
			largest = rect
	return Vector2((float(largest[0]) + float(largest[2])) / 2.0,
		(float(largest[1]) + float(largest[3])) / 2.0)


func _rect_area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _set_view(position: Vector2, target: Vector2, pitch: float, fov: float) -> void:
	var direction := target - position
	if direction.length_squared() < 0.0001:
		direction = Vector2.RIGHT
	player.global_position = Vector3(position.x, 0.6, position.y)
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
