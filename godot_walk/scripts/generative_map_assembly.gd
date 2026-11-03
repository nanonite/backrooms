class_name GenerativeMapAssembly
extends Node3D

## Places each cell's shape room at its envelope position (room coordinates are map
## coordinates) and, in the walkthrough scene, spawns the existing player controller
## in the origin cell. Rooms never change the map; void cells get no room.
##
## gmap-0.3.0 module cells (#188) instance the library index entry's scene instead, at the
## recorded placement: position (translation_xz, minus the socket's floor elevation so the
## module floor meets y = 0) and rotation.y = -rotation_deg. The scene is opened exactly as
## the accepted #160 / #168 assemblies open it: its exported `connector_open` is set before
## it enters the tree (and the standalone player / environment / preset switches are turned
## off). No library scene or catalog file is edited. The joint is a proposed, untested
## connection; the walkthrough never marks it accepted.

const BUILDER := preload("res://scripts/shape_room_builder.gd")
const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const MODULE_SWITCHES := {
	"connector_open": true, "spawn_embedded_player": false, "include_player": false,
	"enable_environment": false, "apply_psx_preset": false,
}
const SPAWN_HEIGHT := 0.6
const SAFETY_DEPTH := -4.0
const SAFETY_MARGIN := 10.0

## False when a test builds the rooms itself without the environment or the player.
var auto_start := true
var map: Dictionary = {}
var specs: Dictionary = {}
var rooms: Dictionary = {}
## cell_id -> instanced library scene (module cells only; shape rooms stay in `rooms`).
var module_rooms: Dictionary = {}
## cell_id -> {placement, entry, socket, floor_offset} for each module cell.
var module_info: Dictionary = {}
## False in the unopened-socket negative control.
var open_modules := true
## False only in the negative control that rebuilds the pre-#189 joint geometry.
var recess_joints := true
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
	var library_entries := _library_entries()
	for cell: Dictionary in map.cells:
		if cell.has("module"):
			_place_module(cell, library_entries)
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		if specs.has(cell_id):
			rooms[cell_id] = BUILDER.build(self, specs[cell_id], materials, _forced_closed(specs[cell_id]),
				_module_joints(specs[cell_id]))
	_add_safety_net()
	origin_cell = String(map.cells[0].cell_id)
	if not specs.has(origin_cell):
		origin_cell = String(specs.keys()[0])
	_compute_spawn(specs[origin_cell])
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)


func has_room(cell_id: String) -> bool:
	return specs.has(cell_id) or module_rooms.has(cell_id)


## Library index entries by "module_id@version" (the map's library_index path, below res://).
func _library_entries() -> Dictionary:
	var entries := {}
	if not map.has("library_index"):
		return entries
	var path := "res://" + String(map.library_index.path).trim_prefix("godot_walk/")
	var index: Variant = load_json(path)
	if index is Dictionary:
		for entry: Dictionary in index.modules:
			entries["%s@%d" % [entry.module_id, int(entry.version)]] = entry
	return entries


func _place_module(cell: Dictionary, library_entries: Dictionary) -> void:
	var placement: Dictionary = cell.module
	var key := "%s@%d" % [placement.module_id, int(placement.version)]
	if not library_entries.has(key):
		push_error("Module %s is not in the library index" % key)
		return
	var entry: Dictionary = library_entries[key]
	var packed := load(String(entry.scene)) as PackedScene
	if packed == null:
		push_error("Cannot load module scene %s" % entry.scene)
		return
	var socket := _entry_socket(entry, String(placement.socket_id))
	var floor_offset := -float(socket.get("floor_elevation_m", 0.0))
	var room := packed.instantiate() as Node3D
	room.name = String(cell.cell_id)
	_apply_module_switches(room)
	room.position = Vector3(float(placement.translation_xz[0]), floor_offset, float(placement.translation_xz[1]))
	room.rotation.y = -deg_to_rad(float(placement.rotation_deg))
	add_child(room)
	_strip_world_environments(room)
	room.set_meta("cell_id", String(cell.cell_id))
	room.set_meta("module_id", String(placement.module_id))
	room.set_meta("connection_status", "proposed_untested")
	room.set_meta("operator_approved", false)
	module_rooms[String(cell.cell_id)] = room
	module_info[String(cell.cell_id)] = {"placement": placement, "entry": entry, "socket": socket,
		"floor_offset": floor_offset}


static func _entry_socket(entry: Dictionary, socket_id: String) -> Dictionary:
	for socket: Dictionary in entry.sockets:
		if String(socket.id) == socket_id:
			return socket
	return {}


## The accepted assemblies open a socket through the scene's exported switches; only
## switches the scene actually declares are set, before it enters the tree.
func _apply_module_switches(room: Node3D) -> void:
	var declared := {}
	for property: Dictionary in room.get_property_list():
		declared[String(property.name)] = true
	for switch_name: String in MODULE_SWITCHES:
		if declared.has(switch_name):
			room.set(switch_name, open_modules if switch_name == "connector_open" else MODULE_SWITCHES[switch_name])


## A library room may bring its own WorldEnvironment (the hall does); the assembly already
## has one, and a second would be ignored with an engine error.
func _strip_world_environments(room: Node3D) -> void:
	for node in room.find_children("*", "WorldEnvironment", true, false):
		node.get_parent().remove_child(node)
		node.free()


## Open doorways that lead into a placed library room (#189). The parent side is cut larger
## than the library's own opening so none of their faces share a plane. `recess_joints` is
## false only in the negative control that rebuilds the old geometry.
func _module_joints(spec: Dictionary) -> PackedStringArray:
	var joints := PackedStringArray()
	if not recess_joints:
		return joints
	for doorway: Dictionary in spec.doorways:
		if String(doorway.kind) == "open" and module_rooms.has(String(doorway.to_cell_id)):
			joints.append(String(doorway.port_id))
	return joints


## Open doorways whose neighbour has no room (a partial index) are built closed.
func _forced_closed(spec: Dictionary) -> PackedStringArray:
	var closed := PackedStringArray()
	for doorway: Dictionary in spec.doorways:
		if String(doorway.kind) == "open" and not has_room(String(doorway.to_cell_id)):
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
