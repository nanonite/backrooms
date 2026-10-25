extends "res://scripts/issue149_generated_walkthrough.gd"

const DEFAULT_LAYOUT := "res://evidence/2026-10-24-issue-164/layout_three_room.json"


func _layout_argument() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--layout="):
			return argument.trim_prefix("--layout=")
	return DEFAULT_LAYOUT
