extends SceneTree

## Headless regression for #247: E opens a latched door from anywhere in the arrival cell.
## godot4 --headless --path godot_walk --script res://scripts/test_issue247_door_key.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map_id>/index.json
## Maps where no door latches (seeds 1, 2, 3, 279) print SKIP: that is the Q13 eligible-only
## rule, not a failure.

const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const EYE_HEIGHT_M := 0.6


func _initialize() -> void:
	call_deferred("_run")


func _center(spec: Dictionary) -> Vector2:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _area(rect) > _area(largest):
			largest = rect
	return Vector2((float(largest[0]) + float(largest[2])) / 2.0,
		(float(largest[1]) + float(largest[3])) / 2.0)


func _area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _move(scene: Node3D, player: CharacterBody3D, cell_id: String) -> void:
	var spec: Dictionary = scene.specs.get(cell_id, {})
	var center := _center(spec)
	player.global_position = Vector3(center.x,
		float(spec.get("floor_y", 0.0)) + EYE_HEIGHT_M, center.y)
	await physics_frame
	await physics_frame


## Inject a real E key press and release through the input system.
func _key_e() -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = KEY_E
		event.physical_keycode = KEY_E
		event.pressed = pressed
		Input.parse_input_event(event)
		Input.flush_buffered_events()
		await process_frame


func _run() -> void:
	var failures: Array[String] = []
	var packed := load(SCENE_PATH) as PackedScene
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	await physics_frame
	await physics_frame
	var doors: Node = scene.get_meta("maze_door_runtime", null)
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	if doors == null or player == null:
		printerr("ISSUE247_DOOR_KEY: FAIL missing door runtime or player")
		quit(1)
		return
	var latched_any := false
	for crossing: Dictionary in doors.plan.eligible_crossings:
		var threshold := String(crossing.threshold_id)
		await _move(scene, player, String(crossing.from_cell))
		await _move(scene, player, String(crossing.to_cell))
		for _i in 3:
			await physics_frame
		if doors.state_of(threshold) != "latched":
			continue
		latched_any = true
		var leaf: Node3D = doors.leaf_node(threshold)
		var distance := player.global_position.distance_to(leaf.global_position)
		await _key_e()
		if doors.state_of(threshold) != "open":
			failures.append("E at %.2f m from the leaf did not open %s" % [distance, threshold])
		print("ISSUE247_DOOR_KEY: %s from %.2f m -> %s" % [threshold, distance, doors.state_of(threshold)])
		await _key_e()
		if doors.state_of(threshold) != "open":
			failures.append("a second E changed the opened door %s" % threshold)
		break
	if not latched_any:
		print("ISSUE247_DOOR_KEY: SKIP no door latches on this map")
		quit(0)
		return
	print("ISSUE247_DOOR_KEY: %s" % ("PASS" if failures.is_empty() else "FAIL " + "; ".join(failures)))
	quit(0 if failures.is_empty() else 1)
