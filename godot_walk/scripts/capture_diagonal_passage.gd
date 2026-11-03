extends SceneTree
## Renders views of every 45-degree doorway of a generated map (needs a display and GPU).
## godot4 --path godot_walk --rendering-driver vulkan --resolution 960x540 \
##   --script res://scripts/capture_diagonal_passage.gd -- --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map>/index.json --out=<dir>
## Per diagonal doorway, from the side the doorway belongs to (a room or the passage): straight on, looking
## up at the header, and oblique. Positions come from the room specs, so no coordinates are hard-coded.

const VIEWS := [
	["face", 3.0, 0.0, 0.0],
	["up", 1.2, 0.0, 40.0],
	["oblique", 1.6, 1.3, 0.0],
]


func _initialize() -> void:
	var out := ""
	var rooms_path := ""
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			out = argument.substr(6)
		elif argument.begins_with("--rooms="):
			rooms_path = argument.substr(8)
	var scene: Node = load("res://scenes/generative_map_walkthrough.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var player: Node3D = null
	for node in scene.find_children("*", "CharacterBody3D", true, false):
		player = node
	player.set_physics_process(false)
	player.set_process_unhandled_input(false)
	var head: Node3D = player.get_node("Head")
	var shots := _shots(rooms_path)
	for shot: Dictionary in shots:
		player.global_position = shot.position
		player.rotation = Vector3(0.0, shot.yaw, 0.0)
		head.rotation.x = deg_to_rad(float(shot.pitch_deg))
		for _frame in 8:
			await process_frame
		root.get_viewport().get_texture().get_image().save_png("%s/%s.png" % [out, shot.name])
	print("captured %d views" % shots.size())
	quit()


func _shots(rooms_path: String) -> Array[Dictionary]:
	var shots: Array[Dictionary] = []
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(rooms_path))
	for entry: Dictionary in index.rooms:
		var spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
			rooms_path.get_base_dir().path_join(String(entry.file))))
		for doorway: Dictionary in spec.doorways:
			var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
			if absf(normal.x) < 0.5 or absf(normal.y) < 0.5:
				continue
			var door := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
			var side := Vector2(-normal.y, normal.x)
			for view: Array in VIEWS:
				var from := door - normal * float(view[1]) + side * float(view[2])
				var heading := (door - from).normalized()
				shots.append({"name": "%s_%s" % [String(doorway.port_id).replace(":", "_"), view[0]],
					"position": Vector3(from.x, 0.0, from.y), "yaw": atan2(-heading.x, -heading.y),
					"pitch_deg": view[3]})
	return shots
