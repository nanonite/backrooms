"""Rebuild the static comparison and provenance for the two Godot review rooms."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
UPSTREAM = "8cd971d0a275ef126151a99adf49cae1a64614c4"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_document(filename, document):
    (EVIDENCE / filename).write_text(json.dumps(document, indent=2) + "\n")


def comparison():
    canvas = Image.new("RGB", (1920, 2312), "#191919")
    painter = ImageDraw.Draw(canvas)
    rows = [("column", "patch_anchor"), ("column", "column_east"),
            ("pocket", "entry"), ("pocket", "return")]
    for index, (room, view) in enumerate(rows):
        for column, mode in enumerate(["native_baseline", "ursc_candidate"]):
            position = (column * 960, index * 578)
            painter.text((position[0] + 12, position[1] + 12),
                         f"{room} / {view} / {mode} (native post ON)", fill="white")
            with Image.open(EVIDENCE / "captures" / room / mode / f"{view}.png") as image:
                canvas.paste(image.convert("RGB"), (position[0], position[1] + 38))
    canvas.save(EVIDENCE / "comparison.png")


def source_hashes():
    protected = json.loads((ROOT / "godot_walk/evidence/2026-10-21-issue-151-column-box/verification.json").read_text())
    entries = protected["protected_hashes"]
    for entry in entries:
        entry["matches"] = digest(ROOT / entry["path"]) == entry["sha256"]
    pocket = ROOT / "godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated"
    report = json.loads((pocket / "early_pocket_scene_report.json").read_text())
    for kind in ["visual", "collision"]:
        path = report[f"{kind}_asset_path"]
        expected = report[f"{kind}_asset_sha256"]
        entries.append({"path": path, "sha256": expected,
                        "matches": digest(ROOT / path) == expected})
    return entries


def plugin_manifest():
    directory = ROOT / "godot_walk/vendor/ursc"
    return {
        "upstream": "https://github.com/Zorochase/ultimate-retro-shader-collection",
        "release": "1.5", "commit": UPSTREAM, "license": "MIT",
        "engine_tested_here": "4.6.3.stable.official.7d41c59c4",
        "renderer_tested_here": "Vulkan Forward+ / NVIDIA RTX 4070 Ti",
        "files": {str(path.relative_to(ROOT)): digest(path)
                  for path in directory.iterdir() if path.suffix != ".uid"},
        "modifications": "No effect code changes. utilities.gdshaderinc gains a final newline; common and license are byte-identical.",
        "upstream_utilities_sha256": "c54ed193069b8b50042de833df7ec810d11a2d0f5b9c6a4f229d5ecd0ee0c2d5",
        "integration": "Macro-only unshaded, double-sided configurations; original UV scale/texture/albedo passed through. Process-lifetime globals; no editor setup/project mutation.",
    }


def room_records():
    return [
        {"id": "godot_later_bay_column_v1", "scene": "res://scenes/library_column_room.tscn",
         "footprint": {"x": [-5.4, 4.5], "z": [-5.0, 8.8]},
         "floor_y": -1.27099049, "height": 2.4,
         "source": "#147 Hunyuan visual, reference frames 85-192; #151 accepted frame0152 column face",
         "authored": "Floor, perimeter collision, column collision proxy and accepted visual box; reference alignment uncalibrated",
         "mechanically_validated": True, "psx_applied": True, "operator_approved": False,
         "column_repair_approved": True, "connectors": [], "socket_status": "Closed collision perimeter; no Godot connector tested"},
        {"id": "godot_authored_early_pocket_v1", "scene": "res://scenes/library_pocket_room.tscn",
         "footprint": {"x": [0.0, 6.0], "z": [0.0, 13.8]},
         "floor_y": -1.27099049, "height": 2.4,
         "source": "#148 authored early pocket inspired by frames13-27; no confirmed second source room or connection",
         "authored": "Original50 collision triangles; original floor/ceiling visual geometry with generated planar visual UVs; report wall/grid/light boxes with existing source textures",
         "mechanically_validated": True, "psx_applied": True, "operator_approved": False,
         "connectors": [], "socket_status": "Closed collision perimeter; no Godot connector tested"},
    ]


def main():
    comparison()
    protected = source_hashes()
    if not all(entry["matches"] for entry in protected):
        raise RuntimeError("Protected source hash mismatch")
    textures = ROOT / "godot_walk/assets/psx_extension/textures"
    save_document("provenance.json", {
        "registration_accepted": False, "scale_calibrated": False,
        "protected": protected, "plugin": plugin_manifest(),
        "source_textures": {str(path.relative_to(ROOT)): digest(path) for path in textures.glob("*_source_video.png")},
        "texture_provenance": "Existing source-video crops, reused unchanged. Historical generation: godot_walk/scripts/run_psx_design_round_4.py (wallpaper/floor/ceiling/column); accepted column direct frame0152 crop retained separately.",
        "source_frame": "data/scenes/corridor_travel/images/frame_0001.jpg",
        "source_crop_manifest": "godot_walk/scripts/run_psx_design_round_4.py:26",
    })
    save_document("room_readiness.json", {
        "status": "provisional_godot_review_only", "ready_for_generation": False,
        "registration_accepted": False, "scale_calibrated": False,
        "preset": {"vertex_snap_intensity": 1, "affine_texture_mapping": True,
                   "texture_filtering": False, "texture_lod_halve_distance": 0,
                   "cull_distance": 0, "unshaded": True, "two_sided": True,
                   "native_post": {"pixel_size": 3, "color_levels": 24, "instances": 1},
                   "toggle": "F6 changes only packaged material effects; native post remains ON"},
        "rooms": room_records(),
    })


if __name__ == "__main__":
    main()
