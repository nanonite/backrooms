extends SceneTree

## Headless room-acoustics checks for #205. The Dummy audio driver produces no
## audible output; these checks observe ray metrics, the pure mapping, bus
## parameter easing and room-flag routing only.

const PROBE := preload("res://scripts/room_acoustic_probe.gd")
const REVERB := preload("res://scripts/room_reverb_bus.gd")
const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const WALK_PLAYER := preload("res://scripts/walk_player.gd")
const SCENE_PATH := "res://scenes/generative_map_walkthrough.tscn"
const FLOOR_TOP := 0.0
const PLAYER_HALF_HEIGHT := 0.6
const BOX_CEILING_M := 3.0
const PROBE_FRAMES := 30

var failures: Array[String] = []
var box_mean := 0.0
var corridor_mean := 0.0
var wet_after_crossfade := 0.0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_check_mapping()
	await _check_probe_geometry()
	await _check_bus_crossfade()
	await _check_player_routing()
	await _check_assembly_runtime()
	await _check_feature_toggle()
	for _frame in 10:
		await process_frame
	print("ISSUE205_ACOUSTICS: %s failures=%d box_mean=%.3f corridor_mean=%.3f wet=%.3f" % [
		"PASS" if failures.is_empty() else "FAIL", failures.size(),
		box_mean, corridor_mean, wet_after_crossfade])
	for message in failures:
		printerr("FAIL: " + message)
	quit(0 if failures.is_empty() else 1)


func _check_mapping() -> void:
	var previous_size := -1.0
	var previous_predelay := -1.0
	for index in range(1, 11):
		var mapped: Dictionary = PROBE.map_metrics({
			"mean_distance_m": float(index),
			"max_distance_m": float(index) * 1.4,
			"ceiling_height_m": 2.2 + float(index) * 0.3,
			"openness": 0.0,
		})
		_expect(mapped.room_size > previous_size,
			"room_size did not grow at mean %.1f m" % float(index))
		_expect(mapped.predelay_msec > previous_predelay,
			"predelay did not grow at mean %.1f m" % float(index))
		_expect(mapped.room_size >= 0.0 and mapped.room_size <= 1.0, "room_size out of range")
		_expect(mapped.damping >= 0.0 and mapped.damping <= 1.0, "damping out of range")
		_expect(mapped.wet >= 0.0 and mapped.wet <= 0.75, "wet out of range")
		previous_size = mapped.room_size
		previous_predelay = mapped.predelay_msec
	var small: Dictionary = PROBE.map_metrics({
		"mean_distance_m": 1.5, "max_distance_m": 2.0,
		"ceiling_height_m": 2.3, "openness": 0.0})
	var large: Dictionary = PROBE.map_metrics({
		"mean_distance_m": 7.0, "max_distance_m": 10.0,
		"ceiling_height_m": 4.5, "openness": 0.0})
	_expect(large.room_size > small.room_size, "large room did not map to a larger room_size")
	_expect(large.predelay_msec > small.predelay_msec, "large room did not map to a longer pre-delay")
	_expect(large.damping >= small.damping, "large room did not map to more damping")
	_expect(large.wet >= small.wet, "large room did not map to at least as much wet")
	_expect(is_equal_approx(float(large.predelay_msec), 7.0 / 343.0 * 1000.0),
		"pre-delay is not mean distance / speed of sound")
	var clamped: Dictionary = PROBE.map_metrics({
		"mean_distance_m": 100.0, "max_distance_m": 100.0,
		"ceiling_height_m": 100.0, "openness": 0.0})
	_expect(is_equal_approx(float(clamped.predelay_msec), PROBE.MAX_PREDELAY_MSEC),
		"pre-delay did not clamp at the maximum")


func _check_probe_geometry() -> void:
	var box_world := _make_world()
	_add_box_room(box_world)
	await _settle_physics()
	var box_probe = PROBE.new()
	var box_parameters: Dictionary = box_probe.sample(
		box_world.get_world_3d().direct_space_state,
		Vector3(0.0, 1.1, 0.0), FLOOR_TOP, [] as Array[RID])
	var box_metrics: Dictionary = box_probe.metrics
	box_mean = float(box_metrics.mean_distance_m)
	_expect(is_zero_approx(float(box_metrics.openness)), "closed box reports open rays")
	_expect(absf(float(box_metrics.ceiling_height_m) - BOX_CEILING_M) <= 0.05,
		"box ceiling %.3f m, expected %.3f m" % [box_metrics.ceiling_height_m, BOX_CEILING_M])
	_expect(box_mean > 1.5 and box_mean < 2.6,
		"box mean wall distance %.3f m is outside the expected band" % box_mean)
	_expect(float(box_metrics.max_distance_m) > box_mean,
		"box max wall distance is not above the mean")
	_expect(box_parameters.has("room_size") and box_parameters.has("wet"),
		"probe did not produce mapped parameters")
	_expect(PROBE.COLLISION_MASK == 1, "probe does not use the floor ray's collision layer")
	box_probe.free()
	await _free_world(box_world)

	var corridor_world := _make_world()
	_add_corridor(corridor_world)
	await _settle_physics()
	var corridor_probe = PROBE.new()
	var corridor_parameters: Dictionary = corridor_probe.sample(
		corridor_world.get_world_3d().direct_space_state,
		Vector3(0.0, 1.1, 0.0), FLOOR_TOP, [] as Array[RID])
	var corridor_metrics: Dictionary = corridor_probe.metrics
	corridor_mean = float(corridor_metrics.mean_distance_m)
	_expect(float(corridor_metrics.openness) > 0.1,
		"open-ended corridor openness %.3f, expected misses" % corridor_metrics.openness)
	_expect(corridor_mean > box_mean,
		"corridor mean %.3f m is not above box mean %.3f m" % [corridor_mean, box_mean])
	_expect(absf(float(corridor_metrics.ceiling_height_m) - BOX_CEILING_M) <= 0.05,
		"corridor ceiling %.3f m, expected %.3f m" % [
			corridor_metrics.ceiling_height_m, BOX_CEILING_M])
	_expect(float(corridor_parameters.room_size) > float(box_parameters.room_size),
		"corridor did not map to a larger room than the box")
	corridor_probe.free()
	await _free_world(corridor_world)


func _check_bus_crossfade() -> void:
	ProjectSettings.set_setting(REVERB.FEATURE_SETTING, true)
	var bus = REVERB.new()
	_expect(bus.ensure_bus(), "could not create the Footsteps reverb bus")
	if not bus.active:
		return
	_expect(_reverb_effect_count(bus.bus_index) == 1,
		"Footsteps bus does not carry exactly one reverb effect")
	var mapped := {"room_size": 0.7, "damping": 0.6, "wet": 0.55, "predelay_msec": 24.0}
	bus.set_targets(mapped, true)
	_expect(is_equal_approx(float(bus.target_wet), 0.55), "wet-room target is not the mapped wet")
	bus.update(1.0 / 60.0)
	_expect(bus.wet > 0.0 and bus.wet < 0.55, "wet level jumped instead of easing")
	_expect(bus.room_size < 0.7, "room_size jumped instead of easing")
	for _frame in 120:
		bus.update(1.0 / 60.0)
	wet_after_crossfade = bus.wet
	_expect(is_equal_approx(bus.wet, 0.55), "wet level did not reach the wet-room target")
	_expect(is_equal_approx(bus.effect.wet, bus.wet), "bus effect wet does not match the controller")
	bus.set_targets(mapped, false)
	_expect(is_zero_approx(float(bus.target_wet)), "dry room target is not zero")
	bus.update(1.0 / 60.0)
	_expect(bus.wet > 0.0 and bus.wet < 0.55, "wet level jumped when entering a dry room")
	for _frame in 120:
		bus.update(1.0 / 60.0)
	_expect(is_zero_approx(bus.wet), "wet level did not reach zero in a dry room")
	_expect(is_zero_approx(bus.effect.wet), "bus effect did not reach zero in a dry room")
	_expect(is_equal_approx(bus.effect.dry, 1.0), "dry signal is not passed through")


func _check_player_routing() -> void:
	ProjectSettings.set_setting(REVERB.FEATURE_SETTING, true)
	var world := _make_world()
	_add_floor(world)
	var player := PLAYER_SCENE.instantiate() as CharacterBody3D
	player.set_script(WALK_PLAYER)
	player.position = Vector3(0.0, FLOOR_TOP + PLAYER_HALF_HEIGHT, 0.0)
	world.add_child(player)
	for _frame in PROBE_FRAMES:
		await physics_frame
	var pools: Dictionary = player.get("_pools")
	for layer: String in WALK_PLAYER.LAYERS:
		for pooled: AudioStreamPlayer in pools[layer]:
			_expect(pooled.bus == REVERB.BUS_NAME,
				"%s footstep player is on bus %s, expected %s" % [
					layer, pooled.bus, REVERB.BUS_NAME])
	var reverb = player.get("_room_reverb")
	_expect(reverb != null and reverb.active, "player has no active Footsteps reverb bus")
	var probe = player.get("_acoustic_probe")
	_expect(probe != null, "player has no acoustic probe")
	if probe != null:
		_expect(probe.metrics.has("mean_distance_m"), "probe did not sample the world")
	_expect(player.get("_room_wet") == false, "player outside an assembled map is not dry")
	if reverb != null:
		_expect(is_zero_approx(float(reverb.target_wet)),
			"player outside an assembled map targets non-zero wet")
	await _free_world(world)


func _check_assembly_runtime() -> void:
	var map_path := ASSEMBLY.argument("--map=")
	var rooms_path := ASSEMBLY.argument("--rooms=")
	if map_path.is_empty() or rooms_path.is_empty():
		_fail("assembly check needs --map= and --rooms=")
		return
	var packed := load(SCENE_PATH) as PackedScene
	_expect(packed != null, "walkthrough scene did not load")
	if packed == null:
		return
	var scene := packed.instantiate() as Node3D
	root.add_child(scene)
	for _frame in 40:
		await physics_frame
	_expect(scene.get_meta("walkthrough_ready", false), "walkthrough scene is not ready")
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, "walkthrough player is missing")
	if player == null:
		await _free_world(scene)
		return
	_expect(not bool(scene.call("room_reverb_at", player.global_position)),
		"spawn room is wet at runtime")
	_expect(player.get("_room_wet") == false, "player started wet in the dry spawn")
	_expect(float(scene.call("room_ceiling_height_at", player.global_position)) > 0.0,
		"spawn room has no authored ceiling fallback")
	var spawn_probe = player.get("_acoustic_probe")
	if spawn_probe != null:
		_expect(float(spawn_probe.metrics.ceiling_height_m) < 10.0,
			"probe ceiling %.3f m did not use the authored fallback" % spawn_probe.metrics.ceiling_height_m)
	var target := _wet_room_target(scene)
	_expect(not target.is_empty(), "map has no wet shape room with a simple interior point")
	if target.is_empty():
		await _free_world(scene)
		return
	var target_position: Vector3 = target.position
	_expect(String(scene.call("cell_at", target_position)) == String(target.cell_id),
		"wet-room target %s is not inside cell %s" % [target_position, target.cell_id])
	player.global_position = target_position
	player.velocity = Vector3.ZERO
	for _frame in 180:
		await physics_frame
	_expect(bool(scene.call("room_reverb_at", player.global_position)),
		"player teleported into a wet room but the runtime flag reads dry")
	_expect(bool(player.get("_room_wet")), "player did not follow the wet room flag")
	var reverb = player.get("_room_reverb")
	_expect(reverb != null, "walkthrough player has no reverb bus")
	if reverb != null:
		_expect(float(reverb.target_wet) > 0.05, "wet room target is too quiet")
		_expect(absf(float(reverb.wet) - float(reverb.target_wet)) <= 0.002,
			"wet crossfade did not reach the wet-room target")
	# Runtime #209 direction: flip the metadata, not the map or geometry.
	var cell_id := String(target.cell_id)
	_expect(bool(scene.call("set_room_reverb", cell_id, false)), "set_room_reverb refused the wet room")
	for _frame in 120:
		await physics_frame
	_expect(player.get("_room_wet") == false, "player did not follow the runtime dry flip")
	if reverb != null:
		_expect(is_zero_approx(float(reverb.target_wet)), "runtime dry flip did not zero the target")
		_expect(is_zero_approx(float(reverb.wet)), "runtime dry flip did not crossfade to zero")
	# Missing metadata must read as dry.
	scene.call("set_room_reverb", cell_id, true)
	var room := scene.call("room_node", cell_id) as Node3D
	_expect(room != null and room.has_meta("reverb_enabled"), "wet room lost its metadata")
	if room != null:
		room.remove_meta("reverb_enabled")
		_expect(not bool(scene.call("room_reverb_at", player.global_position)),
			"missing reverb_enabled metadata did not read as dry")
		for _frame in 40:
			await physics_frame
		_expect(player.get("_room_wet") == false,
			"player did not follow a missing flag to dry")
		room.set_meta("reverb_enabled", true)
	await _free_world(scene)


func _check_feature_toggle() -> void:
	ProjectSettings.set_setting(REVERB.FEATURE_SETTING, false)
	_expect(not REVERB.feature_enabled(), "project toggle off is still enabled")
	var disabled = REVERB.new()
	_expect(not disabled.ensure_bus(), "bus was created while the feature toggle was off")
	_expect(not disabled.active, "disabled feature reports an active bus")
	ProjectSettings.set_setting(REVERB.FEATURE_SETTING, true)
	_expect(REVERB.feature_enabled(), "project toggle default is not on")
	for _frame in 2:
		await physics_frame
	var world := _make_world()
	_add_floor(world)
	ProjectSettings.set_setting(REVERB.FEATURE_SETTING, false)
	var player := PLAYER_SCENE.instantiate() as CharacterBody3D
	player.set_script(WALK_PLAYER)
	player.position = Vector3(0.0, FLOOR_TOP + PLAYER_HALF_HEIGHT, 0.0)
	world.add_child(player)
	for _frame in 10:
		await physics_frame
	_expect(player.get("_room_reverb") == null, "disabled feature still created a reverb bus")
	var pools: Dictionary = player.get("_pools")
	for layer: String in WALK_PLAYER.LAYERS:
		for pooled: AudioStreamPlayer in pools[layer]:
			_expect(pooled.bus == "Master", "disabled feature rerouted %s to %s" % [layer, pooled.bus])
	ProjectSettings.set_setting(REVERB.FEATURE_SETTING, true)
	await _free_world(world)


func _wet_room_target(assembly: Node) -> Dictionary:
	var map: Dictionary = assembly.get("map")
	var specs: Dictionary = assembly.get("specs")
	for cell: Dictionary in map.get("cells", []):
		if String(cell.role) == "void" or not bool(cell.get("reverb", false)):
			continue
		var spec: Dictionary = specs.get(String(cell.cell_id), {})
		var rects: Array = spec.get("rects", [])
		for rect: Array in rects:
			var center := Vector2(
				(float(rect[0]) + float(rect[2])) / 2.0,
				(float(rect[1]) + float(rect[3])) / 2.0)
			return {"cell_id": String(cell.cell_id),
				"position": Vector3(center.x, float(spec.get("floor_y", 0.0)) + PLAYER_HALF_HEIGHT, center.y)}
	return {}


func _add_box_room(world: Node3D) -> void:
	_add_floor(world)
	_add_solid(world, Vector3(0.0, BOX_CEILING_M + 0.05, 0.0), Vector3(5.4, 0.1, 3.4))
	_add_solid(world, Vector3(-2.6, 1.5, 0.0), Vector3(0.2, 3.1, 3.4))
	_add_solid(world, Vector3(2.6, 1.5, 0.0), Vector3(0.2, 3.1, 3.4))
	_add_solid(world, Vector3(0.0, 1.5, -1.6), Vector3(5.4, 3.1, 0.2))
	_add_solid(world, Vector3(0.0, 1.5, 1.6), Vector3(5.4, 3.1, 0.2))


func _add_corridor(world: Node3D) -> void:
	_add_solid(world, Vector3(0.0, -0.05, 0.0), Vector3(20.4, 0.1, 2.4))
	_add_solid(world, Vector3(0.0, BOX_CEILING_M + 0.05, 0.0), Vector3(20.4, 0.1, 2.4))
	_add_solid(world, Vector3(0.0, 1.5, -1.1), Vector3(20.4, 3.1, 0.2))
	_add_solid(world, Vector3(0.0, 1.5, 1.1), Vector3(20.4, 3.1, 0.2))


func _add_floor(world: Node3D) -> void:
	_add_solid(world, Vector3(0.0, FLOOR_TOP - 0.05, 0.0), Vector3(40.0, 0.1, 40.0))


func _add_solid(world: Node3D, position: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.position = position
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	world.add_child(body)


func _make_world() -> Node3D:
	var world := Node3D.new()
	root.add_child(world)
	return world


func _settle_physics() -> void:
	for _frame in 4:
		await physics_frame


func _free_world(world: Node3D) -> void:
	root.remove_child(world)
	world.free()
	for _frame in 2:
		await physics_frame


func _reverb_effect_count(bus_index: int) -> int:
	var count := 0
	for index in AudioServer.get_bus_effect_count(bus_index):
		if AudioServer.get_bus_effect(bus_index, index) is AudioEffectReverb:
			count += 1
	return count


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)


func _fail(message: String) -> void:
	failures.append(message)
