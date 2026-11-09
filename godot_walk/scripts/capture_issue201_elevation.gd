extends SceneTree

## Render the gmap-0.10.0 elevation views (#201): down from a ledge, up at a
## ledge from below, along a ramp, and a double-height room. Run with the
## walkthrough's --map/--rooms arguments plus --out=<directory>.

const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const SETTLE_FRAMES := 5
const EYE_M := 1.6
const DROP_VIEW_M := 2.4
const RAMP_VIEW_M := 1.0


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
	var cells := _cells(scene.map)
	var drops := _edges(scene.map, "drop")
	var ramps := _edges(scene.map, "ramp")
	if drops.is_empty():
		push_error("This map has no drop for the ledge views")
		quit(2)
		return
	var drop: Dictionary = drops[0]
	var drop_upper := String(drop.drop.upper_cell_id)
	var drop_lower := String(drop.drop.lower_cell_id)
	var upper_floor := float(cells[drop_upper].get("floor_y", 0.0))
	var lower_floor := float(cells[drop_lower].get("floor_y", 0.0))
	var upper_port := _port_for(scene.map, drop, drop_upper)
	var lower_port := _port_for(scene.map, drop, drop_lower)
	var ledge := Vector2(float(upper_port.pos_xz[0]), float(upper_port.pos_xz[1]))
	var upper_normal := Vector2(float(upper_port.normal[0]), float(upper_port.normal[1]))
	var lower_normal := Vector2(float(lower_port.normal[0]), float(lower_port.normal[1]))
	var down_from := ledge - upper_normal * 1.1
	var below_at := ledge - lower_normal * DROP_VIEW_M
	await _capture(player, head, camera, absolute_out,
		"down_from_ledge_%s_%s.png" % [drop_upper, drop_lower],
		Vector3(down_from.x, upper_floor + EYE_M, down_from.y),
		Vector3(below_at.x, lower_floor + 0.35, below_at.y), 82.0)
	await _capture(player, head, camera, absolute_out,
		"up_at_ledge_from_below_%s_%s.png" % [drop_upper, drop_lower],
		Vector3(below_at.x, lower_floor + EYE_M, below_at.y),
		Vector3(ledge.x, upper_floor + 0.9, ledge.y), 82.0)
	var lower_rect := _rect(cells[drop_lower])
	var lower_center := lower_rect.get_center()
	await _capture(player, head, camera, absolute_out,
		"double_height_room_%s_%s.png" % [drop_upper, drop_lower],
		Vector3(lower_center.x, lower_floor + 1.0, lower_center.y),
		Vector3(ledge.x, upper_floor + 2.0, ledge.y), 90.0)
	if not ramps.is_empty():
		var ramp: Dictionary = ramps[0]
		var ramp_lower := String(ramp.ramp.lower_cell_id)
		var ramp_upper := String(ramp.ramp.upper_cell_id)
		var ramp_floor := float(cells[ramp_lower].get("floor_y", 0.0))
		var ramp_upper_floor := float(cells[ramp_upper].get("floor_y", 0.0))
		var ramp_port := _port_for(scene.map, ramp, ramp_lower)
		var start := Vector2(float(ramp_port.pos_xz[0]), float(ramp_port.pos_xz[1]))
		var normal := Vector2(float(ramp_port.normal[0]), float(ramp_port.normal[1]))
		var direction := -normal
		var run := float(ramp.ramp.run_m)
		var bottom := start + direction * (run + RAMP_VIEW_M)
		var top := start + direction * 0.2
		await _capture(player, head, camera, absolute_out,
			"along_ramp_%s_%s.png" % [ramp_lower, ramp_upper],
			Vector3(bottom.x, ramp_floor + EYE_M, bottom.y),
			Vector3(top.x, ramp_upper_floor + 0.45, top.y), 85.0)
	quit()


func _capture(player: CharacterBody3D, head: Node3D, camera: Camera3D, out: String,
		filename: String, eye: Vector3, target: Vector3, fov: float) -> void:
	var flat := Vector2(target.x - eye.x, target.z - eye.z)
	var yaw := atan2(-flat.x, -flat.y) if flat.length_squared() > 0.0001 else 0.0
	var pitch := atan2(target.y - eye.y, maxf(flat.length(), 0.001))
	player.global_position = eye
	player.rotation = Vector3(0.0, yaw, 0.0)
	head.rotation.x = pitch
	camera.fov = fov
	for _frame in SETTLE_FRAMES:
		await process_frame
	var image := root.get_viewport().get_texture().get_image()
	var result := image.save_png(out.path_join(filename))
	if result != OK:
		push_error("Failed to save %s: %s" % [filename, error_string(result)])
	else:
		print("elevation capture %s" % filename)


func _rect(cell: Dictionary) -> Rect2:
	var points: Array = cell.envelope_xz
	var minimum := Vector2(float(points[0][0]), float(points[0][1]))
	var maximum := minimum
	for point: Array in points:
		minimum.x = minf(minimum.x, float(point[0]))
		minimum.y = minf(minimum.y, float(point[1]))
		maximum.x = maxf(maximum.x, float(point[0]))
		maximum.y = maxf(maximum.y, float(point[1]))
	return Rect2(minimum, maximum - minimum)


func _cells(map_data: Dictionary) -> Dictionary:
	var result := {}
	for cell: Dictionary in map_data.cells:
		result[String(cell.cell_id)] = cell
	return result


func _edges(map_data: Dictionary, vertical: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for edge: Dictionary in map_data.edges:
		if String(edge.get("vertical", "")) == vertical:
			result.append(edge)
	return result


func _port_for(map_data: Dictionary, edge: Dictionary, cell_id: String) -> Dictionary:
	var port_id := ""
	if String(edge.from).get_slice(":", 0) == cell_id:
		port_id = String(edge.from)
	elif String(edge.to).get_slice(":", 0) == cell_id:
		port_id = String(edge.to)
	else:
		return {}
	for cell: Dictionary in map_data.cells:
		if String(cell.cell_id) != cell_id:
			continue
		for port: Dictionary in cell.required_ports:
			if String(port.port_id) == port_id:
				return port
	return {}
