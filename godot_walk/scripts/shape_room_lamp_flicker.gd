extends OmniLight3D

## Seeded 8 Hz lamp pattern. Elapsed time, rather than frame count, selects each state.

const PATTERN_LENGTH := 32
const STEP_SECONDS := 0.125
const DIM_FACTOR := 0.08

var _elapsed := 0.0
var _base_energy := 1.0
var _base_emission := 0.8
var _pattern: PackedFloat32Array = PackedFloat32Array()
var _lamp_material: StandardMaterial3D


func configure(seed_value: int, energy: float, lamp_material: StandardMaterial3D) -> void:
	_base_energy = energy
	_lamp_material = lamp_material
	_base_emission = lamp_material.emission_energy_multiplier
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	for _index in PATTERN_LENGTH:
		_pattern.append(1.0 if rng.randf() > 0.28 else DIM_FACTOR)
	_pattern[0] = 1.0
	set_process(true)


func _process(delta: float) -> void:
	_elapsed += delta
	var step := int(floor(_elapsed / STEP_SECONDS)) % _pattern.size()
	var strength := _pattern[step]
	light_energy = _base_energy * strength
	_lamp_material.emission_energy_multiplier = _base_emission * strength
