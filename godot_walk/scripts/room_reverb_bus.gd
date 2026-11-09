class_name RoomReverbBus
extends RefCounted

## One stock AudioEffectReverb on a dedicated "Footsteps" bus (#205).
##
## The bus is created in code because project.godot is frozen. Footstep and
## landing players route to it; the ambient track (#82) will get its own bus.
## A dry room leaves the effect wet at exactly zero, so the bus adds no audible
## tail, and the feature can be turned off project-wide with the setting below
## (default on). Parameters ease exponentially instead of jumping.

const PROBE := preload("res://scripts/room_acoustic_probe.gd")
const BUS_NAME := "Footsteps"
const FEATURE_SETTING := "audio/room_acoustics/footstep_reverb_enabled"
const WET_CROSSFADE_SECONDS := 0.5
const PARAMETER_SMOOTHING_SECONDS := 0.3
const EASING_RATE := 8.0
const EASING_SNAP := 0.001
const DEFAULT_ROOM_SIZE := 0.3
const DEFAULT_DAMPING := 0.5
const DEFAULT_PREDELAY_MSEC := 10.0
const DEFAULT_SPREAD := 1.0

var bus_index := -1
var effect: AudioEffectReverb
var active := false
var room_size := DEFAULT_ROOM_SIZE
var damping := DEFAULT_DAMPING
var predelay_msec := DEFAULT_PREDELAY_MSEC
var wet := 0.0
var target_wet := 0.0

var _target_room_size := DEFAULT_ROOM_SIZE
var _target_damping := DEFAULT_DAMPING
var _target_predelay_msec := DEFAULT_PREDELAY_MSEC


static func feature_enabled() -> bool:
	return bool(ProjectSettings.get_setting(FEATURE_SETTING, true))


## Create or re-use the Footsteps bus and its single reverb effect. Idempotent,
## so several test players in one process share one bus.
func ensure_bus() -> bool:
	if not feature_enabled():
		active = false
		return false
	bus_index = AudioServer.get_bus_index(BUS_NAME)
	if bus_index < 0:
		bus_index = AudioServer.bus_count
		AudioServer.add_bus()
		AudioServer.set_bus_name(bus_index, BUS_NAME)
	effect = _single_reverb()
	if effect == null:
		effect = AudioEffectReverb.new()
		AudioServer.add_bus_effect(bus_index, effect)
	effect.dry = 1.0
	effect.predelay_feedback = 0.0
	effect.spread = DEFAULT_SPREAD
	active = true
	_apply()
	return true


## Set the mapped values for the current geometry and whether the current room
## allows reverb. A dry room forces the wet target to zero.
func set_targets(mapped: Dictionary, room_reverb_enabled: bool) -> void:
	_target_room_size = clampf(float(mapped.get("room_size", DEFAULT_ROOM_SIZE)), 0.0, 1.0)
	_target_damping = clampf(float(mapped.get("damping", DEFAULT_DAMPING)), 0.0, 1.0)
	_target_predelay_msec = _clamped_predelay(float(mapped.get("predelay_msec", DEFAULT_PREDELAY_MSEC)))
	target_wet = clampf(float(mapped.get("wet", 0.0)), 0.0, 1.0) if room_reverb_enabled else 0.0


## Step the exponential easing. Called every physics frame; cheap property
## writes only, no audio synthesis.
func update(delta: float) -> void:
	if not active:
		return
	room_size = ease_value(room_size, _target_room_size, delta, PARAMETER_SMOOTHING_SECONDS)
	damping = ease_value(damping, _target_damping, delta, PARAMETER_SMOOTHING_SECONDS)
	predelay_msec = ease_value(
		predelay_msec, _target_predelay_msec, delta, PARAMETER_SMOOTHING_SECONDS)
	wet = ease_value(wet, target_wet, delta, WET_CROSSFADE_SECONDS)
	_apply()


## Exponential ease that reaches the target within `seconds` and snaps once the
## remaining difference is inaudible.
static func ease_value(current: float, target: float, delta: float, seconds: float) -> float:
	if is_equal_approx(current, target):
		return target
	if delta <= 0.0 or seconds <= 0.0:
		return current
	var weight := 1.0 - exp(-EASING_RATE * delta / seconds)
	var value := lerpf(current, target, weight)
	if absf(value - target) <= EASING_SNAP:
		return target
	return value


func _apply() -> void:
	if effect == null:
		return
	effect.room_size = room_size
	effect.damping = damping
	effect.predelay_msec = predelay_msec
	effect.wet = wet
	effect.dry = 1.0


func _single_reverb() -> AudioEffectReverb:
	var found: AudioEffectReverb
	for index in range(AudioServer.get_bus_effect_count(bus_index) - 1, -1, -1):
		var candidate := AudioServer.get_bus_effect(bus_index, index)
		if not candidate is AudioEffectReverb:
			continue
		if found == null:
			found = candidate as AudioEffectReverb
		else:
			AudioServer.remove_bus_effect(bus_index, index)
	return found


static func _clamped_predelay(value: float) -> float:
	return clampf(value, PROBE.MIN_PREDELAY_MSEC, PROBE.MAX_PREDELAY_MSEC)
