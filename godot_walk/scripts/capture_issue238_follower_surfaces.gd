extends SceneTree

## M8 follower surface before/after captures (#238). The output folder must exist.
## godot4 --path godot_walk --script res://scripts/capture_issue238_follower_surfaces.gd -- \
##   --map=res://...json --rooms=res://.../index.json --out=<existing directory> \
##   [--cell=c01] [--surface=floor]

const SURFACE := preload("res://scripts/maze_surface_controller.gd")
const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const SETTLE_FRAMES := 5
const SURFACES := ["floor", "wall", "ceiling", "trim"]
const VARIANT_ORDER := ["clean", "worn", "damaged"]

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
	_disable_drivers()
	var surface := String(GenerativeMapAssembly.argument("--surface="))
	if surface.is_empty():
		surface = "floor"
	if not SURFACES.has(surface):
		push_error("Unknown surface %s" % surface)
		quit(2)
		return
	var target := String(GenerativeMapAssembly.argument("--cell="))
	if target.is_empty():
		target = _default_target(surface)
	if target.is_empty() or not scene.specs.has(target):
		push_error("No generated room with a %s surface is available" % surface)
		quit(2)
		return
	var variants: Dictionary = scene.cell_surface_variants(target)
	var before := String(variants.get(surface, ""))
	var position := VARIANT_ORDER.find(before)
	if position < 0 or position + 1 >= VARIANT_ORDER.size():
		push_error("%s.%s is already %s" % [target, surface, before])
		quit(2)
		return
	var after: String = VARIANT_ORDER[position + 1]
	var materials_before := _surface_materials(target, surface)
	_set_view(target, surface)
	var before_file := "before_%s_%s_%s.png" % [target, surface, before]
	await _save(absolute_out, before_file)
	var next_variants := variants.duplicate(true)
	next_variants[surface] = after
	if not scene.set_cell_surface_variants(target, next_variants):
		push_error("set_cell_surface_variants refused %s.%s" % [target, surface])
		quit(2)
		return
	var after_file := "after_%s_%s_%s.png" % [target, surface, after]
	await _save(absolute_out, after_file)
	var manifest := {
		"map_id": String(scene.map.map_id),
		"cell_id": target,
		"surface": surface,
		"before": before,
		"after": after,
		"wear": scene.cell_wear(target),
		"materials_before": materials_before,
		"materials_after": _surface_materials(target, surface),
		"captures": [before_file, after_file],
	}
	scene.set_cell_surface_variants(target, variants)
	_write_manifest(absolute_out, manifest)
	print("ISSUE238_CAPTURE: target=%s surface=%s before=%s after=%s captures=%s" % [
		target, surface, before, after, str(manifest.captures)])
	quit(0)


func _disable_drivers() -> void:
	for key: String in ["maze_follower_runtime", "maze_exit_runtime"]:
		var driver: Node = scene.get_meta(key, null)
		if driver != null:
			driver.enabled = false


func _default_target(surface: String) -> String:
	var exit_cell := String(scene.exit_cell_id())
	for cell: Dictionary in scene.map.cells:
		if cell.get("module") != null or cell.get("landmark") != null \
				or cell.get("surface_variants") == null:
			continue
		var cell_id := String(cell.cell_id)
		if cell_id == exit_cell or not scene.specs.has(cell_id):
			continue
		var variants: Dictionary = scene.cell_surface_variants(cell_id)
		var current := String(variants.get(surface, ""))
		if current == "clean" or current == "worn":
			return cell_id
	return ""


func _set_view(cell_id: String, surface: String) -> void:
	var spec: Dictionary = scene.specs[cell_id]
	var center := _center(spec)
	var cell: Dictionary = {}
	for entry: Dictionary in scene.map.cells:
		if String(entry.cell_id) == cell_id:
			cell = entry
			break
	var floor_y := float(cell.get("floor_y", 0.0))
	var pitch := -0.15
	if surface == "floor":
		pitch = -0.55
	elif surface == "ceiling":
		pitch = 0.6
	var offset := Vector2(0.0, -1.2)
	player.global_position = Vector3(center.x + offset.x, floor_y + 0.75, center.y + offset.y)
	player.rotation = Vector3(0.0, 0.0, 0.0)
	head.rotation.x = pitch
	camera.fov = 78.0


func _surface_materials(cell_id: String, surface: String) -> Dictionary:
	var room: Node3D = scene.room_node(cell_id)
	var result := {}
	for node: Node in room.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if SURFACE.surface_of(mesh) != surface:
			continue
		var material := mesh.material_override as StandardMaterial3D
		result[String(mesh.name)] = "" if material == null else String(material.get_meta("source_path", ""))
	return result


func _center(spec: Dictionary) -> Vector2:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _rect_area(rect) > _rect_area(largest):
			largest = rect
	return Vector2((float(largest[0]) + float(largest[2])) / 2.0,
		(float(largest[1]) + float(largest[3])) / 2.0)


func _rect_area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


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
