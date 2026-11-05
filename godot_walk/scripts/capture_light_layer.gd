extends SceneTree

## Focused gmap-0.8.0 light captures. Output folder must already exist.

const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const FLICKER_SCRIPT := preload("res://scripts/shape_room_lamp_flicker.gd")
const FLOOR_CENTER_M := 0.6
const SETTLE_FRAMES := 4


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var out := GenerativeMapAssembly.argument("--out=")
	var absolute_out := ProjectSettings.globalize_path(out)
	if out.is_empty() or not DirAccess.dir_exists_absolute(absolute_out):
		push_error("Pass --out=<existing directory>")
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
	if OS.get_cmdline_user_args().has("--matched-only"):
		await _capture_matched(scene, player, head, camera, absolute_out)
	else:
		await _capture_normal(scene, player, head, camera, absolute_out)
		await _capture_flicker(scene, player, head, camera, absolute_out)
		await _capture_dark_wing(scene, player, head, camera, absolute_out)
		await _capture_library_joint(scene, player, head, camera, absolute_out)
	quit()


func _capture_normal(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D, out: String) -> void:
	for cell_id: String in scene.specs:
		var spec: Dictionary = scene.specs[cell_id]
		if spec.light.tier != "normal" or spec.has("landmark"):
			continue
		var center := _center(spec)
		_set_view(player, head, camera, center, center + Vector2.RIGHT, 0.0, 85.0)
		await _save(camera, out, "normal_%s.png" % cell_id)
		return
	print("No normal generated room found")


func _capture_flicker(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D, out: String) -> void:
	for cell_id: String in scene.specs:
		var spec: Dictionary = scene.specs[cell_id]
		for index in spec.light.lamps.size():
			var lamp: Dictionary = spec.light.lamps[index]
			if lamp.state != "flicker":
				continue
			var point := Vector2(float(spec.lamps_xz[index][0]), float(spec.lamps_xz[index][1]))
			var position := point + Vector2(0.0, 2.5)
			_set_view(player, head, camera, position, point, 0.4, 70.0)
			var light := scene.rooms[cell_id].find_child("OmniLamp_%02d" % index, true, false) as OmniLight3D
			if light == null or light.get_script() != FLICKER_SCRIPT:
				push_error("Map flicker state lacks its seeded OmniLight at %s[%d]" % [cell_id, index])
				return
			await _save(camera, out, "flicker_%s_%02d_a.png" % [cell_id, index])
			var first_energy: float = light.light_energy
			var changed := false
			for _attempt in 40:
				await create_timer(0.025).timeout
				if not is_equal_approx(first_energy, light.light_energy):
					changed = true
					break
			for _frame in SETTLE_FRAMES:
				await process_frame
			var second_energy: float = light.light_energy
			await _save(camera, out, "flicker_%s_%02d_b.png" % [cell_id, index])
			print("flicker %s[%d] energy=%.4f->%.4f changed=%s" % [cell_id, index, first_energy, second_energy, changed])
			return
	print("No flickering generated lamp found")


func _capture_dark_wing(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D, out: String) -> void:
	var wing: Array = scene.map.get("dark_wing", {}).get("cell_ids", [])
	if wing.is_empty():
		print("Map has no selected dark wing")
		return
	var cell_id := String(wing[0])
	var center := _center(scene.specs[cell_id])
	_set_view(player, head, camera, center, center + Vector2.RIGHT, 0.0, 90.0)
	await _save(camera, out, "dark_wing_%s.png" % cell_id)


func _capture_library_joint(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D, out: String) -> void:
	for cell_id: String in scene.specs:
		var spec: Dictionary = scene.specs[cell_id]
		for doorway: Dictionary in spec.doorways:
			if not scene.module_rooms.has(String(doorway.to_cell_id)):
				continue
			var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
			var point := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
			_set_view(player, head, camera, point - normal * 2.0, point + normal * 2.0, 0.0, 85.0)
			await _save(camera, out, "library_joint_%s.png" % cell_id)
			return
	print("Map has no generated-to-library joint")


func _capture_matched(scene: Node3D, player: CharacterBody3D, head: Node3D, camera: Camera3D, out: String) -> void:
	for cell_id: String in scene.specs:
		var spec: Dictionary = scene.specs[cell_id]
		if not spec.has("landmark"):
			continue
		var center := Vector2(float(spec.lamps_xz[0][0]), float(spec.lamps_xz[0][1]))
		var forward := Vector2.RIGHT
		if not spec.doorways.is_empty():
			forward = Vector2(float(spec.doorways[0].normal[0]), float(spec.doorways[0].normal[1]))
		_set_view(player, head, camera, center, center + forward, 0.0, 100.0)
		await _save(camera, out, "matched_%s.png" % String(scene.map.map_id))
		return
	push_error("No landmark room is available for matched capture")


func _center(spec: Dictionary) -> Vector2:
	if spec.has("landmark"):
		return Vector2(float(spec.lamps_xz[0][0]), float(spec.lamps_xz[0][1]))
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1])) > (float(largest[2]) - float(largest[0])) * (float(largest[3]) - float(largest[1])):
			largest = rect
	return Vector2((float(largest[0]) + float(largest[2])) / 2.0, (float(largest[1]) + float(largest[3])) / 2.0)


func _set_view(player: CharacterBody3D, head: Node3D, camera: Camera3D, position: Vector2,
		target: Vector2, pitch: float, fov: float) -> void:
	var direction := target - position
	if direction.length_squared() < 0.0001:
		direction = Vector2.RIGHT
	player.global_position = Vector3(position.x, FLOOR_CENTER_M, position.y)
	player.rotation = Vector3(0.0, atan2(-direction.x, -direction.y), 0.0)
	head.rotation.x = pitch
	camera.fov = fov


func _save(camera: Camera3D, out: String, filename: String) -> void:
	for _frame in SETTLE_FRAMES:
		await process_frame
	_save_now(out, filename)


func _save_now(out: String, filename: String) -> void:
	var path := out.path_join(filename)
	if FileAccess.file_exists(path):
		push_error("Refusing to overwrite capture %s" % filename)
		return
	var image := root.get_viewport().get_texture().get_image()
	var result := image.save_png(path)
	if result != OK:
		push_error("Failed to save %s: %s" % [filename, error_string(result)])
