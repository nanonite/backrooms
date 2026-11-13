class_name MazeDoorLeaf
extends RefCounted

## Procedural door leaf for generated shape rooms (#234).
##
## M4 adds the leaf as additive runtime geometry: no committed shape-room spec,
## map, library scene, palette or material file is edited.  The leaf is built
## only when a door first latches, so a walkthrough without a crossing looks
## exactly like the committed opening.  It is a header-hung panel with a real
## StaticBody collider at the doorway plane; manual open swings it against the
## inside wall so the opening is clear again.
##
## The panel reuses the room's own palette materials (``trim`` and ``dark``) and
## adds no texture, mesh file or third-party asset.  All measurements come from
## the generated doorway record, so the leaf fits level, ramp and threshold
## ports without rebuilding their geometry.

const LEAF_THICKNESS_M := 0.08
const LEAF_CLEARANCE_M := 0.02
const HINGE_INSET_M := 0.02
const PANEL_INSET_FRACTION := 0.10
const HANDLE_WIDTH_M := 0.04
const HANDLE_HEIGHT_M := 0.16
const LATCH_WIDTH_M := 0.02
const LATCH_HEIGHT_M := 0.12
const COLLISION_LAYER := 1


static func build(room: Node3D, doorway: Dictionary, record: Dictionary,
		materials: Dictionary, layer: int) -> Dictionary:
	var result := {
		"ok": false,
		"threshold_id": String(record.get("threshold_id", "")),
		"node": null,
		"width_m": 0.0,
		"height_m": 0.0,
		"sill_m": 0.0,
	}
	if room == null or doorway.is_empty() or record.is_empty():
		return result
	var width := float(doorway.get("width_m", 0.0))
	var height := float(doorway.get("height_m", 0.0))
	var sill := float(doorway.get("sill_height_m", 0.0))
	if width <= 0.0 or height <= 0.0:
		return result
	var leaf_width := maxf(0.2, width - 2.0 * LEAF_CLEARANCE_M)
	var leaf_height := maxf(0.2, height - 2.0 * LEAF_CLEARANCE_M)
	var normal := Vector2(float(doorway.normal[0]), float(doorway.normal[1])).normalized()
	var tangent := Vector2(-normal.y, normal.x)
	var inside := -normal
	var plane := Vector2(float(doorway.pos_xz[0]), float(doorway.pos_xz[1]))
	var hinge := plane + tangent * (-width / 2.0 + HINGE_INSET_M) \
		+ inside * HINGE_INSET_M
	var closed_angle := angle_for(tangent)
	var open_angle := angle_for(inside)
	var open_angle_outside := angle_for(-inside)
	var host := Node3D.new()
	host.name = "MazeDoorLeaf_" + _label(String(record.get("threshold_id", "")))
	host.position = Vector3(hinge.x, sill, hinge.y)
	host.rotation.y = closed_angle
	host.set_meta("door_threshold_id", String(record.get("threshold_id", "")))
	host.set_meta("door_state", "latched")
	host.set_meta("door_closed_angle", closed_angle)
	host.set_meta("door_open_angle", open_angle)
	host.set_meta("door_open_angle_outside", open_angle_outside)
	host.set_meta("door_inside_xz", inside)
	host.set_meta("door_leaf_width_m", leaf_width)
	host.set_meta("door_leaf_height_m", leaf_height)
	host.set_meta("door_leaf_thickness_m", LEAF_THICKNESS_M)
	host.set_meta("door_leaf_layer", layer)
	room.add_child(host)
	_add_panel(host, leaf_width, leaf_height, materials, layer)
	_add_latch_bar(host, leaf_width, leaf_height, materials, layer)
	var body := _add_collider(host, leaf_width, leaf_height)
	result["ok"] = body != null
	result["node"] = host
	result["width_m"] = leaf_width
	result["height_m"] = leaf_height
	result["sill_m"] = sill
	return result


static func set_state(node: Node3D, state: String,
		player_in_leaf_room: bool = false) -> bool:
	if node == null:
		return false
	var closed := state != "open"
	node.set_meta("door_state", "latched" if closed else "open")
	if closed:
		node.rotation.y = float(node.get_meta("door_closed_angle", 0.0))
	else:
		var angle_key := "door_open_angle"
		if player_in_leaf_room:
			angle_key = "door_open_angle_outside"
		node.rotation.y = float(node.get_meta(angle_key, 0.0))
	var body := node.get_node_or_null("LeafBody") as StaticBody3D
	if body != null:
		body.collision_layer = COLLISION_LAYER if closed else 0
	var latch := node.get_node_or_null("LatchBolt") as MeshInstance3D
	if latch != null:
		latch.visible = closed
	return true


static func state_of(node: Node3D) -> String:
	if node == null:
		return ""
	return String(node.get_meta("door_state", "open"))


static func is_closed(node: Node3D) -> bool:
	return state_of(node) == "latched"


static func collider(node: Node3D) -> StaticBody3D:
	if node == null:
		return null
	return node.get_node_or_null("LeafBody") as StaticBody3D


static func panel(node: Node3D) -> MeshInstance3D:
	if node == null:
		return null
	return node.get_node_or_null("LeafPanel") as MeshInstance3D


static func angle_for(direction: Vector2) -> float:
	return atan2(-direction.y, direction.x)


static func _label(threshold: String) -> String:
	return threshold.replace("|", "_").replace(":", "_")


static func _add_panel(host: Node3D, leaf_width: float, leaf_height: float,
		materials: Dictionary, layer: int) -> void:
	var leaf_material: Material = materials.get("trim")
	var panel_material: Material = materials.get("dark")
	var leaf := _box(host, "LeafPanel", Vector3(leaf_width / 2.0, leaf_height / 2.0, 0.0),
		Vector3(leaf_width, leaf_height, LEAF_THICKNESS_M), leaf_material, layer)
	leaf.set_meta("door_leaf_surface", "trim")
	for side: float in [-1.0, 1.0]:
		var inset := _box(host, "LeafInset%s" % ("Front" if side > 0.0 else "Back"),
			Vector3(leaf_width / 2.0, leaf_height * 0.56,
				side * (LEAF_THICKNESS_M / 2.0 + 0.004)),
			Vector3(leaf_width * (1.0 - 2.0 * PANEL_INSET_FRACTION),
				leaf_height * 0.56, 0.008), panel_material, layer)
		inset.set_meta("door_leaf_surface", "dark")
	_box(host, "LeafHandle", Vector3(leaf_width - HANDLE_WIDTH_M * 2.0,
		leaf_height * 0.52, 0.0),
		Vector3(HANDLE_WIDTH_M, HANDLE_HEIGHT_M, LEAF_THICKNESS_M + 0.04),
		materials.get("trim"), layer)


static func _add_latch_bar(host: Node3D, leaf_width: float, leaf_height: float,
		materials: Dictionary, layer: int) -> void:
	var latch := _box(host, "LatchBolt", Vector3(leaf_width - LATCH_WIDTH_M,
		leaf_height * 0.52, 0.0),
		Vector3(LATCH_WIDTH_M, LATCH_HEIGHT_M, LEAF_THICKNESS_M + 0.06),
		materials.get("dark"), layer)
	latch.set_meta("door_leaf_surface", "dark")


static func _add_collider(host: Node3D, leaf_width: float,
		leaf_height: float) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "LeafBody"
	body.position = Vector3(leaf_width / 2.0, leaf_height / 2.0, 0.0)
	body.collision_layer = COLLISION_LAYER
	body.collision_mask = 0
	host.add_child(body)
	var collision := CollisionShape3D.new()
	collision.name = "LeafShape"
	var shape := BoxShape3D.new()
	shape.size = Vector3(leaf_width, leaf_height, LEAF_THICKNESS_M)
	collision.shape = shape
	body.add_child(collision)
	return body


static func _box(parent: Node3D, label: String, position: Vector3, size: Vector3,
		material: Material, layer: int) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.position = position
	var mesh := BoxMesh.new()
	mesh.size = size
	instance.mesh = mesh
	instance.material_override = material
	instance.layers = layer
	parent.add_child(instance)
	return instance
