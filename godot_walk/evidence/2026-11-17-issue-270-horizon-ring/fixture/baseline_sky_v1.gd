extends Node3D

# Baseline for issue 270: the identical static sky with the finite horizon ring
# explicitly disabled. No silhouette geometry, no collision, no floor and no
# traversal. The empty AuthoredHorizonRing group makes "disabled" structural.
const HORIZON_SPEC_PATH := "res://evidence/2026-11-17-issue-270-horizon-ring/fixture/horizon_spec_v1.json"


func _ready() -> void:
	set_meta("fixture_id", "issue_270_baseline_sky_v1")
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)
	set_meta("operator_approved", false)
	set_meta("candidate_status", "baseline_pending_review")
	set_meta("representation", "static_sky_no_finite_horizon")
	set_meta("collision_policy", "none")
	set_meta("horizon_enabled", false)
	var horizon := Node3D.new()
	horizon.name = "AuthoredHorizonRing"
	horizon.set_meta("horizon_enabled", false)
	horizon.set_meta("classification", "authored")
	add_child(horizon)
	var file := FileAccess.open(HORIZON_SPEC_PATH, FileAccess.READ)
	if file == null:
		push_error("Issue 270 baseline: could not read horizon spec")
		return
	var camera := Camera3D.new()
	camera.name = "InspectionCamera"
	camera.current = true
	add_child(camera)
