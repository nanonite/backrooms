extends Node

# Static sky background for the issue-270 experiment. A ProceduralSkyMaterial
# assigned to a Sky and used as BG_SKY is rendered at infinity, so its features
# do not parallax under camera translation. Authored gradient, not source pixels.

func _ready() -> void:
	set_meta("classification", "authored")
	set_meta("rendered_at", "infinity")
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.32, 0.42, 0.58, 1.0)
	sky_material.sky_horizon_color = Color(0.78, 0.82, 0.86, 1.0)
	sky_material.ground_horizon_color = Color(0.62, 0.64, 0.66, 1.0)
	sky_material.ground_bottom_color = Color(0.20, 0.22, 0.24, 1.0)
	sky_material.sun_angle_max = 24.0
	var sky := Sky.new()
	sky.sky_material = sky_material
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	var world_environment := WorldEnvironment.new()
	world_environment.name = "WorldEnvironment"
	world_environment.environment = environment
	world_environment.set_meta("background_mode", Environment.BG_SKY)
	world_environment.set_meta("rendered_at", "infinity")
	add_child(world_environment)
