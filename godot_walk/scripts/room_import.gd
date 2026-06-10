@tool
extends EditorScenePostImport

func _post_import(scene: Node) -> Object:
	_add_collision_recursive(scene)
	return scene

func _add_collision_recursive(node: Node) -> void:
	for child in node.get_children():
		if child is MeshInstance3D:
			child.create_trimesh_collision()
		_add_collision_recursive(child)
