class_name MazeFollowerAudio
extends Node

## The M9 follower cue output layer (#239).
##
## Creates a dedicated ``Follower`` bus in code (``project.godot`` is frozen)
## with one fixed lowpass, and owns a small pool of 3D audio players.  The
## followers are never rendered: every node below this driver is either a
## ``Node3D`` group or an ``AudioStreamPlayer3D``, never a visual instance.
##
## Cues reuse the committed footstep stems.  No new audio asset is added.
## Volume is authored here from the cue plan's distance; the players use
## ``ATTENUATION_DISABLED`` so the distance rule has exactly one owner and can
## be checked headlessly.  Panning still comes from the 3D position.

const BUS_NAME := "Follower"
const LOWPASS_HZ := 1600.0
const LOWPASS_RESONANCE := 0.5
const POOL_SIZE := 8
const POOL_NAME := "CuePool"

const STEP_SAMPLE := "res://audio/footsteps/default/body/default_body_01.wav"
const STEP_TRANSIENT_SAMPLE := (
	"res://audio/footsteps/default/transient_soft/default_transient_soft_01.wav"
)
const DOOR_CLOSE_SAMPLE := (
	"res://audio/footsteps/land/transient_hard/land_transient_hard_01.wav"
)
const LOCK_CLICK_SAMPLE := (
	"res://audio/footsteps/metal/transient_hard/metal_transient_hard_01.wav"
)
const ROOM_TONE_SAMPLE := "res://audio/footsteps/land/body/land_body_01.wav"

var bus_index := -1
var lowpass: AudioEffectLowPassFilter
var pool_root: Node3D
var pool: Array[AudioStreamPlayer3D] = []
var played: Array[Dictionary] = []
var clock_s := 0.0
var _queue: Array[Dictionary] = []
var _cursor := 0
var _stream_cache: Dictionary = {}


func ensure_bus() -> bool:
	bus_index = AudioServer.get_bus_index(BUS_NAME)
	if bus_index < 0:
		bus_index = AudioServer.bus_count
		AudioServer.add_bus()
		AudioServer.set_bus_name(bus_index, BUS_NAME)
	lowpass = _single_lowpass()
	if lowpass == null:
		lowpass = AudioEffectLowPassFilter.new()
		AudioServer.add_bus_effect(bus_index, lowpass)
	lowpass.cutoff_hz = LOWPASS_HZ
	lowpass.resonance = LOWPASS_RESONANCE
	AudioServer.set_bus_volume_db(bus_index, 0.0)
	return true


func ensure_pool() -> void:
	if pool_root == null:
		pool_root = Node3D.new()
		pool_root.name = POOL_NAME
		add_child(pool_root)
	while pool.size() < POOL_SIZE:
		var player := AudioStreamPlayer3D.new()
		player.name = "FollowerCue_%02d" % pool.size()
		player.bus = BUS_NAME
		player.attenuation_model = AudioStreamPlayer3D.ATTENUATION_DISABLED
		player.panning_strength = 1.0
		player.max_distance = 100.0
		player.autoplay = false
		pool_root.add_child(player)
		pool.append(player)


func _ready() -> void:
	ensure_bus()
	ensure_pool()


func _process(delta: float) -> void:
	tick(delta)


## Advance the cue clock and play any delayed layer that is due.
func tick(delta: float) -> void:
	clock_s += maxf(0.0, delta)
	if _queue.is_empty():
		return
	var pending: Array[Dictionary] = []
	for entry: Dictionary in _queue:
		if float(entry.get("at_s", 0.0)) <= clock_s:
			_play(entry)
		else:
			pending.append(entry)
	_queue = pending


func play_follower_step(position: Vector3, volume_db: float, steps: int,
		spacing_s: float, pitch: float = 1.0) -> void:
	var count := clampi(steps, 1, 3)
	for index in count:
		var at_s := clock_s + float(index) * maxf(spacing_s, 0.0)
		_schedule({
			"cue": "follower_step",
			"sample": STEP_TRANSIENT_SAMPLE,
			"at_s": at_s,
			"position": position,
			"volume_db": volume_db,
			"pitch": pitch,
			"step_index": index,
		})
		_schedule({
			"cue": "follower_step",
			"sample": STEP_SAMPLE,
			"at_s": at_s,
			"position": position,
			"volume_db": volume_db - 1.0,
			"pitch": pitch * 0.96,
			"step_index": index,
		})


func play_door_close(position: Vector3, volume_db: float, pitch: float = 0.72) -> void:
	_schedule({
		"cue": "door_close",
		"sample": DOOR_CLOSE_SAMPLE,
		"at_s": clock_s,
		"position": position,
		"volume_db": volume_db,
		"pitch": pitch,
		"step_index": 0,
	})


func play_lock_click(position: Vector3, volume_db: float, delay_s: float = 0.0,
		pitch: float = 1.0) -> void:
	_schedule({
		"cue": "lock_click",
		"sample": LOCK_CLICK_SAMPLE,
		"at_s": clock_s + maxf(delay_s, 0.0),
		"position": position,
		"volume_db": volume_db,
		"pitch": pitch,
		"step_index": 0,
	})


## The same latch as ``lock_click`` plus one low room-tone tail.  The latch
## sample path and the tail sample path are deliberately constant, so the
## re-open can never become a different door sound.
func play_door_reopen(position: Vector3, volume_db: float,
		tail_delay_s: float = 0.28) -> void:
	play_lock_click(position, volume_db)
	_schedule({
		"cue": "room_tone_tail",
		"sample": ROOM_TONE_SAMPLE,
		"at_s": clock_s + maxf(tail_delay_s, 0.0),
		"position": position,
		"volume_db": volume_db - 6.0,
		"pitch": 0.55,
		"step_index": 0,
	})


func stop_all() -> void:
	_queue.clear()
	for player: AudioStreamPlayer3D in pool:
		player.stop()


## True when this driver contains no renderable node at all.
func visible_node_count() -> int:
	if pool_root == null:
		return 0
	return pool_root.find_children("*", "VisualInstance3D", true, false).size()


func snapshot() -> Dictionary:
	var bus_ready := AudioServer.get_bus_index(BUS_NAME) >= 0
	var cutoff := lowpass.cutoff_hz if lowpass != null else 0.0
	var samples := {
		"step": STEP_SAMPLE,
		"step_transient": STEP_TRANSIENT_SAMPLE,
		"door_close": DOOR_CLOSE_SAMPLE,
		"lock_click": LOCK_CLICK_SAMPLE,
		"room_tone": ROOM_TONE_SAMPLE,
	}
	var files := {}
	for key: String in samples:
		files[key] = FileAccess.file_exists(
			ProjectSettings.globalize_path(String(samples[key])))
	return {
		"bus_name": BUS_NAME,
		"bus_ready": bus_ready,
		"lowpass_hz": cutoff,
		"pool_size": pool.size(),
		"pool_players_3d": pool.all(func(player: Node) -> bool:
			return player is AudioStreamPlayer3D),
		"visible_nodes": visible_node_count(),
		"played": played.size(),
		"queued": _queue.size(),
		"samples": samples,
		"sample_files_present": files,
	}


func last_played() -> Array:
	return played.duplicate(true)


func _schedule(entry: Dictionary) -> void:
	if float(entry.get("at_s", 0.0)) <= clock_s:
		_play(entry)
		return
	_queue.append(entry)


func _play(entry: Dictionary) -> void:
	var player := _next_player()
	if player == null:
		return
	var path := String(entry.get("sample", ""))
	var stream := _stream(path)
	if stream == null:
		played.append({
			"cue": String(entry.get("cue", "")),
			"sample": path,
			"at_s": clock_s,
			"requested_at_s": float(entry.get("at_s", clock_s)),
			"load_failed": true,
		})
		return
	player.stream = stream
	player.global_position = entry.get("position", Vector3.ZERO)
	player.volume_db = float(entry.get("volume_db", 0.0))
	player.pitch_scale = float(entry.get("pitch", 1.0))
	player.play()
	played.append({
		"cue": String(entry.get("cue", "")),
		"sample": path,
		"at_s": clock_s,
		"requested_at_s": float(entry.get("at_s", clock_s)),
		"position": entry.get("position", Vector3.ZERO),
		"volume_db": player.volume_db,
		"pitch": player.pitch_scale,
		"step_index": int(entry.get("step_index", 0)),
		"bus": player.bus,
		"load_failed": false,
	})


func _next_player() -> AudioStreamPlayer3D:
	if pool.is_empty():
		return null
	for offset in pool.size():
		var index := (_cursor + offset) % pool.size()
		var player := pool[index]
		if not player.playing:
			_cursor = (index + 1) % pool.size()
			return player
	var fallback := pool[_cursor]
	_cursor = (_cursor + 1) % pool.size()
	return fallback


func _stream(path: String) -> AudioStream:
	if path.is_empty():
		return null
	if _stream_cache.has(path):
		return _stream_cache[path] as AudioStream
	if not ResourceLoader.exists(path):
		_stream_cache[path] = null
		return null
	var stream := load(path) as AudioStream
	if stream != null:
		_stream_cache[path] = stream
	return stream


func _single_lowpass() -> AudioEffectLowPassFilter:
	var found: AudioEffectLowPassFilter
	for index in range(AudioServer.get_bus_effect_count(bus_index) - 1, -1, -1):
		var candidate := AudioServer.get_bus_effect(bus_index, index)
		if not candidate is AudioEffectLowPassFilter:
			continue
		if found == null:
			found = candidate as AudioEffectLowPassFilter
		else:
			AudioServer.remove_bus_effect(bus_index, index)
	return found
