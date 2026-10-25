extends SceneTree

const SCENE_PATH := "res://evidence/2026-10-24-issue-163/issue163_room.tscn"
const DEFAULT_OUTPUT := "res://evidence/2026-10-24-issue-163/captures"
const POSES := [
	{"id": "spawn_column", "position": Vector3(-4.0, 0.6, 2.6), "target": Vector3(-2.0, 1.6, 0.0)},
	{"id": "column_south", "position": Vector3(-2.0, 0.6, 2.0), "target": Vector3(-2.0, 1.6, 0.0)},
	{"id": "column_west", "position": Vector3(-4.0, 0.6, 0.0), "target": Vector3(-2.0, 1.6, 0.0)},
	{"id": "open_passage", "position": Vector3(4.0, 0.6, 0.0), "target": Vector3(8.0, 1.2, 0.0)},
	{"id": "hallway_end", "position": Vector3(8.0, 0.6, 0.0), "target": Vector3(12.5, 1.2, 0.0)},
	{"id": "hallway_return", "position": Vector3(8.0, 0.6, 0.0), "target": Vector3(4.0, 1.2, 0.0)},
	{"id": "room_corner", "position": Vector3(4.0, 0.6, 3.0), "target": Vector3(5.5, 1.5, 4.7)},
]

var output_path := DEFAULT_OUTPUT
var capture_records: Array[Dictionary] = []


func _initialize() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_path = argument.trim_prefix("--out=")
	call_deferred("_capture")


func _capture() -> void:
	var packed := load(SCENE_PATH) as PackedScene
	if packed == null:
		printerr("Cannot load Issue 163 scene")
		quit(1)
		return
	var room := packed.instantiate() as Node3D
	root.add_child(room)
	var player := room.get_node_or_null("Player") as CharacterBody3D
	var camera := room.get_node_or_null("Player/Head/Camera3D") as Camera3D
	if player == null or camera == null:
		printerr("Issue 163 scene did not provide the expected player camera")
		quit(1)
		return
	player.set_physics_process(false)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output_path))
	for pose: Dictionary in POSES:
		await _capture_pose(player, camera, pose)
	_write_manifest(room)
	print("ISSUE163_CAPTURES_READY: ", output_path)
	quit(0)


func _capture_pose(player: CharacterBody3D, camera: Camera3D, pose: Dictionary) -> void:
	player.global_position = pose.position
	camera.look_at(pose.target, Vector3.UP)
	for frame in 12:
		await process_frame
	var image := root.get_texture().get_image()
	if image.is_empty():
		push_error("Viewport returned an empty image for %s" % pose.id)
		return
	var path := output_path.path_join("%s.png" % pose.id)
	var error := image.save_png(ProjectSettings.globalize_path(path))
	if error != OK:
		push_error("Could not save capture %s (error %d)" % [path, error])
		return
	capture_records.append({
		"view_id": pose.id,
		"path": path,
		"position": [pose.position.x, pose.position.y, pose.position.z],
		"target": [pose.target.x, pose.target.y, pose.target.z],
		"width": image.get_width(),
		"height": image.get_height(),
	})


func _write_manifest(room: Node3D) -> void:
	var record := {
		"scene": SCENE_PATH,
		"camera_fov_degrees": 75.0,
		"settle_frames": 12,
		"renderer": "Vulkan; Godot project PSX compositor enabled",
		"hunyuan_visual_loaded": room.get_meta("hunyuan_visual_loaded", false),
		"registration_accepted": false,
		"scale_calibrated": false,
		"poses": capture_records,
	}
	var file := FileAccess.open(output_path.path_join("capture_manifest.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write capture manifest")
		return
	file.store_string(JSON.stringify(record, "\t") + "\n")
