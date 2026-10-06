extends SceneTree

## Headless proof that the player can walk the room #84's generated collision
## describes, driven by the production controller in `scripts/player.gd`.
##
## What this does that an import check or a node count cannot: it presses the
## real input actions, lets real physics ticks run, and reports where the real
## capsule ends up. Every assertion is about observed motion or an observed
## physics query, so a scene whose collision node exists but holds no shape fails
## here rather than passing.
##
## The battery runs against five scenes: the corridor as authored, and four
## deliberately broken ones. A battery that cannot fail on the broken ones proves
## nothing about the good one, so the negatives are part of the test. Each has to
## fail *for its own stated reason*, which is what stops "something went wrong"
## from standing in for the specific defect being demonstrated.
##
## Every tolerance comes from `traversal_manifest.json`, written by
## `scripts/splat_pipeline/traversal_plan.py`. None is restated here: a verifier
## carrying its own copy of a tolerance is a second source of truth that drifts,
## and a drifted stop tolerance quietly turns "was stopped by the wall" into
## "ended up somewhere plausible".
##
## Headless physics only. It cannot show that the splat renders, that the visual
## and the collision agree, or that the frame rate holds; #74 owns real-GPU visual
## evidence and #91 the end-to-end gate. Nothing here should be read as either.

const PLAN_PATH := "res://assets/corridor_splat/traversal_manifest.json"
const LOG_PATH := "res://assets/corridor_splat/traversal_run.log"
const SCENE_PATH := "res://scenes/corridor.tscn"

## Optional override so the same battery can be run on the #100 presentation
## scene, which renders a filtered splat but carries byte-identical collision,
## SafetyNet and spawn. The default is unchanged, so the accepted #85 run is
## unaffected; passing `--scene=res://scenes/corridor_psx.tscn` is how the
## visual-cleanup change proves it did not move the world under the player.
const SCENE_ARG_PREFIX := "--scene="
var _scene_path := SCENE_PATH

## Where this run's log is written. The accepted scene keeps the committed
## `traversal_run.log`; an overridden scene writes a sibling file so a
## presentation-scene run can never overwrite #85's evidence.
var _log_path := LOG_PATH

## Loaded by path rather than by `class_name`: the global class cache is only
## rebuilt when the editor scans the project, so a CI run of this script would
## otherwise fail to resolve the name on a fresh checkout.
const TRAVERSAL_PLAN := preload("res://scripts/traversal_plan.gd")

## Ticks allowed to settle after a spawn or a mutation before anything is
## judged. 60 is a second of simulated time: ample for the 0.37 m spawn drop and
## for a body to come to rest after being displaced.
const SETTLE_TICKS := 60

## Ticks a blocked probe may spend pushing into an obstacle before it is
## declared not-stopped. A probe that arrives already against the face would
## otherwise pass on no motion at all, which is why the plan also records a
## minimum displacement.
const PROBE_PUSH_TICKS := 150

## Slack on "no progress this tick", for deciding a walker has come to rest
## against something. 0.004 m is a tenth of a tick's travel: below the
## controller's own resolution, so it cannot be tripped by float noise.
const REST_DELTA := 0.004

## Ticks a walker may make no progress before the leg is abandoned as stuck.
const STUCK_TICKS := 90

## The wrong scale to multiply the collision by in the `wrong_transform` case:
## #83's `metres_per_unit`.  Applying it is exactly the defect that made #84's
## recorded node transform put the floor metres away from the room.
const WRONG_SCALE := 5.1283836

## How far the net is raised in the `safety_net_landing` case, in metres above
## the generated floor.  Positive, so the box overlaps the capsule's lower
## hemisphere: a net left just below the floor would never be touched by a player
## who is standing on the floor, which is exactly the case the negative is meant
## to detect.
const NET_INTRUSION_M := 0.10

var _plan = null
var _lines: Array[String] = []
var _failed := false

## Tolerances, read once from the plan. Every one has a fallback so a malformed
## manifest produces a loud wrong number rather than a silent zero.
var _position_m := 0.18
var _max_step_m := 0.20
var _block_stop_m := 0.12
var _floor_support_min := 0.95
var _floor_surface_m := 0.05
var _max_spawn_drop_m := 1.0
var _speed_mps := 4.0


func _initialize() -> void:
	_scene_path = _scene_argument()
	_log_path = _log_path_for(_scene_path)
	_plan = TRAVERSAL_PLAN.new(PLAN_PATH)
	if not _plan.is_valid():
		printerr("FAIL: %s" % _plan.load_error())
		quit(1)
		return
	_load_tolerances()
	_report_settings()
	var as_built: Array = await _run_case("as_built", "the corridor as authored", "")
	_failed = as_built.size() > 0
	for failure in as_built:
		_emit("  FAIL as_built: %s" % String(failure))
	for entry: Array in _negative_cases():
		await _run_negative(entry)
	print("")
	if _failed:
		_emit("FAIL: traversal verification failed")
		_finish(false)
		quit(1)
		return
	_emit("OK: traversal verified -- route both directions, blocking, openings, corners, "
		+ "clearance, spawn and safety net all hold")
	_finish(true)
	quit(0)


func _negative_cases() -> Array:
	## Broken scenes the battery has to reject, each with the reason it must cite.
	return [
		["missing_collision", "the collision mesh is removed entirely", "GeneratedCollision"],
		["wrong_transform", "the collision node is scaled by metres_per_unit", "floor"],
		["blocked_opening", "a box is dropped across the opening the route threads", "did not reach"],
		["safety_net_landing", "the net is raised into the player's capsule", "SafetyNet"],
	]


func _run_negative(entry: Array) -> void:
	## Run one deliberately broken scene and require the stated reason.
	var label: String = entry[0]
	var description: String = entry[1]
	var reason: String = entry[2]
	var failures: Array = await _run_case(label, description, description)
	if failures.is_empty():
		_failed = true
		_emit("  FAIL [negative %s]: the battery passed on a deliberately broken scene" % label)
		return
	if not _mentions(failures, reason):
		_failed = true
		_emit("  FAIL [negative %s]: rejected, but not for '%s'; the reasons were %s"
			% [label, reason, str(failures)])
		return
	_emit("  OK   [negative %s] rejected for '%s', and for these too:" % [label, reason])
	for failure in failures:
		_emit("         - %s" % String(failure))


func _load_tolerances() -> void:
	_position_m = _plan.tolerance("position_m", _position_m)
	_max_step_m = _plan.tolerance("max_step_m", _max_step_m)
	_block_stop_m = _plan.tolerance("block_stop_m", _block_stop_m)
	_floor_support_min = _plan.tolerance("min_floor_support_fraction", _floor_support_min)
	_floor_surface_m = _plan.tolerance("floor_surface_m", _floor_surface_m)
	_max_spawn_drop_m = _plan.tolerance("max_spawn_drop_m", _max_spawn_drop_m)
	_speed_mps = _plan.player_speed()


func _report_settings() -> void:
	## Print the settings, tolerances and the benchmark verdict every assertion
	## below is measured against, so a reviewer never has to reconstruct them.
	_emit("scene: %s" % _scene_path)
	_emit("traversal plan: %s" % PLAN_PATH)
	_emit("  collision %s" % _plan.collision_glb_path())
	_emit("    %d triangles, md5 %s" % [_plan.collision_triangles(), _plan.collision_md5()])
	_emit("  player capsule radius %.2f m height %.2f m, controller speed %.1f m/s"
		% [_plan.capsule_radius(), _plan.capsule_height(), _speed_mps])
	_emit("  required clearance %.3f m (capsule height + %.2f m margin)"
		% [_plan.required_clearance(), _plan.clearance_margin()])
	_emit("  spawn marker %s (the contract's, #83)" % str(_plan.spawn_marker()))
	_emit("  spawn floor surface %.4f m, ceiling %.4f m, headroom %.3f m"
		% [_plan.spawn_floor_surface(), _plan.spawn_ceiling_surface(),
		   _plan.spawn_ceiling_surface() - _plan.spawn_floor_surface()])
	_emit("  safety net top %.4f m -- a failsafe, never floor support" % _plan.safety_net_top())
	var columns: Dictionary = _plan.column_record()
	_emit("  floor plan %d rows x %d cols of %.2f m: %d tested, %d open at %.2f m, %d walkable"
		% [int(columns.get("rows", 0)), int(columns.get("cols", 0)),
		   float(columns.get("size_m", 0.0)), int(columns.get("tested_cells", 0)),
		   int(columns.get("open_at_test_cells", 0)), _plan.clearance_test_height(),
		   int(columns.get("walkable_cells", 0))])
	_emit("  tolerances from the plan:")
	_emit("    position %.2f m, step %.2f m, block stop %.2f m" % [_position_m, _max_step_m, _block_stop_m])
	_emit("    floor support >= %.0f%%, floor surface %.2f m, spawn drop <= %.2f m"
		% [_floor_support_min * 100.0, _floor_surface_m, _max_spawn_drop_m])
	var verdict: Dictionary = _plan.collision_report()
	_emit("  #84 collision benchmark passed=%s" % str(verdict.get("passed", false)))
	for failed: String in verdict.get("failed_checks", []):
		_emit("    FAILED %s" % failed)
	_emit("    %s" % String(verdict.get("why_this_still_supports_a_walk", "")))
	_emit("  physics: %d ticks/s, %d to settle, %d probe push budget"
		% [Engine.physics_ticks_per_second, SETTLE_TICKS, PROBE_PUSH_TICKS])


func _emit(line: String) -> void:
	## Buffer for the log file, and print immediately so a long run shows progress.
	_lines.append(line)
	print(line)


func _finish(passed: bool) -> void:
	## Write the run log next to the plan, where it is committed as evidence.
	var file := FileAccess.open(_log_path, FileAccess.WRITE)
	if file == null:
		printerr("could not write %s (error %d)" % [_log_path, FileAccess.get_open_error()])
		return
	file.store_string("\n".join(_lines) + "\n")
	file.close()


# --------------------------------------------------------------------------
# cases and mutations
# --------------------------------------------------------------------------


func _run_case(label: String, description: String, mutation: String) -> Array:
	## Instantiate the scene, apply a mutation, settle, and run the battery on it.
	_emit("")
	_emit("== %s: %s" % [label, description])
	var instance := _instantiate()
	if instance == null:
		_emit("  could not instantiate %s" % _scene_path)
		return ["instantiate"]
	root.add_child(instance)
	await process_frame
	if mutation != "":
		_mutate(instance, mutation)
		await process_frame
	await _settle()
	var failures := await _battery(instance, label)
	instance.queue_free()
	await process_frame
	return failures


func _instantiate() -> Node:
	var scene: PackedScene = load(_scene_path)
	if scene == null:
		return null
	return scene.instantiate()


func _scene_argument() -> String:
	## Read `--scene=res://...` from the command line, defaulting to corridor.tscn.
	for argument in OS.get_cmdline_user_args() + OS.get_cmdline_args():
		if argument.begins_with(SCENE_ARG_PREFIX):
			var value := argument.trim_prefix(SCENE_ARG_PREFIX).strip_edges()
			if value != "":
				return value
	return SCENE_PATH


func _log_path_for(scene_path: String) -> String:
	## The accepted scene keeps the committed log; any override gets its own
	## sibling file so a presentation-scene run cannot clobber #85's evidence.
	if scene_path == SCENE_PATH:
		return LOG_PATH
	var stem := scene_path.get_file().get_basename()
	return "%s_%s.log" % [LOG_PATH.get_basename(), stem]


func _mutate(instance: Node, mutation: String) -> void:
	## The mutation is named by the negative case's description, which is also what
	## the log prints, so there is one string per case rather than two that have to
	## be kept in step.
	match mutation:
		"the collision mesh is removed entirely":
			var body := instance.get_node_or_null("GeneratedCollision")
			if body != null:
				body.queue_free()
		"the collision node is scaled by metres_per_unit":
			var scaled := instance.get_node_or_null("GeneratedCollision") as Node3D
			if scaled != null:
				scaled.scale = Vector3.ONE * WRONG_SCALE
		"a box is dropped across the opening the route threads":
			instance.add_child(_opening_block())
		"the net is raised into the player's capsule":
			var net := instance.get_node_or_null("SafetyNet") as Node3D
			if net != null:
				net.position.y = _plan.spawn_floor_surface() + NET_INTRUSION_M - 0.5 * _net_thickness()
		_:
			_emit("  no mutation named '%s'" % mutation)


func _net_thickness() -> float:
	return _plan.safety_net_size().y


func _opening_block() -> StaticBody3D:
	## A box filling the plan's tightest passage, so the route is genuinely walled off.
	##
	## Sized with a cell of slack either side of the three recorded cells, because
	## the capsule has to be stopped by the block rather than squeezed past the
	## edge of it -- a box exactly cell-sized could be walked around, which would
	## let a broken scene pass.
	var columns: Dictionary = _plan.column_record()
	var size: float = float(columns.get("size_m", 0.25))
	var origin: Array = columns.get("origin_world_m", [0.0, 0.0])
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	for cell in _plan.opening_cells():
		var centre := Vector3(
			float(origin[0]) + (float(cell[0]) + 0.5) * size,
			0.0,
			float(origin[1]) + (float(cell[1]) + 0.5) * size
		)
		low.x = minf(low.x, centre.x - 1.5 * size)
		low.z = minf(low.z, centre.z - 1.5 * size)
		high.x = maxf(high.x, centre.x + 1.5 * size)
		high.z = maxf(high.z, centre.z + 1.5 * size)
	low.y = _plan.spawn_floor_surface()
	high.y = _plan.spawn_ceiling_surface()
	var body := StaticBody3D.new()
	body.name = "OpeningBlock"
	var shape_node := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = high - low
	shape_node.shape = box
	body.add_child(shape_node)
	body.position = 0.5 * (low + high)
	return body


# --------------------------------------------------------------------------
# the battery
# --------------------------------------------------------------------------


func _battery(instance: Node, label: String) -> Array:
	## Every step runs even after an earlier one fails.
	##
	## Returning early would mean a scene with no collision never gets walked, and
	## the walk is where the SafetyNet contact a fall-through produces is
	## observed. Reporting one failure and stopping is also what made the negative
	## cases reject for the wrong reason.
	var failures: Array = []
	failures.append_array(_check_collision_present(instance))
	var player := instance.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		failures.append("no Player CharacterBody3D in the scene")
		return failures
	failures.append_array(await _check_spawn(instance, player))
	failures.append_array(await _walk_cells(player, "route_outbound", _plan.route_cells()))
	failures.append_array(await _walk_cells(player, "boundary_out", _plan.access_cells()))
	failures.append_array(await _check_low_clearance(player))
	failures.append_array(await _walk_cells(player, "boundary_back", _reversed(_plan.access_cells())))
	failures.append_array(await _walk_cells(player, "route_inbound", _reversed(_plan.route_cells())))
	failures.append_array(await _walk_probes(instance, player))
	return failures


func _check_collision_present(instance: Node) -> Array:
	## The node existing is not collision existing.
	##
	## `GeneratedCollision` builds its trimesh from the imported GLB at run time, so
	## a missing mesh, a stale import cache or an empty file all leave a node with
	## no shape at all -- a walker falls straight through while every check that
	## only counts nodes still passes.
	var body := instance.get_node_or_null("GeneratedCollision")
	if body == null:
		return ["GeneratedCollision is not in the scene"]
	var triangles: Variant = body.get("triangle_count")
	if typeof(triangles) != TYPE_INT or int(triangles) <= 0:
		return ["GeneratedCollision built no triangles (%s)" % String(body.get("load_error"))]
	if int(triangles) != _plan.collision_triangles():
		return ["GeneratedCollision has %d triangles, the plan was derived from %d"
			% [int(triangles), _plan.collision_triangles()]]
	return []


func _check_spawn(instance: Node, player: CharacterBody3D) -> Array:
	## The player must be standing on the generated collision: not inside it, not
	## on the net, with the plan's headroom above.
	var failures: Array = []
	var floor_y: Variant = _ray_height(
		player.global_position,
		player.global_position + Vector3.DOWN * (_plan.capsule_height() + 0.5)
	)
	if floor_y == null:
		failures.append("no collision surface under the spawn")
	else:
		var measured := float(floor_y)
		if absf(measured - _plan.spawn_floor_surface()) > _floor_surface_m:
			failures.append("measured floor %.4f m differs from the plan's %.4f m by more than %.2f m"
				% [measured, _plan.spawn_floor_surface(), _floor_surface_m])
		var bottom: float = player.global_position.y - 0.5 * _plan.capsule_height()
		if bottom < measured - 0.02:
			failures.append("capsule bottom %.4f m is inside the floor %.4f m"
				% [bottom, measured])
		var drop: float = measured - bottom
		if drop > _max_spawn_drop_m:
			failures.append("the spawn drops %.3f m onto the floor; the plan's limit is %.2f m"
				% [drop, _max_spawn_drop_m])
		_emit("    spawn: floor %.4f m, capsule bottom %.4f m, drop %.4f m"
			% [measured, bottom, drop])
	var ceiling: Variant = _ray_height(
		player.global_position,
		player.global_position + Vector3.UP * (_plan.capsule_height() + 0.5)
	)
	if ceiling == null:
		failures.append("no ceiling above the spawn")
	else:
		var headroom: float = float(ceiling) - (player.global_position.y - 0.5 * _plan.capsule_height())
		if headroom < _plan.required_clearance():
			failures.append("headroom %.3f m at the spawn is under the required %.3f m"
				% [headroom, _plan.required_clearance()])
		_emit("    spawn: headroom %.3f m (required %.3f m)" % [headroom, _plan.required_clearance()])
	if not player.is_on_floor():
		failures.append("the player did not settle on a floor within %d ticks" % SETTLE_TICKS)
	return failures


func _walk_cells(player: CharacterBody3D, label: String, cells: Array) -> Array:
	## Walk a list of floor-plan cells corner to corner, in the given order.
	var failures: Array = []
	if cells.is_empty():
		return failures
	var samples := _Trace.new()
	var legs := 0
	for cell in cells:
		legs += 1
		var target: Vector3 = _plan.waypoint_position(cell)
		var arrived: bool = await _drive_to(player, target, samples)
		if not arrived:
			failures.append("%s: did not reach waypoint %s after %.2f m of route (%s)"
				% [label, str(cell), samples.path_length, samples.summary()])
			break
	failures.append_array(_trace_failures(samples, label))
	if samples.floor_fraction() < _floor_support_min:
		failures.append("%s: floor support %.1f%% over %d legs, the plan requires %.0f%%"
			% [label, samples.floor_fraction() * 100.0, legs, _floor_support_min * 100.0])
	if failures.is_empty():
		_emit("    %s: %d legs, %.2f m, floor support %.1f%%, max step %.3f m, y %.3f..%.3f"
			% [label, legs, samples.path_length, samples.floor_fraction() * 100.0,
			   samples.max_step, samples.lowest, samples.highest])
	return failures


func _check_low_clearance(player: CharacterBody3D) -> Array:
	## Standing in the least-headroom walkable cell: the unsupported boundary.
	##
	## Measured in place rather than walked to again: the preceding leg already
	## ends there, and a walk of zero length samples nothing, which reads as 0%
	## floor support -- a check that fails the *good* scene because the walk was
	## already over.
	var cell: Array = _plan.low_clearance_cell()
	if cell.size() != 2:
		return ["the plan records no low-clearance cell"]
	var failures: Array = []
	var samples := _Trace.new()
	var target: Vector3 = _plan.waypoint_position(cell)
	var flat := Vector2(target.x - player.global_position.x, target.z - player.global_position.z)
	if flat.length() > _position_m:
		var arrived: bool = await _drive_to(player, target, samples)
		if not arrived:
			failures.append("low_clearance: did not reach cell %s (%s)"
				% [str(cell), samples.summary()])
	for _tick in SETTLE_TICKS:
		await physics_frame
		samples.sample(player, _touching_net(player), _standing_on_net(player))
	if samples.floor_fraction() < _floor_support_min:
		failures.append("low_clearance: floor support %.1f%% standing in cell %s"
			% [samples.floor_fraction() * 100.0, str(cell)])
	failures.append_array(_trace_failures(samples, "low_clearance"))
	if failures.is_empty():
		_emit("    low_clearance: cell %s, plan headroom %.3f m, floor support %.1f%% over %d ticks"
			% [str(cell), _plan.low_clearance_m(), samples.floor_fraction() * 100.0, samples.ticks])
	return failures


func _walk_probes(instance: Node, player: CharacterBody3D) -> Array:
	## Every probe must be stopped by solid geometry, after a real approach run.
	##
	## "Stopped" is decided by geometry, not by a flag the driver sets: the walker
	## must come to rest within the plan's block-stop tolerance of the position the
	## plan predicts for a capsule resting against that cell's face, and it must
	## have covered at least the plan's minimum displacement to get there.  A probe
	## that never moved cannot satisfy the second, so a walker released already
	## touching the wall does not pass.
	var failures: Array = []
	for probe: Dictionary in _plan.probes():
		var name := String(probe.get("name", "?"))
		for cell in probe.get("approach_cells", []):
			await _drive_to(player, _plan.waypoint_position(cell), _Trace.new())
		var direction := Vector2(float(probe["direction"][0]), float(probe["direction"][1]))
		var start := player.global_position
		var samples := _Trace.new()
		await _push(player, direction, samples)
		var rest := Vector2(player.global_position.x - start.x, player.global_position.z - start.z)
		var travelled := rest.dot(direction)
		var expected := Vector2(
			float(probe["expected_stop_m"][0]) - start.x,
			float(probe["expected_stop_m"][1]) - start.z
		)
		var tolerance: float = float(probe.get("stop_tolerance_m", _block_stop_m))
		var offset := rest.distance_to(expected)
		if travelled < float(probe.get("min_displacement_m", 0.0)):
			failures.append("probe %s only covered %.3f m, short of the plan's %.3f m minimum"
				% [name, travelled, float(probe.get("min_displacement_m", 0.0))])
		if offset > tolerance:
			failures.append("probe %s came to rest %.3f m from the planned stop, tolerance %.2f m (%s)"
				% [name, offset, tolerance, samples.summary()])
		failures.append_array(_trace_failures(samples, "probe %s" % name))
		if failures.is_empty():
			_emit("    probe %s: ran %.2f m, stopped %.3f m from the planned face at %s (tolerance %.2f m)"
				% [name, travelled, offset, str(probe["expected_stop_m"]), tolerance])
	return failures


# --------------------------------------------------------------------------
# driving the production controller
# --------------------------------------------------------------------------


func _settle() -> void:
	## Let gravity, floor snapping and the capsule resolve before anything is judged.
	for _tick in SETTLE_TICKS:
		await physics_frame


func _budget(distance: float) -> int:
	## Ticks a leg of ``distance`` metres should take, with a fixed margin.
	##
	## Derived from the controller's own speed rather than a flat worst case: a flat
	## budget turns a 9 m leg and a 1 m leg into the same wait, and the sum over
	## every leg and every case is what made the whole run outlast a review window.
	var ticks := distance / maxf(_speed_mps, 0.01) * float(Engine.physics_ticks_per_second)
	return int(ceil(ticks)) + 90


func _drive_to(player: CharacterBody3D, target: Vector3, samples) -> bool:
	## Hold `move_forward` aimed at a point until the walker is close enough.
	var flat := Vector2(target.x - player.global_position.x, target.z - player.global_position.z)
	if flat.length() <= _position_m:
		return true
	return await _drive(player, target, flat.normalized(), _budget(flat.length()), samples)


func _drive(player: CharacterBody3D, target: Vector3, direction: Vector2, budget: int, samples) -> bool:
	## The production controller's own yaw convention.
	##
	## `player.gd` builds its direction as `Vector3(input.x, 0, input.y)` rotated by
	## the body's yaw, and `move_forward` contributes `input.y == -1`, so the body
	## must face `atan2(-direction.x, -direction.y)`.  Setting the body's yaw is
	## what the mouse-look handler does; nothing here bypasses the controller or
	## writes velocity directly.
	player.rotation.y = atan2(-direction.x, -direction.y)
	Input.action_press("move_forward")
	var arrived := false
	var stuck := 0
	var previous := player.global_position
	for tick in budget:
		await physics_frame
		var contact := _touching_net(player)
		samples.sample(player, contact, _standing_on_net(player))
		if contact:
			Input.action_release("move_forward")
			return false
		if player.global_position.distance_to(previous) < REST_DELTA:
			stuck += 1
		else:
			stuck = 0
		previous = player.global_position
		if stuck >= STUCK_TICKS:
			break
		var delta := Vector2(target.x - player.global_position.x, target.z - player.global_position.z)
		if delta.length() <= _position_m:
			arrived = true
			break
	Input.action_release("move_forward")
	return arrived


func _push(player: CharacterBody3D, direction: Vector2, samples) -> void:
	## Hold `move_forward` into an obstacle until the walker stops making progress.
	player.rotation.y = atan2(-direction.x, -direction.y)
	Input.action_press("move_forward")
	var stuck := 0
	var previous := player.global_position
	for tick in PROBE_PUSH_TICKS:
		await physics_frame
		samples.sample(player, _touching_net(player), _standing_on_net(player))
		if samples.touched_net:
			break
		if player.global_position.distance_to(previous) < REST_DELTA:
			stuck += 1
			if stuck >= STUCK_TICKS:
				break
		else:
			stuck = 0
		previous = player.global_position
	Input.action_release("move_forward")


func _reversed(cells: Array) -> Array:
	var copy := cells.duplicate()
	copy.reverse()
	return copy


# --------------------------------------------------------------------------
# physics queries
# --------------------------------------------------------------------------


func _touching_net(player: CharacterBody3D) -> bool:
	## Whether the player's capsule currently overlaps the safety net.
	##
	## The query shape is the **player's** capsule at the player's own transform,
	## and only the player is excluded.  Building the query out of the net's box
	## instead -- and then looking for a collider named SafetyNet -- cannot report
	## a contact: the net either intersects its own query shape on every tick, or
	## is excluded and never reported.  Querying the capsule against the space and
	## asking which bodies it overlaps is the question the acceptance asks.
	var capsule := _player_capsule(player)
	if capsule == null:
		return false
	var space := player.get_world_3d().direct_space_state
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = capsule
	query.transform = player.global_transform
	query.collide_with_areas = false
	query.exclude = [player.get_rid()]
	for hit in space.intersect_shape(query, 16):
		var collider: Variant = hit.get("collider")
		if collider is Node and (collider as Node).name == "SafetyNet":
			return true
	return false


func _standing_on_net(player: CharacterBody3D) -> bool:
	## Whether the surface holding the player up is the safety net.
	##
	## Distinct from :func:`_touching_net`, and the more dangerous of the two.  A
	## scene whose collision has been removed leaves the net as the only floor, and
	## a battery that only checked for overlap would watch the player walk 6.6 m
	## across the net and call it a successful route.  The support question is
	## asked of the downward ray that `is_on_floor()` already implies.
	if not player.is_on_floor():
		return false
	var collider: Variant = _downward_collider(player)
	return collider is Node and (collider as Node).name == "SafetyNet"


func _downward_collider(player: CharacterBody3D) -> Variant:
	## The body directly under the player's capsule, or ``null`` if there is none.
	var space := player.get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(
		player.global_position,
		player.global_position + Vector3.DOWN * (0.5 * _plan.capsule_height() + 0.15)
	)
	query.collide_with_areas = false
	query.exclude = [player.get_rid()]
	var hit: Dictionary = space.intersect_ray(query)
	if hit.is_empty():
		return null
	return hit.get("collider")


func _player_capsule(player: CharacterBody3D) -> CapsuleShape3D:
	for child in player.get_children():
		if child is CollisionShape3D:
			var shape: Shape3D = (child as CollisionShape3D).shape
			if shape is CapsuleShape3D:
				return shape
	return null


func _ray_height(from: Vector3, to: Vector3) -> Variant:
	if from.distance_to(to) < 0.0001:
		return null
	var scene := _scene_root()
	if scene == null:
		return null
	var space: Variant = (scene as Node3D).get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = false
	var hit: Dictionary = space.intersect_ray(query)
	if hit.is_empty():
		return null
	return float((hit["position"] as Vector3).y)


func _scene_root() -> Node:
	for child in root.get_children():
		if child is Node3D:
			return child
	return null


# --------------------------------------------------------------------------
# per-frame trace
# --------------------------------------------------------------------------


class _Trace:
	## What one walk observed: the only evidence any assertion is allowed to use.
	var ticks := 0
	var floor_ticks := 0
	var path_length := 0.0
	var max_step := 0.0
	var lowest := INF
	var highest := -INF
	var touched_net := false
	var stood_on_net := false
	var _previous := Vector3.ZERO
	var _started := false

	func sample(player: CharacterBody3D, net_contact: bool, net_support: bool = false) -> void:
		var position := player.global_position
		ticks += 1
		if player.is_on_floor():
			floor_ticks += 1
		if _started:
			path_length += Vector2(position.x - _previous.x, position.z - _previous.z).length()
			max_step = maxf(max_step, position.distance_to(_previous))
		_previous = position
		_started = true
		lowest = minf(lowest, position.y)
		highest = maxf(highest, position.y)
		if net_contact:
			touched_net = true
		if net_support:
			stood_on_net = true

	func floor_fraction() -> float:
		return 0.0 if ticks == 0 else float(floor_ticks) / float(ticks)

	func summary() -> String:
		return "ticks=%d floor=%.0f%% path=%.2f m max_step=%.3f m y=%.3f..%.3f net=%s support=%s" % [
			ticks, floor_fraction() * 100.0, path_length, max_step, lowest, highest,
			str(touched_net), str(stood_on_net),
		]


func _trace_failures(samples, label: String) -> Array:
	## The invariants every walk must hold, whatever it was walking to.
	var failures: Array = []
	if samples.touched_net:
		failures.append("%s: SafetyNet contact -- the net is a failsafe, never floor support (%s)"
			% [label, samples.summary()])
	if samples.stood_on_net:
		failures.append("%s: stood on the SafetyNet -- a walk that used the net as floor is not a walk (%s)"
			% [label, samples.summary()])
	if samples.max_step > _max_step_m:
		failures.append("%s: one physics tick moved the body %.3f m against a %.2f m limit, which "
			% [label, samples.max_step, _max_step_m]
			+ "is tunnelling or depenetration rather than walking")
	if samples.ticks > 0 and samples.lowest < _plan.safety_net_top():
		failures.append("%s: fell to %.3f m, at or below the safety net's top %.3f m"
			% [label, samples.lowest, _plan.safety_net_top()])
	return failures


func _mentions(failures: Array, needle: String) -> bool:
	for failure in failures:
		if String(failure).contains(needle):
			return true
	return false
