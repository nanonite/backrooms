@tool
extends CompositorEffect
class_name PsxPostEffect

## Optional PSX presentation pass for the cleaned corridor (#100).
##
## Quantizes the scene colour to a small palette with an ordered (Bayer) dither
## and snaps it to a coarse pixel grid: the low-resolution, low-colour-depth look
## the synthetic Backrooms PoC targets. It is presentation only. It never moves
## geometry, never changes collision and never hides an alignment failure,
## because it operates on the finished colour buffer after the splat compositor.
##
## It is switchable off independently of the cleanup, so the geometry/alignment
## review view is unaffected. Three ways, from most to least local:
##   * set `psx_enabled = false` on the effect (exported),
##   * pass `--no-psx` after `--` on the command line,
##   * remove the effect from the scene's Compositor.
##
## The cleanup itself lives in the asset and the scene, not here: this class
## only styles what is already drawn.

const SHADER_PATH := "res://scripts/psx/shaders/psx_post.glsl"
const WORKGROUP_SIZE := 16
const DISABLE_ARG := "--no-psx"
const PUSH_CONSTANT_FLOATS := 8

## When false the effect returns before dispatching, leaving the colour buffer
## untouched. Named `psx_enabled` rather than `enabled` because the native
## `CompositorEffect` base already defines `enabled`, and redefining it is a
## parse error.
@export var psx_enabled := true
## Output pixels per block. 2 is a mild 640x360-ish look at 1280x720; 4 (the
## presentation scene's value) is a coarser 320x180 look. 1 disables the
## pixel-grid part.
@export_range(1, 8, 1) var pixel_size := 2
## Steps per colour channel. 32 (5 bits) is a mild PSX-ish depth; 16 (the
## presentation scene's value) is heavier banding.
@export_range(2, 256, 1) var color_levels := 32
## Bayer threshold amplitude. 1.0 is the full ordered-dither amount; 0.0
## quantizes without dithering.
@export_range(0.0, 2.0, 0.01) var dither_strength := 1.0

var rd: RenderingDevice
var shader: RID
var pipeline: RID


func _init() -> void:
	effect_callback_type = EFFECT_CALLBACK_TYPE_POST_TRANSPARENT
	if _disabled_on_command_line():
		psx_enabled = false
	RenderingServer.call_on_render_thread(_initialize)


func _notification(what: int) -> void:
	if what != NOTIFICATION_PREDELETE:
		return
	if rd != null:
		if pipeline.is_valid():
			rd.free_rid(pipeline)
		if shader.is_valid():
			rd.free_rid(shader)
	pipeline = RID()
	shader = RID()


func _render_callback(_effect_callback_type: int, render_data: RenderData) -> void:
	if not psx_enabled or not rd or not shader.is_valid() or not pipeline.is_valid():
		return

	var scene_buffers: RenderSceneBuffersRD = render_data.get_render_scene_buffers()
	if scene_buffers == null:
		return
	var size: Vector2i = scene_buffers.get_internal_size()
	if size.x <= 0 or size.y <= 0:
		return

	var x_groups := int(ceili(size.x / float(WORKGROUP_SIZE)))
	var y_groups := int(ceili(size.y / float(WORKGROUP_SIZE)))
	var push := PackedFloat32Array([
		size.x,
		size.y,
		float(pixel_size),
		float(color_levels),
		dither_strength,
		0.0,
		0.0,
		0.0,
	])
	if push.size() != PUSH_CONSTANT_FLOATS:
		return

	for view in scene_buffers.get_view_count():
		var scene_tex: RID = scene_buffers.get_color_layer(view)
		if not scene_tex.is_valid():
			continue
		_dispatch(scene_tex, x_groups, y_groups, push)


func _dispatch(scene_tex: RID, x_groups: int, y_groups: int, push: PackedFloat32Array) -> void:
	var image_uniform := RDUniform.new()
	image_uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_IMAGE
	image_uniform.binding = 0
	image_uniform.add_id(scene_tex)

	var uniform_set: RID = UniformSetCacheRD.get_cache(shader, 0, [image_uniform])
	var compute_list: int = rd.compute_list_begin()
	rd.compute_list_bind_compute_pipeline(compute_list, pipeline)
	rd.compute_list_bind_uniform_set(compute_list, uniform_set, 0)
	rd.compute_list_set_push_constant(compute_list, push.to_byte_array(), push.size() * 4)
	rd.compute_list_dispatch(compute_list, x_groups, y_groups, 1)
	rd.compute_list_end()


func _initialize() -> void:
	rd = RenderingServer.get_rendering_device()
	if not rd:
		return
	var glsl_file: RDShaderFile = load(SHADER_PATH)
	if glsl_file == null:
		return
	shader = rd.shader_create_from_spirv(glsl_file.get_spirv())
	pipeline = rd.compute_pipeline_create(shader)


func _disabled_on_command_line() -> bool:
	for argument in OS.get_cmdline_user_args() + OS.get_cmdline_args():
		if argument == DISABLE_ARG:
			return true
	return false
