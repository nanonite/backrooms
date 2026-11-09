extends "res://scripts/player.gd"

## Generated-maze walkthrough player: base movement, hold-Shift sprint (#191) and
## material-aware footsteps (#200). Applied via set_script in
## generative_map_assembly.gd only, so every other scene keeps the unmodified
## player.gd and project.godot stays untouched.

const SPRINT_SPEED: float = 9.0
const SPRINT_ACTION := &"sprint"
const WALK_STRIDE_M := 0.7
const SPRINT_STRIDE_M := 1.0
const LANDING_AIR_SECONDS := 0.3
const VARIANT_COUNT := 4
const DEFAULT_TAG := "default"
const ACOUSTIC_TAGS := ["carpet", "concrete", "tile", "plaster", "metal", "wood", "debris"]
const AUDIO_ROOT := "res://audio/footsteps"
const WALK_VOLUME_DB := -18.0
const SPRINT_VOLUME_DB := -14.0
const LANDING_VOLUME_DB := -15.0
const PITCH_JITTER := 0.05

signal footstep_event(tag: String, sprinting: bool)
signal landing_event()

var _distance_since_step: float = 0.0
var _air_time: float = 0.0
var _was_on_floor: bool = true
var _streams: Dictionary = {}
var _last_variant: Dictionary = {}
var _unknown_floors: Dictionary = {}
var _audio: AudioStreamPlayer
var _land_stream: AudioStream
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	super()
	_register_sprint_action()
	_rng.randomize()
	_audio = AudioStreamPlayer.new()
	_audio.name = "FootstepAudio"
	_audio.volume_db = WALK_VOLUME_DB
	add_child(_audio)
	_load_footstep_streams()


func _physics_process(delta: float) -> void:
	var on_floor := is_on_floor()
	if not on_floor:
		velocity.y -= gravity * delta
		_air_time += delta
	elif not _was_on_floor:
		if _air_time > LANDING_AIR_SECONDS:
			_distance_since_step = 0.0
			_play_landing()
			landing_event.emit()
		_air_time = 0.0
	else:
		_air_time = 0.0
	_was_on_floor = on_floor

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := Vector3(input_dir.x, 0.0, input_dir.y).rotated(Vector3.UP, rotation.y)

	var sprinting := Input.is_action_pressed(SPRINT_ACTION)
	var speed := SPRINT_SPEED if sprinting else SPEED
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed

	var start := global_position
	move_and_slide()
	if is_on_floor():
		var moved := Vector2(global_position.x - start.x, global_position.z - start.z).length()
		if moved > 0.0001:
			_distance_since_step += moved
			var stride := SPRINT_STRIDE_M if sprinting else WALK_STRIDE_M
			while _distance_since_step >= stride:
				_distance_since_step -= stride
				_play_step(sprinting)


func _play_step(sprinting: bool) -> void:
	var tag := _floor_acoustic()
	var play_tag := tag if _streams.has(tag) else DEFAULT_TAG
	var variants: Array = _streams.get(play_tag, [])
	if variants.is_empty() or _audio == null:
		footstep_event.emit(tag, sprinting)
		return
	var index := _pick_variant(play_tag, variants.size())
	_audio.stream = variants[index]
	_audio.volume_db = SPRINT_VOLUME_DB if sprinting else WALK_VOLUME_DB
	_audio.pitch_scale = 1.0 + _rng.randf_range(-PITCH_JITTER, PITCH_JITTER)
	_audio.play()
	footstep_event.emit(tag, sprinting)


func _play_landing() -> void:
	if _land_stream != null and _audio != null:
		_audio.stream = _land_stream
		_audio.volume_db = LANDING_VOLUME_DB
		_audio.pitch_scale = 1.0 + _rng.randf_range(-PITCH_JITTER, PITCH_JITTER)
		_audio.play()


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


func _pick_variant(tag: String, count: int) -> int:
	var previous := int(_last_variant.get(tag, -1))
	var index := _rng.randi_range(0, count - 1)
	if count > 1 and index == previous:
		index = (index + 1) % count
	_last_variant[tag] = index
	return index


func _load_footstep_streams() -> void:
	for tag: String in ACOUSTIC_TAGS + [DEFAULT_TAG]:
		var variants: Array = []
		for variant in range(1, VARIANT_COUNT + 1):
			var stream := _load_stream(tag, variant)
			if stream != null:
				variants.append(stream)
		if not variants.is_empty():
			_streams[tag] = variants
	_land_stream = _load_stream("land", 1)


func _load_stream(tag: String, variant: int) -> AudioStreamWAV:
	var path := ProjectSettings.globalize_path(_footstep_path(tag, variant))
	if not FileAccess.file_exists(path):
		push_warning("Missing footstep sample: %s" % path)
		return null
	return AudioStreamWAV.load_from_file(path)


func _footstep_path(tag: String, variant: int) -> String:
	return "%s/%s/%s_%02d.wav" % [AUDIO_ROOT, tag, tag, variant]


static func _register_sprint_action() -> void:
	if InputMap.has_action(SPRINT_ACTION):
		return
	InputMap.add_action(SPRINT_ACTION)
	for side: KeyLocation in [KEY_LOCATION_LEFT, KEY_LOCATION_RIGHT]:
		var event := InputEventKey.new()
		event.physical_keycode = KEY_SHIFT
		event.location = side
		InputMap.action_add_event(SPRINT_ACTION, event)
