extends SceneTree

const SCENE_PATH := "res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/room.tscn"
const SPAWN := Vector3(0.0, 0.6, 1.6)
const SPAWN_PITCH := deg_to_rad(7.0)

var failures: Array[String] = []
var report_path := "/tmp/issue169-bill-viola-room-test.json"
var report := {"registration_accepted": false, "scale_calibrated": false}


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.trim_prefix("--report=")
	call_deferred("_run")


func _run() -> void:
	var room := await _load_room()
	if room == null:
		quit(1)
		return
	_check_contract(room)
	_check_boundaries(room)
	_check_floor(room)
	_check_obstacle(room)
	await _check_traversal_and_reset(room)
	_check_negative_controls(room)
	_write_report()
	quit(0 if failures.is_empty() else 1)


func _load_room() -> Node3D:
	var packed := load(SCENE_PATH) as PackedScene
	_expect(packed != null, "Candidate scene failed to load")
	if packed == null:
		return null
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	await _physics_steps(10)
	return room


func _check_contract(room: Node3D) -> void:
	_expect(room.get_meta("walkthrough_ready", false), "Room did not finish setup")
	_expect(not room.get_meta("registration_accepted"), "Registration flag changed")
	_expect(not room.get_meta("scale_calibrated"), "Scale flag changed")
	_expect(room.get_meta("observed_openings").is_empty(), "Unexpected source opening was declared")
	_expect(room.get_meta("tested_connectors").is_empty(), "Unexpected connector was declared")
	var player := room.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, "Candidate is missing the shared player controller")
	if player != null:
		_expect(player.global_position.distance_to(SPAWN) < 0.02, "Player spawn differs from the declared safe spawn")
		_expect(player.is_on_floor(), "Player spawn is not supported")


func _check_boundaries(room: Node3D) -> void:
	var probes := [
		[Vector3(0.0, 1.4, 0.0), Vector3(-5.0, 1.4, 0.0), "left"],
		[Vector3(0.0, 1.4, 0.0), Vector3(5.0, 1.4, 0.0), "right"],
		[Vector3(3.4, 1.4, 0.0), Vector3(3.4, 1.4, -5.0), "source-facing"],
		[Vector3(0.0, 1.4, 3.4), Vector3(0.0, 1.4, 5.0), "near"],
	]
	for probe in probes:
		_expect(_ray_hits(room, probe[0], probe[1]), "Closed room boundary missing: " + probe[2])
	report["closed_boundaries"] = probes.size()


func _check_floor(room: Node3D) -> void:
	var supported := 0
	for x in range(-7, 8):
		for z in range(-7, 8):
			var origin := Vector3(float(x) * 0.5, 0.5, float(z) * 0.5)
			if _ray_hits(room, origin, origin + Vector3.DOWN * 0.8):
				supported += 1
	_expect(supported == 225, "Authored floor has a support gap in the 0.5-unit grid")
	report["floor_support_samples"] = supported


func _check_obstacle(room: Node3D) -> void:
	var blocked := _ray_hits(room, Vector3(0.0, 0.75, -1.8), Vector3(0.0, 0.75, -3.8))
	_expect(blocked, "Dresser obstacle has no matching collision")
	report["dresser_collision"] = blocked


func _check_traversal_and_reset(room: Node3D) -> void:
	var player := room.get_node("Player") as CharacterBody3D
	var start := player.global_position
	Input.action_press("move_forward")
	await _physics_steps(45)
	Input.action_release("move_forward")
	var moved := player.global_position.distance_to(start) > 1.0
	_expect(moved and player.is_on_floor(), "Walkable area traversal lost movement or floor support")
	player.global_position = Vector3(80.0, 80.0, 80.0)
	player.velocity = Vector3(4.0, 2.0, -3.0)
	room.call("_unhandled_key_input", _reset_event())
	_expect(player.global_position.distance_to(SPAWN) < 0.001, "R reset did not restore the safe spawn")
	_expect(player.velocity.length() < 0.001, "R reset did not clear velocity")
	_expect(absf(player.get_node("Head").rotation.x - SPAWN_PITCH) < 0.001,
		"R reset did not restore the source-facing pitch")
	report["walk_and_reset"] = moved and player.global_position.distance_to(SPAWN) < 0.001


func _check_negative_controls(room: Node3D) -> void:
	var floor_body := room.get_node("AuthoredBoundaries/WalkableFloor") as StaticBody3D
	var floor_layer := floor_body.collision_layer
	floor_body.collision_layer = 0
	var floor_removed := not _ray_hits(room, Vector3(1.0, 0.45, 1.0), Vector3(1.0, -0.3, 1.0))
	floor_body.collision_layer = floor_layer
	var near_wall := room.get_node("AuthoredBoundaries/NearBoundary") as StaticBody3D
	var wall_layer := near_wall.collision_layer
	near_wall.collision_layer = 0
	var boundary_removed := not _ray_hits(room, Vector3(0.0, 1.4, 3.5), Vector3(0.0, 1.4, 5.0))
	near_wall.collision_layer = wall_layer
	_expect(floor_removed, "Missing-floor negative control did not remove support")
	_expect(boundary_removed, "Open-boundary negative control remained blocked")
	report["negative_controls"] = {"missing_floor": floor_removed, "open_boundary": boundary_removed}


func _ray_hits(room: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	query.collision_mask = 1
	return not room.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _reset_event() -> InputEventKey:
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_R
	return event


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures.append(message)
	push_error(message)


func _write_report() -> void:
	if FileAccess.file_exists(report_path):
		_expect(false, "Refusing to overwrite test report: " + report_path)
		return
	var absolute := ProjectSettings.globalize_path(report_path)
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	var output := FileAccess.open(report_path, FileAccess.WRITE)
	if output == null:
		_expect(false, "Could not write test report")
		return
	report["schema_version"] = 1
	report["candidate_status"] = "pending_operator_review"
	report["failures"] = failures
	output.store_string(JSON.stringify(report, "\t") + "\n")
