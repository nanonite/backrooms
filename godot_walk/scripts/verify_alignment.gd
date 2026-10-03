extends SceneTree

## Runtime proof that both corridor scenes honour the alignment contract.
##
## What this checks, and why each check lives here rather than in an editor
## screenshot:
##
## 1. The manifest loads and self-consistently describes one frame.
## 2. Each scene's splat node has an **effective** world mapping equal to the
##    contract, read after GDGS has applied whatever it applies automatically.
## 3. GDGS' implicit z-180 correction fired in **neither** scene, because the
##    explicit basis neutralises it. A scene relying on the addon's
##    identity-transform guess is the stale behaviour this issue removed.
## 4. Both scenes agree on the effective mapping, not merely on serialised
##    transforms.
## 5. Predicted landmarks land where the manifest says, and the floor->ceiling
##    distance equals the declared scale within tolerance.
## 6. The floor landmark is the lowest point of the rendered splat AABB and the
##    ceiling landmark the highest. That is the numeric form of "it is not on its
##    side", and it is the check that would have caught the original bug.
## 7. Player spawn sits inside the room at the contract's height above the floor.
## 8. The reconstruction camera path lands where the contract says, inside the
##    measured room, at a plausible walking eye height. This is the only check
##    whose reference data (the COLMAP model) was never used to derive the room, so
##    it is the one that can catch the room validating itself.
##
## A screenshot or an import check cannot do any of this: both passed while the
## splat was rendered lying on its side with the wrong scale.

const MANIFEST_PATH := "res://assets/corridor_splat/alignment_manifest.json"

## label -> scene path. Both scenes render the same splat and must agree.
const SCENES := [
	["walkable", "res://scenes/corridor.tscn"],
	["inspection", "res://scenes/corridor_splat.tscn"],
]

## Slack for float32 matrix comparison. Godot stores transforms as float32, so
## exact equality is unavailable even when the values agree to the last digit.
const FLOAT_SLACK := 0.002

## Slack for landmark and clearance distances, in metres.
const TOLERANCE_M := 0.05

## Slack when comparing the rendered AABB with the contract's predicted one, in
## metres. Generous: the renderer derives its AABB from the same float32 Gaussian
## centres the manifest was computed from, but through an import cache and a
## centroid subtraction, so small drift is expected and benign.
const BOUNDS_SLACK_M := 0.25

## Slack for the floor/ceiling landmarks against the core bounds, in metres.
## Larger than TOLERANCE_M because a landmark is measured from a density mode
## while the bound is a hard min/max: floaters sit just outside the sheets.
const FLOOR_TOLERANCE_M := 0.5

## Most the rendered splat may extend past the room before the mismatch is worth
## reporting. Floaters reach ~140 m from the centroid on this asset, so the room
## being a small part of the cloud is normal, not a scale error.
const ROOM_INSIDE_SPLAT_SLACK_M := 1.0

## Slack when requiring the reconstruction camera path to lie inside the room, in
## metres. Mirrors splat_frame.CAMERA_ROOM_SLACK_M: the room's horizontal extents
## are observation bounds derived from the camera window, so demanding exact
## containment would demand the two records agree by construction.
const CAMERA_ROOM_SLACK_M := 2.0

## Plausible band for the mean camera height above the floor, in metres. Mirrors
## splat_frame.EYE_HEIGHT_RANGE_M. A walking camera sits at roughly eye height;
## outside this band the mapping has the room on its side or at the wrong size.
const EYE_HEIGHT_MIN_M := 0.4
const EYE_HEIGHT_MAX_M := 2.2

## Loaded by path rather than by `class_name`: the global class cache is only
## rebuilt when the editor scans the project, so a CI run of this script would
## otherwise fail to resolve the name on a fresh checkout.
const SPLAT_ALIGNMENT := preload("res://scripts/splat_alignment.gd")

## Untyped on purpose; see the note on SPLAT_ALIGNMENT.
var _alignment = null
var _failed := false


## Uses `_initialize`, not `_init`: nodes only get valid `global_transform` values
## once the tree is running, and reading them during construction returns identity
## while printing engine errors. Awaiting a frame after each `add_child` is what
## makes "after runtime initialization" in the acceptance criteria true rather
## than aspirational.
func _initialize() -> void:
	_alignment = SPLAT_ALIGNMENT.new(MANIFEST_PATH)
	var ok := _verify_manifest()
	ok = await _verify_scenes() and ok
	if ok:
		print("OK: alignment contract verified across %d scenes" % SCENES.size())
	quit(0 if ok else 1)


func _fail(message: String) -> bool:
	_failed = true
	printerr("FAIL: %s" % message)
	return false


func _check(condition: bool, message: String) -> bool:
	return true if condition else _fail(message)


# --------------------------------------------------------------------------
# 1. the manifest
# --------------------------------------------------------------------------

func _verify_manifest() -> bool:
	if not _alignment.is_valid():
		return _fail("manifest: %s" % _alignment.load_error())

	var ok := _check(_alignment.metres_per_unit() > 0.0,
		"metres_per_unit must be positive, got %.6f" % _alignment.metres_per_unit())
	var kind: String = _alignment.scale_reference_kind()
	ok = _check(kind == "measured_reference" or kind == "chosen",
		"scale_reference.kind must be 'measured_reference' or 'chosen', got '%s'" % kind) and ok
	ok = _check(_alignment.ceiling_height() > _alignment.floor_height(),
		"ceiling %.4f must be above floor %.4f"
		% [_alignment.ceiling_height(), _alignment.floor_height()]) and ok

	for name: String in ["floor", "ceiling", "room_centre"]:
		ok = _check(_alignment.has_landmark(name),
			"manifest is missing the '%s' landmark" % name) and ok
	if not ok:
		return ok

	# The declared scale must reproduce the declared height.
	var measured: float = _alignment.ceiling_height() - _alignment.floor_height()
	var declared: float = _alignment.scale_reference_target_metres()
	ok = _check(absf(measured - declared) <= TOLERANCE_M,
		"floor->ceiling spans %.4f m but the scale reference declares %.4f m"
		% [measured, declared]) and ok

	# The contract's own up axis must be Godot's +Y. Checked on the unit-length
	# rotation, not the scaled basis: the second basis *column* is the image of the
	# reconstruction frame's y axis, which is not the up axis for this z-up export,
	# and reading basis.y here would test the wrong thing and pass by coincidence.
	var contract_up: Vector3 = _alignment.frame_up_in_world()
	ok = _check(contract_up.is_equal_approx(Vector3.UP),
		"the contract's up axis must map to Godot +Y, got %s" % str(contract_up)) and ok
	var linear: Basis = _alignment.ply_to_world().basis.orthonormalized()
	ok = _check(absf(linear.determinant() - 1.0) <= FLOAT_SLACK,
		"the contract's mapping must be a proper rotation (determinant %.6f), or it "
		% linear.determinant()
		+ "mirrors the room and flips Gaussian handedness") and ok

	# A scene without a PlayerSpawn marker is exempt: it is a render-inspection
	# scene, so only scenes that claim one are checked against the contract.
	if ok:
		print("OK: manifest scene_id=%s scale=%.6f m/unit (%s)"
			% [_alignment.scene_id(), _alignment.metres_per_unit(), kind])
		print("  reference: %.4f +/- %.4f reconstruction units -> %.2f m (tolerance %.3f m)"
			% [_alignment.scale_reference_raw_units(), _alignment.scale_reference_spread(),
			   declared, _alignment.scale_tolerance_metres()])
		print("  walls measured: %s" % ("yes" if _alignment.walls_measured() else
			"no -- horizontal extents are observed bounds, not measured walls"))
		_report_automatic_transforms()
	return ok


func _report_automatic_transforms() -> void:
	for entry: Dictionary in _alignment.automatic_transforms():
		var state := "applied once by addon" if not bool(entry["neutralised"]) \
			else "neutralised by scene (applied zero times)"
		print("  AUTO[%s] %s" % [String(entry["stage"]), state])
		print("        %s" % String(entry["source"]))


# --------------------------------------------------------------------------
# 2-4. both scenes
# --------------------------------------------------------------------------

func _verify_scenes() -> bool:
	var expected: Transform3D = _alignment.expected_node_transform()
	var mappings: Array[Transform3D] = []
	var ok := true

	for scene_entry: Array in SCENES:
		var label := String(scene_entry[0])
		var instance := _instantiate(String(scene_entry[1]))
		if instance == null:
			ok = _fail("%s: could not load %s" % [label, String(scene_entry[1])]) and ok
			continue
		root.add_child(instance)
		# Let the tree settle so GDGS' _enter_tree transform rewrite, the render
		# manager's deferred registration and every ancestor transform are in
		# effect before anything is read.
		await process_frame
		await process_frame
		ok = _verify_scene(label, instance, expected, mappings) and ok
		instance.queue_free()
		await process_frame

	if ok and mappings.size() == SCENES.size():
		for index in range(1, mappings.size()):
			ok = _check(_transforms_match(mappings[0], mappings[index], FLOAT_SLACK),
				"scenes disagree on their effective mapping: %s vs %s"
				% [str(mappings[0]), str(mappings[index])]) and ok
	return ok


func _verify_scene(
	label: String, instance: Node, expected: Transform3D, mappings: Array[Transform3D]
) -> bool:
	var splat := _find_splat_node(instance)
	if splat == null:
		return _fail("%s: no GaussianSplatNode in the instantiated scene" % label)

	var ok := true
	# GDGS rewrites the node transform in _enter_tree, so read the live value.
	var effective: Transform3D = _alignment.effective_mapping(splat)
	ok = _check(_transforms_match(effective, expected, FLOAT_SLACK),
		"%s: effective splat mapping %s does not match the contract %s"
		% [label, str(effective), str(expected)]) and ok
	ok = _check(not _alignment.gdgs_default_correction_applied(splat),
		"%s: GDGS' implicit z-180 correction is present, so an automatic transform "
		% label
		+ "slipped past the contract; give the node an explicit basis") and ok

	mappings.append(effective)
	ok = _verify_cameras(label) and ok
	ok = _verify_landmarks(label, splat) and ok
	ok = _verify_spawn(label, instance) and ok
	return ok


# --------------------------------------------------------------------------
# 8. reconstruction cameras
# --------------------------------------------------------------------------

func _verify_cameras(label: String) -> bool:
	# The cameras are the only part of the contract that no scene file contains:
	# the splat node, collider and spawn are all hand-authored, so without this
	# the check would be the room agreeing with itself. The cameras come from the
	# COLMAP model, so requiring them to land inside the room closes the loop from
	# the reconstruction the splat was actually trained against.
	var count: int = _alignment.camera_count()
	if count <= 0:
		return _fail("%s: the manifest records no reconstruction cameras" % label)
	# The camera path must not be degenerate: a zero-size bound means the manifest
	# recorded an empty path that the containment check below would pass vacuously.
	var cameras: AABB = _alignment.camera_bounds()
	if cameras.size == Vector3.ZERO:
		return _fail("%s: the manifest's camera path has zero extent" % label)
	var room: AABB = _alignment.room_bounds()
	var ok := true
	ok = _check(_aabb_inside(cameras, room, CAMERA_ROOM_SLACK_M),
		"%s: reconstruction cameras %s are outside the calibrated room %s; the "
		% [label, str(cameras), str(room)]
		+ "camera path and the room were mapped through different frames") and ok

	# The strongest single check on both the up axis and the metric scale: a
	# walking camera records an eye height. A room on its side, or at the retired
	# mesh's scale, moves this out of the plausible band.
	var eye: float = _alignment.camera_eye_height()
	ok = _check(eye >= EYE_HEIGHT_MIN_M and eye <= EYE_HEIGHT_MAX_M,
		"%s: mean camera height is %.4f m above the floor, outside the plausible "
		% [label, eye]
		+ "walking range %.2f..%.2f m" % [EYE_HEIGHT_MIN_M, EYE_HEIGHT_MAX_M]) and ok
	if ok:
		print("OK: %s reconstruction cameras %d land inside the room, eye height %.3f m"
			% [label, count, eye])
	return ok


# --------------------------------------------------------------------------
# 5-6. landmarks against the rendered geometry
# --------------------------------------------------------------------------

func _verify_landmarks(label: String, splat: Node3D) -> bool:
	var rendered := _world_aabb(splat)
	if rendered.size == Vector3.ZERO:
		return _fail("%s: splat AABB is degenerate; cannot validate landmarks" % label)

	# Compare the rendered cloud against the *predicted* full extent. A mismatch
	# means a stale imported .res cache, or a scene still pointing at a different
	# PLY -- both of which pass an import check and a screenshot.
	var predicted: AABB = _alignment.full_bounds()
	var ok := _check(_aabb_close(rendered, predicted, BOUNDS_SLACK_M),
		"%s: rendered splat AABB %s does not match the contract's predicted %s"
		% [label, str(rendered), str(predicted)])
	if not ok:
		return false

	var observed: AABB = _alignment.observed_bounds()
	var core: AABB = _alignment.core_bounds()
	var floor: Vector3 = _alignment.landmark("floor")
	var ceiling: Vector3 = _alignment.landmark("ceiling")
	ok = _check(_contains_point(core, floor),
		"%s: floor landmark %s is outside the camera-path core %s"
		% [label, str(floor), str(core)])
	ok = _check(_contains_point(core, ceiling),
		"%s: ceiling landmark %s is outside the camera-path core %s"
		% [label, str(ceiling), str(core)]) and ok

	# "Not on its side" as a number: the floor landmark is the lowest point of the
	# measured room and the ceiling the highest.
	ok = _check(absf(floor.y - observed.position.y) <= FLOOR_TOLERANCE_M,
		"%s: floor landmark y=%.4f is not the lowest point of the observed room (%.4f); "
		% [label, floor.y, observed.position.y]
		+ "the up axis is still mapped wrongly") and ok
	ok = _check(absf(ceiling.y - observed.end.y) <= FLOOR_TOLERANCE_M,
		"%s: ceiling landmark y=%.4f is not the highest point of the observed room (%.4f)"
		% [label, ceiling.y, observed.end.y]) and ok
	ok = _check(ceiling.y > floor.y,
		"%s: the ceiling landmark must be above the floor landmark" % label) and ok

	# The measured room must sit inside the rendered cloud. A volume ratio is
	# deliberately *not* checked: this splat's floaters extend ~140 m from the
	# centroid, so the bounding volume is thousands of times the room's while the
	# geometry is correct. The scale evidence is the numeric full-bounds match
	# above plus the landmark distance, not a volume heuristic.
	var room: AABB = _alignment.room_bounds()
	ok = _check(_contains_point(rendered, room.get_center()),
		"%s: room centre is outside the rendered splat AABB %s" % [label, str(rendered)]) and ok
	ok = _check(_aabb_inside(room, rendered, ROOM_INSIDE_SPLAT_SLACK_M),
		"%s: room %s is not contained in the rendered splat AABB %s"
		% [label, str(room), str(rendered)]) and ok

	# The landmark separation must equal the declared metric scale.
	var measured_height: float = floor.distance_to(ceiling)
	var declared: float = _alignment.scale_reference_target_metres()
	ok = _check(absf(measured_height - declared) <= TOLERANCE_M,
		"%s: landmarks span %.4f m, but the contract declares %.4f m (tolerance %.4f m)"
		% [label, measured_height, declared, _alignment.scale_tolerance_metres()]) and ok
	ok = _check(absf(measured_height - (_alignment.ceiling_height() - _alignment.floor_height())) <= TOLERANCE_M,
		"%s: landmarks span %.4f m but the collider heights span %.4f m"
		% [label, measured_height,
		   _alignment.ceiling_height() - _alignment.floor_height()]) and ok

	if ok:
		print("OK: %s landmarks floor=%s ceiling=%s height=%.4f m, up axis correct"
			% [label, str(floor), str(ceiling), measured_height])
		print("    rendered splat AABB %s" % str(rendered))
		print("    observed room      %s" % str(observed))
		print("    camera-path core   %s" % str(core))
	return ok


func _aabb_close(left: AABB, right: AABB, tolerance: float) -> bool:
	## Whether two AABBs agree on both corners within a tolerance.
	return (
		left.position.distance_to(right.position) <= tolerance
		and left.end.distance_to(right.end) <= tolerance
	)


func _aabb_inside(inner: AABB, outer: AABB, tolerance: float) -> bool:
	## Whether ``inner`` lies within ``outer``, allowing ``tolerance`` of slack.
	return (
		inner.position.x >= outer.position.x - tolerance
		and inner.position.y >= outer.position.y - tolerance
		and inner.position.z >= outer.position.z - tolerance
		and inner.end.x <= outer.end.x + tolerance
		and inner.end.y <= outer.end.y + tolerance
		and inner.end.z <= outer.end.z + tolerance
	)


func _contains_point(box: AABB, point: Vector3) -> bool:
	## Whether an AABB contains a point, with the same float32 slack used elsewhere.
	#
	# AABB.has_point/encloses take an AABB argument in Godot 4, so this spells the
	# per-axis comparison out rather than trying to adapt them.
	return (
		point.x >= box.position.x - FLOAT_SLACK
		and point.y >= box.position.y - FLOAT_SLACK
		and point.z >= box.position.z - FLOAT_SLACK
		and point.x <= box.end.x + FLOAT_SLACK
		and point.y <= box.end.y + FLOAT_SLACK
		and point.z <= box.end.z + FLOAT_SLACK
	)





func _world_aabb(splat: VisualInstance3D) -> AABB:
	# Transform all eight local AABB corners: a rotated AABB is not its own
	# axis-aligned bound, and using only two corners silently halves the extent.
	var local: AABB = splat.get_aabb()
	if local.size == Vector3.ZERO:
		return AABB()
	var bounds := AABB(splat.global_transform * local.get_endpoint(0), Vector3.ZERO)
	for index in range(1, 8):
		bounds = bounds.expand(splat.global_transform * local.get_endpoint(index))
	return bounds


# --------------------------------------------------------------------------
# 7. spawn
# --------------------------------------------------------------------------

func _verify_spawn(label: String, instance: Node) -> bool:
	# A missing spawn is a failure, not a skip. Every scene listed in SCENES renders
	# the contract's splat and is expected to be enterable at the contract's spawn;
	# treating absence as "probably an inspection scene" would let a walkable scene
	# lose its spawn and pass, which is precisely the sort of quiet regression this
	# verifier exists to catch.
	var spawn := instance.get_node_or_null("PlayerSpawn")
	if spawn == null:
		return _fail("%s: PlayerSpawn marker is missing" % label)
	if not spawn is Marker3D:
		return _fail("%s: PlayerSpawn must be a Marker3D" % label)

	var actual: Vector3 = (spawn as Node3D).global_position
	var expected: Vector3 = _alignment.expected_spawn()
	var clearance: float = actual.y - _alignment.floor_height()
	var room: AABB = _alignment.room_bounds()
	var ok := _check(actual.distance_to(expected) <= FLOAT_SLACK,
		"%s: PlayerSpawn at %s but the contract places it at %s"
		% [label, str(actual), str(expected)])
	ok = _check(absf(clearance - _alignment.spawn_clearance()) <= TOLERANCE_M,
		"%s: PlayerSpawn is %.4f m above the floor, contract requires %.4f m"
		% [label, clearance, _alignment.spawn_clearance()]) and ok
	ok = _check(_contains_point(room, actual),
		"%s: PlayerSpawn %s is outside the room %s" % [label, str(actual), str(room)]) and ok
	if ok:
		print("OK: %s spawn %s is %.3f m above the floor at %.4f m"
			% [label, str(actual), clearance, _alignment.floor_height()])
	return ok


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

func _instantiate(scene_path: String) -> Node:
	var scene: PackedScene = load(scene_path)
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


func _transforms_match(left: Transform3D, right: Transform3D, tolerance: float) -> bool:
	if left.origin.distance_to(right.origin) > tolerance:
		return false
	return _basis_match(left.basis, right.basis, tolerance)


func _basis_match(left: Basis, right: Basis, tolerance: float) -> bool:
	var left_columns := [left.x, left.y, left.z]
	var right_columns := [right.x, right.y, right.z]
	for index in 3:
		var a: Vector3 = left_columns[index]
		var b: Vector3 = right_columns[index]
		if a.distance_to(b) > tolerance:
			return false
	return true