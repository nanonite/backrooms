extends "res://scripts/issue164_three_room_walkthrough.gd"

const FOUR_ROOM_LAYOUT := "res://evidence/2026-10-26-four-room-transfer/layout_four_room.json"


func _layout_argument() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--layout="):
			return argument.trim_prefix("--layout=")
	return FOUR_ROOM_LAYOUT
