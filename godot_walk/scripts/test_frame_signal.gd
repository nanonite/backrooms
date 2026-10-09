extends SceneTree

func _init() -> void:
	print("TEST: start")
	var packed: PackedScene = load("res://scenes/corridor_psx.tscn")
	var instance: Node = packed.instantiate()
	root.add_child(instance)
	await process_frame
	print("TEST: frame 1 done")
	await RenderingServer.frame_post_draw
	print("TEST: frame_post_draw 1 done")
	await process_frame
	await RenderingServer.frame_post_draw
	print("TEST: frame_post_draw 2 done")
	quit(0)
