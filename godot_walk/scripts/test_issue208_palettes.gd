extends SceneTree

## Headless palette and floor-acoustic check for gmap-0.12.0 (#208).
## godot4 --headless --path godot_walk --script res://scripts/test_issue208_palettes.gd -- \
##   --map=res://room_catalog/generative_maps/gmap-32-gmap-0.12.0.json \
##   --rooms=res://room_catalog/shape_rooms/gmap-32-gmap-0.12.0/index.json \
##   [--out=res://evidence/2026-11-09-issue-208/runtime_gmap-32.json]

const ASSEMBLY := preload("res://scripts/generative_map_assembly.gd")
const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const FLOOR_TAGS := {
	"tiled_institutional": "tile",
	"metal_service": "metal",
	"wood_parquet": "wood",
}

var failures: Array[String] = []
var map: Dictionary = {}
var specs: Dictionary = {}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var map_data: Variant = ASSEMBLY.load_json(ASSEMBLY.argument("--map="))
	var index_data: Variant = ASSEMBLY.load_json(ASSEMBLY.argument("--rooms="))
	if not map_data is Dictionary or not index_data is Dictionary:
		_fail("Pass --map=res://...json and --rooms=res://.../index.json after --")
		quit(1)
		return
	map = map_data
	specs = ASSEMBLY.load_specs(ASSEMBLY.argument("--rooms="))
	var assembly := ASSEMBLY.new()
	assembly.auto_start = false
	root.add_child(assembly)
	assembly.assemble(map, specs)
	await physics_frame
	await physics_frame
	var counts := {}
	var floor_colliders := 0
	var floor_visuals := 0
	for cell_id: String in specs:
		var spec: Dictionary = specs[cell_id]
		var palette_id := String(spec.materials.get("palette_id", ""))
		if not FLOOR_TAGS.has(palette_id):
			continue
		counts[palette_id] = int(counts.get(palette_id, 0)) + 1
		var expected := String(spec.materials.acoustic.floor)
		_expect(expected == String(FLOOR_TAGS[palette_id]),
			"%s: floor tag %s does not match palette %s" % [cell_id, expected, palette_id])
		_expect(String(spec.materials.registry_version) == "0.3.0",
			"%s: registry version is not 0.3.0" % cell_id)
		var room: Node3D = assembly.rooms.get(cell_id)
		_expect(room != null, "%s: no instanced room" % cell_id)
		if room == null:
			continue
		var bodies := room.find_children("WalkableFloor", "StaticBody3D", true, false)
		_expect(not bodies.is_empty(), "%s: no WalkableFloor collider" % cell_id)
		for body_node: Node in bodies:
			var body := body_node as StaticBody3D
			floor_colliders += 1
			var tag := String(body.get_meta("surface_acoustic", ""))
			_expect(tag == expected, "%s: floor collider tag %s, expected %s" % [cell_id, tag, expected])
			_expect(int(body.get_meta("surface_wear", -1)) == int(spec.materials.get("wear", 0)),
				"%s: floor collider wear metadata differs" % cell_id)
			_expect(String(body.get_meta("surface_variant", "")) == String(spec.materials.floor.variant),
				"%s: floor collider variant metadata differs" % cell_id)
		var visual := room.get_node_or_null("AuthoredVisuals/WalkableFloorVisual") as Node3D
		_expect(visual != null, "%s: no WalkableFloorVisual" % cell_id)
		if visual == null:
			continue
		for mesh_node in visual.get_children():
			if not mesh_node is MeshInstance3D:
				continue
			floor_visuals += 1
			var source := MATERIALS.source_path((mesh_node as MeshInstance3D).material_override)
			_expect(source == String(spec.materials.floor.texture),
				"%s: floor visual texture %s, expected %s" % [cell_id, source, spec.materials.floor.texture])
	for palette_id: String in FLOOR_TAGS:
		_expect(int(counts.get(palette_id, 0)) > 0,
			"map has no %s room to check" % palette_id)
	var report := {
		"map_id": map.map_id,
		"rooms": counts,
		"floor_colliders": floor_colliders,
		"floor_visuals": floor_visuals,
		"failures": failures,
	}
	_write_report(report)
	print("ISSUE208_PALETTES: %s map=%s rooms=%s floor_colliders=%d floor_visuals=%d failures=%d" % [
		"PASS" if failures.is_empty() else "FAIL", map.map_id, JSON.stringify(counts),
		floor_colliders, floor_visuals, failures.size()])
	root.remove_child(assembly)
	assembly.free()
	quit(0 if failures.is_empty() else 1)


func _write_report(report: Dictionary) -> void:
	var out := ASSEMBLY.argument("--out=")
	if out.is_empty():
		return
	var text := JSON.stringify(report, "\t", true) + "\n"
	var absolute := ProjectSettings.globalize_path(out)
	if FileAccess.file_exists(absolute) and FileAccess.get_file_as_string(absolute) != text:
		_fail("Refusing to overwrite a different runtime report: " + out)
		return
	DirAccess.make_dir_recursive_absolute(absolute.get_base_dir())
	var file := FileAccess.open(absolute, FileAccess.WRITE)
	if file == null:
		_fail("Cannot write runtime report: " + out)
		return
	file.store_string(text)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		printerr("ISSUE208_PALETTES: " + message)


func _fail(message: String) -> void:
	failures.append(message)
	printerr("ISSUE208_PALETTES: " + message)
