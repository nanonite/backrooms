"""Compute (never invent) hashes for supplemental pinned project files.

This generator is part of the reproducible local fixture data. It reads the
working tree and writes a supplementary pinned-file record; the read-only
validator re-checks those hashes at verification time. It edits no pinned file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
FIXTURE_DIR = EVIDENCE_DIR / "fixture"
ROOT = EVIDENCE_DIR.parents[2]

ACCEPTED_ROOM = "godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2"
PINNED_PATHS = (
    "godot_walk/room_catalog/MATERIAL_LANGUAGE.md",
    "godot_walk/room_catalog/material_palettes/PALETTES.md",
    "godot_walk/room_catalog/catalog.json",
    "godot_walk/project.godot",
    "godot_walk/scripts/player.gd",
    f"{ACCEPTED_ROOM}/room.gd",
    f"{ACCEPTED_ROOM}/adaptation_standalone_accepted_v1.json",
    f"{ACCEPTED_ROOM}/crop_plan.json",
    f"{ACCEPTED_ROOM}/textures/crop_manifest.json",
    f"{ACCEPTED_ROOM}/textures/stone_robe.png",
    f"{ACCEPTED_ROOM}/textures/stone_figure.png",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    target = FIXTURE_DIR / "pinned_supplement_v1.json"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite pinned supplement: {target}")
    record = {
        "schema_version": 1,
        "record_id": "issue-271-pinned-supplement-v1",
        "note": "Hashes computed from the working tree by generate_pinned_supplement_v1.py, not authored by hand. These files must not be edited by this slice.",
        "files": {relative: sha256_file(ROOT / relative) for relative in PINNED_PATHS},
    }
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target} with {len(record['files'])} computed hashes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
