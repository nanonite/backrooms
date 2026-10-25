extends SceneTree

const EVIDENCE := "res://evidence/2026-10-21-issue-155-godot-library"
const ROOMS := {
	"column": [
		["patch_anchor", Vector3(2.9209783, -0.1003, 3.703508), Vector3(-0.691, 0, -0.723)],
		["column_east", Vector3(2.37, -0.1003, 0.323), Vector3(-1, 0, 0)]],
	"pocket": [
		["entry", Vector3(0.8, -0.1003, 0.8), Vector3(0.25, 0.03, 1)],
		["return", Vector3(5.2, -0.1003, 13.0), Vector3(-0.25, 0.03, -1)]],
}
var records: Array[Dictionary] = []


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	for room: String in ROOMS:
		var started := Time.get_ticks_msec()
		var scene := load("res://scenes/library_%s_room.tscn" % room).instantiate() as Node3D
		root.add_child(scene)
		scene.set_meta("scene_load_to_ready_ms", Time.get_ticks_msec() - started)
		var player := scene.get_node("Player")
		player.set_physics_process(false)
		player.set_process(false)
		for child in player.get_children():
			if child is CanvasLayer:
				child.visible = false
		var camera := Camera3D.new()
		camera.fov = 75
		scene.add_child(camera)
		camera.make_current()
		await _capture_room(scene, camera, room)
		scene.queue_free()
		await process_frame
	var file := FileAccess.open(EVIDENCE + "/capture_manifest.json", FileAccess.WRITE)
	if file == null:
		quit(2)
		return
	file.store_string(JSON.stringify(records, "\t") + "\n")
	print("LIBRARY_CAPTURE_COMPLETE")
	quit()


func _capture_room(scene: Node3D, camera: Camera3D, room: String) -> void:
	for mode in ["native_baseline", "ursc_candidate"]:
		scene.get_node("LibraryPsxPreset").set_packaged_enabled(mode == "ursc_candidate")
		var directory: String = EVIDENCE + "/captures/" + room + "/" + mode
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory))
		for view: Array in ROOMS[room]:
			camera.global_position = view[1]
			camera.look_at(view[1] + view[2], Vector3.UP)
			for frame in 20:
				await process_frame
			await RenderingServer.frame_post_draw
			var destination: String = directory + "/" + view[0] + ".png"
			var image := root.get_texture().get_image()
			if image.is_empty() or image.save_png(destination) != OK:
				push_error("Cannot save %s" % destination)
				quit(2)
				return
			records.append({"room": room, "mode": mode, "view": view[0],
				"scene_load_to_ready_ms": scene.get_meta("scene_load_to_ready_ms"),
				"eye": _coordinates(view[1]), "forward": _coordinates(view[2]),
				"fov": camera.fov, "resolution": [image.get_width(), image.get_height()],
				"settle_frames": 20, "path": destination})


func _coordinates(vector: Vector3) -> Array:
	return [vector.x, vector.y, vector.z]
