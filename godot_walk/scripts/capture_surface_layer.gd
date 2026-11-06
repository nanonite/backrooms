extends SceneTree

## Focused gmap-0.9.0 surface captures: one room per palette/wear pair present in
## the loaded map, plus a dark-wing wear-2 room when one exists.

const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const EYE_HEIGHT_M := 1.6
const SETTLE_FRAMES := 4


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var out := GenerativeMapAssembly.argument("--out=")
	var absolute_out := ProjectSettings.globalize_path(out)
	if out.is_empty():
		push_error("Pass --out=<directory>")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(absolute_out)
	var scene := load(WALK_SCENE).instantiate() as Node3D
	root.add_child(scene)
	await process_frame
	await process_frame
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		push_error("Walkthrough did not start")
		quit(2)
		return
	player.set_physics_process(false)
	player.set_process_unhandled_input(false)
	var head := player.get_node("Head") as Node3D
	var camera := head.get_node("Camera3D") as Camera3D
	var fixed_cell := GenerativeMapAssembly.argument("--cell=")
	if not fixed_cell.is_empty():
		if not scene.specs.has(fixed_cell):
			push_error("Map has no cell %s" % fixed_cell)
			quit(2)
			return
		await _capture(scene, player, head, camera, absolute_out,
			"matched_%s_%s.png" % [String(scene.map.map_id), fixed_cell], fixed_cell)
		quit()
		return
	var choices := {}
	for cell_id: String in scene.specs:
		var spec: Dictionary = scene.specs[cell_id]
		if not spec.materials.has("variants") or spec.has("landmark"):
			continue
		var palette := String(spec.materials.palette_id)
		var wear := int(spec.materials.wear)
		var key := "%s:%d" % [palette, wear]
		var rank := 2 if String(spec.light.tier) == "bright" else 1 if String(spec.light.tier) == "normal" else 0
		if not choices.has(key) or rank > int(choices[key].rank):
			choices[key] = {"cell_id": cell_id, "rank": rank}
	for key: String in choices:
		var cell_id := String(choices[key].cell_id)
		var parts := key.split(":")
		await _capture(scene, player, head, camera, absolute_out,
			"surface_%s_wear%s_%s.png" % [parts[0], parts[1], cell_id], cell_id)
	var wing: Array = scene.map.get("dark_wing", {}).get("cell_ids", [])
	for cell_id: String in wing:
		if not scene.specs.has(cell_id):
			continue
		var spec: Dictionary = scene.specs[cell_id]
		if int(spec.materials.get("wear", 0)) != 2:
			continue
		await _capture(scene, player, head, camera, absolute_out,
			"dark_wing_wear2_%s.png" % cell_id, cell_id)
		break
	quit()


func _capture(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D,
		out: String, filename: String, cell_id: String) -> void:
	var spec: Dictionary = scene.specs[cell_id]
	var rect := _largest_rect(spec)
	var x0 := float(rect[0]); var z0 := float(rect[1])
	var x1 := float(rect[2]); var z1 := float(rect[3])
	var inset := minf(0.9, minf(x1 - x0, z1 - z0) * 0.28)
	_set_view(player, head, camera, Vector2(x0 + inset, z0 + inset),
		Vector2(x1 - inset, z1 - inset))
	for _frame in SETTLE_FRAMES:
		await process_frame
	var image := root.get_viewport().get_texture().get_image()
	var result := image.save_png(out.path_join(filename))
	if result != OK:
		push_error("Failed to save %s: %s" % [filename, error_string(result)])
	else:
		print("surface capture %s" % filename)


func _largest_rect(spec: Dictionary) -> Array:
	if spec.has("landmark"):
		var x := float(spec.lamps_xz[0][0]); var z := float(spec.lamps_xz[0][1])
		return [x - 2.0, z - 2.0, x + 2.0, z + 2.0]
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		var area := (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))
		var largest_area := (float(largest[2]) - float(largest[0])) * (float(largest[3]) - float(largest[1]))
		if area > largest_area:
			largest = rect
	return largest


func _set_view(player: CharacterBody3D, head: Node3D, camera: Camera3D,
		position: Vector2, target: Vector2) -> void:
	var direction := target - position
	if direction.length_squared() < 0.0001:
		direction = Vector2.RIGHT
	player.global_position = Vector3(position.x, EYE_HEIGHT_M, position.y)
	player.rotation = Vector3(0.0, atan2(-direction.x, -direction.y), 0.0)
	head.rotation.x = -0.14
	camera.fov = 85.0
