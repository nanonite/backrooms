extends Node3D

const COLLISION_GLB_PATH := "res://evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/authored_route_collision.glb"
const REPORT_PATH := "res://evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/route_report.json"


func _ready() -> void:
	var packed := load(COLLISION_GLB_PATH) as PackedScene
	if packed == null:
		push_error("Cannot load experimental authored route GLB: %s" % COLLISION_GLB_PATH)
		return
	var meshes := packed.instantiate()
	meshes.name = "AuthoredRouteMeshes"
	var source_root := get_node_or_null("AuthoredRouteGlbSource") as Node3D
	if source_root == null or source_root.transform != Transform3D.IDENTITY:
		push_error("Authored route GLB source root must exist at identity")
		return
	source_root.add_child(meshes)
	var floor_mesh := meshes.find_child("AuthoredPlanarRouteFloor", true, false) as MeshInstance3D
	var column_mesh := meshes.find_child("ColumnObstacleProxy", true, false) as MeshInstance3D
	var inner_boundary := meshes.find_child("authored_edge_boundary_inner", true, false) as MeshInstance3D
	var outer_boundary := meshes.find_child("authored_edge_boundary_outer", true, false) as MeshInstance3D
	if not _require_meshes(floor_mesh, column_mesh, inner_boundary, outer_boundary):
		return
	_style_meshes(floor_mesh, column_mesh, inner_boundary, outer_boundary)
	_attach_floor_collider(floor_mesh)
	_attach_column_collider(column_mesh)
	_attach_edge_boundary_collider(inner_boundary, "Inner")
	_attach_edge_boundary_collider(outer_boundary, "Outer")
	_add_route_start_marker()
	_add_preview_camera()


func _require_meshes(
	floor_mesh: MeshInstance3D,
	column_mesh: MeshInstance3D,
	inner_boundary: MeshInstance3D,
	outer_boundary: MeshInstance3D
) -> bool:
	if floor_mesh == null or floor_mesh.mesh == null:
		push_error("Authored route floor mesh is missing")
		return false
	if column_mesh == null or column_mesh.mesh == null:
		push_error("Projected column proxy mesh is missing")
		return false
	if inner_boundary == null or inner_boundary.mesh == null:
		push_error("Authored inner edge boundary is missing")
		return false
	if outer_boundary == null or outer_boundary.mesh == null:
		push_error("Authored outer edge boundary is missing")
		return false
	return true


func _style_meshes(
	floor_mesh: MeshInstance3D,
	column_mesh: MeshInstance3D,
	inner_boundary: MeshInstance3D,
	outer_boundary: MeshInstance3D
) -> void:
	floor_mesh.material_override = _material(Color(0.16, 0.52, 0.46, 1.0))
	column_mesh.material_override = _material(Color(0.82, 0.31, 0.22, 1.0))
	inner_boundary.material_override = _material(Color(0.91, 0.68, 0.20, 1.0))
	outer_boundary.material_override = _material(Color(0.91, 0.68, 0.20, 1.0))


func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.92
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return material


func _attach_floor_collider(floor_mesh: MeshInstance3D) -> void:
	var body := StaticBody3D.new()
	body.name = "AuthoredRouteFloorCollision"
	body.global_transform = floor_mesh.global_transform
	var shape := CollisionShape3D.new()
	shape.name = "AuthoredPlanarFloorShape"
	shape.shape = floor_mesh.mesh.create_trimesh_shape()
	body.add_child(shape)
	add_child(body)


func _attach_column_collider(column_mesh: MeshInstance3D) -> void:
	var bounds := column_mesh.mesh.get_aabb()
	var body := StaticBody3D.new()
	body.name = "ReviewedColumnObstacleProxy"
	body.global_transform = column_mesh.global_transform
	var shape := CollisionShape3D.new()
	shape.name = "ColumnObstacleBoxShape"
	var box := BoxShape3D.new()
	box.size = bounds.size
	shape.shape = box
	shape.position = bounds.position + bounds.size * 0.5
	body.add_child(shape)
	add_child(body)


func _attach_edge_boundary_collider(boundary_mesh: MeshInstance3D, side: String) -> void:
	var body := StaticBody3D.new()
	body.name = "AuthoredEdgeBoundary%s" % side
	body.set_meta("origin", "authored_not_reconstructed")
	body.global_transform = boundary_mesh.global_transform
	var shape := CollisionShape3D.new()
	shape.name = "AuthoredEdgeBoundary%sShape" % side
	shape.shape = boundary_mesh.mesh.create_trimesh_shape()
	body.add_child(shape)
	add_child(body)


func _add_route_start_marker() -> void:
	var report: Variant = JSON.parse_string(FileAccess.get_file_as_string(REPORT_PATH))
	if not report is Dictionary:
		return
	var route: Variant = report.get("route", {})
	var start_xz: Array = route.get("start_xz_m", [])
	if start_xz.size() != 2:
		return
	var floor_y := float(report.get("plane", {}).get("height_m", 0.0))
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.12
	mesh.bottom_radius = 0.12
	mesh.height = 0.025
	var marker := MeshInstance3D.new()
	marker.name = "AuthoredRouteStartEndMarker"
	marker.mesh = mesh
	marker.position = Vector3(float(start_xz[0]), floor_y + 0.013, float(start_xz[1]))
	marker.material_override = _material(Color(0.18, 0.82, 0.86, 1.0))
	add_child(marker)


func _add_preview_camera() -> void:
	var report: Variant = JSON.parse_string(FileAccess.get_file_as_string(REPORT_PATH))
	if not report is Dictionary:
		return
	var center: Array = report.get("route", {}).get("center_xz_m", [])
	if center.size() != 2:
		return
	var floor_y := float(report.get("plane", {}).get("height_m", 0.0))
	var camera := Camera3D.new()
	camera.current = true
	camera.position = Vector3(float(center[0]) + 4.5, floor_y + 4.0, float(center[1]) + 4.5)
	add_child(camera)
	camera.look_at(Vector3(float(center[0]), floor_y, float(center[1])), Vector3.UP)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-48.0, -35.0, 0.0)
	light.light_energy = 1.0
	add_child(light)
