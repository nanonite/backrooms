extends SceneTree

## Headless check for the sprint action (#191).
## godot4 --headless --path godot_walk --script res://scripts/test_issue191_sprint.gd
## Drives scenes/player.tscn with the walk_player.gd script (as generative_map_assembly.gd applies it) on a flat floor with move_forward held, with and
## without 'sprint', and asserts the distance ratio (SPRINT_SPEED / SPEED) and that
## a 0.2 m wall is not tunnelled through at sprint speed.

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PLAYER_SCRIPT := preload("res://scripts/walk_player.gd")
const BASE_SCRIPT := preload("res://scripts/player.gd")
const RUN_TICKS := 60
const WALL_RUN_TICKS := 120
const WALL_THICKNESS := 0.2
const RATIO_TOLERANCE := 0.05

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var speed: float = PLAYER_SCRIPT.SPEED
	var sprint_speed: float = PLAYER_SCRIPT.SPRINT_SPEED
	var expected_ratio := sprint_speed / speed

	if BASE_SCRIPT.SPEED != speed:
		_fail("walk player must keep the base SPEED")
	if InputMap.has_action("sprint"):
		_fail("'sprint' must not be in the project input map before the walk player registers it")
	# The walk player registers the action at runtime in _ready().
	await _run_flat(false)
	if not InputMap.has_action("sprint"):
		_fail("InputMap has no 'sprint' action")
	else:
		var keys: Array[int] = []
		var locations: Array[int] = []
		for event in InputMap.action_get_events("sprint"):
			if event is InputEventKey:
				keys.append((event as InputEventKey).physical_keycode)
				locations.append((event as InputEventKey).location)
		locations.sort()
		if locations != [KEY_LOCATION_LEFT as int, KEY_LOCATION_RIGHT as int]:
			_fail("sprint must cover left and right Shift: %s" % [locations])
		if keys.is_empty() or keys.any(func(k: int) -> bool: return k != KEY_SHIFT):
			_fail("sprint is not bound to physical Shift: %s" % [keys])

	var assembly := FileAccess.get_file_as_string("res://scripts/generative_map_assembly.gd")
	if not assembly.contains("player.set_script(WALK_PLAYER)"):
		_fail("generative_map_assembly.gd does not apply walk_player.gd")
	var scene_player := PLAYER_SCENE.instantiate()
	if scene_player.get_script() != BASE_SCRIPT:
		_fail("scenes/player.tscn must keep the unmodified base player script")
	scene_player.free()

	var walk := await _run_flat(false)
	var sprint := await _run_flat(true)
	var ratio: float = sprint / walk if walk > 0.0 else 0.0
	if absf(ratio - expected_ratio) > expected_ratio * RATIO_TOLERANCE:
		_fail("distance ratio %.3f, expected %.3f" % [ratio, expected_ratio])
	if absf(walk - speed * RUN_TICKS / 60.0) > 0.2:
		_fail("walk distance %.3f far from %.3f" % [walk, speed * RUN_TICKS / 60.0])

	var wall_sprint := await _run_wall(true)
	var wall_walk := await _run_wall(false)
	for r: Dictionary in [wall_sprint, wall_walk]:
		if not r.stopped:
			_fail("tunnelled wall (sprint=%s): z=%.3f wall_far_face=%.3f" % [r.sprint, r.z, r.wall_far_z])

	print("ISSUE191_SPRINT: %s walk=%.3f sprint=%.3f ratio=%.3f expected=%.3f wall_sprint_z=%.3f wall_walk_z=%.3f wall_far_z=%.3f" % [
		"PASS" if failures.is_empty() else "FAIL", walk, sprint, ratio, expected_ratio,
		wall_sprint.z, wall_walk.z, wall_sprint.wall_far_z])
	for f in failures:
		printerr("FAIL: " + f)
	quit(0 if failures.is_empty() else 1)


func _fail(msg: String) -> void:
	failures.append(msg)


func _make_world() -> Node3D:
	var world := Node3D.new()
	root.add_child(world)
	var floor_body := StaticBody3D.new()
	var floor_shape := CollisionShape3D.new()
	var floor_box := BoxShape3D.new()
	floor_box.size = Vector3(40.0, 1.0, 200.0)
	floor_shape.shape = floor_box
	floor_body.add_child(floor_shape)
	floor_body.position = Vector3(0.0, -0.5, -80.0)
	world.add_child(floor_body)
	return world


func _spawn_player(world: Node3D) -> CharacterBody3D:
	var player := PLAYER_SCENE.instantiate() as CharacterBody3D
	player.set_script(PLAYER_SCRIPT)
	player.position = Vector3(0.0, 0.7, 0.0)  # capsule half height 0.6 + margin above floor
	world.add_child(player)
	return player


func _hold(sprint: bool) -> void:
	Input.action_press("move_forward")
	if sprint:
		Input.action_press("sprint")
	else:
		Input.action_release("sprint")


func _release() -> void:
	Input.action_release("move_forward")
	Input.action_release("sprint")


func _run_flat(sprint: bool) -> float:
	var world := _make_world()
	var player := _spawn_player(world)
	for i in 10:  # settle onto the floor
		await physics_frame
	var start_z := player.global_position.z
	_hold(sprint)
	for i in RUN_TICKS:
		await physics_frame
	var distance := start_z - player.global_position.z
	_release()
	world.queue_free()
	await process_frame
	return distance


func _run_wall(sprint: bool) -> Dictionary:
	var world := _make_world()
	var wall := StaticBody3D.new()
	var wall_shape := CollisionShape3D.new()
	var wall_box := BoxShape3D.new()
	wall_box.size = Vector3(10.0, 3.0, WALL_THICKNESS)
	wall_shape.shape = wall_box
	wall.add_child(wall_shape)
	var wall_z := -6.0
	wall.position = Vector3(0.0, 1.5, wall_z)
	world.add_child(wall)
	var player := _spawn_player(world)
	for i in 10:
		await physics_frame
	_hold(sprint)
	for i in WALL_RUN_TICKS:
		await physics_frame
	var z := player.global_position.z
	_release()
	world.queue_free()
	await process_frame
	var far_z := wall_z - WALL_THICKNESS * 0.5
	# Stopped means the capsule centre stays on the near side of the wall's near face.
	return {"sprint": sprint, "z": z, "wall_far_z": far_z, "stopped": z > wall_z + WALL_THICKNESS * 0.5}
