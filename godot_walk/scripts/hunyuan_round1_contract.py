"""Shared identifiers and immutable source references for Hunyuan round 1."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
SCHEMA_DIR = PROJECT / "design_rounds"
ROUND_ID = "hunyuan-psx-r1"
VARIANTS = ("preserve_hunyuan", "source_surface_cleanup")
ROUND_VARIANTS = {
    "hunyuan-psx-r1": VARIANTS,
    "hunyuan-psx-r2": ("preserve_hunyuan", "column_box_source_face"),
}
VIEW_IDS = (
    "patch_anchor",
    "south_end",
    "north_end",
    "west_wall",
    "east_wall",
    "column_south",
    "column_north",
    "column_west",
    "column_east",
)
EXPECTED_HASHES = {
    "data/scenes/corridor_travel/video.mp4": "ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4",
    "data/scenes/corridor_travel/images/frame_0152.jpg": "94b2643eee79583a1b3d4f0151577dc87e4cd37b3639c947edcb5396c15f5b12",
    "godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb": "5b3e879c0309448887cd3ceb7b29eaca49476566ac75010f7e5c5253443a23bf",
}
