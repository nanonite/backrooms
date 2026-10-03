extends RefCounted
class_name SplatAlignment

## Runtime reader for the alignment manifest written by
## `scripts/splat_pipeline/measure_splat_frame.py`.
##
## The manifest is the single source of truth for how reconstruction-space
## Gaussian centres map into Godot world metres. This class turns it into
## Transform3D values and can state what the *effective* mapping is after GDGS
## has had its say -- which is what the verifier compares against. Equal
## serialised transforms prove nothing; equal effective world mapping does.
##
## Every getter returns a concretely typed value. GDScript cannot infer the type
## of an expression built from an untyped Dictionary read, so returning `Variant`
## and letting `:=` at the call site fail to infer would be a trap for every
## reader of this class.
##
## See `assets/<scene>/alignment_manifest.json` and the asset README for the
## narrative version of the same contract.

## Version of the manifest schema this build understands. Must match
## `splat_frame.SCHEMA_VERSION`. Bumped to 2 when the reconstruction camera path
## became a required field: a v1 manifest says nothing about where the training
## cameras land, so loading it here would leave the camera check silently absent.
const MANIFEST_SCHEMA_VERSION := 2

## GDGS' `_apply_default_orientation_if_needed` correction: a -180 degree z
## rotation. Recorded so the verifier can prove whether the addon applied it or
## whether the scene's explicit basis neutralised it.
##
## The three arguments are the basis **axes**, in Godot's `Basis(x_axis, y_axis,
## z_axis)` order, so the z axis must be `(0, 0, 1)`. Writing `(1, 0, 0)` here
## builds a matrix with determinant 0 that no rotation can ever equal, which
## silently turns `gdgs_default_correction_applied` into a check that can never
## fire -- the "the addon did not quietly rotate the room" assertion would then
## pass no matter what the addon did. `test_splat_alignment.gd` asserts the
## determinant is +1 and that the predicate does fire on a corrected basis.
const GDGS_DEFAULT_CORRECTION := Basis(
	Vector3(-1.0, 0.0, 0.0),
	Vector3(0.0, -1.0, 0.0),
	Vector3(0.0, 0.0, 1.0)
)

var _data: Dictionary = {}
var _load_error := ""


func _init(manifest_path: String) -> void:
	_load_error = ""
	var file := FileAccess.open(manifest_path, FileAccess.READ)
	if file == null:
		_load_error = "cannot open alignment manifest %s (error %d)" % [
			manifest_path, FileAccess.get_open_error(),
		]
		return
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		_load_error = "alignment manifest %s is not a JSON object" % manifest_path
		return
	_data = parsed
	var schema := int(_data.get("schema_version", -1))
	if schema != MANIFEST_SCHEMA_VERSION:
		_load_error = "alignment manifest %s has schema_version %d, expected %d" % [
			manifest_path, schema, MANIFEST_SCHEMA_VERSION,
		]


func is_valid() -> bool:
	## Whether the manifest loaded and declares a schema this build understands.
	return _load_error.is_empty()


func load_error() -> String:
	## Why loading failed, or an empty string when it succeeded.
	return _load_error


func scene_id() -> String:
	return String(_data.get("scene_id", ""))


func ply_to_world() -> Transform3D:
	## The explicit PLY-frame -> Godot-world mapping, as a Transform3D.
	##
	## This is the transform a scene must put on the splat node and on the
	## collision root.
	##
	## It is rotation plus uniform scale and **zero translation**, on purpose: the
	## GDGS resource builder already subtracts the mean Gaussian centre when it
	## imports the PLY, so the renderer already works in centroid-relative space.
	## Adding the centroid translation again would double-subtract it and shift the
	## whole room -- a silent error that still renders, still imports, and is
	## numerically checkable but easy to miss by eye. The manifest records
	## `origin_ply_units` for anyone mapping *raw PLY* points to world; a node
	## transform must not reapply it.
	var mapping: Dictionary = _data.get("ply_to_world", {})
	var columns: Array = mapping.get("basis_columns", [])
	if columns.size() != 3:
		return Transform3D.IDENTITY
	var basis := Basis(_vector(columns[0]), _vector(columns[1]), _vector(columns[2]))
	# Scaling the Basis by a single float keeps this a rotation times one uniform
	# factor, so Gaussian covariances stay valid under the shader's
	# M3 * covariance * M3^T. (Basis.scaled() takes a Vector3 and scales rows;
	# with a uniform value the two agree, but the float form states the intent.)
	return Transform3D(basis * metres_per_unit(), Vector3.ZERO)


func expected_node_transform() -> Transform3D:
	## The transform the contract requires, ignoring any addon behaviour.
	return ply_to_world()


func effective_mapping(node: Node3D) -> Transform3D:
	## Effective PLY-frame -> world mapping for a splat node, after addon behaviour.
	##
	## Uses `global_transform` because that is exactly what the renderer consumes
	## (`gaussian_scene_registry._get_node_transform`), including every ancestor
	## transform in the chain.
	return node.global_transform


func frame_up_in_world() -> Vector3:
	## The reconstruction frame's up axis, expressed in Godot world axes.
	##
	## Read from the manifest's `up_axis`/`up_sign` rather than from a basis
	## column: the frame's up axis is not its y axis for a z-up export, so the
	## wrong column returns a plausible direction that is unrelated to gravity.
	var mapping: Dictionary = _data.get("ply_to_world", {})
	var up_axis := String(mapping.get("up_axis", "y"))
	var up_sign := int(mapping.get("up_sign", 1))
	if up_axis != "x" and up_axis != "y" and up_axis != "z":
		return Vector3.UP
	var rotation := ply_to_world().basis.orthonormalized()
	return rotation * _axis_vector(up_axis) * float(up_sign)


func _axis_vector(name: String) -> Vector3:
	match name:
		"x":
			return Vector3.RIGHT
		"z":
			return Vector3.BACK
		_:
			return Vector3.UP


func gdgs_default_correction_applied(node: Node3D) -> bool:
	## Whether the addon's implicit z-180 correction is present on this node.
	##
	## GDGS applies `GDGS_DEFAULT_CORRECTION` exactly when the node's incoming
	## basis is identity, so a scene carrying an explicit basis neutralises it.
	## Comparing the node's live basis against the correction detects that case
	## without needing the pre-addon value. Stating this explicitly is what lets
	## the verifier assert each automatic transform was applied exactly once
	## (zero times here) instead of inferring it from a matrix comparison.
	##
	## Only meaningful on an unscaled basis: the correction has no scale, so it
	## is compared against a normalised copy and scale is checked separately
	## against the contract.
	return node.transform.basis.orthonormalized().is_equal_approx(GDGS_DEFAULT_CORRECTION)


func metres_per_unit() -> float:
	return float(_data.get("ply_to_world", {}).get("metres_per_unit", 1.0))


func scale_reference_kind() -> String:
	return String(_data.get("scale_reference", {}).get("kind", ""))


func scale_reference_target_metres() -> float:
	return float(_data.get("scale_reference", {}).get("target_metres", 0.0))


func scale_reference_raw_units() -> float:
	return float(_data.get("scale_reference", {}).get("raw_units", 0.0))


func scale_reference_spread() -> float:
	return float(_data.get("scale_reference", {}).get("raw_units_spread", 0.0))


func scale_tolerance_metres() -> float:
	var reference: Dictionary = _data.get("scale_reference", {})
	var raw_units := float(reference.get("raw_units", 0.0))
	var target := float(reference.get("target_metres", 0.0))
	if raw_units <= 0.0:
		return 0.0
	# Two standard deviations of the raw measurement, floored at 10% of the
	# target so a suspiciously tight reconstruction cannot demand a tolerance no
	# real scene will meet. Mirrors splat_frame.ScaleReference.tolerance_metres.
	var relative := 2.0 * float(reference.get("raw_units_spread", 0.0)) / raw_units
	return maxf(target * relative, 0.10 * target)


func floor_height() -> float:
	return float(_data.get("collider", {}).get("floor_height", 0.0))


func ceiling_height() -> float:
	return float(_data.get("collider", {}).get("ceiling_height", 0.0))


func room_bounds() -> AABB:
	## The measured/observed room extent as a world-space AABB.
	var collider: Dictionary = _data.get("collider", {})
	var low := _vector(collider.get("min_corner", [0.0, 0.0, 0.0]))
	var high := _vector(collider.get("max_corner", [0.0, 0.0, 0.0]))
	return AABB(low, high - low)


func observed_bounds() -> AABB:
	## World bounds of the measured room interior.
	##
	## This, not the full cloud or the padded camera window, is what the floor and
	## ceiling landmarks must sit on the extremes of: the full extent is dominated
	## by far-field floaters, and the camera window is deliberately padded beyond
	## the walls, so either would make a correctly aligned scene fail on a floater.
	var bounds: Dictionary = _data.get("splat_bounds", {})
	var low := _vector(bounds.get("observed_min", [0.0, 0.0, 0.0]))
	var high := _vector(bounds.get("observed_max", [0.0, 0.0, 0.0]))
	return AABB(low, high - low)


func core_bounds() -> AABB:
	## World bounds of the camera-path analysis window, padded beyond the walls.
	var bounds: Dictionary = _data.get("splat_bounds", {})
	var low := _vector(bounds.get("core_min", [0.0, 0.0, 0.0]))
	var high := _vector(bounds.get("core_max", [0.0, 0.0, 0.0]))
	return AABB(low, high - low)


func full_bounds() -> AABB:
	## World bounds of every Gaussian the renderer loads, floaters included.
	var bounds: Dictionary = _data.get("splat_bounds", {})
	var low := _vector(bounds.get("full_min", [0.0, 0.0, 0.0]))
	var high := _vector(bounds.get("full_max", [0.0, 0.0, 0.0]))
	return AABB(low, high - low)


func camera_count() -> int:
	## How many registered reconstruction cameras the contract recorded.
	return int(_data.get("cameras", {}).get("count", 0))


func camera_bounds() -> AABB:
	## World bounds of the reconstruction camera path.
	var cameras: Dictionary = _data.get("cameras", {})
	var low := _vector(cameras.get("world_min", [0.0, 0.0, 0.0]))
	var high := _vector(cameras.get("world_max", [0.0, 0.0, 0.0]))
	return AABB(low, high - low)


func camera_heights() -> Vector3:
	## Camera heights as ``(min, mean, max)`` in Godot world metres.
	var cameras: Dictionary = _data.get("cameras", {})
	return Vector3(
		float(cameras.get("height_min_m", 0.0)),
		float(cameras.get("height_mean_m", 0.0)),
		float(cameras.get("height_max_m", 0.0))
	)


func camera_eye_height() -> float:
	## Mean camera height above the floor, in metres.
	##
	## The strongest available cross-check that the up axis and the scale are both
	## right: a person walking a corridor records an eye height, so a value far
	## from one means the mapping put the room on its side or at the wrong size.
	return camera_heights().y - floor_height()


func landmark(name: String) -> Vector3:
	## Return a named landmark in Godot world metres.
	return _vector(_data.get("landmarks", {}).get(name, [0.0, 0.0, 0.0]))


func has_landmark(name: String) -> bool:
	return _data.get("landmarks", {}).has(name)


func landmark_names() -> Array:
	return _data.get("landmarks", {}).keys()


func expected_spawn() -> Vector3:
	## Where the contract places PlayerSpawn, in Godot world metres.
	return _vector(_data.get("spawn", [0.0, 0.0, 0.0]))


func spawn_clearance() -> float:
	## Required height of PlayerSpawn above the floor, in metres.
	return float(_data.get("spawn_clearance_m", 0.0))


func expected_splat_count() -> int:
	return int(_data.get("asset", {}).get("splat_count", 0))


func footage_kind() -> String:
	return String(_data.get("capture", {}).get("footage_kind", ""))


func asset_md5() -> String:
	return String(_data.get("asset", {}).get("md5", ""))


func walls_measured() -> bool:
	## Whether horizontal wall planes were actually resolved, or only observed.
	return bool(_data.get("capture", {}).get("walls_measured", false))


func automatic_transforms() -> Array[Dictionary]:
	## Every transform the addon applies on its own, for display and review.
	var entries: Array[Dictionary] = []
	for entry: Dictionary in _data.get("automatic_transforms", []):
		entries.append({
			"stage": String(entry.get("stage", "")),
			"source": String(entry.get("source", "")),
			"summary": String(entry.get("summary", "")),
			"neutralised": bool(entry.get("neutralised", false)),
			"neutralised_by": String(entry.get("neutralised_by", "")),
		})
	return entries


func _vector(value: Variant) -> Vector3:
	if value is Array and (value as Array).size() == 3:
		return Vector3(float(value[0]), float(value[1]), float(value[2]))
	return Vector3.ZERO