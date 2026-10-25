extends RefCounted

var floor_ticks := 0
var ticks := 0
var distance := 0.0
var max_step := 0.0
var safety_contacts := 0
var stale_contact_references := 0
var support_bodies := {}
var previous := Vector3.ZERO
var started := false


func sample(player: CharacterBody3D) -> void:
	ticks += 1
	if player.is_on_floor():
		floor_ticks += 1
	if started:
		var step := player.global_position.distance_to(previous)
		distance += Vector2(player.position.x - previous.x, player.position.z - previous.z).length()
		max_step = maxf(max_step, step)
	previous = player.global_position
	started = true
	for index in player.get_slide_collision_count():
		var hit := player.get_slide_collision(index)
		var body: Node = hit.get_collider()
		if body == null:
			stale_contact_references += 1
			continue
		if body.name == "SafetyNet":
			safety_contacts += 1
		if hit.get_normal().y > 0.7:
			support_bodies[str(body.name)] = support_bodies.get(str(body.name), 0) + 1


func report() -> Dictionary:
	return {"ticks": ticks, "floor_fraction": float(floor_ticks) / maxi(1, ticks),
		"distance_m": distance, "max_step_m": max_step,
		"safety_contacts": safety_contacts, "stale_contact_references": stale_contact_references,
		"support_bodies": support_bodies}
