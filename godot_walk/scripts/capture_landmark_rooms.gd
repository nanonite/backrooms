extends SceneTree
## Captures each landmark doorway from inside and from its neighboring room, plus a wide view.
## Create --out first; this script refuses to create or overwrite evidence directories.
## godot4 --path godot_walk --rendering-driver vulkan --resolution 960x540 \
##   --script res://scripts/capture_landmark_rooms.gd -- \
##   --map=res://room_catalog/generative_maps/<map>.json \
##   --rooms=res://room_catalog/shape_rooms/<map>/index.json --out=<existing-dir>

const WALK_SCENE := "res://scenes/generative_map_walkthrough.tscn"
const PLAYER_FLOOR_CENTER := 0.6
const DOOR_DISTANCE := 3.0
const NEIGHBOR_DISTANCE := 1.5
const WIDE_FOV := 100.0
const SETTLE_FRAMES := 8


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var out := GenerativeMapAssembly.argument("--out=")
	var rooms_path := GenerativeMapAssembly.argument("--rooms=")
	var absolute_out := ProjectSettings.globalize_path(out)
	if out.is_empty() or rooms_path.is_empty() or not DirAccess.dir_exists_absolute(absolute_out):
		push_error("Pass --rooms and an existing --out directory")
		quit(2)
		return
	var scene: Node = load(WALK_SCENE).instantiate()
	root.add_child(scene)
	await process_frame
	await process_frame
	var player := scene.find_child("Player", true, false) as CharacterBody3D
	if player == null:
		push_error("Walkthrough scene did not create its player")
		quit(2)
		return
	player.set_physics_process(false)
	player.set_process_unhandled_input(false)
	var head := player.get_node("Head") as Node3D
	var camera := head.get_node("Camera3D") as Camera3D
	var shots := _shots(rooms_path)
	if shots.is_empty():
		push_error("No placed landmarks with authored open doorways found")
		quit(2)
		return
	for shot: Dictionary in shots:
		camera.fov = WIDE_FOV if shot.wide else 75.0
		player.global_position = Vector3(shot.position.x, PLAYER_FLOOR_CENTER, shot.position.y)
		player.rotation = Vector3(0.0, float(shot.yaw), 0.0)
		head.rotation.x = 0.0
		for _frame in SETTLE_FRAMES:
			await process_frame
		var image := root.get_viewport().get_texture().get_image()
		var result := image.save_png(absolute_out.path_join(String(shot.name) + ".png"))
		if result != OK:
			push_error("Could not save %s: %s" % [shot.name, error_string(result)])
			quit(1)
			return
	print("captured %d landmark views" % shots.size())
	quit()


func _shots(rooms_path: String) -> Array[Dictionary]:
	var shots: Array[Dictionary] = []
	var index: Variant = GenerativeMapAssembly.load_json(rooms_path)
	if not index is Dictionary:
		return shots
	for entry: Dictionary in index.rooms:
		var path := rooms_path.get_base_dir().path_join(String(entry.file))
		var spec: Variant = GenerativeMapAssembly.load_json(path)
		if not spec is Dictionary or not spec.has("landmark"):
			continue
		_add_landmark_shots(shots, String(index.map_id), spec)
	return shots


func _add_landmark_shots(shots: Array[Dictionary], map_id: String, spec: Dictionary) -> void:
	var prefix := "%s_%s" % [map_id, String(spec.landmark.class)]
	var center := Vector2(float(spec.lamps_xz[0][0]), float(spec.lamps_xz[0][1]))
	var first_direction := Vector2.RIGHT
	var has_first_direction := false
	for doorway: Dictionary in spec.doorways:
		if String(doorway.kind) != "open":
			continue
		var door := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		if not has_first_direction:
			first_direction = normal
			has_first_direction = true
		_add_shot(shots, "%s_%s_inside" % [prefix, String(doorway.port_id)], door - normal * DOOR_DISTANCE, normal, false)
		_add_shot(shots, "%s_%s_neighbor" % [prefix, String(doorway.port_id)], door + normal * NEIGHBOR_DISTANCE, -normal, false)
	_add_shot(shots, "%s_wide" % prefix, center, first_direction, true)


func _add_shot(shots: Array[Dictionary], name: String, position: Vector2, forward: Vector2, wide: bool) -> void:
	var yaw := atan2(-forward.x, -forward.y)
	shots.append({"name": name, "position": position, "yaw": yaw, "wide": wide})
