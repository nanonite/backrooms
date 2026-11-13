class_name MazeLightController
extends RefCounted

## Runtime lamp-state application for the M2 follower edit (#232).
##
## The committed map and the instanced room are not rebuilt. One lamp's mesh
## material and OmniLight are replaced in place, so every other cell, mesh and
## layer keeps its state. ``tag_room`` records the pristine inputs the setter
## needs; a module or landmark room is never tagged for editing.

const LIGHTING := preload("res://scripts/shape_room_lighting.gd")
const FLICKER := preload("res://scripts/shape_room_lamp_flicker.gd")

const LAMP_STATES := ["on", "flicker", "dead"]
const LAMP_MESH_PREFIX := "CeilingLight_"
const LAMP_LIGHT_PREFIX := "OmniLamp_"
const LANDMARK_MESH_PREFIX := "LandmarkLampRing_"
const DEFAULT_TIER_ENERGY := 0.9


static func tag_room(room: Node3D, spec: Dictionary, base_material: Material) -> void:
	if room == null or not spec.has("light"):
		return
	room.set_meta("maze_lamp_base_material", base_material)
	room.set_meta("maze_lamp_tier", String(spec.light.tier))
	room.set_meta("maze_lamp_color_temp_k", int(spec.light.color_temp_k))
	var states := {}
	var seeds := {}
	var mesh_paths := {}
	var light_paths := {}
	var landmark := is_landmark(spec)
	for lamp: Dictionary in spec.light.lamps:
		var index := int(lamp.lamp_index)
		states[index] = String(lamp.state)
		seeds[index] = int(lamp.flicker_seed)
		var meshes: Array[NodePath] = []
		for node: Node in _lamp_meshes(room, index, landmark):
			meshes.append(room.get_path_to(node))
		mesh_paths[index] = meshes
		var light := _lamp_light(room, index)
		if light != null:
			light_paths[index] = room.get_path_to(light)
	room.set_meta("maze_lamp_states", states)
	room.set_meta("maze_lamp_flicker_seeds", seeds)
	room.set_meta("maze_lamp_meshes", mesh_paths)
	room.set_meta("maze_lamp_lights", light_paths)


static func is_landmark(spec: Dictionary) -> bool:
	return spec.has("landmark") and spec["landmark"] != null


static func lamp_states(room: Node3D) -> Array:
	if room == null or not room.has_meta("maze_lamp_states"):
		return []
	var states: Dictionary = room.get_meta("maze_lamp_states")
	var result := []
	var indices: Array = states.keys()
	indices.sort()
	for index: int in indices:
		result.append({"lamp_index": index, "state": String(states[index])})
	return result


static func lamp_state(room: Node3D, lamp_index: int) -> String:
	if room == null or not room.has_meta("maze_lamp_states"):
		return ""
	var states: Dictionary = room.get_meta("maze_lamp_states")
	return String(states.get(lamp_index, ""))


static func lamp_flicker_seeds(room: Node3D) -> Array:
	if room == null or not room.has_meta("maze_lamp_flicker_seeds"):
		return []
	var seeds: Dictionary = room.get_meta("maze_lamp_flicker_seeds")
	var result := []
	var indices: Array = seeds.keys()
	indices.sort()
	for index: int in indices:
		result.append({"lamp_index": index, "flicker_seed": int(seeds[index])})
	return result


static func apply_lamp_state(room: Node3D, lamp_index: int, state: String,
		flicker_seed: int = -1) -> bool:
	if room == null or not room.has_meta("maze_lamp_states"):
		return false
	if not LAMP_STATES.has(state):
		return false
	var states: Dictionary = room.get_meta("maze_lamp_states")
	if not states.has(lamp_index):
		return false
	var seeds: Dictionary = room.get_meta("maze_lamp_flicker_seeds")
	var seed_value := int(seeds.get(lamp_index, 0)) if flicker_seed < 0 else flicker_seed
	if state == "flicker" and seed_value < 0:
		return false
	return _apply_one(room, lamp_index, state, seed_value)


static func apply_override(room: Node3D, override: Dictionary) -> bool:
	"""Apply one folded ``{lamp_state: [...], lamp_flicker: [...]}`` record."""
	if room == null or not room.has_meta("maze_lamp_states"):
		return false
	var states_raw: Variant = override.get("lamp_state", [])
	var flicker_raw: Variant = override.get("lamp_flicker", [])
	if not states_raw is Array or not flicker_raw is Array:
		return false
	var states_override: Array = states_raw
	var flicker_override: Array = flicker_raw
	var states: Dictionary = (room.get_meta("maze_lamp_states") as Dictionary).duplicate(true)
	var seeds: Dictionary = (room.get_meta("maze_lamp_flicker_seeds") as Dictionary).duplicate(true)
	for raw_state: Variant in states_override:
		if not raw_state is Dictionary:
			return false
		var entry: Dictionary = raw_state
		var index := int(entry.get("lamp_index", -1))
		var state := String(entry.get("state", ""))
		if not states.has(index) or not LAMP_STATES.has(state):
			return false
		states[index] = state
	for raw_flicker: Variant in flicker_override:
		if not raw_flicker is Dictionary:
			return false
		var entry: Dictionary = raw_flicker
		var index := int(entry.get("lamp_index", -1))
		var seed := int(entry.get("flicker_seed", -1))
		if not seeds.has(index) or seed < 0:
			return false
		seeds[index] = seed
	var indices: Array = states.keys()
	indices.sort()
	var current_states: Dictionary = room.get_meta("maze_lamp_states")
	var current_seeds: Dictionary = room.get_meta("maze_lamp_flicker_seeds")
	for index: int in indices:
		var state := String(states[index])
		var seed := int(seeds[index])
		if String(current_states.get(index, "")) == state and int(current_seeds.get(index, -1)) == seed:
			continue
		if not _apply_one(room, index, state, seed):
			return false
	return true


static func _apply_one(room: Node3D, lamp_index: int, state: String, flicker_seed: int) -> bool:
	var base_material := room.get_meta("maze_lamp_base_material", null) as StandardMaterial3D
	var mesh_paths: Dictionary = room.get_meta("maze_lamp_meshes", {})
	var light_paths: Dictionary = room.get_meta("maze_lamp_lights", {})
	if base_material == null or not mesh_paths.has(lamp_index) or not light_paths.has(lamp_index):
		return false
	var old_light := room.get_node_or_null(light_paths[lamp_index]) as OmniLight3D
	if old_light == null:
		return false
	var color_temp := int(room.get_meta("maze_lamp_color_temp_k", 4000))
	var material := LIGHTING.material_for_state(base_material, state, color_temp)
	for path: NodePath in mesh_paths[lamp_index]:
		var mesh := room.get_node_or_null(path) as MeshInstance3D
		if mesh == null:
			return false
		mesh.material_override = material
	var energy := _tier_energy(room)
	var fresh := _fresh_light(old_light, state, energy, flicker_seed, material)
	if fresh == null:
		return false
	var parent := old_light.get_parent()
	var position := old_light.get_index()
	parent.remove_child(old_light)
	old_light.free()
	parent.add_child(fresh)
	parent.move_child(fresh, position)
	var states: Dictionary = room.get_meta("maze_lamp_states")
	var seeds: Dictionary = room.get_meta("maze_lamp_flicker_seeds")
	states[lamp_index] = state
	seeds[lamp_index] = flicker_seed
	light_paths[lamp_index] = room.get_path_to(fresh)
	return true


static func _fresh_light(old: OmniLight3D, state: String, energy: float,
		flicker_seed: int, material: StandardMaterial3D) -> OmniLight3D:
	var fresh: OmniLight3D
	if state == "flicker":
		fresh = FLICKER.new() as OmniLight3D
	else:
		fresh = OmniLight3D.new()
	fresh.name = old.name
	fresh.position = old.position
	fresh.rotation = old.rotation
	fresh.scale = old.scale
	fresh.light_color = old.light_color
	fresh.omni_range = old.omni_range
	fresh.omni_attenuation = old.omni_attenuation
	fresh.shadow_enabled = old.shadow_enabled
	fresh.light_cull_mask = old.light_cull_mask
	fresh.light_specular = old.light_specular
	fresh.layers = old.layers
	fresh.visible = old.visible
	if state == "flicker":
		fresh.call("configure", flicker_seed, energy, material)
	fresh.light_energy = 0.0 if state == "dead" else energy
	return fresh


static func _tier_energy(room: Node3D) -> float:
	var tier := String(room.get_meta("maze_lamp_tier", "normal"))
	return float(LIGHTING.TIER_ENERGY.get(tier, DEFAULT_TIER_ENERGY))


static func _lamp_meshes(room: Node3D, lamp_index: int, landmark: bool) -> Array:
	if landmark and lamp_index == 0:
		return room.find_children(LANDMARK_MESH_PREFIX + "*", "MeshInstance3D", true, false)
	var mesh := room.find_child("%s%02d" % [LAMP_MESH_PREFIX, lamp_index], true, false)
	return [] if mesh == null else [mesh]


static func _lamp_light(room: Node3D, lamp_index: int) -> OmniLight3D:
	return room.find_child("%s%02d" % [LAMP_LIGHT_PREFIX, lamp_index], true, false) as OmniLight3D
