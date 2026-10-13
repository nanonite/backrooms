extends SceneTree

var scene: Node3D
var samples: Array = []


func _initialize() -> void:
	call_deferred("_sample")


func _sample() -> void:
	scene = load("res://scenes/corridor_psx.tscn").instantiate()
	root.add_child(scene)
	var player: CharacterBody3D = scene.get_node("Player")
	for z in [0.5, 1.7, 2.9, 4.1]:
		for x in [-1.8, -0.65, 0.5]:
			player.global_position = Vector3(x, -0.54, z)
			player.velocity = Vector3.ZERO
			for tick in range(60):
				await physics_frame
			var shape := PhysicsShapeQueryParameters3D.new()
			shape.shape = player.get_node("CollisionShape3D").shape
			shape.transform = player.global_transform
			shape.exclude = [player.get_rid()]
			var overlaps := player.get_world_3d().direct_space_state.intersect_shape(shape)
			var eye: Vector3 = player.get_node("Head").global_position
			samples.append({"id": "x%.2f_z%.2f" % [x, z],
				"requested": [x, z], "eye": [eye.x, eye.y, eye.z],
				"floor": player.is_on_floor(), "overlaps": overlaps.size(),
				"displacement": Vector2(eye.x - x, eye.z - z).length()})
	var file := FileAccess.open("res://evidence/2026-10-13-bounded-psx/search_positions.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(samples, "\t") + "\n")
	print(JSON.stringify(samples))
	quit()
