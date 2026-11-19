extends SceneTree
## Issue #276 — deterministic scripted walk for Movie Maker audio capture.
##
## Instantiates an accepted #266 room read-only, equips a fresh player with the
## real walk_player.gd (material footsteps + #205 reverb bus + acoustic probe),
## sets the accepted room's #266 footstep tag on the floor collider and walks a
## fixed path. Nothing in the room, the player script or project.godot is edited.
## --quit-after / --fixed-fps on the command line bound the run.

const WALK_PLAYER := preload("res://scripts/walk_player.gd")
const ACOUSTIC_ZONE := preload("res://evidence/2026-11-19-issue-276-movie-maker-audio/fixture/acoustic_zone.gd")
const ROOMS := {
	"nested-light-corridor-v1": {
		"scene": "res://source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v1/room.tscn",
		"tag": "tile",
		"spawn": Vector3(0.0, 0.6, 10.0),
	},
}
const SEED := 20261119
const STRIDE_M := 0.7
const FALLBACK_FRAMES := 120

var room_key := "nested-light-corridor-v1"
var step_every_frames := 15
var total_frames := FALLBACK_FRAMES
var reverb_enabled := true


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--room="):
			room_key = argument.trim_prefix("--room=")
		elif argument.begins_with("--step-every="):
			step_every_frames = maxi(1, int(argument.trim_prefix("--step-every=")))
		elif argument.begins_with("--frames="):
			total_frames = maxi(1, int(argument.trim_prefix("--frames=")))
		elif argument.begins_with("--reverb="):
			reverb_enabled = argument.trim_prefix("--reverb=") != "off"
	call_deferred("_run")


func _run() -> void:
	ProjectSettings.set_setting("audio/room_acoustics/footstep_reverb_enabled", reverb_enabled)
	if not ROOMS.has(room_key):
		printerr("Unknown room: ", room_key)
		quit(2)
		return
	var spec: Dictionary = ROOMS[room_key]
	var packed := load(spec.scene) as PackedScene
	if packed == null:
		printerr("Could not load room scene: ", spec.scene)
		quit(2)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	var floor := room.find_child("WalkableFloor", true, false)
	if floor == null:
		printerr("Room has no WalkableFloor collider")
		quit(2)
		return
	floor.set_meta("surface_acoustic", spec.tag)
	var zone := Node3D.new()
	zone.name = "AcousticZone"
	zone.set_script(ACOUSTIC_ZONE)
	room.add_child(zone)
	var player := _make_player()
	zone.add_child(player)
	player.global_position = spec.spawn
	player._rng.seed = SEED
	player.set_physics_process(false)
	var steps := 0
	for frame in total_frames:
		if frame > 0 and frame % step_every_frames == 0:
			player._play_step(false)
			player.global_position.z -= STRIDE_M
			steps += 1
		if player._room_reverb != null:
			player._room_reverb.update(1.0 / 30.0)
		await process_frame
	print("AUDIO276_WALK_READY room=%s tag=%s steps=%d frames=%d seed=%d reverb=%s" % [
		room_key, spec.tag, steps, total_frames, SEED, str(reverb_enabled),
	])
	quit(0)


func _make_player() -> CharacterBody3D:
	var player := CharacterBody3D.new()
	player.name = "Player"
	player.set_script(WALK_PLAYER)
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3
	capsule.height = 1.2
	var collision := CollisionShape3D.new()
	collision.shape = capsule
	player.add_child(collision)
	var head := Node3D.new()
	head.name = "Head"
	head.position = Vector3(0.0, 0.5, 0.0)
	var camera := Camera3D.new()
	camera.name = "Camera3D"
	camera.current = true
	head.add_child(camera)
	player.add_child(head)
	return player
