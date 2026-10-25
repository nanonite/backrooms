extends "res://scripts/hunyuan_psx_column_box.gd"

const LIBRARY_PRESET := preload("res://scripts/library_psx_preset.gd")


func _ready() -> void:
	variant_id = "four_sided_box"
	super._ready()
	LIBRARY_PRESET.new().configure(self)
	set_meta("room_id", "godot_later_bay_column_v1")


func _requested_variant() -> String:
	return "four_sided_box"
