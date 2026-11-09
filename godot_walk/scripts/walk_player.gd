extends "res://scripts/player.gd"

## Generated-maze walkthrough player: base movement, hold-Shift sprint (#191),
## layered material-aware footsteps (#200, #203) and Spacebar jump (#206).
## Applied via set_script in generative_map_assembly.gd only, so every other
## scene keeps the unmodified player.gd and project.godot stays untouched.
##
## Each step takes one pooled player per layer: a brightness-tuned transient,
## a modal body and a granular texture. The 0-8 ms per-layer onset offsets are
## baked into the stems, so playback needs neither a timer allocation nor a
## per-frame DSP pass.

const SPRINT_SPEED: float = 9.0
const SPRINT_ACTION := &"sprint"
const WALK_STRIDE_M := 0.7
const SPRINT_STRIDE_M := 1.0
const LANDING_AIR_SECONDS := 0.3
const JUMP_ACTION := &"jump"
const JUMP_HEIGHT_M := 0.9
## v = sqrt(2 * g * h) for the 9.8 m/s^2 project gravity.
const JUMP_VELOCITY := 4.2
## A take-off is a quiet step: a quarter of walk force, below walk volume.
const JUMP_TAKEOFF_FORCE := 0.25
const JUMP_TAKEOFF_VOLUME_DB := -3.0
const VARIANT_COUNT := 4
const DEFAULT_TAG := "default"
const LAND_TAG := "land"
const ACOUSTIC_TAGS := ["carpet", "concrete", "tile", "plaster", "metal", "wood", "debris"]
const AUDIO_ROOT := "res://audio/footsteps"
const TRANSIENT_SOFT := "transient_soft"
const TRANSIENT_HARD := "transient_hard"
const BODY := "body"
const TEXTURE := "texture"
const LAYERS := [TRANSIENT_SOFT, TRANSIENT_HARD, BODY, TEXTURE]
const POOL_PER_LAYER := 4
const WALK_FORCE := 0.5
const SPRINT_FORCE := 0.8
const LAND_FORCE := 1.0
const BRIGHTNESS_LOW_FORCE := 0.30
const BRIGHTNESS_HIGH_FORCE := 0.80
const TRANSIENT_GAIN_LOW := 0.75
const TRANSIENT_GAIN_HIGH := 1.0
const BODY_GAIN_LOW := 0.85
const BODY_GAIN_HIGH := 1.0
const TEXTURE_GAIN_LOW := 0.50
const TEXTURE_GAIN_HIGH := 1.0
const PITCH_JITTER := 0.05
const WALK_VOLUME_DB := 0.0
const SPRINT_VOLUME_DB := 1.5
const LANDING_VOLUME_DB := 0.0

signal footstep_event(tag: String, sprinting: bool)
signal landing_event()
signal jump_event(tag: String)

var _distance_since_step: float = 0.0
var _air_time: float = 0.0
var _was_on_floor: bool = true
var _layer_streams: Dictionary = {}
var _last_variant: Dictionary = {}
var _unknown_floors: Dictionary = {}
var _pools: Dictionary = {}
var _pool_cursor: Dictionary = {}
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	super()
	_register_sprint_action()
	_rng.randomize()
	_create_pools()
	_load_footstep_streams()


func _physics_process(delta: float) -> void:
	var on_floor := is_on_floor()
	if not on_floor:
		velocity.y -= gravity * delta
		_air_time += delta
	elif not _was_on_floor:
		if _air_time > LANDING_AIR_SECONDS:
			_play_landing()
			landing_event.emit()
		_distance_since_step = 0.0
		_air_time = 0.0
	else:
		_air_time = 0.0
	_was_on_floor = on_floor

	var jumped := on_floor and Input.is_action_just_pressed(JUMP_ACTION)
	if jumped:
		_take_off()

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := Vector3(input_dir.x, 0.0, input_dir.y).rotated(Vector3.UP, rotation.y)

	var sprinting := Input.is_action_pressed(SPRINT_ACTION)
	var speed := SPRINT_SPEED if sprinting else SPEED
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed

	var start := global_position
	move_and_slide()
	if is_on_floor() and not jumped:
		var moved := Vector2(global_position.x - start.x, global_position.z - start.z).length()
		if moved > 0.0001:
			_distance_since_step += moved
			var stride := SPRINT_STRIDE_M if sprinting else WALK_STRIDE_M
			while _distance_since_step >= stride:
				_distance_since_step -= stride
				_play_step(sprinting)


func _play_step(sprinting: bool) -> void:
	var tag := _floor_acoustic()
	var play_tag := tag if _has_streams(tag) else DEFAULT_TAG
	var force := _impact_force(Vector2(velocity.x, velocity.z).length())
	var master := SPRINT_VOLUME_DB if sprinting else WALK_VOLUME_DB
	_play_layer(
		play_tag, _choose_transient(force), master,
		_layer_gain(TRANSIENT_GAIN_LOW, TRANSIENT_GAIN_HIGH, force), _pitch()
	)
	_play_layer(
		play_tag, BODY, master,
		_layer_gain(BODY_GAIN_LOW, BODY_GAIN_HIGH, force), _pitch()
	)
	_play_layer(
		play_tag, TEXTURE, master,
		_layer_gain(TEXTURE_GAIN_LOW, TEXTURE_GAIN_HIGH, force), _pitch()
	)
	footstep_event.emit(tag, sprinting)


func _play_landing() -> void:
	_play_layer(
		LAND_TAG, TRANSIENT_HARD, LANDING_VOLUME_DB,
		_layer_gain(TRANSIENT_GAIN_LOW, TRANSIENT_GAIN_HIGH, LAND_FORCE), _pitch()
	)
	_play_layer(
		LAND_TAG, BODY, LANDING_VOLUME_DB,
		_layer_gain(BODY_GAIN_LOW, BODY_GAIN_HIGH, LAND_FORCE), _pitch()
	)
	_play_layer(
		LAND_TAG, TEXTURE, LANDING_VOLUME_DB,
		_layer_gain(TEXTURE_GAIN_LOW, TEXTURE_GAIN_HIGH, LAND_FORCE), _pitch()
	)


func _take_off() -> void:
	velocity.y = JUMP_VELOCITY
	var tag := _floor_acoustic()
	_play_takeoff(tag)
	jump_event.emit(tag)


func _play_takeoff(tag: String) -> void:
	var play_tag := tag if _has_streams(tag) else DEFAULT_TAG
	var force := JUMP_TAKEOFF_FORCE
	_play_layer(
		play_tag, _choose_transient(force), JUMP_TAKEOFF_VOLUME_DB,
		_layer_gain(TRANSIENT_GAIN_LOW, TRANSIENT_GAIN_HIGH, force), _pitch()
	)
	_play_layer(
		play_tag, BODY, JUMP_TAKEOFF_VOLUME_DB,
		_layer_gain(BODY_GAIN_LOW, BODY_GAIN_HIGH, force), _pitch()
	)
	_play_layer(
		play_tag, TEXTURE, JUMP_TAKEOFF_VOLUME_DB,
		_layer_gain(TEXTURE_GAIN_LOW, TEXTURE_GAIN_HIGH, force), _pitch()
	)


func _play_layer(tag: String, layer: String, master_db: float, gain: float, pitch: float) -> void:
	var key := _stream_key(tag, layer)
	if not _layer_streams.has(key):
		return
	var variants: Array = _layer_streams[key]
	var player := _acquire_player(layer)
	player.stream = variants[_pick_variant(key, variants.size())]
	player.volume_db = master_db + linear_to_db(gain)
	player.pitch_scale = pitch
	player.play()


func _impact_force(speed: float) -> float:
	if speed <= SPEED:
		return lerpf(WALK_FORCE * 0.6, WALK_FORCE, clampf(speed / SPEED, 0.0, 1.0))
	var sprint_ratio := clampf((speed - SPEED) / (SPRINT_SPEED - SPEED), 0.0, 1.0)
	return lerpf(WALK_FORCE, SPRINT_FORCE, sprint_ratio)


func _layer_gain(gain_low: float, gain_high: float, force: float) -> float:
	# Normalised so a walk-force step reproduces the baked -19.9 dBFS RMS mix.
	var reference := lerpf(gain_low, gain_high, WALK_FORCE)
	return lerpf(gain_low, gain_high, force) / reference


func _choose_transient(force: float) -> String:
	var brightness := clampf(
		(force - BRIGHTNESS_LOW_FORCE) / (BRIGHTNESS_HIGH_FORCE - BRIGHTNESS_LOW_FORCE),
		0.0,
		1.0
	)
	# Dithered gain crossfade: the hard tier's probability follows force, so the
	# average brightness tracks force continuously while one transient player is
	# enough for a step.
	return TRANSIENT_HARD if _rng.randf() < brightness else TRANSIENT_SOFT


func _pitch() -> float:
	return 1.0 + _rng.randf_range(-PITCH_JITTER, PITCH_JITTER)


func _floor_acoustic() -> String:
	var space := get_world_3d().direct_space_state
	var from := global_position + Vector3.UP * 0.4
	var to := global_position + Vector3.DOWN * 0.6
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collision_mask = 1
	query.exclude = [get_rid()]
	var hit := space.intersect_ray(query)
	if hit.is_empty():
		return DEFAULT_TAG
	var collider := hit.collider as Node
	var tag := String(collider.get_meta("surface_acoustic", "")) if collider != null else ""
	if not tag.is_empty():
		return tag
	var path := String(collider.get_path()) if collider != null else "<none>"
	if not _unknown_floors.has(path):
		_unknown_floors[path] = true
		print("footsteps: unknown floor %s; using default" % path)
	return DEFAULT_TAG


func _pick_variant(key: String, count: int) -> int:
	var previous := int(_last_variant.get(key, -1))
	var index := _rng.randi_range(0, count - 1)
	if count > 1 and index == previous:
		index = (index + 1) % count
	_last_variant[key] = index
	return index


func _create_pools() -> void:
	for layer: String in LAYERS:
		var players: Array = []
		for index in POOL_PER_LAYER:
			var player := AudioStreamPlayer.new()
			player.name = "Footstep_%s_%d" % [layer, index]
			player.volume_db = WALK_VOLUME_DB
			add_child(player)
			players.append(player)
		_pools[layer] = players
		_pool_cursor[layer] = 0


func _acquire_player(layer: String) -> AudioStreamPlayer:
	var players: Array = _pools[layer]
	var cursor := int(_pool_cursor[layer])
	var player := players[cursor] as AudioStreamPlayer
	_pool_cursor[layer] = (cursor + 1) % players.size()
	if player.playing:
		player.stop()
	return player


func _has_streams(tag: String) -> bool:
	return _layer_streams.has(_stream_key(tag, BODY))


func _stream_key(tag: String, layer: String) -> String:
	return "%s/%s" % [tag, layer]


func _load_footstep_streams() -> void:
	for tag: String in ACOUSTIC_TAGS + [DEFAULT_TAG]:
		for layer: String in LAYERS:
			_load_tag_layer(tag, layer, VARIANT_COUNT)
	for layer: String in LAYERS:
		_load_tag_layer(LAND_TAG, layer, 1)


func _load_tag_layer(tag: String, layer: String, variant_count: int) -> void:
	var variants: Array = []
	for variant in range(1, variant_count + 1):
		var stream := _load_stream(tag, layer, variant)
		if stream != null:
			variants.append(stream)
	if not variants.is_empty():
		_layer_streams[_stream_key(tag, layer)] = variants


func _load_stream(tag: String, layer: String, variant: int) -> AudioStreamWAV:
	var path := ProjectSettings.globalize_path(_footstep_path(tag, layer, variant))
	if not FileAccess.file_exists(path):
		push_warning("Missing footstep sample: %s" % path)
		return null
	return AudioStreamWAV.load_from_file(path)


func _footstep_path(tag: String, layer: String, variant: int) -> String:
	return "%s/%s/%s/%s_%s_%02d.wav" % [AUDIO_ROOT, tag, layer, tag, layer, variant]


static func _register_sprint_action() -> void:
	if InputMap.has_action(SPRINT_ACTION):
		return
	InputMap.add_action(SPRINT_ACTION)
	for side: KeyLocation in [KEY_LOCATION_LEFT, KEY_LOCATION_RIGHT]:
		var event := InputEventKey.new()
		event.physical_keycode = KEY_SHIFT
		event.location = side
		InputMap.action_add_event(SPRINT_ACTION, event)
