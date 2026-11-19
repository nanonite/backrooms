extends SceneTree

## Issue #283 headless variant-pair tests. Four straight corridor chains, each
## assembled by reference from the unmodified source-library rooms. Every pair
## runs the nominal geometry/clearance/traversal assertions plus the same two
## negative controls (mismatched yaw, 0.3 m floor offset) through the same
## _pair_geometry_errors() gate.

const ASSEMBLY := "res://evidence/2026-11-19-issue-283-variant-pairs/variant_pairs_scene.tscn"
const POSITION_TOLERANCE := 0.001
const NORMAL_TOLERANCE := 0.999

var failures: Array[String] = []
var result_lines: Array[String] = []
var report := {
	"schema_version": 1,
	"issue": 283,
	"registration_accepted": false,
	"scale_calibrated": false,
	"socket_test_status": "untested",
	"layout_eligible": false,
	"pairs": {},
}
var report_path := "res://evidence/2026-11-19-issue-283-variant-pairs/mechanics/traversal.json"


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.trim_prefix("--report=")
	call_deferred("_run")


func _pair_definitions() -> Array[Dictionary]:
	return [
		{
			"label": "P1", "id": "p1_chevron175_south__chevron176_north",
			"from_key": "chevron_175", "to_key": "chevron_176",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 20.0),
			"from_yaw": 0, "to_yaw": 0, "seam_z": 10.0,
			"spawn": Vector3(0.0, 0.6, 4.0),
			"from_depth": 10.0, "to_depth": 10.0,
			"from_width": 12.0, "to_width": 16.0,
			"from_height": 3.8, "to_height": 4.2,
		},
		{
			"label": "P2", "id": "p2_chevron176_south__chevron177_north",
			"from_key": "chevron_176", "to_key": "chevron_cross_177",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 20.0),
			"from_yaw": 0, "to_yaw": 0, "seam_z": 10.0,
			"spawn": Vector3(0.0, 0.6, 4.0),
			"from_depth": 10.0, "to_depth": 10.0,
			"from_width": 16.0, "to_width": 16.0,
			"from_height": 4.2, "to_height": 4.2,
		},
		{
			"label": "P3", "id": "p3_chevron177_south__nestedlight173_north",
			"from_key": "chevron_cross_177", "to_key": "nested_light_173",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 22.0),
			"from_yaw": 0, "to_yaw": 0, "seam_z": 10.0,
			"spawn": Vector3(0.0, 0.6, 4.0),
			"from_depth": 10.0, "to_depth": 12.0,
			"from_width": 16.0, "to_width": 10.0,
			"from_height": 4.2, "to_height": 4.8,
		},
		{
			"label": "P4", "id": "p4_nestedlight173_south__chevron175_north",
			"from_key": "nested_light_173", "to_key": "chevron_175",
			"from_socket": "south", "to_socket": "north",
			"from_origin": Vector3(0.0, 0.0, 0.0), "to_origin": Vector3(0.0, 0.0, 22.0),
			"from_yaw": 0, "to_yaw": 0, "seam_z": 12.0,
			"spawn": Vector3(0.0, 0.6, 6.0),
			"from_depth": 12.0, "to_depth": 10.0,
			"from_width": 10.0, "to_width": 12.0,
			"from_height": 4.8, "to_height": 3.8,
		},
	]


func _run() -> void:
	for pair in _pair_definitions():
		await _check_pair(pair)
	_write_report()
	if failures.is_empty():
		_result("ISSUE283_VARIANT_PAIR_TESTS_PASSED")
		quit(0)
	else:
		_result("ISSUE283_VARIANT_PAIR_TESTS_FAILED count=%d" % failures.size())
		quit(1)


func _overrides_for(pair: Dictionary) -> Dictionary:
	return {
		"pair_id": pair["id"],
		"from_room_key": pair["from_key"],
		"to_room_key": pair["to_key"],
		"from_socket_id": pair["from_socket"],
		"to_socket_id": pair["to_socket"],
		"from_origin": pair["from_origin"],
		"to_origin": pair["to_origin"],
		"from_yaw_degrees": pair["from_yaw"],
		"to_yaw_degrees": pair["to_yaw"],
		"player_spawn": pair["spawn"],
		"player_yaw_degrees": 180,
	}


func _check_pair(pair: Dictionary) -> void:
	var label := String(pair["label"])
	var scene := await _load_assembly(_overrides_for(pair), label)
	if scene == null:
		return
	var from_socket := _socket_world(scene, "FromRoom", String(pair["from_socket"]))
	var to_socket := _socket_world(scene, "ToRoom", String(pair["to_socket"]))
	_expect(not from_socket.is_empty() and not to_socket.is_empty(), label + " socket metadata missing")
	if from_socket.is_empty() or to_socket.is_empty():
		scene.queue_free()
		await process_frame
		return
	var errors := _pair_geometry_errors(from_socket, to_socket)
	_expect(errors.is_empty(), label + " nominal geometry rejected: " + str(errors))
	var xz_error := Vector2(float(from_socket["position"].x) - float(to_socket["position"].x),
		float(from_socket["position"].z) - float(to_socket["position"].z)).length()
	var floor_delta := absf(float(from_socket["floor_y"]) - float(to_socket["floor_y"]))
	var normal_dot := (from_socket["normal"] as Vector3).dot(to_socket["normal"] as Vector3)
	_result("%s_NOMINAL_CENTER_XZ_ERROR %.6f" % [label, xz_error])
	_result("%s_NOMINAL_FLOOR_DELTA %.6f" % [label, floor_delta])
	_result("%s_NOMINAL_NORMAL_DOT %.6f" % [label, normal_dot])
	_result("%s_NOMINAL_CLEAR_SIZE %s vs %s" % [label, str(from_socket["size"]), str(to_socket["size"])])
	var ceiling_step := float(pair["to_height"]) - float(pair["from_height"])
	var width_delta_side := (float(pair["to_width"]) - float(pair["from_width"])) * 0.5
	_result("%s_CEILING_SEAM from_h=%.6f to_h=%.6f step=%.6f walking_step=%.6f" % [
		label, pair["from_height"], pair["to_height"], ceiling_step, floor_delta])
	_result("%s_WIDTH_SEAM from_w=%.6f to_w=%.6f delta_each_side=%.6f" % [
		label, pair["from_width"], pair["to_width"], width_delta_side])
	var pair_report := {
		"id": pair["id"],
		"placement": {
			"from_origin": pair["from_origin"], "from_yaw_degrees": pair["from_yaw"],
			"to_origin": pair["to_origin"], "to_yaw_degrees": pair["to_yaw"],
			"seam_world_z": pair["seam_z"],
		},
		"center_xz_error": xz_error, "floor_delta": floor_delta, "normal_dot": normal_dot,
		"clear_size_from": from_socket["size"], "clear_size_to": to_socket["size"],
		"ceiling_step_m": ceiling_step, "walking_step_m": floor_delta,
		"width_delta_each_side_m": width_delta_side,
		"errors": errors,
	}
	report["pairs"][label] = pair_report
	_pair_report_checks(scene, pair, label, pair_report)
	await _check_traversal(scene, pair, label, pair_report)
	scene.queue_free()
	await process_frame
	await _check_mismatched_yaw(pair, label, pair_report)
	await _check_floor_offset(pair, label, pair_report)


func _pair_geometry_errors(from_socket: Dictionary, to_socket: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	var xz_error := Vector2(float(from_socket["position"].x) - float(to_socket["position"].x),
		float(from_socket["position"].z) - float(to_socket["position"].z)).length()
	if xz_error > POSITION_TOLERANCE:
		errors.append("socket floor centers do not coincide in XZ (error=%.6f)" % xz_error)
	var floor_delta := absf(float(from_socket["floor_y"]) - float(to_socket["floor_y"]))
	if floor_delta > POSITION_TOLERANCE:
		errors.append("connector floor elevations differ (delta=%.6f)" % floor_delta)
	var normal_dot := (from_socket["normal"] as Vector3).dot(to_socket["normal"] as Vector3)
	if normal_dot > -NORMAL_TOLERANCE:
		errors.append("socket normals do not oppose (dot=%.6f)" % normal_dot)
	if from_socket["size"] != to_socket["size"]:
		errors.append("socket clear dimensions differ")
	if String(from_socket["compatibility_type"]) != String(to_socket["compatibility_type"]):
		errors.append("socket compatibility types differ")
	return errors


func _pair_report_checks(scene: Node3D, pair: Dictionary, label: String, pair_report: Dictionary) -> void:
	var seam := float(pair["seam_z"])
	var space := scene.get_world_3d().direct_space_state
	var excluded := (scene.get_node("Player") as CharacterBody3D).get_rid()
	var clear_count := 0
	var total := 0
	for step in range(-15, 16):
		total += 1
		if _capsule_clear(space, Vector3(0.0, 0.64, seam + float(step) * 0.1), excluded):
			clear_count += 1
	_expect(clear_count == total, label + " capsule cannot pass through the doorway")
	_result("%s_DOORWAY_CAPSULE_SAMPLES_CLEAR %d/%d" % [label, clear_count, total])
	pair_report["doorway_capsule_samples_clear"] = clear_count
	var supported := true
	var worst_error := 0.0
	for step in range(25):
		var z := seam - 0.24 + float(step) * 0.02
		var y := _floor_y(scene, z)
		if absf(y) > 0.02:
			supported = false
		worst_error = maxf(worst_error, absf(y))
	_expect(supported, label + " floor elevation is discontinuous across the socket seam")
	_result("%s_FLOOR_CONTINUITY_SUPPORTED %s worst_abs_error=%.6f" % [
		label, str(supported), worst_error])
	pair_report["floor_continuity"] = {"supported": supported, "worst_abs_error": worst_error}
	var center_open := not _ray_hits(scene, Vector3(0.0, 1.1, seam - 2.5), Vector3(0.0, 1.1, seam + 2.5))
	var side_open := not _ray_hits(scene, Vector3(0.95, 1.1, seam - 2.5), Vector3(0.95, 1.1, seam + 2.5))
	var jamb_blocks := _ray_hits(scene, Vector3(1.2, 1.1, seam - 2.5), Vector3(1.2, 1.1, seam + 2.5))
	var header_blocks := _ray_hits(scene, Vector3(0.0, 2.5, seam - 2.5), Vector3(0.0, 2.5, seam + 2.5))
	_expect(center_open and side_open, label + " 2.0 m clear aperture is blocked")
	_expect(jamb_blocks and header_blocks, label + " jamb or header collider is missing")
	_result("%s_APERTURE_CENTER_OPEN %s NEAR_SIDE_OPEN %s JAMB_BLOCKS %s HEADER_BLOCKS %s" % [
		label, str(center_open), str(side_open), str(jamb_blocks), str(header_blocks)])
	pair_report["aperture"] = {
		"center_open": center_open, "near_side_open": side_open,
		"jamb_blocks": jamb_blocks, "header_blocks": header_blocks,
	}
	var from_w := float(pair["from_width"]) * 0.5
	var to_w := float(pair["to_width"]) * 0.5
	var from_x_min := float(pair["from_origin"].x) - from_w
	var from_x_max := float(pair["from_origin"].x) + from_w
	var to_x_min := float(pair["to_origin"].x) - to_w
	var to_x_max := float(pair["to_origin"].x) + to_w
	var from_z_min := float(pair["from_origin"].z) - float(pair["from_depth"])
	var from_z_max := float(pair["from_origin"].z) + float(pair["from_depth"])
	var to_z_min := float(pair["to_origin"].z) - float(pair["to_depth"])
	var to_z_max := float(pair["to_origin"].z) + float(pair["to_depth"])
	var overlap_x := minf(from_x_max, to_x_max) - maxf(from_x_min, to_x_min)
	var overlap_z := minf(from_z_max, to_z_max) - maxf(from_z_min, to_z_min)
	var no_overlap := overlap_z <= POSITION_TOLERANCE or overlap_x <= POSITION_TOLERANCE
	_expect(no_overlap, label + " room footprints overlap beyond the doorway")
	_result("%s_FOOTPRINT_OVERLAP_X %.6f OVERLAP_Z %.6f NO_OVERLAP %s" % [
		label, overlap_x, overlap_z, str(no_overlap)])
	pair_report["footprint_overlap"] = {
		"overlap_x": overlap_x, "overlap_z": overlap_z, "no_overlap_beyond_doorway": no_overlap,
	}
	var from_center_z := float(pair["from_origin"].z)
	var to_center_z := float(pair["to_origin"].z)
	var probes := [
		[Vector3(0.0, 1.0, from_center_z), Vector3(-from_w - 1.0, 1.0, from_center_z), "from_west"],
		[Vector3(0.0, 1.0, from_center_z), Vector3(from_w + 1.0, 1.0, from_center_z), "from_east"],
		[Vector3(0.0, 1.0, to_center_z), Vector3(-to_w - 1.0, 1.0, to_center_z), "to_west"],
		[Vector3(0.0, 1.0, to_center_z), Vector3(to_w + 1.0, 1.0, to_center_z), "to_east"],
	]
	var closed_count := 0
	for probe in probes:
		if _ray_hits(scene, probe[0], probe[1]):
			closed_count += 1
		else:
			_expect(false, label + " exterior boundary is open: " + String(probe[2]))
	var from_other_z := from_center_z - float(pair["from_depth"])
	var to_other_z := to_center_z + float(pair["to_depth"])
	var from_other_open := not _ray_hits(scene,
		Vector3(0.0, 1.1, from_other_z + 1.5), Vector3(0.0, 1.1, from_other_z - 1.5))
	var to_other_open := not _ray_hits(scene,
		Vector3(0.0, 1.1, to_other_z - 1.5), Vector3(0.0, 1.1, to_other_z + 1.5))
	_expect(from_other_open and to_other_open, label + " declared unconnected sockets are not both open")
	_result("%s_EXTERIOR_BOUNDARIES_CLOSED %d/%d UNCONNECTED_SOCKETS_OPEN %d/2" % [
		label, closed_count, probes.size(),
		int(from_other_open) + int(to_other_open)])
	pair_report["exterior_closure"] = {
		"closed_probes": closed_count, "probe_count": probes.size(),
		"from_other_socket_open": from_other_open, "to_other_socket_open": to_other_open,
	}


func _check_traversal(scene: Node3D, pair: Dictionary, label: String, pair_report: Dictionary) -> void:
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, label + " assembly must have one player")
	if player == null:
		return
	var spawn := pair["spawn"] as Vector3
	var seam := float(pair["seam_z"])
	_expect(player.is_on_floor(), label + " player spawn lacks floor support")
	var spawn_transform := _transform_record(player)
	Input.action_press("move_forward")
	await _physics_steps(180)
	Input.action_release("move_forward")
	var reached := player.global_position.z > seam + 2.0 and player.is_on_floor()
	_expect(reached, label + " player did not walk from the from-room into the to-room")
	var forward_transform := _transform_record(player)
	_result("%s_TRAVERSAL_A_TO_B x=%.6f y=%.6f z=%.6f on_floor=%s" % [
		label, player.global_position.x, player.global_position.y, player.global_position.z,
		str(player.is_on_floor())])
	Input.action_press("move_back")
	await _physics_steps(180)
	Input.action_release("move_back")
	var returned := player.global_position.z < seam - 2.0 and player.is_on_floor()
	_expect(returned, label + " player did not walk back into the from-room")
	var back_transform := _transform_record(player)
	_result("%s_TRAVERSAL_B_TO_A x=%.6f y=%.6f z=%.6f on_floor=%s" % [
		label, player.global_position.x, player.global_position.y, player.global_position.z,
		str(player.is_on_floor())])
	scene.call("_reset_player")
	var reset := player.global_position.distance_to(spawn) < POSITION_TOLERANCE
	_expect(reset, label + " player reset did not restore the safe spawn")
	var reset_transform := _transform_record(player)
	_result("%s_TRAVERSAL_RESET x=%.6f y=%.6f z=%.6f" % [
		label, player.global_position.x, player.global_position.y, player.global_position.z])
	pair_report["traversal"] = {
		"spawn": spawn_transform, "after_a_to_b": forward_transform,
		"reached_to_room": reached, "after_b_to_a": back_transform,
		"returned_to_from_room": returned, "after_reset": reset_transform,
		"reset_restored_spawn": reset,
	}


func _check_mismatched_yaw(pair: Dictionary, label: String, pair_report: Dictionary) -> void:
	# Flip the to-room to yaw 180 and move it so the XZ centers still align;
	# only normal opposition can then reject the pair.
	var overrides := _overrides_for(pair)
	overrides["to_yaw_degrees"] = 180
	overrides["to_origin"] = Vector3(float(pair["to_origin"].x), 0.0,
		float(pair["seam_z"]) - float(pair["to_depth"]))
	var scene := await _load_assembly(overrides, label + "_neg_yaw")
	if scene == null:
		return
	var from_socket := _socket_world(scene, "FromRoom", String(pair["from_socket"]))
	var to_socket := _socket_world(scene, "ToRoom", String(pair["to_socket"]))
	var errors := _pair_geometry_errors(from_socket, to_socket)
	var rejected := errors.size() > 0 and _contains(errors, "socket normals do not oppose")
	_expect(rejected, label + " mismatched-yaw negative control was not rejected")
	var dot := (from_socket["normal"] as Vector3).dot(to_socket["normal"] as Vector3)
	_result("%s_NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=%.6f errors=%s" % [label, dot, str(errors)])
	pair_report["negative_controls"] = {} if not pair_report.has("negative_controls") else pair_report["negative_controls"]
	pair_report["negative_controls"]["mismatched_yaw"] = {
		"to_yaw_degrees": 180, "to_origin": overrides["to_origin"],
		"normal_dot": dot, "errors": errors, "rejected": rejected,
	}
	scene.queue_free()
	await process_frame


func _check_floor_offset(pair: Dictionary, label: String, pair_report: Dictionary) -> void:
	var overrides := _overrides_for(pair)
	overrides["to_origin"] = Vector3(float(pair["to_origin"].x), 0.3, float(pair["to_origin"].z))
	var scene := await _load_assembly(overrides, label + "_neg_floor")
	if scene == null:
		return
	var from_socket := _socket_world(scene, "FromRoom", String(pair["from_socket"]))
	var to_socket := _socket_world(scene, "ToRoom", String(pair["to_socket"]))
	var errors := _pair_geometry_errors(from_socket, to_socket)
	var rejected := errors.size() > 0 and _contains(errors, "connector floor elevations differ")
	_expect(rejected, label + " floor-offset negative control was not rejected")
	var delta := absf(float(from_socket["floor_y"]) - float(to_socket["floor_y"]))
	_result("%s_NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=%.6f errors=%s" % [label, delta, str(errors)])
	pair_report["negative_controls"]["floor_offset_0_3m"] = {
		"to_origin": overrides["to_origin"], "floor_delta": delta,
		"errors": errors, "rejected": rejected,
	}
	scene.queue_free()
	await process_frame


func _load_assembly(overrides: Dictionary, label: String) -> Node3D:
	var packed := load(ASSEMBLY) as PackedScene
	_expect(packed != null, label + " cannot load variant-pair assembly")
	if packed == null:
		return null
	var scene := packed.instantiate() as Node3D
	for key in overrides:
		scene.set(key, overrides[key])
	root.add_child(scene)
	for _tick in range(180):
		await process_frame
		if scene.get_meta("walkthrough_ready", false):
			break
	_expect(scene.get_meta("walkthrough_ready", false), label + " assembly did not become ready")
	await _physics_steps(8)
	return scene


func _socket_world(scene: Node3D, room_name: String, socket_id: String) -> Dictionary:
	return scene.call("get_connection_socket_world", [room_name, socket_id]) as Dictionary


func _contains(errors: Array[String], fragment: String) -> bool:
	for error in errors:
		if error.contains(fragment):
			return true
	return false


func _capsule_clear(space: PhysicsDirectSpaceState3D, position: Vector3, excluded: RID) -> bool:
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3
	capsule.height = 1.2
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = capsule
	query.transform = Transform3D(Basis(), position)
	query.collision_mask = 1
	query.exclude = [excluded]
	return space.intersect_shape(query, 8).is_empty()


func _ray_hits(scene: Node3D, start: Vector3, end: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(start, end)
	query.collision_mask = 1
	return not scene.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func _floor_y(scene: Node3D, z: float) -> float:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(0.0, 0.45, z), Vector3(0.0, -0.2, z))
	query.collision_mask = 1
	var hit := scene.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return -999.0
	return (hit["position"] as Vector3).y


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _transform_record(player: CharacterBody3D) -> Dictionary:
	return {
		"position": player.global_position,
		"rotation_y_degrees": rad_to_deg(player.rotation.y),
		"on_floor": player.is_on_floor(),
	}


func _result(line: String) -> void:
	result_lines.append(line)
	print(line)


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures.append(message)
	printerr("ISSUE283_TEST_FAILURE: " + message)


func _write_report() -> void:
	if FileAccess.file_exists(report_path):
		_expect(false, "refusing to overwrite test report " + report_path)
		return
	var absolute := ProjectSettings.globalize_path(report_path)
	if DirAccess.make_dir_recursive_absolute(absolute.get_base_dir()) != OK:
		_expect(false, "could not create report directory " + report_path)
		return
	var output := FileAccess.open(report_path, FileAccess.WRITE)
	if output == null:
		_expect(false, "could not write report " + report_path)
		return
	report["failures"] = failures
	report["result_lines"] = result_lines
	report["candidate_status"] = "pending_operator_review"
	output.store_string(JSON.stringify(report, "\t") + "\n")
