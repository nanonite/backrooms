extends SceneTree

const SCENE_PATH := "res://evidence/2026-10-24-issue-163/issue163_room.tscn"
var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_verify")


func _verify() -> void:
	var packed := load(SCENE_PATH) as PackedScene
	_expect(packed != null, "Candidate scene did not load")
	if packed == null:
		quit(1)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	await process_frame
	_check_contract(room)
	_check_visual_provenance(room)
	_check_collision(room)
	_check_psx(room)
	for failure in failures:
		printerr(failure)
	print("ISSUE163_ROOM_CONTRACT: ", "PASS" if failures.is_empty() else "FAIL")
	quit(0 if failures.is_empty() else 1)


func _check_contract(room: Node3D) -> void:
	_expect(room.get_meta("registration_accepted") == false, "Registration flag changed")
	_expect(room.get_meta("scale_calibrated") == false, "Scale flag changed")
	_expect(room.get_meta("operator_approved") == true, "Operator acceptance was not recorded")
	_expect(room.get_meta("source_video") == "data/videos/room_large.mp4", "Source provenance missing")
	_expect(room.get_node_or_null("Player") is CharacterBody3D, "Player/controller missing")
	var route: PackedVector2Array = room.get_meta("walk_route")
	_expect(route.size() >= 6, "Walk route is incomplete")


func _check_visual_provenance(room: Node3D) -> void:
	_expect(room.get_meta("hunyuan_visual_loaded") == false, "Unexpected Hunyuan output was loaded")
	_expect(room.get_meta("hunyuan_stage_status") == "blocked_vram_before_panorama", "Hunyuan limitation is not recorded")
	var visual := room.get_node_or_null("HunyuanGeneratedVisualOnly")
	_expect(visual == null, "No Hunyuan mesh should be present after the blocked stage")
	_expect(room.get_node_or_null("AuthoredVisuals/SingleColumnVisualVisual") != null, "Authored source-textured column missing")


func _check_collision(room: Node3D) -> void:
	var boundaries := room.get_node_or_null("AuthoredBoundaries")
	_expect(boundaries != null, "Authored collision container missing")
	if boundaries == null:
		return
	_expect(boundaries.find_children("*", "CollisionShape3D", true, false).size() >= 12, "Authored shell collision is incomplete")
	_expect(boundaries.get_node_or_null("ColumnObstacle/CollisionShape3D") != null, "Column collision missing")
	_expect(boundaries.get_node_or_null("EastSouthBoundary/CollisionShape3D") != null, "Boundary negative-control target missing")


func _check_psx(room: Node3D) -> void:
	var preset := room.get_node_or_null("LibraryPsxPreset")
	_expect(preset != null and not preset.originals.is_empty(), "URSC packaged PSX materials were not applied")
	var world := room.get_node_or_null("WorldEnvironment") as WorldEnvironment
	if world == null:
		for child in room.get_children():
			print("ISSUE163_CHILD: ", child.name, " class=", child.get_class())
	_expect(world != null, "WorldEnvironment is missing")
	if world != null:
		_expect(world.compositor != null, "PSX compositor is missing")
	if preset != null:
		preset.set_packaged_enabled(false)
		preset.set_packaged_enabled(true)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
