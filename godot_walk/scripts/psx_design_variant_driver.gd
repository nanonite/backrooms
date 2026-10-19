extends Node

const CATALOG := preload("res://scripts/psx_design_variant_catalog.gd")
const FLUSH_SHIFT_M := 0.0155
const DROPPED_CEILING_Y := 1.4
const SOURCE_WALL_TEXTURE := "res://assets/psx_extension/textures/wallpaper_source_video.png"
const SOURCE_TEXTURE_DIR := "res://assets/psx_extension/textures/"
const FLOOR_Y := -1.143
const CEILING_Y := 1.8
const SOURCE_CEILING_Y := 1.0
const SOURCE_COLUMN_X := 1.25
const SOURCE_COLUMN_Z := 0.2
const SOURCE_COLUMN_WIDTH := 0.62
const CEILING_CORNER_TRIM := 0.08
const ROOM_WEST := -1.35
const ROOM_EAST := 4.0
const ROOM_SOUTH := -2.8
const ROOM_NORTH := 3.4

@export_enum("v2_control", "door_flush", "door_removed", "wall_endcap",
	"north_wall_smooth", "north_wall_source_texture", "clean_ceiling",
	"source_texture_cleanup") var variant_id := "v2_control"


func _ready() -> void:
	var cli_variant := _variant_from_arguments()
	if not cli_variant.is_empty():
		variant_id = cli_variant
	var spec := CATALOG.load_variant(variant_id)
	if spec.is_empty():
		get_tree().quit(1)
		return
	var room := get_parent() as Node3D
	if room == null:
		get_tree().quit(1)
		return
	var boundaries := room.get_node_or_null("AuthoredBoundaries") as Node3D
	if boundaries == null or not _apply_doorway_policy(room, spec["design"]["doorway_policy"]):
		get_tree().quit(1)
		return
	if not _apply_surface_treatment(room, boundaries, str(spec["design"].get("surface_treatment", "none"))):
		get_tree().quit(1)
		return
	room.set_meta("design_candidate_id", variant_id)
	room.set_meta("design_candidate_spec", spec)
	print("DESIGN_CANDIDATE id=%s hypothesis=%s" % [variant_id, spec["hypothesis"]])


func _variant_from_arguments() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--variant="):
			return argument.trim_prefix("--variant=")
	return ""


func _apply_doorway_policy(room: Node3D, policy: String) -> bool:
	var boundaries := room.get_node_or_null("AuthoredBoundaries")
	if boundaries == null:
		push_error("Candidate scene is missing AuthoredBoundaries")
		return false
	if policy == "wall_endcap":
		return _apply_wall_endcap(room, boundaries)
	for child in boundaries.get_children():
		if not child is MeshInstance3D or not _is_door_component(child.name):
			continue
		if policy == "omit":
			child.visible = false
		elif policy == "flush_to_wall_face":
			if child.name == "EastServiceDoorFrame":
				continue
			child.position.x += FLUSH_SHIFT_M
	return true


func _apply_surface_treatment(room: Node3D, boundaries: Node3D, treatment: String) -> bool:
	if treatment == "none":
		return true
	if treatment == "north_wall_paneling":
		return _apply_north_wall_paneling(room, boundaries)
	if treatment == "north_wall_source_texture":
		return _apply_north_wall_source_texture(room, boundaries)
	if treatment == "lowered_ceiling_grid":
		return _apply_clean_ceiling_grid(room, boundaries)
	if treatment == "source_texture_room_shell":
		return _apply_source_texture_room_shell(room, boundaries)
	if treatment == "source_floor_single_column":
		return _apply_source_floor_single_column(room)
	if treatment == "source_floor_ceiling_single_column":
		return _apply_source_floor_ceiling_single_column(room, boundaries)
	push_error("Unsupported PSX surface treatment: %s" % treatment)
	return false


func _apply_source_texture_room_shell(room: Node3D, boundaries: Node3D) -> bool:
	var north := _first_mesh(boundaries.get_node_or_null("NorthBoundary"))
	var ceiling := boundaries.get_node_or_null("CeilingBackstop") as MeshInstance3D
	var wall_material := _source_video_material("wallpaper_source_video.png", Vector3(3.0, 1.0, 1.0))
	if north == null or ceiling == null or wall_material == null:
		push_error("Source-texture cleanup is missing a boundary or registered source texture")
		return false
	north.material_override = wall_material
	north.position.z -= 0.08
	ceiling.position.y = 1.55
	ceiling.material_override = _source_video_material("ceiling_source_video.png", Vector3.ONE)
	if ceiling.material_override == null:
		return false
	_reposition_ceiling_lights(boundaries)
	_add_source_floor(room)
	_add_source_column(room)
	return true


func _reposition_ceiling_lights(boundaries: Node3D) -> void:
	for child in boundaries.get_children():
		if child is MeshInstance3D and child.name.begins_with("CeilingLight"):
			child.position.y = 1.49


func _add_source_floor(room: Node3D) -> bool:
	var material := _source_video_material("floor_source_video.png", Vector3.ONE)
	if material == null:
		return false
	var floor := MeshInstance3D.new()
	floor.name = "DesignSourceFloor"
	var plane := PlaneMesh.new()
	plane.size = Vector2(ROOM_EAST - ROOM_WEST, ROOM_NORTH - ROOM_SOUTH)
	floor.mesh = plane
	floor.position = Vector3((ROOM_WEST + ROOM_EAST) * 0.5, FLOOR_Y + 0.015,
		(ROOM_SOUTH + ROOM_NORTH) * 0.5)
	floor.material_override = material
	room.add_child.call_deferred(floor)
	return true


func _apply_source_floor_single_column(room: Node3D) -> bool:
	if not _add_source_floor(room):
		return false
	return _add_aligned_source_column(room)


func _apply_source_floor_ceiling_single_column(room: Node3D, boundaries: Node3D) -> bool:
	var ceiling := boundaries.get_node_or_null("CeilingBackstop") as MeshInstance3D
	var material := _source_video_material("ceiling_source_video.png", Vector3.ONE)
	if ceiling == null or material == null:
		return false
	ceiling.position.y = SOURCE_CEILING_Y
	ceiling.material_override = material
	if not _fit_visible_walls_to_source_ceiling(boundaries):
		return false
	_reposition_ceiling_lights_to(SOURCE_CEILING_Y - 0.09, boundaries)
	if not _add_source_floor(room) or not _add_aligned_source_column(room):
		return false
	return _add_source_ceiling_corner_trim(room, boundaries)


func _add_aligned_source_column(room: Node3D) -> bool:
	var height := CEILING_Y - FLOOR_Y
	var material := _source_video_material("column_source_video.png", Vector3.ONE)
	if material == null:
		return false
	_add_endcap_panel(room, "DesignAlignedSourceColumn",
		Vector3(SOURCE_COLUMN_X, FLOOR_Y + height * 0.5, SOURCE_COLUMN_Z),
		Vector3(SOURCE_COLUMN_WIDTH, height, SOURCE_COLUMN_WIDTH), material)
	return true


func _fit_visible_walls_to_source_ceiling(boundaries: Node3D) -> bool:
	for boundary_name in ["WestBoundary", "EastBoundary", "NorthBoundary", "SouthBoundary"]:
		var boundary := boundaries.get_node_or_null(boundary_name) as Node3D
		var mesh := _first_mesh(boundary)
		if boundary == null or mesh == null:
			return false
		_fit_wall_mesh_height(mesh, boundary, SOURCE_CEILING_Y + 0.035)
	return true


func _fit_wall_mesh_height(mesh: MeshInstance3D, boundary: Node3D, top_y: float) -> void:
	var height := top_y - FLOOR_Y
	var original_height := CEILING_Y - FLOOR_Y
	mesh.scale.y = height / original_height
	mesh.position.y = (FLOOR_Y + top_y) * 0.5 - boundary.position.y


func _reposition_ceiling_lights_to(height: float, boundaries: Node3D) -> void:
	for child in boundaries.get_children():
		if child is MeshInstance3D and child.name.begins_with("CeilingLight"):
			child.position.y = height


func _add_source_ceiling_corner_trim(room: Node3D, boundaries: Node3D) -> bool:
	var material := _material_from(boundaries, "NorthRail")
	if material == null:
		return false
	var trim_y := SOURCE_CEILING_Y
	var width := ROOM_EAST - ROOM_WEST
	var depth := ROOM_NORTH - ROOM_SOUTH
	_add_endcap_panel(room, "DesignCeilingTrimNorth",
		Vector3((ROOM_WEST + ROOM_EAST) * 0.5, trim_y, ROOM_NORTH - 0.045),
		Vector3(width, CEILING_CORNER_TRIM, CEILING_CORNER_TRIM), material)
	_add_endcap_panel(room, "DesignCeilingTrimSouth",
		Vector3((ROOM_WEST + ROOM_EAST) * 0.5, trim_y, ROOM_SOUTH + 0.045),
		Vector3(width, CEILING_CORNER_TRIM, CEILING_CORNER_TRIM), material)
	_add_side_ceiling_trim(room, "West", ROOM_WEST + 0.045, trim_y, depth, material)
	_add_side_ceiling_trim(room, "East", ROOM_EAST - 0.045, trim_y, depth, material)
	return true


func _add_side_ceiling_trim(room: Node3D, label: String, x: float,
		y: float, depth: float, material: Material) -> void:
	_add_endcap_panel(room, "DesignCeilingTrim%s" % label,
		Vector3(x, y, (ROOM_SOUTH + ROOM_NORTH) * 0.5),
		Vector3(CEILING_CORNER_TRIM, CEILING_CORNER_TRIM, depth), material)


func _add_source_column(room: Node3D) -> void:
	var height := CEILING_Y - FLOOR_Y
	_add_endcap_panel(room, "DesignSourceColumn", Vector3(1.25, FLOOR_Y + height * 0.5, 2.55),
		Vector3(0.58, height, 0.58),
		_source_video_material("column_source_video.png", Vector3.ONE))


func _source_video_material(filename: String, uv_scale: Vector3) -> StandardMaterial3D:
	var texture := load(SOURCE_TEXTURE_DIR + filename) as Texture2D
	if texture == null:
		return null
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.roughness = 1.0
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.uv1_scale = uv_scale
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _apply_north_wall_paneling(room: Node3D, boundaries: Node3D) -> bool:
	var wall_mesh := _first_mesh(boundaries.get_node_or_null("NorthBoundary"))
	var trim_material := _material_from(boundaries, "NorthRail")
	if wall_mesh == null or trim_material == null:
		push_error("Candidate scene is missing north wall treatment inputs: wall=%s trim=%s" % [
			str(wall_mesh != null), str(trim_material != null),
		])
		return false
	wall_mesh.material_override = _flat_material(Color(0.68, 0.64, 0.48))
	_add_north_wall_stiles(room, trim_material)
	return true


func _apply_north_wall_source_texture(room: Node3D, boundaries: Node3D) -> bool:
	var wall_mesh := _first_mesh(boundaries.get_node_or_null("NorthBoundary"))
	var trim_material := _material_from(boundaries, "NorthRail")
	var texture := load(SOURCE_WALL_TEXTURE) as Texture2D
	if wall_mesh == null or trim_material == null or texture == null:
		push_error("Source-textured north wall is missing its wall, trim, or source image")
		return false
	wall_mesh.material_override = _source_wallpaper_material(texture)
	_add_north_wall_stiles(room, trim_material)
	return true


func _add_north_wall_stiles(room: Node3D, trim_material: Material) -> void:
	var bottom := -0.5
	var top := 1.58
	var height := top - bottom
	for index in range(4):
		var x := -0.65 + float(index) * 1.35
		_add_endcap_panel(room, "DesignNorthWallStile%d" % index,
			Vector3(x, (bottom + top) * 0.5, 3.235), Vector3(0.045, height, 0.05),
			trim_material)
	_add_endcap_panel(room, "DesignNorthWallTopRail",
		Vector3(1.325, top, 3.235), Vector3(5.05, 0.04, 0.05), trim_material)


func _apply_clean_ceiling_grid(room: Node3D, boundaries: Node3D) -> bool:
	var ceiling_mesh := boundaries.get_node_or_null("CeilingBackstop") as MeshInstance3D
	var grid_material := _material_from(boundaries, "NorthRail")
	if ceiling_mesh == null or grid_material == null:
		push_error("Candidate scene is missing the ceiling or its trim material")
		return false
	ceiling_mesh.position.y = DROPPED_CEILING_Y + 0.035
	ceiling_mesh.material_override = _flat_material(Color(0.68, 0.65, 0.53))
	for child in boundaries.get_children():
		if child is MeshInstance3D and child.name.begins_with("CeilingLight"):
			child.position.y = DROPPED_CEILING_Y - 0.055
	for index in range(1, 5):
		var x := -1.35 + float(index) * 1.07
		_add_endcap_panel(room, "DesignCeilingGridX%d" % index,
			Vector3(x, DROPPED_CEILING_Y - 0.02, 0.3),
			Vector3(0.025, 0.025, 5.95), grid_material)
		var z := -2.8 + float(index) * 1.24
		_add_endcap_panel(room, "DesignCeilingGridZ%d" % index,
			Vector3(1.325, DROPPED_CEILING_Y - 0.02, z),
			Vector3(5.1, 0.025, 0.025), grid_material)
	return true


func _flat_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 1.0
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _first_mesh(parent: Node) -> MeshInstance3D:
	if parent == null:
		return null
	for child in parent.get_children():
		if child is MeshInstance3D:
			return child
	return null


func _apply_wall_endcap(room: Node3D, boundaries: Node3D) -> bool:
	for child in boundaries.get_children():
		if child is MeshInstance3D and _is_door_component(child.name):
			child.visible = false
	var wall_material := _wallpaper_material()
	var wainscot_material := _material_from(boundaries, "EastWainscot")
	var trim_material := _material_from(boundaries, "EastRail")
	if wall_material == null or wainscot_material == null or trim_material == null:
		push_error("Candidate scene is missing east-end wall materials: wall=%s wainscot=%s trim=%s" % [
			str(wall_material != null), str(wainscot_material != null),
			str(trim_material != null),
		])
		return false
	_add_endcap_panel(room, "DesignEndcapWallpaper", Vector3(3.84, 0.3285, 0.3),
		Vector3(0.02, 2.943, 6.2), wall_material)
	_add_endcap_panel(room, "DesignEndcapWainscot", Vector3(3.82, -0.833, 0.3),
		Vector3(0.02, 0.62, 6.2), wainscot_material)
	_add_endcap_panel(room, "DesignEndcapRail", Vector3(3.80, -0.523, 0.3),
		Vector3(0.02, 0.045, 6.2), trim_material)
	return true


func _material_from(parent: Node, relative_path: String) -> Material:
	var source := parent.get_node_or_null(relative_path)
	if source is MeshInstance3D:
		return source.material_override
	if source == null:
		return null
	for child in source.get_children():
		if child is MeshInstance3D and child.material_override != null:
			return child.material_override
	return null


func _wallpaper_material() -> Material:
	var texture := load("res://assets/psx_extension/textures/wallpaper.png") as Texture2D
	if texture == null:
		return null
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.roughness = 1.0
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.uv1_scale = Vector3(3.0, 1.8, 1.0)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _source_wallpaper_material(texture: Texture2D) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.roughness = 1.0
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.uv1_scale = Vector3(3.0, 1.0, 1.0)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _add_endcap_panel(room: Node3D, label: String, centre: Vector3,
		size: Vector3, material: Material) -> void:
	var mesh := MeshInstance3D.new()
	mesh.name = label
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.position = centre
	mesh.material_override = material
	room.add_child.call_deferred(mesh)


func _is_door_component(node_name: String) -> bool:
	return (
		node_name.begins_with("EastServiceDoor")
		or node_name.begins_with("EastDoorPanel")
		or node_name.begins_with("EastDoorHandle")
	)
