extends SceneTree

## M4 door-leaf captures (#234). The output folder must exist.
## godot4 --path godot_walk --script res://scripts/capture_issue234_doors.gd -- \
##   --map=res://...json --rooms=res://.../index.json --out=<existing directory>

const MAZE_DOORS := preload("res://scripts/maze_doors.gd")
const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const SETTLE_FRAMES := 5
const EYE_HEIGHT_M := 0.6
const VIEW_DISTANCE_M := 2.4

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
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	if doors == null:
		push_error("The walkthrough has no door runtime")
		quit(2)
		return
	doors.set_physics_process(false)
	var plan: Dictionary = doors.plan
	var eligible: Array = plan.get("eligible_crossings", [])
	var manifest := {
		"map_id": String(scene.map.map_id),
		"seed": int(scene.map.seed),
		"threshold_id": "",
		"from_cell": "",
		"to_cell": "",
		"leaf_side": "",
		"vertical": "",
		"state_closed": "",
		"state_open": "",
		"views": [] as Array[String],
		"eligible": eligible.size(),
	}
	if eligible.is_empty():
		manifest["note"] = "no lock-behind-eligible crossing on this seed"
		_set_view(Vector2.ZERO, Vector2.RIGHT, 0.0, 0.0, 70.0)
		_write_manifest(absolute_out, manifest)
		print("ISSUE234_CAPTURE: map=%s eligible=0 views=0" % scene.map.map_id)
		quit(0)
		return
	var crossing: Dictionary = eligible[0]
	var threshold := String(crossing.threshold_id)
	var from_cell := String(crossing.from_cell)
	var to_cell := String(crossing.to_cell)
	var door := MAZE_DOORS.door_by_threshold(plan, threshold)
	var doorway := _doorway(String(door.leaf_side), String(door.leaf_port))
	if doorway.is_empty():
		push_error("The eligible door has no doorway record")
		quit(2)
		return
	var point := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1])).normalized()
	# The doorway normal points from the leaf's cell_a side into cell_b. Put the
	# camera on the player's current side so the view is the one the player has.
	var view_sign := 1.0 if to_cell == String(door.cell_b) else -1.0
	var view_normal := normal * view_sign
	var floor_y := _cell_floor_y(to_cell)
	manifest.threshold_id = threshold
	manifest.from_cell = from_cell
	manifest.to_cell = to_cell
	manifest.leaf_side = String(door.leaf_side)
	manifest.vertical = String(door.vertical)

	_expect_clear(absolute_out)
	_set_view(point + view_normal * VIEW_DISTANCE_M, point, floor_y, 0.02, 70.0)
	await process_frame
	if not doors.force_latch(threshold, from_cell, to_cell):
		manifest["note"] = "no runtime-latchable door on this seed"
		_write_manifest(absolute_out, manifest)
		print("ISSUE234_CAPTURE: map=%s eligible=%d views=0 note=no_latchable" % [
			scene.map.map_id, eligible.size()])
		quit(0)
		return
	manifest.state_closed = doors.state_of(threshold)
	await _save(absolute_out, "door_closed_from_target.png")
	manifest.views.append("door_closed_from_target.png")
	manifest["ray_closed"] = _ray_hits_leaf(door)
	_set_view(point + view_normal * 1.25, point, floor_y, 0.0, 72.0)
	await _save(absolute_out, "door_latched_detail.png")
	manifest.views.append("door_latched_detail.png")
	if not doors.open_door(threshold, to_cell):
		push_error("The capture could not open %s" % threshold)
		quit(2)
		return
	manifest.state_open = doors.state_of(threshold)
	_set_view(point + view_normal * VIEW_DISTANCE_M, point, floor_y, 0.02, 70.0)
	await _save(absolute_out, "door_open_from_target.png")
	manifest.views.append("door_open_from_target.png")
	manifest["ray_open"] = _ray_hits_leaf(door)
	_write_manifest(absolute_out, manifest)
	print("ISSUE234_CAPTURE: map=%s door=%s %s->%s closed=%s open=%s views=%s" % [
		scene.map.map_id, threshold, from_cell, to_cell,
		manifest.state_closed, manifest.state_open, str(manifest.views)])
	quit(0)


func _doorway(cell_id: String, port_id: String) -> Dictionary:
	var spec: Dictionary = scene.specs.get(cell_id, {})
	for item: Dictionary in spec.get("doorways", []):
		if String(item.get("port_id", "")) == port_id:
			return item
	return {}


func _cell_floor_y(cell_id: String) -> float:
	for cell: Dictionary in scene.map.cells:
		if String(cell.cell_id) == cell_id:
			return float(cell.get("floor_y", 0.0))
	return 0.0


func _ray_hits_leaf(door: Dictionary) -> bool:
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	if doors == null:
		return false
	var leaf: Node3D = doors.leaf_node(String(door.threshold_id))
	if leaf == null:
		return false
	var doorway := _doorway(String(door.leaf_side), String(door.leaf_port))
	if doorway.is_empty():
		return false
	var position := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1])).normalized()
	var y := _cell_floor_y(String(door.leaf_side)) \
		+ float(doorway.get("sill_height_m", 0.0)) \
		+ float(doorway.get("height_m", 2.1)) / 2.0
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(position.x + normal.x * 0.8, y, position.y + normal.y * 0.8),
		Vector3(position.x - normal.x * 0.8, y, position.y - normal.y * 0.8))
	query.collision_mask = 1
	query.collide_with_bodies = true
	query.collide_with_areas = false
	query.exclude = [player.get_rid()]
	var hit := scene.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return false
	return hit.collider == leaf.get_node_or_null("LeafBody")


func _set_view(position: Vector2, target: Vector2, floor_y: float, pitch: float,
		fov: float) -> void:
	var direction := target - position
	if direction.length_squared() < 0.0001:
		direction = Vector2.RIGHT
	player.global_position = Vector3(position.x, floor_y + EYE_HEIGHT_M, position.y)
	player.rotation = Vector3(0.0, atan2(-direction.x, -direction.y), 0.0)
	head.rotation.x = pitch
	camera.fov = fov


func _expect_clear(out: String) -> void:
	for name: String in [
		"door_closed_from_target.png", "door_latched_detail.png", "door_open_from_target.png",
	]:
		if FileAccess.file_exists(out.path_join(name)):
			push_error("Refusing to overwrite capture %s" % name)


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
