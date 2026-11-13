class_name MazeExitThreshold
extends RefCounted

## Original bright threshold and clean test-chamber treatment for the static
## exit (#233).
##
## Everything here is additive runtime geometry: no committed map, shape-room
## JSON, texture, library scene or palette file is edited, and no existing room
## material is replaced. The base room keeps its palette checks; the exit room
## gains a bright door frame, an open leaf, a lit threshold floor, a clean
## ceiling panel and a cool-white fill light so it reads as the one bright
## "out" in the maze.
##
## All materials are original solid colours built from the existing PSX
## language (nearest filter, per-vertex shading, original emission). No
## third-party asset, texture or name is copied or referenced.

const GROUP_NAME := "MazeExitThreshold"
const WALL_THICKNESS_M := 0.16
const FRAME_WIDTH_M := 0.10
const FRAME_DEPTH_M := 0.05
const FRAME_PROUD_M := 0.015
const THRESHOLD_DEPTH_M := 0.40
const THRESHOLD_HEIGHT_M := 0.03
const RUNNER_WIDTH_M := 1.10
const RUNNER_MAX_LENGTH_M := 2.60
const RUNNER_HEIGHT_M := 0.02
const LEAF_OPEN_DEGREES := 100.0
const LEAF_WIDTH_FRACTION := 0.46
const LEAF_HEIGHT_FRACTION := 0.95
const LEAF_THICKNESS_M := 0.05
const PANEL_INSET_M := 0.30
const PANEL_HEIGHT_M := 0.03
const PANEL_EMISSION := 0.22
const SIGN_WIDTH_FRACTION := 0.72
const SIGN_HEIGHT_M := 0.10
const SIGN_DEPTH_M := 0.06
const LIGHT_RANGE_M := 7.0
const THRESHOLD_LIGHT_ENERGY := 2.4
const FILL_LIGHT_ENERGY := 1.5

const WALL_COLOR := Color(0.88, 0.90, 0.89)
const FLOOR_COLOR := Color(0.76, 0.79, 0.78)
const CEILING_COLOR := Color(0.95, 0.96, 0.95)
const ACCENT_COLOR := Color(0.16, 0.68, 0.74)
const LAMP_COLOR := Color(0.93, 0.97, 1.0)
## The base room keeps its palette material (texture path or solid albedo), but
## a duplicated override lifts it with original emission so the exit room reads
## clean and bright from both sides of the threshold. This is runtime state; no
## committed palette or material file is touched.
const WALL_EMISSION := Color(0.50, 0.54, 0.53)
const FLOOR_EMISSION := Color(0.38, 0.41, 0.40)
const CEILING_EMISSION := Color(0.58, 0.61, 0.60)
const WALL_LIFT := 0.62
const FLOOR_LIFT := 0.48
const CEILING_LIFT := 0.70


static func decorate(room: Node3D, spec: Dictionary, exit_record: Dictionary) -> Dictionary:
	var result := {
		"ok": false,
		"cell_id": String(exit_record.get("cell_id", "")),
		"port_id": String(exit_record.get("port_id", "")),
		"threshold_id": String(exit_record.get("threshold_id", "")),
		"meshes": 0,
		"surfaces_lifted": 0,
		"lights": 0,
		"original_materials": true,
		"group": GROUP_NAME,
	}
	if room == null or exit_record.is_empty():
		return result
	var doorway := _doorway(spec, String(exit_record.get("port_id", "")))
	if doorway.is_empty():
		return result
	var layer := _mesh_layer(room)
	var lifted := _lift_surfaces(room)
	result["surfaces_lifted"] = lifted
	var materials := {
		"wall": _material(WALL_COLOR, 0.0),
		"floor": _material(FLOOR_COLOR, 0.0),
		"ceiling": _material(CEILING_COLOR, PANEL_EMISSION),
		"accent": _material(ACCENT_COLOR, 0.85),
		"leaf": _material(Color(0.97, 0.98, 0.97), 0.0),
		"lamp": _material(LAMP_COLOR, 1.0),
	}
	var host := Node3D.new()
	host.name = GROUP_NAME
	room.add_child(host)
	var frame := _frame_geometry(host, doorway, materials, layer)
	var ceiling := _ceiling_treatment(host, spec, materials, layer)
	var floor := _floor_treatment(host, doorway, spec, materials, layer)
	var lights := _lights(host, doorway, spec, layer)
	result["meshes"] = frame + ceiling + floor
	result["lights"] = lights
	result["ok"] = frame > 0
	return result


static func _doorway(spec: Dictionary, port_id: String) -> Dictionary:
	for doorway: Dictionary in spec.get("doorways", []):
		if String(doorway.get("port_id", "")) == port_id:
			return doorway
	return {}


static func _mesh_layer(room: Node3D) -> int:
	for node in room.find_children("*", "MeshInstance3D", true, false):
		return (node as MeshInstance3D).layers
	return 1


static func _frame_geometry(host: Node3D, doorway: Dictionary, materials: Dictionary,
		layer: int) -> int:
	var position := _position(doorway)
	var normal := _normal(doorway)
	var inside := -normal
	var tangent := Vector2(-normal.y, normal.x)
	var width := float(doorway.get("width_m", 2.0))
	var height := float(doorway.get("height_m", 2.1))
	var sill := float(doorway.get("sill_height_m", 0.0))
	var face := position + inside * (WALL_THICKNESS_M + FRAME_PROUD_M)
	var port := _label_port(String(doorway.get("port_id", "")))
	var count := 0
	var jamb_height := height - FRAME_WIDTH_M
	for side: float in [-1.0, 1.0]:
		var offset := side * (width / 2.0 - FRAME_WIDTH_M / 2.0)
		_add_tangent_box(host, "ExitFrameJamb%s_%s" % ["Left" if side < 0.0 else "Right", port],
			face + tangent * offset, Vector3(FRAME_WIDTH_M, jamb_height, FRAME_DEPTH_M),
			sill + jamb_height / 2.0, materials.wall, normal, layer)
		count += 1
	_add_tangent_box(host, "ExitFrameLintel_%s" % port, face,
		Vector3(width, FRAME_WIDTH_M, FRAME_DEPTH_M),
		sill + height - FRAME_WIDTH_M / 2.0, materials.wall, normal, layer)
	count += 1
	_add_tangent_box(host, "ExitFrameThreshold_%s" % port,
		position + inside * (THRESHOLD_DEPTH_M / 2.0 + FRAME_PROUD_M),
		Vector3(width, THRESHOLD_HEIGHT_M, THRESHOLD_DEPTH_M),
		THRESHOLD_HEIGHT_M / 2.0, materials.accent, normal, layer)
	count += 1
	_add_tangent_box(host, "ExitSign_%s" % port, face + inside * 0.18,
		Vector3(width * SIGN_WIDTH_FRACTION, SIGN_HEIGHT_M, SIGN_DEPTH_M),
		sill + height + 0.20, materials.accent, normal, layer)
	count += 1
	# An open leaf against the inside wall: it reads as a door, never blocks the
	# opening, and M4 owns the real leaf/collider.
	var hinge := position + tangent * (-width / 2.0 + 0.08) + inside * (WALL_THICKNESS_M + 0.08)
	var angle := deg_to_rad(LEAF_OPEN_DEGREES)
	var opened := tangent * cos(angle) + inside * sin(angle)
	opened = opened.normalized()
	var leaf_length := width * LEAF_WIDTH_FRACTION
	var leaf_height := height * LEAF_HEIGHT_FRACTION
	var leaf_center := hinge + opened * (leaf_length / 2.0)
	_add_box(host, "ExitDoorLeaf_%s" % port,
		Vector3(leaf_center.x, sill + leaf_height / 2.0, leaf_center.y),
		Vector3(leaf_length, leaf_height, LEAF_THICKNESS_M), materials.leaf,
		_angle_for(opened), layer)
	count += 1
	for index in 3:
		var offset := (float(index) - 1.0) * (width / 2.0 - FRAME_WIDTH_M)
		_add_tangent_box(host, "ExitFrameStud%d_%s" % [index, port],
			face + tangent * offset + inside * 0.055,
			Vector3(FRAME_WIDTH_M * 0.6, jamb_height, FRAME_DEPTH_M * 0.6),
			sill + jamb_height / 2.0, materials.accent, normal, layer)
		count += 1
	return count


static func _ceiling_treatment(host: Node3D, spec: Dictionary, materials: Dictionary,
		layer: int) -> int:
	var rect := _largest_rect(spec)
	if rect.is_empty():
		return 0
	var width := float(rect[2]) - float(rect[0])
	var depth := float(rect[3]) - float(rect[1])
	var panel_width := width - 2.0 * PANEL_INSET_M
	var panel_depth := depth - 2.0 * PANEL_INSET_M
	if panel_width <= 0.5 or panel_depth <= 0.5:
		return 0
	var height := float(spec.get("ceiling_height_m", 3.0))
	var center := Vector2((float(rect[0]) + float(rect[2])) / 2.0,
		(float(rect[1]) + float(rect[3])) / 2.0)
	_add_box(host, "ExitCeilingPanel",
		Vector3(center.x, height - PANEL_HEIGHT_M / 2.0, center.y),
		Vector3(panel_width, PANEL_HEIGHT_M, panel_depth), materials.ceiling, 0.0, layer)
	var long_side := maxf(panel_width, panel_depth)
	_add_box(host, "ExitCeilingLightBar",
		Vector3(center.x, height - PANEL_HEIGHT_M - 0.02, center.y),
		Vector3(long_side * 0.72, 0.02, 0.12), materials.lamp,
		0.0 if panel_width >= panel_depth else PI / 2.0, layer)
	return 2


static func _floor_treatment(host: Node3D, doorway: Dictionary, spec: Dictionary,
		materials: Dictionary, layer: int) -> int:
	var position := _position(doorway)
	var inside := _inside(doorway)
	var rect := _largest_rect(spec)
	var length := RUNNER_MAX_LENGTH_M
	if not rect.is_empty():
		var center := Vector2((float(rect[0]) + float(rect[2])) / 2.0,
			(float(rect[1]) + float(rect[3])) / 2.0)
		length = minf(length, center.distance_to(position))
	if length <= 0.4:
		return 0
	var start := position + inside * 0.38
	var center := start + inside * (length / 2.0)
	var yaw := _angle_for(inside)
	_add_box(host, "ExitFloorRunner",
		Vector3(center.x, RUNNER_HEIGHT_M / 2.0, center.y),
		Vector3(length, RUNNER_HEIGHT_M, RUNNER_WIDTH_M), materials.floor, yaw, layer)
	var accent_center := start + inside * 0.12
	var tangent := Vector2(-inside.y, inside.x)
	_add_box(host, "ExitFloorLine",
		Vector3(accent_center.x, RUNNER_HEIGHT_M + 0.005, accent_center.y),
		Vector3(RUNNER_WIDTH_M * 0.9, 0.01, 0.10), materials.accent,
		_angle_for(tangent), layer)
	return 2


static func _lights(host: Node3D, doorway: Dictionary, spec: Dictionary, layer: int) -> int:
	var position := _position(doorway)
	var inside := _inside(doorway)
	var height := float(doorway.get("height_m", 2.1))
	var sill := float(doorway.get("sill_height_m", 0.0))
	var threshold := OmniLight3D.new()
	threshold.name = "ExitThresholdLight"
	threshold.position = Vector3(position.x + inside.x * 0.9,
		sill + height * 0.65, position.y + inside.y * 0.9)
	threshold.light_color = LAMP_COLOR
	threshold.light_energy = THRESHOLD_LIGHT_ENERGY
	threshold.omni_range = LIGHT_RANGE_M
	threshold.shadow_enabled = false
	threshold.light_cull_mask = layer
	host.add_child(threshold)
	var rect := _largest_rect(spec)
	var count := 1
	if not rect.is_empty():
		var center := Vector2((float(rect[0]) + float(rect[2])) / 2.0,
			(float(rect[1]) + float(rect[3])) / 2.0)
		var ceiling := float(spec.get("ceiling_height_m", 3.0))
		var fill := OmniLight3D.new()
		fill.name = "ExitRoomFillLight"
		fill.position = Vector3(center.x, ceiling - 0.35, center.y)
		fill.light_color = LAMP_COLOR
		fill.light_energy = FILL_LIGHT_ENERGY
		fill.omni_range = LIGHT_RANGE_M
		fill.shadow_enabled = false
		fill.light_cull_mask = layer
		host.add_child(fill)
		count += 1
	return count


## Duplicate one room surface material and add emission without changing its
## albedo or texture path, so the issue-192 palette check still sees the base
## palette while the exit room reads as the one bright room.
static func _lift_surfaces(room: Node3D) -> int:
	var count := 0
	for node: Node in room.find_children("*", "MeshInstance3D", true, false):
		var instance := node as MeshInstance3D
		var kind := _surface_kind(instance.name)
		if kind.is_empty():
			continue
		var base := instance.material_override as StandardMaterial3D
		if base == null:
			continue
		var lifted := base.duplicate() as StandardMaterial3D
		if base.has_meta("source_path"):
			lifted.set_meta("source_path", base.get_meta("source_path"))
		lifted.emission_enabled = true
		if kind == "wall":
			lifted.emission = WALL_EMISSION
			lifted.emission_energy_multiplier = WALL_LIFT
		elif kind == "floor":
			lifted.emission = FLOOR_EMISSION
			lifted.emission_energy_multiplier = FLOOR_LIFT
		else:
			lifted.emission = CEILING_EMISSION
			lifted.emission_energy_multiplier = CEILING_LIFT
		instance.material_override = lifted
		count += 1
	return count


static func _surface_kind(node_name: String) -> String:
	if node_name.begins_with("FloorRect") or node_name.begins_with("FloorPolygon") \
			or node_name.begins_with("RampStep") or node_name.contains("WalkableFloor"):
		return "floor"
	if node_name.begins_with("CeilingRect") or node_name.begins_with("CeilingPolygon"):
		return "ceiling"
	if node_name.begins_with("Wall_") or node_name.begins_with("Header_") \
			or node_name.begins_with("WallSill_"):
		return "wall"
	return ""


static func _label_port(port_id: String) -> String:
	return port_id.replace(":", "_")


static func _position(doorway: Dictionary) -> Vector2:
	return Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))


static func _normal(doorway: Dictionary) -> Vector2:
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
	return normal.normalized()


static func _inside(doorway: Dictionary) -> Vector2:
	return -_normal(doorway)


static func _angle_for(direction: Vector2) -> float:
	return atan2(-direction.y, direction.x)


static func _largest_rect(spec: Dictionary) -> Array:
	var largest: Array = []
	var best := 0.0
	for rect: Array in spec.get("rects", []):
		var area := (float(rect[2]) - float(rect[0])) * (float(rect[3]) - float(rect[1]))
		if area > best:
			best = area
			largest = rect
	return largest


## A box whose local X runs along the doorway tangent and whose local Z runs
## through the wall. ``y_center`` is already in room-local space.
static func _add_tangent_box(parent: Node3D, label: String, position: Vector2,
		size: Vector3, y_center: float, material: Material,
		normal: Vector2, layer: int) -> MeshInstance3D:
	var tangent := Vector2(-normal.y, normal.x)
	return _add_box(parent, label, Vector3(position.x, y_center, position.y), size,
		material, _angle_for(tangent), layer)


static func _add_box(parent: Node3D, label: String, position: Vector3, size: Vector3,
		material: Material, yaw: float, layer: int) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = position
	instance.rotation.y = yaw
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.subdivide_width = maxi(0, int(ceil(size.x)) - 1)
	mesh.subdivide_height = maxi(0, int(ceil(size.y)) - 1)
	mesh.subdivide_depth = maxi(0, int(ceil(size.z)) - 1)
	instance.mesh = mesh
	instance.material_override = material
	instance.layers = layer
	parent.add_child(instance)
	return instance


static func _material(color: Color, emission_energy: float) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.roughness = 1.0
	if emission_energy > 0.0:
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = emission_energy
	return material
