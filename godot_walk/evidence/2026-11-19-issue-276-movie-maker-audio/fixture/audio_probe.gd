extends SceneTree
## Issue #276 probe: play a known synthetic signal while Movie Maker renders.
## Modes: tone (440 Hz sine), clipped (full-scale alternating samples),
## tone_then_clip (2 s tone then 2 s clip) and spatial3d (tone through an
## AudioStreamPlayer3D with a Camera3D listener). The movie writer is enabled by
## --write-movie on the command line; this script only supplies a deterministic
## audio source and stays alive until --quit-after stops the run.

const MIX_RATE := 48000
const SECONDS := 4.0
const AMPLITUDE := 16000.0

var mode := "tone"


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--mode="):
			mode = argument.trim_prefix("--mode=")
	call_deferred("_run")


func _run() -> void:
	var stream := _make_stream()
	if mode == "spatial3d":
		var stage := Node3D.new()
		root.add_child(stage)
		var camera := Camera3D.new()
		camera.current = true
		stage.add_child(camera)
		var player := AudioStreamPlayer3D.new()
		player.name = "ProbePlayer3D"
		player.stream = stream
		player.attenuation_model = AudioStreamPlayer3D.ATTENUATION_DISABLED
		player.position = Vector3(1.0, 0.0, -2.0)
		stage.add_child(player)
		player.play()
	else:
		var player := AudioStreamPlayer.new()
		player.name = "ProbePlayer"
		player.stream = stream
		root.add_child(player)
		player.play()
	print("AUDIO276_PROBE_READY mode=%s mix_rate=%d frames=%d seconds=%.3f" % [
		mode, MIX_RATE, stream.data.size() / 2, SECONDS,
	])
	while true:
		await process_frame


func _make_stream() -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = MIX_RATE
	stream.stereo = false
	var sample_count := int(MIX_RATE * SECONDS)
	var data := PackedByteArray()
	for index in sample_count:
		var sample := 0.0
		var is_clip_segment := mode == "clipped" or (
			mode == "tone_then_clip" and index >= sample_count / 2)
		if is_clip_segment:
			# Deliberately alternate +full-scale and -full-scale: the analyser
			# must report near-full-scale clipping in this segment.
			sample = 32767.0 if index % 2 == 0 else -32768.0
		else:
			sample = sin(TAU * 440.0 * float(index) / float(MIX_RATE)) * AMPLITUDE
		data.append(int(sample) & 0xFF)
		data.append((int(sample) >> 8) & 0xFF)
	stream.data = data
	return stream
