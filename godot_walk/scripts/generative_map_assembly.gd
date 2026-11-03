class_name GenerativeMapAssembly
extends Node3D

## Places each cell's shape room at its envelope position (room coordinates are map
## coordinates) and, in the walkthrough scene, spawns the existing player controller
## in the origin cell. Rooms never change the map; void cells get no room.

const BUILDER := preload("res://scripts/shape_room_builder.gd")
const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const SPAWN_HEIGHT := 0.6
const SAFETY_DEPTH := -4.0
const SAFETY_MARGIN := 10.0

## False when a test builds the rooms itself without the environment or the player.
var auto_start := true
var map: Dictionary = {}
var specs: Dictionary = {}
var rooms: Dictionary = {}
var materials: Dictionary = {}
var player: CharacterBody3D
var spawn_position := Vector3.ZERO
var spawn_yaw := 0.0
var origin_cell := ""


static func load_json(path: String) -> Variant:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		push_error("Cannot read %s" % path)
		return null
	return JSON.parse_string(text)


static func load_specs(index_path: String) -> Dictionary:
	var index: Variant = load_json(index_path)
	var loaded := {}
	if not index is Dictionary:
		return loaded
	for entry: Dictionary in index.rooms:
		var spec: Variant = load_json(index_path.get_base_dir().path_join(String(entry.file)))
		if spec is Dictionary:
			loaded[String(entry.cell_id)] = spec
	return loaded


static func argument(prefix: String) -> String:
	for item in OS.get_cmdline_user_args():
		if item.begins_with(prefix):
			return item.trim_prefix(prefix)
	return ""


func _ready() -> void:
	if not auto_start:
		return
	var map_data: Variant = load_json(argument("--map="))
	var room_specs := load_specs(argument("--rooms="))
	if not map_data is Dictionary or room_specs.is_empty():
		push_error("Pass --map=res://...json and --rooms=res://.../index.json after --")
		return
	_build_environment()
	assemble(map_data, room_specs)
	_build_player()
	PSX_PRESET.new().configure(self)
	set_meta("walkthrough_ready", true)
	set_meta("operator_approved", false)


func assemble(map_data: Dictionary, room_specs: Dictionary) -> void:
	map = map_data
	specs = room_specs
	materials = MATERIALS.make(specs[specs.keys()[0]])
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		if specs.has(cell_id):
			rooms[cell_id] = BUILDER.build(self, specs[cell_id], materials, _forced_closed(specs[cell_id]))
	_add_safety_net()
	origin_cell = String(map.cells[0].cell_id)
	if not specs.has(origin_cell):
		origin_cell = String(specs.keys()[0])
	_compute_spawn(specs[origin_cell])
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)


## Open doorways whose neighbour has no room (a partial index) are built closed.
func _forced_closed(spec: Dictionary) -> PackedStringArray:
	var closed := PackedStringArray()
	for doorway: Dictionary in spec.doorways:
		if String(doorway.kind) == "open" and not specs.has(String(doorway.to_cell_id)):
			closed.append(String(doorway.port_id))
	return closed


func _add_safety_net() -> void:
	var bounds := Rect2()
	var first := true
	for cell: Dictionary in map.cells:
		var envelope := Rect2(Vector2(cell.envelope_xz[0][0], cell.envelope_xz[0][1]), Vector2.ZERO)
		envelope = envelope.expand(Vector2(cell.envelope_xz[2][0], cell.envelope_xz[2][1]))
		bounds = envelope if first else bounds.merge(envelope)
		first = false
	var safety := StaticBody3D.new()
	safety.name = "SafetyNet"
	safety.position = Vector3(bounds.get_center().x, SAFETY_DEPTH, bounds.get_center().y)
	add_child(safety)
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(bounds.size.x + 2.0 * SAFETY_MARGIN, 0.1, bounds.size.y + 2.0 * SAFETY_MARGIN)
	shape.shape = box
	safety.add_child(shape)


func _compute_spawn(spec: Dictionary) -> void:
	var largest: Array = spec.rects[0]
	for rect: Array in spec.rects:
		if _area(rect) > _area(largest):
			largest = rect
	var center := Vector2((float(largest[0]) + float(largest[2])) / 2.0, (float(largest[1]) + float(largest[3])) / 2.0)
	spawn_position = Vector3(center.x, SPAWN_HEIGHT, center.y)
	spawn_yaw = 0.0
	for doorway: Dictionary in spec.doorways:
		if String(doorway.kind) == "open":
			var heading := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1])) - center
			spawn_yaw = atan2(-heading.x, -heading.y)
			return


static func _area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.035)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.88, 0.86, 0.78)
	environment.ambient_light_energy = 0.8
	var compositor := Compositor.new()
	var effect = PSX_EFFECT.new()
	effect.pixel_size = 3
	effect.color_levels = 24
	effect.dither_strength = 1.0
	compositor.compositor_effects = [effect]
	world.environment = environment
	world.compositor = compositor
	add_child(world)


func _build_player() -> void:
	player = PLAYER_SCENE.instantiate() as CharacterBody3D
	player.name = "Player"
	player.position = spawn_position
	player.rotation.y = spawn_yaw
	add_child(player)


func _reset_player() -> void:
	if player == null:
		return
	player.global_position = spawn_position
	player.rotation = Vector3(0.0, spawn_yaw, 0.0)
	player.velocity = Vector3.ZERO
	player.get_node("Head").rotation = Vector3.ZERO


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_R:
		_reset_player()
