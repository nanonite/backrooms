"""Constants for the operator-directed column iteration."""

from pathlib import Path

from hunyuan_round1_contract import PROJECT, VIEW_IDS

ROUND_ID = "hunyuan-psx-r2"
VARIANTS = ("preserve_hunyuan", "column_box_source_face")
OUT = PROJECT / "evidence" / "2026-10-21-issue-151-round-2"
SCENE = "res://scenes/hunyuan_psx_round2.tscn"
CAPTURE_SCRIPT = "res://scripts/capture_hunyuan_psx_round1.gd"
VERIFY_SCRIPT = "res://scripts/verify_bounded_psx.gd"
FPS_SCRIPT = "res://scripts/measure_bounded_fps.gd"
TEXTURE = PROJECT / "assets" / "psx_extension" / "textures" / "column_face_frame_0152.png"
ROUND_ONE = PROJECT / "evidence" / "2026-10-21-issue-151-round-1"
