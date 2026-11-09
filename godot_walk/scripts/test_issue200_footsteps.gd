extends SceneTree

## Headless footstep event checks for #200. Asserts emitted tags and strides, not
## audible output (the dummy audio driver produces none).

const PLAYER_SCENE := preload("res://scenes/player.tscn")
const WALK_PLAYER := preload("res://scripts/walk_player.gd")
const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const FLOOR_TOP := 0.0
const START_Y := 0.6
const WALK_STRIDE := 0.7
const SPRINT_STRIDE := 1.0
const SPRINT_ACTION := &"sprint"

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	await _check_footstep_path()
	await _check_assembly_floor_tags()
	print("ISSUE200_FOOTSTEPS: %s failures=%d" % [
		"PASS" if failures.is_empty() else "FAIL", failures.size()])
	quit(0 if failures.is_empty() else 1)


func _check_footstep_path() -> void:
	var world := Node3D.new()
	root.add_child(world)
	_add_floor(world, 0.0, 7.0, "carpet", false)
	_add_floor(world, 7.0, 14.0, "concrete", false)
	_add_floor(world, 14.0, 21.0, "debris", true)
	_add_floor(world, 21.0, 28.0, "", false)

	var player := PLAYER_SCENE.instantiate() as CharacterBody3D
	player.set_script(WALK_PLAYER)
	player.position = Vector3(0.6, START_Y, 0.0)
	player.rotation.y = -PI / 2.0
	world.add_child(player)
	for _frame in 6:
		await physics_frame
	_check_layered_players(player)
	var child_count := player.get_child_count()

	var steps: Array[String] = []
	var sprint_steps: Array[bool] = []
	var landings: Array[bool] = []
	player.footstep_event.connect(func(tag: String, sprinting: bool) -> void:
		steps.append(tag)
		sprint_steps.append(sprinting))
	player.landing_event.connect(func() -> void:
		landings.append(true))

	for _frame in 30:
		await physics_frame
	_expect(steps.is_empty(), "standing still emitted a footstep")

	Input.action_press("move_forward")
	var start_x := player.global_position.x
	for _frame in 900:
		await physics_frame
		if player.global_position.x >= 27.0:
			break
	Input.action_release("move_forward")
	var distance := player.global_position.x - start_x
	for _frame in 20:
		await physics_frame

	_expect(not steps.is_empty(), "walking emitted no footsteps")
	var tags := steps.duplicate()
	var wanted := ["carpet", "concrete", "debris", "default"]
	var previous := -1
	for tag: String in wanted:
		var index := tags.find(tag)
		if index < 0:
			_fail("walking path did not emit %s" % tag)
		else:
			_expect(index > previous, "walking tag order is not carpet -> concrete -> debris -> default")
			previous = index
	var expected_steps := int(distance / WALK_STRIDE)
	_expect(abs(steps.size() - expected_steps) <= 2, "walk stride count %d is not near %d for %.2f m" % [steps.size(), expected_steps, distance])
	_expect(sprint_steps.all(func(value: bool) -> bool: return not value), "walking steps were marked as sprinting")

	# Sprint over a fixed distance: fewer, louder steps than walking.
	player.global_position = Vector3(0.6, START_Y, 0.0)
	player.velocity = Vector3.ZERO
	player.set("_distance_since_step", 0.0)
	for _frame in 6:
		await physics_frame
	steps.clear()
	sprint_steps.clear()
	Input.action_press(SPRINT_ACTION)
	Input.action_press("move_forward")
	for _frame in 240:
		await physics_frame
		if player.global_position.x >= 7.6:
			break
	Input.action_release("move_forward")
	Input.action_release(SPRINT_ACTION)
	for _frame in 10:
		await physics_frame
	_expect(not steps.is_empty(), "sprinting emitted no footsteps")
	_expect(steps.size() < int(7.0 / WALK_STRIDE), "sprint stride did not produce fewer steps than walking")
	_expect(steps.size() <= int(7.0 / SPRINT_STRIDE) + 2, "sprint stride count is too high")
	_expect(sprint_steps.all(func(value: bool) -> bool: return value), "sprint steps were not marked as sprinting")

	# Landing after more than 0.3 s in the air: exactly one landing event.
	player.global_position = Vector3(5.0, 3.0, 0.0)
	player.velocity = Vector3.ZERO
	var steps_before_landing := steps.size()
	var landings_before := landings.size()
	for _frame in 180:
		await physics_frame
		if player.is_on_floor():
			break
	for _frame in 6:
		await physics_frame
	_expect(steps.size() == steps_before_landing, "airborne motion emitted footsteps")
	_expect(landings.size() == landings_before + 1, "expected exactly one landing event, got %d" % (landings.size() - landings_before))
	_expect(player.get_child_count() == child_count, "footsteps allocated stream players during playback")

	world.free()


func _check_layered_players(player: Node) -> void:
	var pools: Dictionary = player.get("_pools")
	_expect(pools.size() == WALK_PLAYER.LAYERS.size(), "expected %d layer pools, got %d" % [WALK_PLAYER.LAYERS.size(), pools.size()])
	for layer: String in WALK_PLAYER.LAYERS:
		_expect(pools.has(layer), "missing player pool for %s" % layer)
		if pools.has(layer):
			_expect(pools[layer].size() == WALK_PLAYER.POOL_PER_LAYER, "%s pool has %d players, expected %d" % [layer, pools[layer].size(), WALK_PLAYER.POOL_PER_LAYER])
	var streams: Dictionary = player.get("_layer_streams")
	for tag: String in WALK_PLAYER.ACOUSTIC_TAGS + [WALK_PLAYER.DEFAULT_TAG]:
		for layer: String in WALK_PLAYER.LAYERS:
			var key := "%s/%s" % [tag, layer]
			_expect(streams.has(key), "missing streams for %s" % key)
			if streams.has(key):
				_expect(streams[key].size() == WALK_PLAYER.VARIANT_COUNT, "%s has %d variants" % [key, streams[key].size()])
	for layer: String in WALK_PLAYER.LAYERS:
		var key := "%s/%s" % [WALK_PLAYER.LAND_TAG, layer]
		_expect(streams.has(key), "missing landing streams for %s" % key)
		if streams.has(key):
			_expect(streams[key].size() == 1, "landing %s should have one variant" % layer)
	var audio_players := 0
	for child: Node in player.get_children():
		if child is AudioStreamPlayer:
			audio_players += 1
	_expect(audio_players == WALK_PLAYER.LAYERS.size() * WALK_PLAYER.POOL_PER_LAYER, "expected %d pooled players, got %d" % [WALK_PLAYER.LAYERS.size() * WALK_PLAYER.POOL_PER_LAYER, audio_players])
	_expect(is_equal_approx(float(player.call("_impact_force", WALK_PLAYER.SPEED)), WALK_PLAYER.WALK_FORCE), "walk speed did not map to walk force")
	_expect(is_equal_approx(float(player.call("_impact_force", WALK_PLAYER.SPRINT_SPEED)), WALK_PLAYER.SPRINT_FORCE), "sprint speed did not map to sprint force")
	player.call("_play_step", false)
	var playing := 0
	for child: Node in player.get_children():
		if child is AudioStreamPlayer and child.playing:
			playing += 1
	_expect(playing == 3, "one step started %d players, expected 3" % playing)
	for child: Node in player.get_children():
		if child is AudioStreamPlayer:
			child.stop()


func _add_floor(world: Node3D, from_x: float, to_x: float, tag: String, library_floor: bool) -> void:
	var body := StaticBody3D.new()
	body.position = Vector3((from_x + to_x) / 2.0, FLOOR_TOP - 0.05, 0.0)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(to_x - from_x, 0.1, 4.0)
	shape.shape = box
	body.add_child(shape)
	if not tag.is_empty():
		body.set_meta("surface_acoustic", tag)
	if library_floor:
		body.set_meta("surface_acoustic_source", "module_acoustics.json")
		body.set_meta("surface_acoustic_module", "video_ccf9722164a0bdc8_debris_window_rock_room_v1@1")
	world.add_child(body)


func _check_assembly_floor_tags() -> void:
	var map_path := ASSEMBLY.argument("--map=")
	var rooms_path := ASSEMBLY.argument("--rooms=")
	if map_path.is_empty() or rooms_path.is_empty():
		_fail("assembly check needs --map= and --rooms=")
		return
	var map_data: Variant = ASSEMBLY.load_json(map_path)
	var specs := ASSEMBLY.load_specs(rooms_path)
	if not map_data is Dictionary or specs.is_empty():
		_fail("assembly check could not load the map or rooms")
		return
	var table: Variant = ASSEMBLY.load_json("res://room_catalog/module_acoustics.json")
	if not table is Dictionary:
		_fail("assembly check could not load module_acoustics.json")
		return
	var assembly := ASSEMBLY.new()
	assembly.auto_start = false
	root.add_child(assembly)
	assembly.assemble(map_data, specs)
	await process_frame
	var checked := 0
	for cell_id: String in assembly.module_rooms:
		var info: Dictionary = assembly.module_info[cell_id]
		var entry: Dictionary = info.entry
		var key := "%s@%d" % [entry.module_id, int(entry.version)]
		var expected := String(table.modules.get(key, {}).get("acoustic", ""))
		var names: PackedStringArray = assembly.module_rooms[cell_id].get_meta(
			"walk_floor_bodies", PackedStringArray(["WalkableFloor"]))
		for body_name: String in names:
			for node: Node in assembly.module_rooms[cell_id].find_children(body_name, "StaticBody3D", true, false):
				var actual := String(node.get_meta("surface_acoustic", ""))
				_expect(actual == expected, "%s/%s: library floor tag %s != %s" % [cell_id, body_name, actual, expected])
				checked += 1
	_expect(checked > 0, "assembly check found no library floor colliders")
	assembly.free()


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_fail(message)


func _fail(message: String) -> void:
	failures.append(message)
	push_error(message)
