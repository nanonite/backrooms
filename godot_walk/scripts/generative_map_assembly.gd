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
##
## gmap-0.11.0 (#204) copies each cell's `reverb` flag onto its instanced room as
## `reverb_enabled` metadata, with a nominal `room_volume_m3` figure. The flag is not baked
## into geometry: `set_room_reverb` changes it at runtime, and the later mutation issue can
## flip one visited room without rebuilding the map.

const BUILDER := preload("res://scripts/shape_room_builder.gd")
const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const LIGHT_CONTROLLER := preload("res://scripts/maze_light_controller.gd")
const SURFACE_CONTROLLER := preload("res://scripts/maze_surface_controller.gd")
const FOLLOWER_RUNTIME := preload("res://scripts/maze_follower_runtime.gd")
const MAZE_EXIT := preload("res://scripts/maze_exit.gd")
const MAZE_EXIT_THRESHOLD := preload("res://scripts/maze_exit_threshold.gd")
const EXIT_RUNTIME := preload("res://scripts/maze_exit_runtime.gd")
const MAZE_DOORS := preload("res://scripts/maze_doors.gd")
const DOOR_RUNTIME := preload("res://scripts/maze_door_runtime.gd")
const REWIRE_RUNTIME := preload("res://scripts/maze_rewire_runtime.gd")
const RUN_SAVE := preload("res://scripts/maze_run_save.gd")
const PLAYER_SCENE := preload("res://scenes/player.tscn")
const WALK_PLAYER := preload("res://scripts/walk_player.gd")
const PSX_PRESET := preload("res://scripts/library_psx_preset.gd")
const PSX_EFFECT := preload("res://scripts/psx/psx_post_effect.gd")
const MODULE_SWITCHES := {
	"connector_open": true, "spawn_embedded_player": false, "include_player": false,
	"enable_environment": false, "apply_psx_preset": false,
}
const SPAWN_HEIGHT := 0.6
const SAFETY_MARGIN := 10.0
const GENERATED_LIGHT_LAYER_COUNT := 19
const MODULE_RENDER_LAYER := 20
const LIGHT_CULL_DISTANCE_M := 6.2
const LIT_VERSIONS := ["gmap-0.8.0", "gmap-0.9.0", "gmap-0.10.0", "gmap-0.11.0", "gmap-0.12.0", "gmap-0.13.0"]
const ELEVATED_VERSIONS := ["gmap-0.10.0", "gmap-0.11.0", "gmap-0.12.0", "gmap-0.13.0"]
const MODULE_ACOUSTICS_PATH := "res://room_catalog/module_acoustics.json"
const MODULE_FLOOR_FALLBACKS := ["WalkableFloor", "AuthoredFloor", "AuthoredPlanarRouteFloor", "ConnectorThreshold"]
## Fallback map/rooms pair when no user args are given (godot-mcp run_project, #197). Gitignored.
const WALK_TARGET_PATH := "res://.walk_target.json"

## False when a test builds the rooms itself without the environment or the player.
var auto_start := true
var map: Dictionary = {}
## The committed map path used for the save base hash; empty when assembled in memory.
var source_map_path := ""
var specs: Dictionary = {}
var rooms: Dictionary = {}
## cell_id -> instanced library scene (module cells only; shape rooms stay in `rooms`).
var module_rooms: Dictionary = {}
## Generated-room layers are greedily colored by light reach; layer 20 is reserved for modules.
var light_layers: Dictionary = {}
## The one static exit for this map (#233); empty for an older map with no candidate.
var exit_record: Dictionary = {}
## What the additive threshold/room treatment built, for the headless checks.
var exit_visual: Dictionary = {}
## The derived M4 door registry (#234); the committed map is never edited.
var door_plan: Dictionary = {}
## cell_id -> {placement, entry, socket, floor_offset} for each module cell.
var module_info: Dictionary = {}
## False in the unopened-socket negative control.
var open_modules := true
## False only in the negative control that rebuilds the pre-#189 joint geometry.
var recess_joints := true
## #190 negative controls: diagonal walls without collision, diagonal walls pulled back from their joints.
var diagonal_collision := true
var diagonal_pullback := 0.0
var materials: Dictionary = {}
var palette_materials: Dictionary = {}  # palette_id -> materials (shape-room-0.5.0 specs, #192)
var module_acoustics: Dictionary = {}  # module_id@version -> accepted poetics projection (#200)
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
	var map_path := argument("--map=")
	var rooms_path := argument("--rooms=")
	if map_path.is_empty() and rooms_path.is_empty():
		# godot-mcp's run_project cannot pass user args; it writes this
		# gitignored file instead (#197).
		var target: Variant = load_json(WALK_TARGET_PATH) if FileAccess.file_exists(WALK_TARGET_PATH) else null
		if target is Dictionary:
			map_path = String(target.get("map", ""))
			rooms_path = String(target.get("rooms", ""))
	source_map_path = map_path
	var map_data: Variant = load_json(map_path)
	var room_specs := load_specs(rooms_path)
	if not map_data is Dictionary or room_specs.is_empty():
		push_error("Pass --map=res://...json and --rooms=res://.../index.json after --, or write %s" % WALK_TARGET_PATH)
		return
	_build_environment(String(map_data.get("generator_version", "")) in LIT_VERSIONS)
	assemble(map_data, room_specs)
	_build_player()
	var follower := FOLLOWER_RUNTIME.new()
	follower.name = "MazeFollowerRuntime"
	add_child(follower)
	follower.setup(self, player)
	set_meta("maze_follower_runtime", follower)
	var exit_driver := EXIT_RUNTIME.new()
	exit_driver.name = "MazeExitRuntime"
	add_child(exit_driver)
	exit_driver.setup(self, player)
	set_meta("maze_exit_runtime", exit_driver)
	var door_driver := DOOR_RUNTIME.new()
	door_driver.name = "MazeDoorRuntime"
	add_child(door_driver)
	door_driver.setup(self, player)
	set_meta("maze_door_runtime", door_driver)
	var rewire_driver := REWIRE_RUNTIME.new()
	rewire_driver.name = "MazeRewireRuntime"
	add_child(rewire_driver)
	rewire_driver.setup(self, door_driver)
	set_meta("maze_rewire_runtime", rewire_driver)
	_apply_psx_preset()
	set_meta("walkthrough_ready", true)
	set_meta("operator_approved", false)


func assemble(map_data: Dictionary, room_specs: Dictionary) -> void:
	map = map_data
	specs = room_specs
	if String(map.get("generator_version", "")) in LIT_VERSIONS and not _assign_light_layers():
		return
	module_acoustics = _load_module_acoustics()
	materials = MATERIALS.make(specs[specs.keys()[0]])
	var library_entries := _library_entries()
	for cell: Dictionary in map.cells:
		if cell.has("module"):
			_place_module(cell, library_entries)
	for cell: Dictionary in map.cells:
		var cell_id := String(cell.cell_id)
		if specs.has(cell_id):
			var room_materials := materials_for(specs[cell_id])
			rooms[cell_id] = BUILDER.build(self, specs[cell_id], room_materials, _forced_closed(specs[cell_id]),
				_module_joints(specs[cell_id]),
				{"diagonal_collision": diagonal_collision, "diagonal_pullback": diagonal_pullback,
				"light_layer": _light_layer(cell_id)})
			(rooms[cell_id] as Node3D).position.y = float(cell.get("floor_y", 0.0))
			_tag_reverb(rooms[cell_id], cell)
			LIGHT_CONTROLLER.tag_room(rooms[cell_id], specs[cell_id], room_materials.get("lamp"))
			SURFACE_CONTROLLER.tag_room(rooms[cell_id], specs[cell_id])
	_select_and_decorate_exit()
	door_plan = MAZE_DOORS.plan(map, specs, exit_record)
	set_meta("maze_doors", door_plan)
	_add_risers()
	_add_safety_net()
	origin_cell = String(map.cells[0].cell_id)
	if not specs.has(origin_cell):
		origin_cell = String(specs.keys()[0])
	_compute_spawn(specs[origin_cell])
	set_meta("registration_accepted", false)
	set_meta("scale_calibrated", false)


## Build one room node from a committed or in-memory derived spec. The M6
## re-roll uses this for changed cells only; the rest of the assembly is not
## rebuilt.
func build_room_from_spec(spec: Dictionary) -> Node3D:
	var cell_id := String(spec.get("cell_id", ""))
	var room_materials := materials_for(spec)
	return BUILDER.build(self, spec, room_materials, _forced_closed(spec),
		_module_joints(spec), {
			"diagonal_collision": diagonal_collision,
			"diagonal_pullback": diagonal_pullback,
			"light_layer": _light_layer(cell_id),
		})


## Rebuild the derived door registry after a committed re-roll. The committed
## map is still untouched; ``runtime_map`` is an in-memory copy with the
## current passage set.
func refresh_door_plan(runtime_map: Dictionary) -> Dictionary:
	door_plan = MAZE_DOORS.plan(runtime_map, specs, exit_record)
	set_meta("maze_doors", door_plan)
	return door_plan


## Replay one stored ``door_reroll`` event through the M6 runtime.
func apply_stored_rewire(event: Dictionary, player_cell: String = "") -> Dictionary:
	var runtime: Node = get_meta("maze_rewire_runtime") if has_meta("maze_rewire_runtime") else null
	if runtime == null:
		return {"ok": false, "reason": "no_rewire_runtime"}
	return runtime.apply_stored_event(event, player_cell)


func rewire_snapshot() -> Dictionary:
	var runtime: Node = get_meta("maze_rewire_runtime") if has_meta("maze_rewire_runtime") else null
	if runtime == null:
		return {}
	return runtime.snapshot()


## The save base identity: the raw committed map hash plus the map's own IDs.
func run_base_identity() -> Dictionary:
	var hash := ""
	if not source_map_path.is_empty():
		var absolute := ProjectSettings.globalize_path(source_map_path)
		if FileAccess.file_exists(absolute):
			hash = FileAccess.get_sha256(absolute)
	return RUN_SAVE.base_identity(map, hash)


## Persist the door/re-roll event stream with the base identity, never a pool.
func run_save() -> Dictionary:
	var runtime: Node = get_meta("maze_door_runtime") if has_meta("maze_door_runtime") else null
	var events: Array = runtime.export_log() if runtime != null else []
	return RUN_SAVE.build(run_base_identity(), events)


## Restore a saved run into this freshly assembled scene.  Committed re-rolls
## replay their stored P; a door that was merely latched is re-enumerated.
func restore_run(save: Dictionary) -> Dictionary:
	var checked := RUN_SAVE.validate(save, run_base_identity())
	if not bool(checked.get("ok", false)):
		return checked
	var log: Array = (checked.get("save", {}) as Dictionary).get("event_log", [])
	var doors: Node = get_meta("maze_door_runtime") if has_meta("maze_door_runtime") else null
	if doors != null:
		doors.restore_log(log)
	var rewire: Node = get_meta("maze_rewire_runtime") if has_meta("maze_rewire_runtime") else null
	if rewire == null:
		return {"ok": false, "reason": "no_rewire_runtime"}
	return rewire.restore_events(log)


func write_run_save(path: String) -> Dictionary:
	var save := run_save()
	if not bool(save.get("ok", false)):
		return save
	return RUN_SAVE.write(path, run_base_identity(), save.get("save", {}))


func load_run_save(path: String) -> Dictionary:
	var loaded := RUN_SAVE.read(path, run_base_identity())
	if not bool(loaded.get("ok", false)):
		return loaded
	return restore_run(loaded.get("save", {}))


func passage_revision(cell_id: String) -> int:
	var runtime: Node = get_meta("maze_rewire_runtime") if has_meta("maze_rewire_runtime") else null
	if runtime == null:
		return 0
	return int(runtime.passage_revision(cell_id))


## One materials set per palette; a spec without `palette_id` (shape-room-0.1.0 to 0.4.0) keeps the shared one.
func materials_for(spec: Dictionary) -> Dictionary:
	if not spec.materials.has("palette_id"):
		return materials
	var palette_id := String(spec.materials.palette_id)
	var cache_key := palette_id
	if spec.materials.has("variants"):
		cache_key += "@wear%d@%s" % [
			int(spec.materials.get("wear", 0)),
			JSON.stringify(spec.materials.get("variants", {}))]
	if not palette_materials.has(cache_key):
		palette_materials[cache_key] = MATERIALS.make(spec)
	return palette_materials[cache_key]


func has_room(cell_id: String) -> bool:
	return specs.has(cell_id) or module_rooms.has(cell_id)


## gmap-0.11.0 (#204): the map's reverb flag is runtime metadata, not baked geometry.
func _tag_reverb(room: Node3D, cell: Dictionary) -> void:
	room.set_meta("reverb_enabled", bool(cell.get("reverb", false)))
	room.set_meta("room_volume_m3", nominal_room_volume_m3(cell))


## Envelope area times the authored maximum ceiling: the same nominal figure the map
## generator biases its wet draw with. It is a heuristic, not a measured acoustic volume.
static func nominal_room_volume_m3(cell: Dictionary) -> float:
	var points: Array = cell.envelope_xz
	var twice_area := 0.0
	for index in points.size():
		var current: Array = points[index]
		var following: Array = points[(index + 1) % points.size()]
		twice_area += float(current[0]) * float(following[1]) - float(following[0]) * float(current[1])
	var heights: Array = cell.ceiling_range_m
	var height := maxf(float(heights[0]), float(heights[heights.size() - 1]))
	return absf(twice_area) / 2.0 * height


func room_node(cell_id: String) -> Node3D:
	if rooms.has(cell_id):
		return rooms[cell_id] as Node3D
	if module_rooms.has(cell_id):
		return module_rooms[cell_id] as Node3D
	return null


func room_reverb_enabled(cell_id: String) -> bool:
	var room := room_node(cell_id)
	return room != null and bool(room.get_meta("reverb_enabled", false))


## Runtime mutation point for the wet/dry tell; the map document is never edited.
func set_room_reverb(cell_id: String, enabled: bool) -> bool:
	var room := room_node(cell_id)
	if room == null:
		return false
	room.set_meta("reverb_enabled", enabled)
	return true


## Static exit (#233): selected before any re-roll eligibility map, decorated
## only on a generated room. A library module keeps its hash-pinned scene, so an
## exit that lands there (a later-map fallback only) is functional but unstyled.
func _select_and_decorate_exit() -> void:
	exit_record = MAZE_EXIT.select_exit(map)
	var exit_cell := String(exit_record.get("cell_id", ""))
	set_meta("maze_exit", exit_record)
	set_meta("maze_exit_cell", exit_cell)
	if exit_cell.is_empty():
		return
	if not rooms.has(exit_cell):
		push_warning("Static exit %s is not a generated room; no threshold treatment" % exit_cell)
		return
	exit_visual = MAZE_EXIT_THRESHOLD.decorate(rooms[exit_cell], specs[exit_cell], exit_record)
	set_meta("maze_exit_visual", exit_visual)


func exit_cell_id() -> String:
	return String(exit_record.get("cell_id", ""))


func exit_record_data() -> Dictionary:
	return exit_record.duplicate(true)


func exit_threshold_visual() -> Dictionary:
	return exit_visual.duplicate(true)


## Derived M4 door registry: base doors + procedural-leaf fit + eligible crossings.
func door_plan_data() -> Dictionary:
	return door_plan.duplicate(true)


## Live door state from the M4 runtime, or "open" before the runtime starts.
func door_state(threshold: String) -> String:
	var runtime: Node = get_meta("maze_door_runtime") if has_meta("maze_door_runtime") else null
	if runtime == null:
		return "open"
	return String((runtime.get("states") as Dictionary).get(threshold, "open"))


func door_state_snapshot() -> Dictionary:
	var runtime: Node = get_meta("maze_door_runtime") if has_meta("maze_door_runtime") else null
	if runtime == null:
		return {}
	return (runtime.snapshot() as Dictionary).duplicate(true)


## Manual open through the M4 runtime; false for a door that is not latched or
## for a request from a cell that is not one of its two sides.
func open_door(threshold: String, from_cell: String = "") -> bool:
	var runtime: Node = get_meta("maze_door_runtime") if has_meta("maze_door_runtime") else null
	if runtime == null:
		return false
	return bool(runtime.open_door(threshold, from_cell))


## Runtime mutation point for the M2 follower lamp edit (#232). Generated rooms
## only: a library module's lamp is baked into its hash-pinned scene, and the
## landmark is operator-approved and frozen. The map document is never edited.
func set_cell_light(cell_id: String, lamp_index: int, state: String,
		flicker_seed: int = -1) -> bool:
	if cell_id == exit_cell_id():
		return false
	if module_rooms.has(cell_id) or not specs.has(cell_id):
		return false
	if LIGHT_CONTROLLER.is_landmark(specs[cell_id]):
		return false
	var room := room_node(cell_id)
	if room == null:
		return false
	return LIGHT_CONTROLLER.apply_lamp_state(room, lamp_index, state, flicker_seed)


## Apply one folded overlay record (`lamp_state` and/or `lamp_flicker`) to a room.
func apply_cell_light_override(cell_id: String, override: Dictionary) -> bool:
	if cell_id == exit_cell_id():
		return false
	if module_rooms.has(cell_id) or not specs.has(cell_id):
		return false
	if LIGHT_CONTROLLER.is_landmark(specs[cell_id]):
		return false
	var room := room_node(cell_id)
	if room == null or not room.has_meta("maze_lamp_states"):
		return false
	return LIGHT_CONTROLLER.apply_override(room, override)


func cell_light_state(cell_id: String, lamp_index: int) -> String:
	var room := room_node(cell_id)
	if room == null:
		return ""
	return LIGHT_CONTROLLER.lamp_state(room, lamp_index)


func cell_light_states(cell_id: String) -> Array:
	var room := room_node(cell_id)
	if room == null:
		return []
	return LIGHT_CONTROLLER.lamp_states(room)


func cell_lamp_flicker_seeds(cell_id: String) -> Array:
	var room := room_node(cell_id)
	if room == null:
		return []
	return LIGHT_CONTROLLER.lamp_flicker_seeds(room)


## M8 (#238): wear and surface variants are runtime metadata; a generated room
## is rebuilt only when a later slice asks. Library modules and the landmark are
## hash-pinned or frozen, so they refuse this edit.
func _surface_mutable(cell_id: String) -> bool:
	if cell_id == exit_cell_id():
		return false
	if module_rooms.has(cell_id) or not specs.has(cell_id):
		return false
	if LIGHT_CONTROLLER.is_landmark(specs[cell_id]):
		return false
	return true


func set_room_wear(cell_id: String, wear: int) -> bool:
	if not _surface_mutable(cell_id):
		return false
	var room := room_node(cell_id)
	return SURFACE_CONTROLLER.apply_override(room, {"wear": wear})


func set_cell_surface_variants(cell_id: String, variants: Dictionary) -> bool:
	if not _surface_mutable(cell_id):
		return false
	var room := room_node(cell_id)
	return SURFACE_CONTROLLER.apply_override(room, {"surface_variant": variants})


## Apply one folded overlay record (`wear` and/or `surface_variant`) to a room.
func apply_cell_surface_override(cell_id: String, override: Dictionary) -> bool:
	if not _surface_mutable(cell_id):
		return false
	var room := room_node(cell_id)
	return SURFACE_CONTROLLER.apply_override(room, override)


func cell_wear(cell_id: String) -> int:
	var room := room_node(cell_id)
	if room == null or not SURFACE_CONTROLLER.tagged(room):
		return -1
	return SURFACE_CONTROLLER.wear(room)


func cell_surface_variants(cell_id: String) -> Dictionary:
	var room := room_node(cell_id)
	if room == null or not SURFACE_CONTROLLER.tagged(room):
		return {}
	return SURFACE_CONTROLLER.variants(room)


## Walkable cell under a world-space point, or "" outside every room. The
## highest compatible floor wins, then the smaller envelope (a threshold cell
## inside a larger room). Used by the acoustic probe every sample, so a runtime
## #209 mutation is read fresh rather than baked into the player.
func cell_at(world_position: Vector3) -> String:
	var best := ""
	var best_floor := -INF
	var best_area := INF
	for cell: Dictionary in map.get("cells", []):
		if String(cell.get("role", "")) == "void":
			continue
		if not _cell_contains(cell, world_position):
			continue
		var floor_y := float(cell.get("floor_y", 0.0))
		var heights: Array = cell.get("ceiling_range_m", [0.0, 0.0])
		var ceiling := maxf(float(heights[0]), float(heights[heights.size() - 1]))
		if world_position.y < floor_y - 0.1 or world_position.y > floor_y + ceiling + 0.5:
			continue
		var area := _envelope_area(cell.get("envelope_xz", []))
		if best.is_empty() or floor_y > best_floor + 0.001 or (
			is_equal_approx(floor_y, best_floor) and area < best_area
		):
			best = String(cell.cell_id)
			best_floor = floor_y
			best_area = area
	return best


## Current reverb permission at a world-space point. The flag is read from the
## instanced room's metadata, so `set_room_reverb` changes it immediately; a
## missing flag reads as dry.
func room_reverb_at(world_position: Vector3) -> bool:
	var cell_id := cell_at(world_position)
	return not cell_id.is_empty() and room_reverb_enabled(cell_id)


## Authored ceiling over a point, above the cell floor. Generated ceilings are
## rendered but have no collider, so the probe uses this as a fallback when its
## up ray misses; a real collider still wins when one exists.
func room_ceiling_height_at(world_position: Vector3) -> float:
	var cell_id := cell_at(world_position)
	if cell_id.is_empty():
		return 0.0
	var room := room_node(cell_id)
	if room != null and room.has_meta("ceiling_height_m"):
		return float(room.get_meta("ceiling_height_m"))
	for cell: Dictionary in map.get("cells", []):
		if String(cell.get("cell_id", "")) != cell_id:
			continue
		var heights: Array = cell.get("ceiling_range_m", [0.0, 0.0])
		return maxf(float(heights[0]), float(heights[heights.size() - 1]))
	return 0.0


static func _cell_contains(cell: Dictionary, world_position: Vector3) -> bool:
	var points: Array = cell.get("envelope_xz", [])
	if points.size() < 3:
		return false
	var polygon := PackedVector2Array()
	for point: Array in points:
		polygon.append(Vector2(float(point[0]), float(point[1])))
	return Geometry2D.is_point_in_polygon(Vector2(world_position.x, world_position.z), polygon)


static func _envelope_area(points: Array) -> float:
	if points.size() < 3:
		return INF
	var twice_area := 0.0
	for index in points.size():
		var current: Array = points[index]
		var following: Array = points[(index + 1) % points.size()]
		twice_area += float(current[0]) * float(following[1]) - float(following[0]) * float(current[1])
	return absf(twice_area) / 2.0


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
	room.position = Vector3(float(placement.translation_xz[0]), float(cell.get("floor_y", 0.0)) + floor_offset, float(placement.translation_xz[1]))
	room.rotation.y = -deg_to_rad(float(placement.rotation_deg))
	add_child(room)
	_strip_world_environments(room)
	_tag_module_floor(room, entry)
	if String(map.get("generator_version", "")) in LIT_VERSIONS:
		_set_module_render_layer(room)
	room.set_meta("cell_id", String(cell.cell_id))
	room.set_meta("module_id", String(placement.module_id))
	room.set_meta("connection_status", "proposed_untested")
	room.set_meta("operator_approved", false)
	_tag_reverb(room, cell)
	module_rooms[String(cell.cell_id)] = room
	module_info[String(cell.cell_id)] = {"placement": placement, "entry": entry, "socket": socket,
		"floor_offset": floor_offset}


static func _entry_socket(entry: Dictionary, socket_id: String) -> Dictionary:
	for socket: Dictionary in entry.sockets:
		if String(socket.id) == socket_id:
			return socket
	return {}


## The table is a projection of accepted module poetics (#200); it carries each
## module's acoustic tag and poetics path/hash. Missing entries stay untagged so
## the player's default fallback can log them.
func _load_module_acoustics() -> Dictionary:
	var data: Variant = load_json(MODULE_ACOUSTICS_PATH)
	if not data is Dictionary:
		push_warning("Module acoustic table is missing: %s" % MODULE_ACOUSTICS_PATH)
		return {}
	return data.get("modules", {})


func _tag_module_floor(room: Node3D, entry: Dictionary) -> void:
	var key := "%s@%d" % [entry.module_id, int(entry.version)]
	var record: Dictionary = module_acoustics.get(key, {})
	var acoustic := String(record.get("acoustic", ""))
	if acoustic.is_empty() or acoustic == "default":
		return
	var names: PackedStringArray = room.get_meta("walk_floor_bodies", PackedStringArray())
	if names.is_empty():
		names = PackedStringArray(MODULE_FLOOR_FALLBACKS)
	for body_name: String in names:
		for node: Node in room.find_children(body_name, "StaticBody3D", true, false):
			var body := node as StaticBody3D
			body.set_meta("surface_acoustic", acoustic)
			body.set_meta("surface_acoustic_source", MODULE_ACOUSTICS_PATH)
			body.set_meta("surface_acoustic_module", key)
	room.set_meta("surface_acoustic", acoustic)


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


func _add_risers() -> void:
	if String(map.get("generator_version", "")) not in ELEVATED_VERSIONS:
		return
	var host := Node3D.new()
	host.name = "Risers"
	add_child(host)
	var cells: Array[Dictionary] = []
	for cell: Dictionary in map.cells:
		if String(cell.role) != "void":
			cells.append(cell)
	for left_index in cells.size():
		for right_index in range(left_index + 1, cells.size()):
			_add_riser(host, cells[left_index], cells[right_index])


func _add_riser(host: Node3D, left: Dictionary, right: Dictionary) -> void:
	var shared := _shared_envelope_boundary(left, right)
	if shared.is_empty():
		return
	if _has_direct_connection(String(left.cell_id), String(right.cell_id)):
		return
	var left_floor := float(left.get("floor_y", 0.0))
	var right_floor := float(right.get("floor_y", 0.0))
	if absf(left_floor - right_floor) <= 0.0001:
		return
	var upper_is_left := left_floor > right_floor
	var upper: Dictionary = left if upper_is_left else right
	var lower: Dictionary = right if upper_is_left else left
	var upper_id := String(upper.cell_id)
	var lower_id := String(lower.cell_id)
	var bottom := minf(left_floor, right_floor)
	var top := maxf(left_floor, right_floor) - 0.05
	var height := top - bottom
	var along: float = float(shared.high) - float(shared.low)
	if along <= 0.0001 or height <= 0.0001:
		return
	var thickness := 0.16
	var into := (-1.0 if bool(shared.left_is_low) else 1.0) * (1.0 if upper_is_left else -1.0)
	var center := Vector3.ZERO
	var size := Vector3.ZERO
	if String(shared.axis) == "x":
		center = Vector3(float(shared.boundary) + into * thickness / 2.0, (bottom + top) / 2.0,
			(float(shared.low) + float(shared.high)) / 2.0)
		size = Vector3(thickness, height, along)
	else:
		center = Vector3((float(shared.low) + float(shared.high)) / 2.0, (bottom + top) / 2.0,
			float(shared.boundary) + into * thickness / 2.0)
		size = Vector3(along, height, thickness)
	var visual := MeshInstance3D.new()
	visual.name = "WallRiser_%s_%sVisual" % [upper_id, lower_id]
	visual.position = center
	var mesh := BoxMesh.new()
	mesh.size = size
	visual.mesh = mesh
	var upper_spec: Dictionary = specs.get(upper_id, {})
	var material_set: Dictionary = materials_for(upper_spec) if not upper_spec.is_empty() else materials
	visual.material_override = MATERIALS.scaled(material_set, "wallpaper", along, height)
	if String(map.get("generator_version", "")) in LIT_VERSIONS:
		var layer := MODULE_RENDER_LAYER if module_rooms.has(upper_id) else _light_layer(upper_id)
		visual.layers = 1 << (layer - 1)
	host.add_child(visual)
	var body := StaticBody3D.new()
	body.name = "WallRiser_%s_%s" % [upper_id, lower_id]
	body.position = center
	host.add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "CollisionShape3D"
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)


func _has_direct_connection(left_id: String, right_id: String) -> bool:
	for edge: Dictionary in map.get("edges", []):
		if String(edge.get("connector", "")) != "direct":
			continue
		var from_id := String(edge.from).get_slice(":", 0)
		var to_id := String(edge.to).get_slice(":", 0)
		if (from_id == left_id and to_id == right_id) or (from_id == right_id and to_id == left_id):
			return true
	return false


## Shared axis-aligned envelope boundary, with the side into the higher cell.
func _shared_envelope_boundary(left: Dictionary, right: Dictionary) -> Dictionary:
	var left_rect := _envelope_rect(left)
	var right_rect := _envelope_rect(right)
	if absf(left_rect.end.x - right_rect.position.x) <= 0.0001:
		return {"axis": "x", "boundary": left_rect.end.x,
			"low": maxf(left_rect.position.y, right_rect.position.y),
			"high": minf(left_rect.end.y, right_rect.end.y), "left_is_low": true} if minf(left_rect.end.y, right_rect.end.y) - maxf(left_rect.position.y, right_rect.position.y) > 0.0001 else {}
	if absf(left_rect.position.x - right_rect.end.x) <= 0.0001:
		return {"axis": "x", "boundary": left_rect.position.x,
			"low": maxf(left_rect.position.y, right_rect.position.y),
			"high": minf(left_rect.end.y, right_rect.end.y), "left_is_low": false} if minf(left_rect.end.y, right_rect.end.y) - maxf(left_rect.position.y, right_rect.position.y) > 0.0001 else {}
	if absf(left_rect.end.y - right_rect.position.y) <= 0.0001:
		return {"axis": "z", "boundary": left_rect.end.y,
			"low": maxf(left_rect.position.x, right_rect.position.x),
			"high": minf(left_rect.end.x, right_rect.end.x), "left_is_low": true} if minf(left_rect.end.x, right_rect.end.x) - maxf(left_rect.position.x, right_rect.position.x) > 0.0001 else {}
	if absf(left_rect.position.y - right_rect.end.y) <= 0.0001:
		return {"axis": "z", "boundary": left_rect.position.y,
			"low": maxf(left_rect.position.x, right_rect.position.x),
			"high": minf(left_rect.end.x, right_rect.end.x), "left_is_low": false} if minf(left_rect.end.x, right_rect.end.x) - maxf(left_rect.position.x, right_rect.position.x) > 0.0001 else {}
	return {}


func _envelope_rect(cell: Dictionary) -> Rect2:
	var points: Array = cell.envelope_xz
	var minimum := Vector2(float(points[0][0]), float(points[0][1]))
	var maximum := minimum
	for point: Array in points:
		minimum.x = minf(minimum.x, float(point[0]))
		minimum.y = minf(minimum.y, float(point[1]))
		maximum.x = maxf(maximum.x, float(point[0]))
		maximum.y = maxf(maximum.y, float(point[1]))
	return Rect2(minimum, maximum - minimum)


func _add_safety_net() -> void:
	var bounds := Rect2()
	var first := true
	var lowest := 0.0
	for cell: Dictionary in map.cells:
		var envelope := Rect2(Vector2(cell.envelope_xz[0][0], cell.envelope_xz[0][1]), Vector2.ZERO)
		envelope = envelope.expand(Vector2(cell.envelope_xz[2][0], cell.envelope_xz[2][1]))
		bounds = envelope if first else bounds.merge(envelope)
		lowest = minf(lowest, float(cell.get("floor_y", 0.0))) if not first else float(cell.get("floor_y", 0.0))
		first = false
	var safety := StaticBody3D.new()
	safety.name = "SafetyNet"
	safety.position = Vector3(bounds.get_center().x, lowest - 4.0, bounds.get_center().y)
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
	var floor_y := float(spec.get("floor_y", 0.0))
	spawn_position = Vector3(center.x, floor_y + SPAWN_HEIGHT, center.y)
	spawn_yaw = 0.0
	for doorway: Dictionary in spec.doorways:
		if String(doorway.kind) == "open":
			var heading := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1])) - center
			spawn_yaw = atan2(-heading.x, -heading.y)
			return


func _light_layer(cell_id: String) -> int:
	return int(light_layers.get(cell_id, 1))


func _assign_light_layers() -> bool:
	var cells: Array[Dictionary] = []
	for cell: Dictionary in map.cells:
		if cell["role"] != "void" and not cell.has("module"):
			cells.append(cell)
	var conflicts := _light_conflicts(cells)
	var order: Array[String] = []
	for cell: Dictionary in cells:
		order.append(String(cell.cell_id))
	order.sort_custom(func(left: String, right: String) -> bool:
		if conflicts[left].size() != conflicts[right].size():
			return conflicts[left].size() > conflicts[right].size()
		return left < right
	)
	light_layers.clear()
	for cell_id: String in order:
		if not _assign_cell_layer(cell_id, conflicts):
			return false
	return true


func _light_conflicts(cells: Array[Dictionary]) -> Dictionary:
	var result := {}
	for cell: Dictionary in cells:
		result[String(cell.cell_id)] = []
	for left in cells.size():
		for right in range(left + 1, cells.size()):
			var left_id := String(cells[left].cell_id)
			var right_id := String(cells[right].cell_id)
			if _bounds_are_within_light_range(cells[left], cells[right]):
				result[left_id].append(right_id)
				result[right_id].append(left_id)
	return result


func _assign_cell_layer(cell_id: String, conflicts: Dictionary) -> bool:
	var occupied: Dictionary = {}
	for neighbor: String in conflicts[cell_id]:
		if light_layers.has(neighbor):
			occupied[int(light_layers[neighbor])] = true
	var layer := 1
	while layer <= GENERATED_LIGHT_LAYER_COUNT and occupied.has(layer):
		layer += 1
	if layer > GENERATED_LIGHT_LAYER_COUNT:
		push_error("Generated light culling needs more than %d isolated layers at %s" % [GENERATED_LIGHT_LAYER_COUNT, cell_id])
		return false
	light_layers[cell_id] = layer
	return true


func _bounds_are_within_light_range(left: Dictionary, right: Dictionary) -> bool:
	var left_bounds := _bounds(left)
	var right_bounds := _bounds(right)
	var gap_x := maxf(0.0, maxf(left_bounds.position.x - right_bounds.end.x, right_bounds.position.x - left_bounds.end.x))
	var gap_z := maxf(0.0, maxf(left_bounds.position.y - right_bounds.end.y, right_bounds.position.y - left_bounds.end.y))
	return Vector2(gap_x, gap_z).length() <= LIGHT_CULL_DISTANCE_M


func _bounds(cell: Dictionary) -> Rect2:
	var points: Array = cell.envelope_xz
	var minimum := Vector2(float(points[0][0]), float(points[0][1]))
	var maximum := minimum
	for point: Array in points:
		minimum.x = minf(minimum.x, float(point[0]))
		minimum.y = minf(minimum.y, float(point[1]))
		maximum.x = maxf(maximum.x, float(point[0]))
		maximum.y = maxf(maximum.y, float(point[1]))
	return Rect2(minimum, maximum - minimum)


func _set_module_render_layer(room: Node3D) -> void:
	var mask := 1 << (MODULE_RENDER_LAYER - 1)
	for instance: Node in room.find_children("*", "VisualInstance3D", true, false):
		(instance as VisualInstance3D).layers = mask


static func _area(rect: Array) -> float:
	return (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))


func _apply_psx_preset() -> void:
	if String(map.get("generator_version", "")) not in LIT_VERSIONS:
		PSX_PRESET.new().configure(self)
		return
	for room: Node3D in module_rooms.values():
		PSX_PRESET.new().configure(room)
	set_meta("psx_package", "URSC 1.5 subset / 8cd971d")
	set_meta("operator_approved", false)
	set_meta("psx_applied", true)


func _build_environment(lit_map: bool) -> void:
	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.04, 0.035)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.88, 0.86, 0.78)
	environment.ambient_light_energy = 0.2 if lit_map else 0.8
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
	player.set_script(WALK_PLAYER)  # hold-Shift sprint, walkthrough only (#191)
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
