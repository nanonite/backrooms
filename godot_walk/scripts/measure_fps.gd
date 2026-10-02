extends SceneTree
## Measure the runtime frame rate of a splat scene at a stated resolution.
##
## Run with:
##   godot --path godot_walk --resolution 1280x720 -- scripts/measure_fps.gd --scene=res://scenes/corridor_splat.tscn --frames=300
##
## Prints one machine-readable line so the benchmark harness can record the
## number without parsing Godot's banner:
##   FPS_JSON {"scene":"...","frames":300,"elapsed_seconds":4.9,"fps":61.2,"warmup_frames":60}
##
## The first `--warmup` frames are discarded. Shader compilation, texture upload
## and the compositor's first splat build all land in that window; including them
## reports the loading cost as if it were the steady-state frame rate, which is
## the number a player never experiences.

const DEFAULT_SCENE := "res://scenes/corridor_splat.tscn"
const DEFAULT_FRAMES := 300
const DEFAULT_WARMUP := 60
const ARGUMENT_PREFIX := "--"

var _scene_path := ""
var _total_frames := DEFAULT_FRAMES
var _warmup_frames := DEFAULT_WARMUP
var _frames_drawn := 0
var _measured_frames := 0
var _warmup_done_at := -1
var _measurement_started_ms := 0
var _start_position := Vector3.ZERO
var _start_position_read := false
var _orbit_radius := 0.0


func _initialize() -> void:
	_scene_path = _argument("--scene=", DEFAULT_SCENE)
	_total_frames = int(_argument("--frames=", str(DEFAULT_FRAMES)))
	_warmup_frames = int(_argument("--warmup=", str(DEFAULT_WARMUP)))
	_orbit_radius = float(_argument("--orbit-radius=", "0.0"))
	var packed: PackedScene = load(_scene_path)
	if packed == null:
		_fail("scene not found: %s" % _scene_path)
		return
	var scene: Node = packed.instantiate()
	root.add_child(scene)


func _process(_delta: float) -> bool:
	_frames_drawn += 1
	if not _start_position_read:
		_start_position = root.get_child(0).global_position
		_start_position_read = true
	if _frames_drawn < _warmup_frames:
		return false
	if _warmup_done_at == -1:
		_warmup_done_at = _frames_drawn
		_measurement_started_ms = Time.get_ticks_msec()
	_measured_frames += 1
	_advance_orbit()
	if _measured_frames >= _total_frames:
		_report()
		return true
	return false


func _advance_orbit() -> void:
	"""Move the viewpoint around the scene so a static frame cannot flatter the result.

	Every real walkthrough changes what the splat is asked to draw. Measuring one
	fixed camera measures one lucky culling result, so the probe orbits instead --
	unless the caller pinned the viewpoint with --orbit-radius=0.
	"""
	if _orbit_radius <= 0.0:
		return
	var centre := root.get_child(0)
	var angle := TAU * float(_measured_frames) / float(_total_frames)
	centre.global_position = _start_position + Vector3(
		cos(angle) * _orbit_radius, 0.0, sin(angle) * _orbit_radius
	)


func _report() -> void:
	var elapsed := float(Time.get_ticks_msec() - _measurement_started_ms) / 1000.0
	var fps := float(_measured_frames) / elapsed if elapsed > 0.0 else 0.0
	print(
		"FPS_JSON {" +
		'"scene":"%s",' % _scene_path +
		'"frames":%d,' % _measured_frames +
		'"elapsed_seconds":%.3f,' % elapsed +
		'"fps":%.2f,' % fps +
		'"warmup_frames":%d' % _warmup_frames +
		"}"
	)
	quit(0)


func _fail(message: String) -> void:
	printerr("FPS_FAIL %s" % message)
	quit(1)


func _argument(prefix: String, fallback: String) -> String:
	for argument in OS.get_cmdline_user_args() + OS.get_cmdline_args():
		if argument.begins_with(prefix):
			return argument.trim_prefix(prefix)
	return fallback