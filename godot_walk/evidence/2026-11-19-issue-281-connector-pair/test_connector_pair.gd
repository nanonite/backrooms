extends SceneTree

## Issue #281 headless connector-pair test.
##
## Nominal pair: A = chevron-corridor-v2 north socket, yaw 90, origin
## (23.06, 0, 0); B = accepted textured_large_room hall_end at floor 0.0.
## Also runs two negative controls through the SAME geometry assertions:
## a mismatched yaw (normals not opposed) and a 0.3 m floor offset.

const ASSEMBLY := "res://evidence/2026-11-19-issue-281-connector-pair/connector_pair_scene.tscn"
const B_SOCKET := "hall_end"
const A_SOCKET := "north"
const SOCKET_X := 13.06
const SPAWN := Vector3(16.0, 0.6, 0.0)
const POSITION_TOLERANCE := 0.001
const NORMAL_TOLERANCE := 0.999

var failures: Array[String] = []
var result_lines: Array[String] = []
var report := {
	"schema_version": 1,
	"issue": 281,
	"pair": "chevron_corridor_v2_north__textured_large_room_hall_end",
	"registration_accepted": false,
	"scale_calibrated": false,
	"socket_test_status": "untested",
	"negative_controls": {},
}
var report_path := "res://evidence/2026-11-19-issue-281-connector-pair/mechanics/traversal.json"


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.trim_prefix("--report=")
	call_deferred("_run")


func _run() -> void:
	var nominal := await _load_assembly({}, "nominal")
	if nominal != null:
		await _check_nominal(nominal)
		nominal.queue_free()
		await process_frame
	await _check_mismatched_yaw()
	await _check_floor_offset()
	_write_report()
	if failures.is_empty():
		_result("ISSUE281_CONNECTOR_PAIR_TESTS_PASSED")
		quit(0)
	else:
		_result("ISSUE281_CONNECTOR_PAIR_TESTS_FAILED count=%d" % failures.size())
		quit(1)


func _load_assembly(overrides: Dictionary, label: String) -> Node3D:
	var packed := load(ASSEMBLY) as PackedScene
	_expect(packed != null, "cannot load connector-pair assembly")
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


func _check_nominal(scene: Node3D) -> void:
	var large := _socket_world(scene, "LargeRoomHallEnd", B_SOCKET)
	var chevron := _socket_world(scene, "ChevronCorridorV2", A_SOCKET)
	_expect(not large.is_empty() and not chevron.is_empty(), "nominal socket metadata is missing")
	if large.is_empty() or chevron.is_empty():
		return
	var geometry_errors := _pair_geometry_errors(large, chevron)
	_expect(geometry_errors.is_empty(), "nominal pair geometry rejected: " + str(geometry_errors))
	var xz_error := Vector2(large["position"].x - chevron["position"].x,
		large["position"].z - chevron["position"].z).length()
	var floor_delta := absf(float(large["floor_y"]) - float(chevron["floor_y"]))
	var normal_dot := (large["normal"] as Vector3).dot(chevron["normal"] as Vector3)
	_result("NOMINAL_PAIR_CENTER_XZ_ERROR %.6f" % xz_error)
	_result("NOMINAL_PAIR_FLOOR_DELTA %.6f" % floor_delta)
	_result("NOMINAL_PAIR_NORMAL_DOT %.6f" % normal_dot)
	_result("NOMINAL_PAIR_CLEAR_SIZE %s vs %s" % [str(large["size"]), str(chevron["size"])])
	report["pair_geometry"] = {
		"b_hall_end_center": large["position"],
		"a_north_center": chevron["position"],
		"center_xz_error": xz_error,
		"floor_delta": floor_delta,
		"normal_dot": normal_dot,
		"b_normal": large["normal"],
		"a_normal": chevron["normal"],
		"clear_size_b": large["size"],
		"clear_size_a": chevron["size"],
		"errors": geometry_errors,
	}
	_check_doorway_clearance(scene)
	_check_floor_continuity(scene)
	_check_aperture(scene)
	_check_footprint_overlap()
	_check_exterior_closure(scene)
	await _check_traversal(scene)


func _pair_geometry_errors(large: Dictionary, chevron: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	var xz_error := Vector2(large["position"].x - chevron["position"].x,
		large["position"].z - chevron["position"].z).length()
	if xz_error > POSITION_TOLERANCE:
		errors.append("socket floor centers do not coincide in XZ (error=%.6f)" % xz_error)
	var floor_delta := absf(float(large["floor_y"]) - float(chevron["floor_y"]))
	if floor_delta > POSITION_TOLERANCE:
		errors.append("connector floor elevations differ (delta=%.6f)" % floor_delta)
	var normal_dot := (large["normal"] as Vector3).dot(chevron["normal"] as Vector3)
	if normal_dot > -NORMAL_TOLERANCE:
		errors.append("socket normals do not oppose (dot=%.6f)" % normal_dot)
	if large["size"] != chevron["size"]:
		errors.append("socket clear dimensions differ")
	if String(large["compatibility_type"]) != String(chevron["compatibility_type"]):
		errors.append("socket compatibility types differ")
	return errors


func _check_mismatched_yaw() -> void:
	# yaw 0 with origin (13.06, 0, 10) keeps XZ centers aligned, so only the
	# normal-opposition assertion can reject it.
	var scene := await _load_assembly({
		"a_yaw_degrees": 0,
		"a_origin": Vector3(13.06, 0.0, 10.0),
	}, "mismatched_yaw")
	if scene == null:
		return
	var large := _socket_world(scene, "LargeRoomHallEnd", B_SOCKET)
	var chevron := _socket_world(scene, "ChevronCorridorV2", A_SOCKET)
	var errors := _pair_geometry_errors(large, chevron)
	var rejected := errors.size() > 0 and _contains(errors, "socket normals do not oppose")
	_expect(rejected, "mismatched-yaw negative control was not rejected by normal assertion")
	var dot := (large["normal"] as Vector3).dot(chevron["normal"] as Vector3)
	_result("NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=%.6f errors=%s" % [dot, str(errors)])
	report["negative_controls"]["mismatched_yaw"] = {
		"a_yaw_degrees": 0,
		"a_origin": Vector3(13.06, 0.0, 10.0),
		"normal_dot": dot,
		"errors": errors,
		"rejected": rejected,
	}
	scene.queue_free()
	await process_frame


func _check_floor_offset() -> void:
	# Same yaw and XZ placement as the nominal pair, with A raised 0.3 m.
	var scene := await _load_assembly({
		"a_yaw_degrees": 90,
		"a_origin": Vector3(23.06, 0.3, 0.0),
	}, "floor_offset")
	if scene == null:
		return
	var large := _socket_world(scene, "LargeRoomHallEnd", B_SOCKET)
	var chevron := _socket_world(scene, "ChevronCorridorV2", A_SOCKET)
	var errors := _pair_geometry_errors(large, chevron)
	var rejected := errors.size() > 0 and _contains(errors, "connector floor elevations differ")
	_expect(rejected, "0.3 m floor-offset negative control was not rejected by floor assertion")
	var delta := absf(float(large["floor_y"]) - float(chevron["floor_y"]))
	_result("NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=%.6f errors=%s" % [delta, str(errors)])
	report["negative_controls"]["floor_offset_0_3m"] = {
		"a_origin": Vector3(23.06, 0.3, 0.0),
		"floor_delta": delta,
		"errors": errors,
		"rejected": rejected,
	}
	scene.queue_free()
	await process_frame


func _check_doorway_clearance(scene: Node3D) -> void:
	var space := scene.get_world_3d().direct_space_state
	var excluded := (scene.get_node("Player") as CharacterBody3D).get_rid()
	var clear_count := 0
	var total := 0
	for step in range(-15, 16):
		var x := SOCKET_X + float(step) * 0.1
		total += 1
		if _capsule_clear(space, Vector3(x, 0.64, 0.0), excluded):
			clear_count += 1
	_expect(clear_count == total, "capsule cannot pass through the doorway")
	_result("DOORWAY_CAPSULE_SAMPLES_CLEAR %d/%d" % [clear_count, total])
	report["doorway_capsule_samples_clear"] = clear_count


func _check_floor_continuity(scene: Node3D) -> void:
	var supported := true
	var worst_error := 0.0
	for step in range(0, 25):
		var x := 12.8 + float(step) * 0.02
		var y := _floor_y(scene, x)
		if absf(y) > 0.02:
			supported = false
		worst_error = maxf(worst_error, absf(y))
	_expect(supported, "floor elevation is discontinuous across the socket seam")
	_result("FLOOR_CONTINUITY_SUPPORTED %s worst_abs_error=%.6f" % [str(supported), worst_error])
	report["floor_continuity"] = {"supported": supported, "worst_abs_error": worst_error}


func _check_aperture(scene: Node3D) -> void:
	var center_open := not _ray_hits(scene, Vector3(14.5, 1.1, 0.0), Vector3(11.5, 1.1, 0.0))
	var near_side_open := not _ray_hits(scene, Vector3(14.5, 1.1, 0.95), Vector3(11.5, 1.1, 0.95))
	var jamb_blocks := _ray_hits(scene, Vector3(14.5, 1.1, 1.2), Vector3(11.5, 1.1, 1.2))
	var header_blocks := _ray_hits(scene, Vector3(14.5, 2.5, 0.0), Vector3(11.5, 2.5, 0.0))
	_expect(center_open and near_side_open, "2.0 m clear aperture is blocked at center or side")
	_expect(jamb_blocks and header_blocks, "jamb or header collider is missing")
	_result("APERTURE_CENTER_OPEN %s NEAR_SIDE_OPEN %s JAMB_BLOCKS %s HEADER_BLOCKS %s" % [
		str(center_open), str(near_side_open), str(jamb_blocks), str(header_blocks)])
	report["aperture"] = {
		"center_open": center_open,
		"near_side_open": near_side_open,
		"jamb_blocks": jamb_blocks,
		"header_blocks": header_blocks,
	}


func _check_footprint_overlap() -> void:
	# Catalog footprints: B [[-6,-5] .. [13,1.5]], A [-6,6] x [-10,10] at
	# yaw 90 -> world x [13.06, 33.06], z [-6, 6].
	var overlap_x := minf(13.0, 33.06) - maxf(-6.0, 13.06)
	var overlap_z := minf(5.0, 6.0) - maxf(-5.0, -6.0)
	var no_overlap := overlap_x <= POSITION_TOLERANCE or overlap_z <= POSITION_TOLERANCE
	_expect(no_overlap, "room footprints overlap beyond the doorway")
	_result("FOOTPRINT_OVERLAP_X %.6f OVERLAP_Z %.6f NO_OVERLAP %s" % [
		overlap_x, overlap_z, str(no_overlap)])
	report["footprint_overlap"] = {
		"overlap_x": overlap_x,
		"overlap_z": overlap_z,
		"no_overlap_beyond_doorway": no_overlap,
	}


func _check_exterior_closure(scene: Node3D) -> void:
	var probes := [
		[Vector3(0.0, 1.0, 0.0), Vector3(-9.0, 1.0, 0.0), "large_room_west"],
		[Vector3(0.0, 1.0, 0.0), Vector3(0.0, 1.0, -8.0), "large_room_north"],
		[Vector3(0.0, 1.0, 0.0), Vector3(0.0, 1.0, 8.0), "large_room_south"],
		[Vector3(9.0, 1.0, 0.0), Vector3(9.0, 1.0, 5.0), "large_room_hall_side"],
		[Vector3(23.0, 1.0, 0.0), Vector3(23.0, 1.0, 9.0), "chevron_west_world"],
		[Vector3(23.0, 1.0, 0.0), Vector3(23.0, 1.0, -9.0), "chevron_east_world"],
	]
	var closed_count := 0
	for probe in probes:
		if _ray_hits(scene, probe[0], probe[1]):
			closed_count += 1
		else:
			_expect(false, "exterior boundary is open: " + String(probe[2]))
	var south_open := not _ray_hits(scene, Vector3(32.0, 1.1, 0.0), Vector3(34.0, 1.1, 0.0))
	_expect(south_open, "declared unconnected chevron south socket is not open")
	_result("EXTERIOR_BOUNDARIES_CLOSED %d/%d DECLARED_SOUTH_OPEN %s" % [
		closed_count, probes.size(), str(south_open)])
	report["exterior_closure"] = {
		"closed_probes": closed_count,
		"probe_count": probes.size(),
		"declared_unconnected_south_open": south_open,
	}


func _check_traversal(scene: Node3D) -> void:
	var player := scene.get_node_or_null("Player") as CharacterBody3D
	_expect(player != null, "assembly must have one player")
	if player == null:
		return
	_expect(player.is_on_floor(), "player spawn lacks floor support")
	var spawn_transform := _transform_record(player)
	Input.action_press("move_forward")
	await _physics_steps(180)
	Input.action_release("move_forward")
	var inside_b := player.global_position.x < 6.0 and player.is_on_floor()
	_expect(inside_b, "player did not walk from A through the doorway into B")
	var forward_transform := _transform_record(player)
	_result("TRAVERSAL_A_TO_B x=%.6f y=%.6f z=%.6f on_floor=%s" % [
		player.global_position.x, player.global_position.y, player.global_position.z,
		str(player.is_on_floor())])
	Input.action_press("move_back")
	await _physics_steps(180)
	Input.action_release("move_back")
	var returned := player.global_position.x > 15.0 and player.is_on_floor()
	_expect(returned, "player did not walk back from B through the doorway into A")
	var back_transform := _transform_record(player)
	_result("TRAVERSAL_B_TO_A x=%.6f y=%.6f z=%.6f on_floor=%s" % [
		player.global_position.x, player.global_position.y, player.global_position.z,
		str(player.is_on_floor())])
	scene.call("_reset_player")
	var reset := player.global_position.distance_to(SPAWN) < POSITION_TOLERANCE
	_expect(reset, "player reset did not restore the safe spawn")
	var reset_transform := _transform_record(player)
	_result("TRAVERSAL_RESET x=%.6f y=%.6f z=%.6f" % [
		player.global_position.x, player.global_position.y, player.global_position.z])
	report["traversal"] = {
		"spawn": spawn_transform,
		"after_a_to_b": forward_transform,
		"reached_b_main_room": inside_b,
		"after_b_to_a": back_transform,
		"returned_to_a": returned,
		"after_reset": reset_transform,
		"reset_restored_spawn": reset,
	}


func _transform_record(player: CharacterBody3D) -> Dictionary:
	return {
		"position": player.global_position,
		"rotation_y_degrees": rad_to_deg(player.rotation.y),
		"on_floor": player.is_on_floor(),
	}


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


func _floor_y(scene: Node3D, x: float) -> float:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(x, 0.45, 0.0), Vector3(x, -0.2, 0.0))
	query.collision_mask = 1
	var hit := scene.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return -999.0
	return (hit["position"] as Vector3).y


func _physics_steps(count: int) -> void:
	for _index in count:
		await physics_frame


func _result(line: String) -> void:
	result_lines.append(line)
	print(line)


func _expect(condition: bool, message: String) -> void:
	if condition:
		return
	failures.append(message)
	printerr("ISSUE281_TEST_FAILURE: " + message)


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
