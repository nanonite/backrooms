class_name ShapeRoomBuilder
extends RefCounted

## Builds one generated shape room from its spec: separate AuthoredVisuals and
## AuthoredBoundaries nodes, as in issue165_room_geometry.gd. Everything stays inside
## the room's polygon, so walls of adjacent cells sit back to back.

const MATERIALS := preload("res://scripts/shape_room_materials.gd")
const DOORWAYS := preload("res://scripts/doorway_sizes.gd")
const DIAGONAL := preload("res://scripts/shape_room_diagonal.gd")
const DIAGONAL_PASSAGE := preload("res://scripts/shape_room_diagonal_passage.gd")
const WALL_THICKNESS := 0.16
const TRIM_WIDTH := 0.06
const TRIM_PROTRUSION := 0.04
const TRIM_HEIGHT := 0.06
const PANEL_DEPTH := 0.10
const PANEL_THICKNESS := 0.03
const SEAM_REACH := 0.1
const LAMP_SIZE := Vector3(0.9, 0.03, 0.42)
const EPSILON := 0.001
## A doorway that opens onto a library room (#189) is cut this much wider on each side and
## higher than the library's own opening, so the wall ends and header underside stay out of
## the planes of the library's matching faces.
const MODULE_JOINT_RECESS := 0.04
const FLOOR_VISUAL_THICKNESS := 0.05
const FLOOR_COLLIDER_THICKNESS := 0.12


## `options` (all optional) are for the #190 negative controls only: `diagonal_collision` false builds
## diagonal walls without collision, `diagonal_pullback` shortens diagonal wall boxes at both ends.
static func build(parent: Node3D, spec: Dictionary, materials: Dictionary,
		forced_closed: PackedStringArray = PackedStringArray(),
		module_joints: PackedStringArray = PackedStringArray(), options: Dictionary = {}) -> Node3D:
	var room := Node3D.new()
	room.name = String(spec.cell_id)
	parent.add_child(room)
	var visuals := _group(room, "AuthoredVisuals")
	var boundaries := _group(room, "AuthoredBoundaries")
	var context := _context(spec, materials, forced_closed, module_joints)
	context["chamfered"] = DIAGONAL.is_chamfered(spec)
	context["diagonal_passage_visuals"] = spec.has("diagonal_passage")
	context["diagonal_collision"] = bool(options.get("diagonal_collision", true))
	context["diagonal_pullback"] = float(options.get("diagonal_pullback", 0.0))
	_add_floor(visuals, boundaries, context)
	_add_ceiling(visuals, context)
	_add_walls(visuals, boundaries, context)
	_add_lamps(visuals, context)
	room.set_meta("cell_id", String(spec.cell_id))
	room.set_meta("walkable_polygon_xz", PackedVector2Array(context.ring))
	room.set_meta("ceiling_height_m", float(spec.ceiling_height_m))
	room.set_meta("registration_accepted", false)
	room.set_meta("scale_calibrated", false)
	return room


static func ring_of(spec: Dictionary) -> Array[Vector2]:
	var ring: Array[Vector2] = []
	for point: Array in spec.outline_xz:
		ring.append(Vector2(float(point[0]), float(point[1])))
	if _signed_area(ring) < 0.0:
		ring.reverse()
	return ring


static func _context(spec: Dictionary, materials: Dictionary, forced_closed: PackedStringArray,
		module_joints: PackedStringArray) -> Dictionary:
	var doorways: Array[Dictionary] = []
	for source: Dictionary in spec.doorways:
		var doorway := source.duplicate()
		var size := DOORWAYS.size_of(source)
		doorway["door_width"] = size.x
		doorway["door_height"] = size.y
		doorway["recess"] = MODULE_JOINT_RECESS if module_joints.has(String(source.port_id)) else 0.0
		doorway["effective_kind"] = "closed_visible" if (
			String(source.kind) != "open" or forced_closed.has(String(source.port_id))) else "open"
		doorways.append(doorway)
	return {"spec": spec, "materials": materials, "ring": ring_of(spec),
		"height": float(spec.ceiling_height_m), "doorways": doorways}


static func _signed_area(ring: Array[Vector2]) -> float:
	var total := 0.0
	for index in ring.size():
		var next := ring[(index + 1) % ring.size()]
		total += ring[index].x * next.y - next.x * ring[index].y
	return total / 2.0


static func _add_floor(visuals: Node3D, boundaries: Node3D, context: Dictionary) -> void:
	var floor_visual := _group(visuals, "WalkableFloorVisual")
	var body := StaticBody3D.new()
	body.name = "WalkableFloor"
	boundaries.add_child(body)
	if context.chamfered:
		DIAGONAL.add_floor(floor_visual, body, context, FLOOR_COLLIDER_THICKNESS)
	else:
		_add_floor_rects(floor_visual, body, context)
	for doorway: Dictionary in context.doorways:
		if doorway.effective_kind == "open":
			_add_floor_seam(body, doorway)


static func _add_floor_rects(floor_visual: Node3D, body: StaticBody3D, context: Dictionary) -> void:
	for rect: Array in context.spec.rects:
		var x0 := float(rect[0]); var z0 := float(rect[1]); var x1 := float(rect[2]); var z1 := float(rect[3])
		var center := Vector2((x0 + x1) / 2.0, (z0 + z1) / 2.0)
		var material := MATERIALS.scaled(context.materials, "floor", x1 - x0, z1 - z0)
		_add_box(floor_visual, "FloorRect", Vector3(center.x, -FLOOR_VISUAL_THICKNESS / 2.0, center.y),
			Vector3(x1 - x0, FLOOR_VISUAL_THICKNESS, z1 - z0), material)
		_add_collision(body, "FloorRectShape", Vector3(center.x, -FLOOR_COLLIDER_THICKNESS / 2.0, center.y),
			Vector3(x1 - x0, FLOOR_COLLIDER_THICKNESS, z1 - z0))


static func _add_floor_seam(body: StaticBody3D, doorway: Dictionary) -> void:
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
	if absf(normal.x) > 0.5 and absf(normal.y) > 0.5:
		return  # triangulated diagonal floors overlap under the opening; an axis-aligned seam box would be wrong.
	var width: float = doorway.door_width
	var size := Vector3(width, FLOOR_COLLIDER_THICKNESS, 2.0 * SEAM_REACH)
	if absf(normal.x) > 0.5:
		size = Vector3(2.0 * SEAM_REACH, FLOOR_COLLIDER_THICKNESS, width)
	var position := Vector3(float(doorway.pos_xz[0]), -FLOOR_COLLIDER_THICKNESS / 2.0, float(doorway.pos_xz[1]))
	_add_collision(body, "DoorwayFloorSeam_" + String(doorway.port_id), position, size)


static func _add_ceiling(visuals: Node3D, context: Dictionary) -> void:
	var ceiling := _group(visuals, "RenderedCeiling")
	var height: float = context.height
	if context.chamfered:
		DIAGONAL.add_ceiling(ceiling, context)
		return
	for rect: Array in context.spec.rects:
		var x0 := float(rect[0]); var z0 := float(rect[1]); var x1 := float(rect[2]); var z1 := float(rect[3])
		var material := MATERIALS.scaled(context.materials, "ceiling", x1 - x0, z1 - z0)
		_add_box(ceiling, "CeilingRect", Vector3((x0 + x1) / 2.0, height + FLOOR_VISUAL_THICKNESS / 2.0, (z0 + z1) / 2.0),
			Vector3(x1 - x0, FLOOR_VISUAL_THICKNESS, z1 - z0), material)


static func _add_lamps(visuals: Node3D, context: Dictionary) -> void:
	var lamps := _group(visuals, "CeilingLamps")
	var index := 0
	for point: Array in context.spec.lamps_xz:
		_add_box(lamps, "CeilingLight_%02d" % index, Vector3(float(point[0]), context.height - LAMP_SIZE.y / 2.0, float(point[1])),
			LAMP_SIZE, context.materials.lamp)
		index += 1


static func _add_walls(visuals: Node3D, boundaries: Node3D, context: Dictionary) -> void:
	var ring: Array[Vector2] = context.ring
	if context.diagonal_passage_visuals:
		DIAGONAL_PASSAGE.add_visuals(visuals, context)
	var count := ring.size()
	for index in count:
		var frame := _edge_frame(ring, index)
		var gaps := _edge_gaps(frame, context.doorways)
		_add_edge_pieces(visuals, boundaries, context, frame, gaps, index)
		for gap: Dictionary in gaps:
			_add_doorway(visuals, boundaries, context, frame, gap)


static func _edge_frame(ring: Array[Vector2], index: int) -> Dictionary:
	var count := ring.size()
	var start := ring[index]
	var finish := ring[(index + 1) % count]
	var direction := (finish - start).normalized()
	var before := (start - ring[(index - 1 + count) % count]).normalized()
	var after := (ring[(index + 2) % count] - finish).normalized()
	return {"index": index, "start": start, "direction": direction, "length": start.distance_to(finish),
		"diagonal": DIAGONAL.is_diagonal(direction),
		"inward": Vector2(-direction.y, direction.x),
		"start_reflex": before.x * direction.y - before.y * direction.x < 0.0,
		"end_reflex": direction.x * after.y - direction.y * after.x < 0.0}


static func _edge_gaps(frame: Dictionary, doorways: Array[Dictionary]) -> Array[Dictionary]:
	var gaps: Array[Dictionary] = []
	var start: Vector2 = frame.start
	var direction: Vector2 = frame.direction
	var inward: Vector2 = frame.inward
	var length: float = frame.length
	for doorway: Dictionary in doorways:
		var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1]))
		var offset := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1])) - start
		var along := offset.dot(direction)
		var on_line := absf(offset.dot(inward)) < EPSILON
		var faces_out := normal.distance_to(-inward) < EPSILON
		var half: float = float(doorway.door_width) / 2.0 + float(doorway.recess)
		if on_line and faces_out and along - half > -EPSILON and along + half < length + EPSILON:
			gaps.append({"doorway": doorway, "from": along - half, "to": along + half,
				"height": float(doorway.door_height) + float(doorway.recess)})
	gaps.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a["from"] < b["from"])
	return gaps


static func _add_edge_pieces(visuals: Node3D, boundaries: Node3D, context: Dictionary,
		frame: Dictionary, gaps: Array[Dictionary], index: int) -> void:
	var spans: Array[Vector2] = []
	var cursor := 0.0
	var pullback: float = context.diagonal_pullback if frame.diagonal else 0.0
	for gap in gaps:
		if gap["from"] > cursor + EPSILON:
			spans.append(Vector2(cursor, gap["from"]))
		cursor = gap["to"]
	if frame.length > cursor + EPSILON:
		spans.append(Vector2(cursor, frame.length))
	for piece in spans.size():
		var span := spans[piece]
		if frame.diagonal:
			span = Vector2(span.x + pullback, span.y - pullback)
		if context.diagonal_passage_visuals and span.y - span.x <= EPSILON:
			continue
		var passage_corner: bool = context.diagonal_passage_visuals and frame.length > 3.0
		var reach_start := WALL_THICKNESS if span.x < EPSILON and (frame.start_reflex or passage_corner) else 0.0
		var reach_end := WALL_THICKNESS if span.y > frame.length - EPSILON and (frame.end_reflex or passage_corner) else 0.0
		var label := "Wall_%02d_%d" % [index, piece]
		var box := _edge_box(frame, span.x - reach_start, span.y + reach_end, 0.0, WALL_THICKNESS, 0.0, context.height)
		if not context.diagonal_passage_visuals:
			var material := MATERIALS.scaled(context.materials, "wallpaper", box.size_along, context.height)
			_add_box(visuals, label + "Visual", box.center, box.size, material, box.yaw)
		if context.diagonal_collision or not frame.diagonal:
			_add_body(boundaries, label, box.center, box.size, box.yaw)


static func _add_doorway(visuals: Node3D, boundaries: Node3D, context: Dictionary,
		frame: Dictionary, gap: Dictionary) -> void:
	var doorway: Dictionary = gap.doorway
	var port := String(doorway.port_id)
	var door_height: float = gap.height
	var header := _edge_box(frame, gap["from"], gap["to"], 0.0, WALL_THICKNESS, door_height, context.height)
	if not context.diagonal_passage_visuals:
		var material := MATERIALS.scaled(context.materials, "wallpaper", header.size_along, context.height - door_height)
		_add_box(visuals, "Header_" + port + "Visual", header.center, header.size, material, header.yaw)
	_add_body(boundaries, "Header_" + port, header.center, header.size, header.yaw)
	if not context.diagonal_passage_visuals:
		_add_trim(visuals, context, frame, gap, port)
	if doorway.effective_kind == "closed_visible":
		_add_closed_door(visuals, boundaries, context, frame, gap, port)


## The trim lines the opening (jambs and lintel sit inside the gap) instead of
## framing it from outside. Outside framing put the jamb's inner face in the same
## plane as the wall's end face, and the lintel's underside in the header's plane:
## two coplanar textured faces that z-fought (worse under PSX vertex snap) as the
## player walked by. Lining the reveal hides the wall end and header underside
## behind the trim, so no two visible faces share a plane. Visual only: collision
## keeps the full 2.0 m clear width.
## A degenerate corner doorway ends where the outline turns: the perpendicular wall of
## the neighbouring edge then fills the first WALL_THICKNESS of the opening, so the trim
## on that side starts at that wall's inner face. Otherwise the jamb would sit inside the
## perpendicular wall, sharing its outer and bottom planes.
static func _add_trim(visuals: Node3D, context: Dictionary, frame: Dictionary, gap: Dictionary, port: String) -> void:
	var door_height: float = gap.height
	var depth := WALL_THICKNESS + TRIM_PROTRUSION
	var trim: Material = context.materials.trim
	var low_from: float = gap["from"] + (WALL_THICKNESS if gap["from"] < EPSILON else 0.0)
	var high_to: float = gap["to"] - (WALL_THICKNESS if gap["to"] > frame.length - EPSILON else 0.0)
	var jamb_top := door_height - TRIM_HEIGHT
	var low := _edge_box(frame, low_from, low_from + TRIM_WIDTH, 0.0, depth, 0.0, jamb_top)
	var high := _edge_box(frame, high_to - TRIM_WIDTH, high_to, 0.0, depth, 0.0, jamb_top)
	var lintel := _edge_box(frame, low_from, high_to, 0.0, depth, jamb_top, door_height)
	_add_box(visuals, "TrimJambLow_" + port, low.center, low.size, trim, low.yaw)
	_add_box(visuals, "TrimJambHigh_" + port, high.center, high.size, trim, high.yaw)
	_add_box(visuals, "TrimLintel_" + port, lintel.center, lintel.size, trim, lintel.yaw)


static func _add_closed_door(visuals: Node3D, boundaries: Node3D, context: Dictionary,
		frame: Dictionary, gap: Dictionary, port: String) -> void:
	var door_height: float = gap.height
	var panel := _edge_box(frame, gap["from"], gap["to"], PANEL_DEPTH, PANEL_DEPTH + PANEL_THICKNESS, 0.0, door_height)
	_add_box(visuals, "ClosedDoorPanel_" + port + "Visual", panel.center, panel.size, context.materials.dark, panel.yaw)
	var blocker := _edge_box(frame, gap["from"], gap["to"], 0.0, WALL_THICKNESS, 0.0, door_height)
	_add_body(boundaries, "ClosedDoor_" + port, blocker.center, blocker.size, blocker.yaw)


## Box over [from, to] along an outline edge, [depth_from, depth_to] inward from the edge and
## [y_from, y_to] up. Returns center, size, the along-edge length and the yaw (zero on an axis-aligned
## edge; a diagonal edge turns the box about Y so its local X runs along the wall).
static func _edge_box(frame: Dictionary, from: float, to: float, depth_from: float, depth_to: float,
		y_from: float, y_to: float) -> Dictionary:
	var middle: Vector2 = frame.start + frame.direction * ((from + to) / 2.0) + frame.inward * ((depth_from + depth_to) / 2.0)
	var along := to - from
	var across := depth_to - depth_from
	var size := Vector3(along, y_to - y_from, across) if absf(frame.direction.x) > 0.5 else Vector3(across, y_to - y_from, along)
	var yaw := 0.0
	if frame.diagonal:
		size = Vector3(along, y_to - y_from, across)
		yaw = DIAGONAL.yaw_of(frame.direction)
	return {"center": Vector3(middle.x, (y_from + y_to) / 2.0, middle.y), "size": size, "size_along": along, "yaw": yaw}


static func _group(parent: Node3D, label: String) -> Node3D:
	var node := Node3D.new()
	node.name = label
	parent.add_child(node)
	return node


static func _add_box(parent: Node3D, label: String, center: Vector3, size: Vector3, material: Material,
		yaw: float = 0.0) -> void:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = center
	instance.rotation.y = yaw
	var mesh := BoxMesh.new()
	mesh.size = size
	instance.mesh = mesh
	instance.material_override = material
	parent.add_child(instance)


static func _add_body(parent: Node3D, label: String, center: Vector3, size: Vector3, yaw: float = 0.0) -> void:
	var body := StaticBody3D.new()
	body.name = label
	body.position = center
	body.rotation.y = yaw
	parent.add_child(body)
	_add_collision(body, "CollisionShape3D", Vector3.ZERO, size)


static func _add_collision(parent: Node3D, label: String, center: Vector3, size: Vector3) -> void:
	var collision := CollisionShape3D.new()
	collision.name = label
	collision.position = center
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	parent.add_child(collision)
