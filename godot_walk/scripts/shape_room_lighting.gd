class_name ShapeRoomLighting
extends RefCounted

## Runtime helpers for the gmap-0.8.0 light layer. Older specs never call these.

const FLICKER := preload("res://scripts/shape_room_lamp_flicker.gd")
const OMI_RANGE_M := 6.0
const EMISSION_ENERGY := 0.8
const TIER_ENERGY := {"dim": 0.45, "normal": 0.9, "bright": 1.35}
const DARK_LAMP := Color(0.10, 0.095, 0.075)


static func material_for_state(base: Material, state: String, color_temp_k: int) -> StandardMaterial3D:
	var material := base.duplicate() as StandardMaterial3D
	if state == "dead":
		material.albedo_color = DARK_LAMP
		material.emission_enabled = false
		return material
	var warm := temperature_color(color_temp_k)
	var original := material.albedo_color
	var tint := Color(original.r * warm.r, original.g * warm.g, original.b * warm.b, original.a)
	material.albedo_color = tint
	material.emission_enabled = true
	material.emission = tint
	material.emission_energy_multiplier = EMISSION_ENERGY
	return material


static func add_lamp_light(parent: Node3D, point: Array, state: Dictionary, light_spec: Dictionary,
		lamp_material: StandardMaterial3D, layer: int) -> OmniLight3D:
	var light: OmniLight3D
	if String(state.state) == "flicker":
		light = FLICKER.new() as OmniLight3D
	else:
		light = OmniLight3D.new()
	light.name = "OmniLamp_%02d" % int(state.lamp_index)
	light.position = Vector3(float(point[0]), float(light_spec.position_y), float(point[1]))
	light.omni_range = OMI_RANGE_M
	light.shadow_enabled = false
	light.light_color = temperature_color(int(light_spec.color_temp_k))
	light.light_cull_mask = 1 << (layer - 1)
	var energy := float(TIER_ENERGY[String(light_spec.tier)])
	if String(state.state) == "dead":
		light.light_energy = 0.0
	else:
		light.light_energy = energy
	if String(state.state) == "flicker":
		light.call("configure", int(state.flicker_seed), energy, lamp_material)
	parent.add_child(light)
	return light


static func temperature_color(kelvin: int) -> Color:
	var temperature := clampf(float(kelvin), 1000.0, 40000.0) / 100.0
	var red: float
	var green: float
	var blue: float
	if temperature <= 66.0:
		red = 255.0
		green = 99.4708 * log(temperature) - 161.1196
		blue = 0.0 if temperature <= 19.0 else 138.5177 * log(temperature - 10.0) - 305.0448
	else:
		red = 329.6987 * pow(temperature - 60.0, -0.1332)
		green = 288.1222 * pow(temperature - 60.0, -0.0755)
		blue = 255.0
	return Color(clampf(red / 255.0, 0.0, 1.0), clampf(green / 255.0, 0.0, 1.0), clampf(blue / 255.0, 0.0, 1.0))
