extends SceneTree

## Palette captures for gmap-0.12.0 (#208): one generated room for each new
## palette in clean, worn and damaged variants. The room geometry and lights are
## the committed map's; only the palette variant is forced so all nine looks can
## be judged from one walkable scene.

const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const REGISTRY_PATH := "res://room_catalog/material_palettes/palettes-0.3.0.json"
const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const EYE_HEIGHT_M := 1.6
const SETTLE_FRAMES := 4
const NEW_PALETTES := ["tiled_institutional", "metal_service", "wood_parquet"]
const VARIANTS := ["clean", "worn", "damaged"]
const SURFACES := ["wall", "floor", "ceiling", "trim"]


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var out := GenerativeMapAssembly.argument("--out=")
	if out.is_empty():
		push_error("Pass --out=<directory>")
		quit(2)
		return
	var absolute_out := ProjectSettings.globalize_path(out)
	DirAccess.make_dir_recursive_absolute(absolute_out)
	var registry: Variant = GenerativeMapAssembly.load_json(REGISTRY_PATH)
	if not registry is Dictionary:
		push_error("Cannot read the 0.3.0 registry")
		quit(2)
		return
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
	for palette_id: String in NEW_PALETTES:
		var palette := _palette(registry, palette_id)
		var cell_id := _largest_room(scene.specs, palette_id)
		if cell_id.is_empty():
			push_error("Map has no %s room" % palette_id)
			continue
		var spec: Dictionary = scene.specs[cell_id]
		var room: Node3D = scene.rooms[cell_id]
		for wear in VARIANTS.size():
			var variant: String = VARIANTS[wear]
			_apply_materials(room, spec, _surface_materials(palette, variant, wear))
			await _capture(scene, player, head, camera, absolute_out,
				"palette_%s_%s_%s.png" % [palette_id, variant, cell_id], cell_id)
	quit()


func _palette(registry: Dictionary, palette_id: String) -> Dictionary:
	for palette: Dictionary in registry.palettes:
		if String(palette.palette_id) == palette_id:
			return palette
	return {}


func _largest_room(specs: Dictionary, palette_id: String) -> String:
	var best := ""
	var best_area := -1.0
	for cell_id: String in specs:
		var spec: Dictionary = specs[cell_id]
		if String(spec.materials.get("palette_id", "")) != palette_id:
			continue
		var area := float(spec.get("area_m2", 0.0))
		if area > best_area:
			best = cell_id
			best_area = area
	return best


func _surface_materials(palette: Dictionary, variant: String, wear: int) -> Dictionary:
	var materials := {
		"palette_id": String(palette.palette_id),
		"registry_version": "0.3.0",
		"wear": wear,
		"acoustic": {},
		"variants": {},
		"lamp_color": palette.lamp_color.color,
	}
	for surface: String in SURFACES:
		var field: Dictionary = palette.surfaces[surface]
		var chosen: String = variant if field.variants.has(variant) else "clean"
		var record: Dictionary = field.variants[chosen]
		materials.acoustic[surface] = field.acoustic
		materials.variants[surface] = chosen
		if surface == "trim":
			materials.trim_color = record.color
			continue
		var value := {}
		for key: String in record:
			if key != "provenance":
				value[key] = record[key]
		value["acoustic"] = field.acoustic
		value["variant"] = chosen
		materials[surface] = value
	return materials


func _apply_materials(room: Node3D, spec: Dictionary, source: Dictionary) -> void:
	var materials := MATERIALS.make({"materials": source, "light": spec.get("light")})
	var visuals := room.get_node("AuthoredVisuals") as Node3D
	var floors := visuals.get_node("WalkableFloorVisual") as Node3D
	for mesh_node in floors.get_children():
		if mesh_node is MeshInstance3D:
			mesh_node.material_override = _surface_material(materials, "floor", mesh_node)
	var ceilings := visuals.get_node("RenderedCeiling") as Node3D
	for mesh_node in ceilings.get_children():
		if mesh_node is MeshInstance3D:
			mesh_node.material_override = _surface_material(materials, "ceiling", mesh_node)
	for mesh_node in visuals.get_children():
		if not mesh_node is MeshInstance3D:
			continue
		var label := String(mesh_node.name)
		if label.begins_with("Wall_") or label.begins_with("Header_") or label.begins_with("WallSill_"):
			mesh_node.material_override = _surface_material(materials, "wallpaper", mesh_node)
		elif label.begins_with("Trim"):
			mesh_node.material_override = materials.trim
		elif label.begins_with("CeilingLight"):
			mesh_node.material_override = materials.lamp


static func _surface_material(materials: Dictionary, key: String, mesh_node: MeshInstance3D) -> Material:
	var box := mesh_node.mesh as BoxMesh
	if box == null:
		return MATERIALS.planar(materials, key)
	var size := box.size
	if key == "wallpaper":
		return MATERIALS.scaled(materials, key, maxf(size.x, size.z), size.y)
	return MATERIALS.scaled(materials, key, size.x, size.z)


func _capture(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D,
		out: String, filename: String, cell_id: String) -> void:
	var spec: Dictionary = scene.specs[cell_id]
	var cell := _cell(scene.map, cell_id)
	var rect := _largest_rect(spec)
	var x0 := float(rect[0]); var z0 := float(rect[1])
	var x1 := float(rect[2]); var z1 := float(rect[3])
	var inset := minf(0.9, minf(x1 - x0, z1 - z0) * 0.28)
	_set_view(player, head, camera, Vector2(x0 + inset, z0 + inset),
		Vector2(x1 - inset, z1 - inset), float(cell.get("floor_y", 0.0)))
	for _frame in SETTLE_FRAMES:
		await process_frame
	var image := root.get_viewport().get_texture().get_image()
	var result := image.save_png(out.path_join(filename))
	if result != OK:
		push_error("Failed to save %s: %s" % [filename, error_string(result)])
	else:
		print("palette capture %s" % filename)


func _cell(map_data: Dictionary, cell_id: String) -> Dictionary:
	for cell: Dictionary in map_data.cells:
		if String(cell.cell_id) == cell_id:
			return cell
	return {}


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
		position: Vector2, target: Vector2, floor_y: float) -> void:
	var direction := target - position
	if direction.length_squared() < 0.0001:
		direction = Vector2.RIGHT
	player.global_position = Vector3(position.x, floor_y + EYE_HEIGHT_M, position.y)
	player.rotation = Vector3(0.0, atan2(-direction.x, -direction.y), 0.0)
	head.rotation.x = -0.14
	camera.fov = 85.0
