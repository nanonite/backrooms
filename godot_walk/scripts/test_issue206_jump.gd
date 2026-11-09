extends SceneTree

## Headless jump checks for #206. Drives scenes/player.tscn with walk_player.gd
## (as generative_map_assembly.gd applies it) on a tagged flat floor. Asserts
## jump and landing events, jump height, no double jump, no footsteps while
## airborne, sprint carry and unchanged walk/sprint stride counts. The Dummy
## audio driver produces no audible output; this test only observes events.

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const WALK_PLAYER := preload("res://scripts/walk_player.gd")
const BASE_SCRIPT := preload("res://scripts/player.gd")
const FLOOR_TOP := 0.0
const START_Y := 0.6
const START_X := 0.6
const JUMP_ACTION := &"jump"
const SPRINT_ACTION := &"sprint"
const FORWARD_ACTION := &"move_forward"
const FLOOR_TAG := "carpet"
const TAKEOFF_PLAYERS := 3
const HEIGHT_TOLERANCE_M := 0.08
const SPEED_TOLERANCE := 0.05
const STRIDE_TOLERANCE := 2
const JUMP_FRAMES := 240
const WALK_FRAMES := 150
const SPRINT_FRAMES := 75

var failures: Array[String] = []
var measured_height := 0.0
var measured_sprint_speed := 0.0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_jump_action()
	await _check_standing_jump()
	await _check_no_double_jump()
	await _check_sprint_jump()
	await _check_ground_stride_counts()
	for _frame in 10:
		await process_frame
	print("ISSUE206_JUMP: %s failures=%d height=%.3f sprint_speed=%.3f" % [
		"PASS" if failures.is_empty() else "FAIL", failures.size(),
		measured_height, measured_sprint_speed])
	for message in failures:
		printerr("FAIL: " + message)
	quit(0 if failures.is_empty() else 1)


func _check_jump_action() -> void:
	if not InputMap.has_action(JUMP_ACTION):
		_fail("InputMap has no 'jump' action")
		return
	var keys: Array[int] = []
	for event in InputMap.action_get_events(JUMP_ACTION):
		if event is InputEventKey:
			keys.append((event as InputEventKey).physical_keycode)
	if not keys.has(KEY_SPACE):
		_fail("'jump' is not bound to physical Space: %s" % [keys])
	if BASE_SCRIPT.SPEED != WALK_PLAYER.SPEED:
		_fail("walk player must keep the base SPEED")
	var gravity := float(ProjectSettings.get_setting("physics/3d/default_gravity", 9.8))
	var expected_velocity := sqrt(2.0 * gravity * WALK_PLAYER.JUMP_HEIGHT_M)
	if absf(WALK_PLAYER.JUMP_VELOCITY - expected_velocity) > 0.01:
		_fail("JUMP_VELOCITY %.3f does not match sqrt(2*g*h) = %.3f" % [
			WALK_PLAYER.JUMP_VELOCITY, expected_velocity])
	if WALK_PLAYER.JUMP_TAKEOFF_FORCE >= WALK_PLAYER.WALK_FORCE:
		_fail("take-off force must be below walk force")
	if WALK_PLAYER.JUMP_TAKEOFF_VOLUME_DB >= WALK_PLAYER.WALK_VOLUME_DB:
		_fail("take-off volume must be below walk volume")


func _check_standing_jump() -> void:
	var world := _make_world()
	var player := _spawn_player(world)
	await _settle(player)
	var start_y := player.global_position.y
	var child_count := player.get_child_count()
	var jumps: Array[String] = []
	var landings: Array[bool] = []
	var steps: Array[String] = []
	_connect_events(player, jumps, landings, steps)
	player.call("_play_takeoff", FLOOR_TAG)
	_expect(
		_playing_players(player) == TAKEOFF_PLAYERS,
		"take-off started %d players, expected %d" % [
			_playing_players(player), TAKEOFF_PLAYERS])
	_stop_players(player)
	await _tap_jump()
	var max_y := player.global_position.y
	var airborne := false
	for _frame in JUMP_FRAMES:
		await physics_frame
		max_y = maxf(max_y, player.global_position.y)
		if not player.is_on_floor():
			airborne = true
		elif airborne:
			break
	for _frame in 6:
		await physics_frame
	var height := max_y - start_y
	measured_height = height
	_expect(jumps == [FLOOR_TAG], "standing jump emitted %s, expected [%s]" % [jumps, FLOOR_TAG])
	_expect(landings.size() == 1, "standing jump emitted %d landings, expected 1" % landings.size())
	_expect(steps.is_empty(), "standing jump emitted %d footstep events" % steps.size())
	_expect(airborne, "standing jump never left the floor")
	_expect(
		absf(height - WALK_PLAYER.JUMP_HEIGHT_M) <= HEIGHT_TOLERANCE_M,
		"jump height %.3f m is outside %.3f +/- %.3f m" % [
			height, WALK_PLAYER.JUMP_HEIGHT_M, HEIGHT_TOLERANCE_M])
	_expect(player.get_child_count() == child_count, "jump allocated stream players")
	await _free_world(world)


func _check_no_double_jump() -> void:
	var world := _make_world()
	var player := _spawn_player(world)
	await _settle(player)
	var jumps: Array[String] = []
	var landings: Array[bool] = []
	var steps: Array[String] = []
	_connect_events(player, jumps, landings, steps)
	await _tap_jump()
	var airborne := false
	for _frame in 30:
		await physics_frame
		if not player.is_on_floor():
			airborne = true
			break
	_expect(airborne, "first jump did not leave the floor")
	await _tap_jump()
	for _frame in JUMP_FRAMES:
		await physics_frame
		if player.is_on_floor():
			break
	for _frame in 6:
		await physics_frame
	_expect(jumps.size() == 1, "airborne jump press emitted %d jump events, expected 1" % jumps.size())
	_expect(landings.size() == 1, "double-jump attempt emitted %d landings, expected 1" % landings.size())
	await _free_world(world)


func _check_sprint_jump() -> void:
	var world := _make_world()
	var player := _spawn_player(world)
	await _settle(player)
	var jumps: Array[String] = []
	var landings: Array[bool] = []
	var steps: Array[String] = []
	_connect_events(player, jumps, landings, steps)
	Input.action_press(SPRINT_ACTION)
	Input.action_press(FORWARD_ACTION)
	for _frame in 15:
		await physics_frame
	steps.clear()
	var start_y := player.global_position.y
	await _tap_jump()
	var max_y := player.global_position.y
	var seen_airborne := not player.is_on_floor()
	var airborne_steps := steps.size() if seen_airborne else 0
	steps.clear()
	var airborne_speed := 0.0
	for frame in JUMP_FRAMES:
		await physics_frame
		max_y = maxf(max_y, player.global_position.y)
		if not player.is_on_floor():
			seen_airborne = true
			airborne_steps += steps.size()
			steps.clear()
			if frame >= 5 and airborne_speed == 0.0:
				airborne_speed = Vector2(player.velocity.x, player.velocity.z).length()
		elif seen_airborne:
			break
	Input.action_release(FORWARD_ACTION)
	Input.action_release(SPRINT_ACTION)
	for _frame in 6:
		await physics_frame
	measured_sprint_speed = airborne_speed
	_expect(seen_airborne, "sprint jump never left the floor")
	_expect(jumps.size() == 1, "sprint jump emitted %d jump events, expected 1" % jumps.size())
	_expect(landings.size() == 1, "sprint jump emitted %d landings, expected 1" % landings.size())
	_expect(airborne_steps == 0, "sprint jump emitted %d footsteps while airborne" % airborne_steps)
	_expect(
		absf(airborne_speed - WALK_PLAYER.SPRINT_SPEED) <= SPEED_TOLERANCE,
		"airborne sprint speed %.3f, expected %.3f" % [airborne_speed, WALK_PLAYER.SPRINT_SPEED])
	_expect(max_y > start_y, "sprint jump did not gain height")
	await _free_world(world)


func _check_ground_stride_counts() -> void:
	var walk := await _count_steps(false)
	var sprint := await _count_steps(true)
	_expect(int(walk.events) > 0, "walking emitted no footsteps")
	_expect(int(sprint.events) > 0, "sprinting emitted no footsteps")
	var expected_walk := int(walk.distance / WALK_PLAYER.WALK_STRIDE_M)
	var expected_sprint := int(sprint.distance / WALK_PLAYER.SPRINT_STRIDE_M)
	_expect(
		absf(walk.events - expected_walk) <= STRIDE_TOLERANCE,
		"walk stride count %d is not near %d for %.2f m" % [
			walk.events, expected_walk, walk.distance])
	_expect(
		absf(sprint.events - expected_sprint) <= STRIDE_TOLERANCE,
		"sprint stride count %d is not near %d for %.2f m" % [
			sprint.events, expected_sprint, sprint.distance])


func _count_steps(sprint: bool) -> Dictionary:
	var world := _make_world()
	var player := _spawn_player(world)
	await _settle(player)
	var steps: Array[String] = []
	player.footstep_event.connect(func(tag: String, _sprinting: bool) -> void:
		steps.append(tag))
	if sprint:
		Input.action_press(SPRINT_ACTION)
	Input.action_press(FORWARD_ACTION)
	var start_x := player.global_position.x
	for _frame in (SPRINT_FRAMES if sprint else WALK_FRAMES):
		await physics_frame
	var distance := player.global_position.x - start_x
	Input.action_release(FORWARD_ACTION)
	Input.action_release(SPRINT_ACTION)
	for _frame in 6:
		await physics_frame
	await _free_world(world)
	return {"events": steps.size(), "distance": distance}


func _tap_jump() -> void:
	await physics_frame
	Input.action_press(JUMP_ACTION)
	await physics_frame
	Input.action_release(JUMP_ACTION)


func _settle(player: CharacterBody3D) -> void:
	for _frame in 10:
		await physics_frame
	_expect(player.is_on_floor(), "player did not settle on the floor")


func _connect_events(
	player: CharacterBody3D,
	jumps: Array[String],
	landings: Array[bool],
	steps: Array[String]
) -> void:
	player.jump_event.connect(func(tag: String) -> void: jumps.append(tag))
	player.landing_event.connect(func() -> void: landings.append(true))
	player.footstep_event.connect(func(tag: String, _sprinting: bool) -> void: steps.append(tag))


func _free_world(world: Node3D) -> void:
	for child: Node in world.find_children("*", "AudioStreamPlayer", true, false):
		(child as AudioStreamPlayer).stop()
	world.queue_free()
	for _frame in 3:
		await process_frame


func _playing_players(player: Node) -> int:
	var count := 0
	for child: Node in player.get_children():
		if child is AudioStreamPlayer and child.playing:
			count += 1
	return count


func _stop_players(player: Node) -> void:
	for child: Node in player.get_children():
		if child is AudioStreamPlayer:
			child.stop()


func _make_world() -> Node3D:
	var world := Node3D.new()
	root.add_child(world)
	var floor_body := StaticBody3D.new()
	floor_body.name = "Floor"
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40.0, 1.0, 20.0)
	shape.shape = box
	floor_body.add_child(shape)
	floor_body.position = Vector3(0.0, FLOOR_TOP - 0.5, 0.0)
	floor_body.set_meta("surface_acoustic", FLOOR_TAG)
	world.add_child(floor_body)
	return world


func _spawn_player(world: Node3D) -> CharacterBody3D:
	var player := PLAYER_SCENE.instantiate() as CharacterBody3D
	player.set_script(WALK_PLAYER)
	player.position = Vector3(START_X, START_Y, 0.0)
	player.rotation.y = -PI / 2.0
	world.add_child(player)
	return player


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
