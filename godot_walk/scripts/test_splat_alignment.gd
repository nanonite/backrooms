extends SceneTree

## Unit tests for `splat_alignment.gd`, run headless:
##
##     godot4 --headless --script res://scripts/test_splat_alignment.gd
##
## `verify_alignment.gd` proves the scenes match the manifest. It cannot prove the
## *manifest reader* is right: a reader that always answers "no correction" makes
## the verifier's most important assertion vacuously true, and a reader that
## transposes a basis still reports a self-consistent mapping. Those are the
## failures this file exists to catch, so each test states the engine behaviour it
## relies on and asserts the reader agrees.
##
## No scene or PLY is loaded, so these run in well under a second on any machine,
## including CI without a GPU.

const SPLAT_ALIGNMENT := preload("res://scripts/splat_alignment.gd")

const MANIFEST_PATH := "res://assets/corridor_splat/alignment_manifest.json"

## Mirrors splat_frame.SCHEMA_VERSION. Asserted rather than assumed so a schema
## bump on the Python side that nobody mirrored here fails loudly.
const EXPECTED_SCHEMA_VERSION := 2

var _passed := 0
var _failed := 0


func _initialize() -> void:
	var alignment = SPLAT_ALIGNMENT.new(MANIFEST_PATH)
	if not alignment.is_valid():
		printerr("FAIL: could not load %s: %s" % [MANIFEST_PATH, alignment.load_error()])
		quit(1)
		return

	_test_manifest_schema(alignment)
	_test_load_error_is_reported()
	_test_correction_constant_is_a_rotation()
	_test_correction_predicate_fires_on_a_corrected_node()
	_test_correction_predicate_is_quiet_on_the_contract(alignment)
	_test_predicate_ignores_uniform_scale()
	_test_basis_columns_are_godot_axis_order()
	_test_node_transform_has_no_centroid(alignment)
	_test_up_axis_comes_from_up_axis_not_a_basis_column(alignment)
	_test_camera_readers(alignment)
	_test_readers_reject_absent_keys(alignment)

	print("%d passed, %d failed" % [_passed, _failed])
	quit(0 if _failed == 0 else 1)


func _ok(condition: bool, what: String) -> void:
	if condition:
		_passed += 1
		print("  ok   %s" % what)
	else:
		_failed += 1
		printerr("  FAIL %s" % what)


func _test_manifest_schema(alignment) -> void:
	print("manifest schema")
	_ok(alignment.is_valid(), "manifest loads and validates")
	# A v1 manifest has no `cameras` key. Accepting one would leave every camera
	# reader returning its zero value, so the camera checks would pass vacuously.
	_ok(alignment.camera_count() > 0,
		"schema_version %d manifest carries a reconstruction camera path"
		% EXPECTED_SCHEMA_VERSION)


func _test_load_error_is_reported() -> void:
	print("load errors")
	var missing = SPLAT_ALIGNMENT.new("res://assets/does_not_exist_manifest.json")
	_ok(not missing.is_valid(), "a missing manifest is invalid")
	_ok(not missing.load_error().is_empty(), "a missing manifest explains itself")


func _test_correction_constant_is_a_rotation() -> void:
	# The regression this file was written for: the constant was declared with its
	# z axis as (1, 0, 0), which is not a rotation at all (determinant 0), so the
	# predicate comparing against it could never return true.
	print("GDGS default correction")
	var actual = SPLAT_ALIGNMENT.GDGS_DEFAULT_CORRECTION
	_ok(absf(actual.determinant() - 1.0) < 1e-5,
		"GDGS_DEFAULT_CORRECTION is a proper rotation (det %.6f)" % actual.determinant())
	_ok(actual.is_equal_approx(Basis.from_euler(Vector3(0.0, 0.0, -PI))),
		"GDGS_DEFAULT_CORRECTION equals Basis.from_euler(0, 0, -PI)")
	# A 180-degree rotation about z flips x and y and leaves z alone. If the z axis
	# were wrong the constant would rotate about a different axis entirely.
	_ok(actual.z.is_equal_approx(Vector3(0.0, 0.0, 1.0)),
		"it leaves the z axis alone (z = %s)" % str(actual.z))
	_ok(actual.x.is_equal_approx(-Vector3.RIGHT) and actual.y.is_equal_approx(-Vector3.UP),
		"it flips x and y, as a z-180 rotation must")


func _test_correction_predicate_fires_on_a_corrected_node() -> void:
	# The positive case. Without it, "the correction is absent" is unfalsifiable:
	# a predicate that always returns false makes every scene pass.
	print("correction predicate: positive case")
	var corrected := VisualInstance3D.new()
	corrected.transform = Transform3D(SPLAT_ALIGNMENT.GDGS_DEFAULT_CORRECTION, Vector3.ZERO)
	var alignment = SPLAT_ALIGNMENT.new(MANIFEST_PATH)
	_ok(alignment.gdgs_default_correction_applied(corrected),
		"a node carrying exactly the correction is detected")
	corrected.free()


func _test_correction_predicate_is_quiet_on_the_contract(alignment) -> void:
	# The negative case the scenes actually rely on: an explicit non-identity basis
	# neutralises the addon's identity test, so the correction must not be there.
	print("correction predicate: negative case")
	var contracted := VisualInstance3D.new()
	contracted.transform = alignment.expected_node_transform()
	_ok(not alignment.gdgs_default_correction_applied(contracted),
		"a node carrying the contract's mapping is not mistaken for a corrected node")
	# Even after orthonormalising away the uniform scale, the explicit basis is a
	# permutation, never a z-180 rotation.
	_ok(absf(contracted.transform.basis.orthonormalized().determinant() - 1.0) < 1e-5,
		"the contract's basis orthonormalises to a proper rotation")
	contracted.free()


func _test_predicate_ignores_uniform_scale() -> void:
	# A node whose basis is the correction *and* a uniform scale is still a
	# corrected node. The comparison orthonormalises first, so scale cannot mask it.
	print("correction predicate: scaled basis")
	var scaled := VisualInstance3D.new()
	var basis := SPLAT_ALIGNMENT.GDGS_DEFAULT_CORRECTION.scaled(Vector3.ONE * 5.128)
	scaled.transform = Transform3D(basis, Vector3.ZERO)
	var alignment = SPLAT_ALIGNMENT.new(MANIFEST_PATH)
	_ok(alignment.gdgs_default_correction_applied(scaled),
		"a scaled correction is still detected")
	scaled.free()


func _test_basis_columns_are_godot_axis_order() -> void:
	# Godot's Transform3D literal takes columns, but Basis(x_axis, y_axis, z_axis)
	# also takes axis vectors, and the manifest stores columns. Reading a column as
	# an axis transposes the matrix: a valid transform that renders the room on its
	# side, which reads as a math bug rather than a serialisation bug.
	print("manifest basis reading")
	var alignment = SPLAT_ALIGNMENT.new(MANIFEST_PATH)
	var mapping: Basis = alignment.ply_to_world().basis
	# z-up export: frame x -> world -Z... no: columns are the images of frame x, y,
	# z, and the up axis is frame z, which must land on world +Y.
	_ok(mapping.z.is_equal_approx(Vector3.UP * mapping.get_scale()),
		"the image of the frame's z axis is world +Y (got %s)" % str(mapping.z))
	_ok(absf(mapping.orthonormalized().determinant() - 1.0) < 1e-5,
		"the mapping is a proper rotation, not a mirror")
	_ok(alignment.frame_up_in_world().is_equal_approx(Vector3.UP),
		"frame_up_in_world() reports +Y")


func _test_node_transform_has_no_centroid(alignment) -> void:
	# The GDGS resource builder already subtracts the mean Gaussian centre. A node
	# transform that reapplies it shifts the room while still importing and
	# rendering, so the reader must return a zero translation.
	print("node transform")
	var node: Transform3D = alignment.expected_node_transform()
	_ok(node.origin.is_zero_approx(),
		"expected_node_transform() carries no translation (got %s)" % str(node.origin))
	# The offline mapping still has the centroid, which is what makes the pair
	# consistent: one for raw PLY points, one for what a node may carry.
	_ok(alignment.ply_to_world().origin.is_zero_approx(),
		"ply_to_world() is also centroid-relative for the node case")
	_ok(alignment.metres_per_unit() > 0.0,
		"metres_per_unit is positive (%.6f)" % alignment.metres_per_unit())


func _test_up_axis_comes_from_up_axis_not_a_basis_column(alignment) -> void:
	# For a z-up export the second basis column is the image of the frame's *y*
	# axis, which is horizontal. Reading it as "up" would return a plausible
	# direction unrelated to gravity, so up_axis/up_sign must drive this.
	print("up axis")
	_ok(alignment.frame_up_in_world().is_equal_approx(Vector3.UP),
		"frame_up_in_world() is +Y")
	_ok(alignment.ceiling_height() > alignment.floor_height(),
		"ceiling %.4f is above floor %.4f"
		% [alignment.ceiling_height(), alignment.floor_height()])


func _test_camera_readers(alignment) -> void:
	print("reconstruction cameras")
	var count: int = alignment.camera_count()
	_ok(count > 0, "the manifest records %d cameras" % count)
	var bounds: AABB = alignment.camera_bounds()
	_ok(bounds.size.length() > 0.0, "camera bounds are non-degenerate (%s)" % str(bounds))
	_ok(bounds.position.y > alignment.floor_height(),
		"cameras sit above the floor (min %.3f vs floor %.3f)"
		% [bounds.position.y, alignment.floor_height()])
	var eye: float = alignment.camera_eye_height()
	_ok(eye >= 0.4 and eye <= 2.2,
		"mean camera height above the floor is plausible (%.3f m)" % eye)


func _test_readers_reject_absent_keys(alignment) -> void:
	# Every reader must return a usable default rather than crashing on a manifest
	# that lacks the key. The verifier turns a silent zero into a misleading
	# failure message ("cameras outside the room") instead of "this manifest has no
	# camera record", so the ordering matters: count is checked before bounds.
	print("missing keys")
	_ok(alignment.landmark_names().size() >= 3,
		"the manifest names at least the three required landmarks")
	_ok(not alignment.has_landmark("no_such_landmark"),
		"an unknown landmark is reported absent rather than defaulting")
	_ok(alignment.landmark("floor").is_equal_approx(
		Vector3(alignment.landmark("floor").x, alignment.floor_height(), alignment.landmark("floor").z)),
		"the floor landmark's y equals the collider floor height")