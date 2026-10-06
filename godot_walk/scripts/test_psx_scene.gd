extends SceneTree

## Focused check for the #100 PSX presentation scene.
##
## The presentation scene renders a filtered derivative of the corridor splat
## (corridor_clean.ply), so it must NOT be validated by verify_alignment.gd's
## rendered-AABB check: that check deliberately compares the loaded cloud with
## the *source* contract's full bounds, and a filtered cloud is a strict subset.
## Weakening it would blind the review path it protects.
##
## What this checks instead, and why each check lives here:
##
## 1. The presentation node's effective world mapping equals the source
##    contract's mapping. GDGS subtracts the mean of the loaded PLY at import,
##    so filtering changes the centroid; the scene must add the report's
##    `node_translation_world` or the room shifts (~1.56 m on this asset). This
##    is the check that catches a missing or stale translation.
## 2. The filtered cloud's rendered AABB matches the cleanup report's kept
##    world bounds, so the thing on screen is the thing the report describes.
## 3. Collision, SafetyNet, PlayerSpawn and Player are identical to the accepted
##    corridor.tscn. Visual cleanup must not move the world under the player, and
##    the #85 traversal battery runs on corridor.tscn; equality here is what
##    makes its pass transfer to the presentation scene.

const PSX_SCENE := "res://scenes/corridor_psx.tscn"
const REVIEW_SCENE := "res://scenes/corridor.tscn"
const REPORT_PATH := "res://assets/corridor_splat/corridor_clean.report.json"
const MANIFEST_PATH := "res://assets/corridor_splat/alignment_manifest.json"
const SPLAT_ALIGNMENT := preload("res://scripts/splat_alignment.gd")

## Slack for float32 transform comparison.
const FLOAT_SLACK := 0.002
## Slack for the rendered filtered AABB against the report, in metres.
const BOUNDS_SLACK_M := 0.25

var _alignment = null
var _failed := false


func _initialize() -> void:
	_alignment = SPLAT_ALIGNMENT.new(MANIFEST_PATH)
	var report := _load_report()
	var ok := not report.is_empty()
	if not ok:
		_fail("could not load %s" % REPORT_PATH)
	ok = await _verify_presentation_scene(report) and ok
	ok = await _verify_world_unchanged() and ok
	if ok:
		print("OK: PSX presentation scene inherits the contract mapping and the accepted collision")
	quit(0 if ok else 1)


func _fail(message: String) -> bool:
	_failed = true
	printerr("FAIL: %s" % message)
	return false


func _check(condition: bool, message: String) -> bool:
	return true if condition else _fail(message)


func _load_report() -> Dictionary:
	var file := FileAccess.open(REPORT_PATH, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed


func _instantiate(path: String) -> Node:
	var scene: PackedScene = load(path)
	if scene == null:
		return null
	return scene.instantiate()


func _find_splat_node(node: Node) -> Node3D:
	if node is GaussianSplatNode:
		return node as Node3D
	for child in node.get_children():
		var found := _find_splat_node(child)
		if found != null:
			return found
	return null


func _verify_presentation_scene(report: Dictionary) -> bool:
	if not _alignment.is_valid():
		return _fail("alignment manifest: %s" % _alignment.load_error())
	var instance := _instantiate(PSX_SCENE)
	if instance == null:
		return _fail("could not instantiate %s" % PSX_SCENE)
	root.add_child(instance)
	await process_frame
	await process_frame

	var splat := _find_splat_node(instance)
	if splat == null:
		instance.queue_free()
		return _fail("no GaussianSplatNode in %s" % PSX_SCENE)

	var translation := _vector(report.get("node_translation_world", []))
	var expected := Transform3D(_alignment.ply_to_world().basis, translation)
	var ok := _check(_transforms_match(splat.global_transform, expected, FLOAT_SLACK),
		"presentation splat mapping %s does not equal contract basis + report translation %s"
		% [str(splat.global_transform), str(expected)])

	# The filtered cloud's rendered AABB must be the report's kept bounds.
	var rendered := _world_aabb(splat)
	var kept: Dictionary = report.get("kept_bounds_world", {})
	var low := _vector(kept.get("min", []))
	var high := _vector(kept.get("max", []))
	var expected_bounds := AABB(low, high - low)
	ok = _check(_aabb_close(rendered, expected_bounds, BOUNDS_SLACK_M),
		"filtered splat AABB %s does not match the report's kept bounds %s"
		% [str(rendered), str(expected_bounds)]) and ok

	if ok:
		print("OK: presentation splat AABB %s, node translation %s"
			% [str(rendered), str(translation)])
	instance.queue_free()
	await process_frame
	return ok


func _verify_world_unchanged() -> bool:
	var review := _instantiate(REVIEW_SCENE)
	var psx := _instantiate(PSX_SCENE)
	if review == null or psx == null:
		return _fail("could not instantiate both scenes")

	var ok := true

	# Player is a CharacterBody3D: physics moves it as soon as it enters the
	# tree, so compare its authored transform before that happens. The two
	# scenes must start the player in the same place, which is what makes the
	# visual cleanup "does not move the world under the player" true at the
	# point the player is actually placed.
	var player_a := review.get_node_or_null("Player") as Node3D
	var player_b := psx.get_node_or_null("Player") as Node3D
	if player_a == null or player_b == null:
		ok = _fail("Player is missing from one of the scenes") and ok
	else:
		ok = _check(_transforms_match(player_a.transform, player_b.transform, FLOAT_SLACK),
			"Player transform differs: review %s vs presentation %s"
			% [str(player_a.transform), str(player_b.transform)]) and ok

	root.add_child(review)
	root.add_child(psx)
	await process_frame
	await process_frame

	for node_path in ["GeneratedCollision", "SafetyNet"]:
		var a := review.get_node_or_null(node_path) as Node3D
		var b := psx.get_node_or_null(node_path) as Node3D
		if a == null or b == null:
			ok = _fail("%s is missing from one of the scenes" % node_path) and ok
			continue
		ok = _check(_transforms_match(a.global_transform, b.global_transform, FLOAT_SLACK),
			"%s differs: review %s vs presentation %s"
			% [node_path, str(a.global_transform), str(b.global_transform)]) and ok

	var spawn_a := review.get_node_or_null("PlayerSpawn") as Node3D
	var spawn_b := psx.get_node_or_null("PlayerSpawn") as Node3D
	if spawn_a == null or spawn_b == null:
		ok = _fail("PlayerSpawn is missing from one of the scenes") and ok
	else:
		ok = _check(spawn_a.global_position.distance_to(spawn_b.global_position) <= FLOAT_SLACK,
			"PlayerSpawn differs: %s vs %s"
			% [str(spawn_a.global_position), str(spawn_b.global_position)]) and ok

	if ok:
		print("OK: collision, safety net, spawn and player identical to the accepted review scene")
	review.queue_free()
	psx.queue_free()
	await process_frame
	return ok


func _world_aabb(splat: VisualInstance3D) -> AABB:
	var local: AABB = splat.get_aabb()
	if local.size == Vector3.ZERO:
		return AABB()
	var bounds := AABB(splat.global_transform * local.get_endpoint(0), Vector3.ZERO)
	for index in range(1, 8):
		bounds = bounds.expand(splat.global_transform * local.get_endpoint(index))
	return bounds


func _aabb_close(left: AABB, right: AABB, tolerance: float) -> bool:
	return (
		left.position.distance_to(right.position) <= tolerance
		and left.end.distance_to(right.end) <= tolerance
	)


func _transforms_match(left: Transform3D, right: Transform3D, tolerance: float) -> bool:
	if left.origin.distance_to(right.origin) > tolerance:
		return false
	for index in 3:
		var a: Vector3 = [left.basis.x, left.basis.y, left.basis.z][index]
		var b: Vector3 = [right.basis.x, right.basis.y, right.basis.z][index]
		if a.distance_to(b) > tolerance:
			return false
	return true


func _vector(value: Variant) -> Vector3:
	if value is Array and (value as Array).size() == 3:
		return Vector3(float(value[0]), float(value[1]), float(value[2]))
	return Vector3.ZERO
