"""Compute (never invent) hashes for frozen and accepted files in scope.

Reads the working tree and writes a supplementary pinned-file record. It edits
no pinned file, writes no ledger event, and is reproducible from the repository.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
ROOT = EVIDENCE_DIR.parents[2]
BASELINE = "godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1"

PINNED_PATHS = (
    "godot_walk/project.godot",
    "godot_walk/scenes/player.tscn",
    "godot_walk/scripts/player.gd",
    "godot_walk/room_catalog/catalog.json",
    "godot_walk/room_catalog/MATERIAL_LANGUAGE.md",
    "godot_walk/room_catalog/material_palettes/PALETTES.md",
    "godot_walk/room_catalog/contract_freeze_v1.json",
    "godot_walk/room_catalog/contract_freeze_v1.sha256",
    "godot_walk/room_catalog/contract_freeze_v2.json",
    "godot_walk/room_catalog/contract_freeze_v2.sha256",
    "godot_walk/room_catalog/contract_freeze_v3.json",
    "godot_walk/room_catalog/contract_freeze_v3.sha256",
    "godot_walk/room_catalog/contract_freeze_v4.json",
    "godot_walk/room_catalog/contract_freeze_v4.sha256",
    "godot_walk/shaders/library_psx_textured.gdshader",
    "godot_walk/shaders/library_psx_vertex.gdshader",
    "godot_walk/vendor/ursc/common.gdshaderinc",
    "godot_walk/vendor/ursc/utilities.gdshaderinc",
    "godot_walk/source_library/sources/video-22909eb734e4d8e2/hunyuan/attempt-001/panorama/panorama.png",
    "godot_walk/source_library/sources/video-22909eb734e4d8e2/frames/issue172-2s-a/frame_1363.png",
    f"{BASELINE}/room.gd",
    f"{BASELINE}/room.tscn",
    f"{BASELINE}/adaptation_candidate.json",
    f"{BASELINE}/test_room.gd",
    f"{BASELINE}/capture_room.gd",
    f"{BASELINE}/textures/wall_strata_dark.png",
    f"{BASELINE}/textures/wall_strata_warm.png",
    f"{BASELINE}/textures/sandy_floor.png",
    f"{BASELINE}/textures/slot_glow.png",
    f"{BASELINE}/textures/rock_rubble.png",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    target = EVIDENCE_DIR / "fixture" / "pinned_supplement_v1.json"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite pinned supplement: {target}")
    record = {
        "schema_version": 1,
        "record_id": "issue-273-pinned-supplement-v1",
        "note": (
            "Hashes computed from the working tree by generate_pinned_supplement_v1.py, "
            "not authored by hand. These frozen and accepted files must not be edited by "
            "this slice."
        ),
        "files": {relative: sha256_file(ROOT / relative) for relative in PINNED_PATHS},
    }
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {target.relative_to(ROOT)} with {len(record['files'])} computed hashes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
