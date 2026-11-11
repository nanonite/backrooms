"""Derive the library-module floor acoustic table from accepted module poetics (#200).

The table is committed as `room_catalog/module_acoustics.json`. It is deliberately
a small, auditable projection: acoustic tag, matched style evidence, and the
accepted poetics record path/hash. Library scenes are never edited.

Usage:
    python3 godot_walk/scripts/module_acoustics.py generate
    python3 godot_walk/scripts/module_acoustics.py check
    python3 godot_walk/scripts/module_acoustics.py generate-v2
    python3 godot_walk/scripts/module_acoustics.py check-v2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, plan_write, sha256_file, write_new
from gmap_library import Library, load_library
from gmap_palette_registry import ACOUSTIC_TAGS

INDEX = Path("godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json")
OUTPUT = Path("godot_walk/room_catalog/module_acoustics.json")
SCRIPT_VERSION = "module-acoustics-0.1.0"
PRECEDENCE = (
    ("rock_field", "debris"),
    ("concrete_grey", "concrete"),
    ("carpet_floor", "carpet"),
    ("dark_carpet", "carpet"),
    ("plaster_walls", "plaster"),
    ("metal", "metal"),
    ("wood", "wood"),
    ("tile", "tile"),
)


def derive_acoustic(style_tags: list[str] | tuple[str, ...]) -> tuple[str, list[str]]:
    tags = set(style_tags)
    evidence = [tag for tag in tags if any(tag == key for key, _ in PRECEDENCE)]
    for key, acoustic in PRECEDENCE:
        if key in tags:
            return acoustic, sorted(evidence)
    return "default", []


def mapping_document(library: Library) -> dict[str, Any]:
    modules = {}
    for module in library.modules:
        acoustic, evidence = derive_acoustic(module.style_tags)
        modules[f"{module.module_id}@{module.version}"] = {
            "acoustic": acoustic,
            "evidence": evidence,
            "poetics": dict(module.metadata_record or {}),
        }
    return {
        "schema_version": 1,
        "generator": "godot_walk/scripts/module_acoustics.py",
        "generator_version": SCRIPT_VERSION,
        "source_index": dict(library.index_ref),
        "precedence": [list(item) for item in PRECEDENCE],
        "modules": modules,
    }


def document_bytes(library: Library) -> bytes:
    return (
        json.dumps(mapping_document(library), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def generate(library: Library, root: Path = ROOT) -> dict[str, Any]:
    data = document_bytes(library)
    path = root / OUTPUT
    status = plan_write(path, data)
    if status == "create":
        write_new(path, data)
    return {
        "path": OUTPUT.as_posix(),
        "status": status,
        "modules": len(json.loads(data)["modules"]),
    }


def check(library: Library, root: Path = ROOT) -> list[str]:
    path = root / OUTPUT
    if not path.is_file():
        return [f"{OUTPUT.as_posix()}: missing"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"{OUTPUT.as_posix()}: {error}"]
    expected = mapping_document(library)
    if document != expected:
        return [f"{OUTPUT.as_posix()}: differs from accepted poetics projection"]
    for key, record in document["modules"].items():
        if record["acoustic"] not in (*ACOUSTIC_TAGS, "default"):
            return [f"{key}: unknown acoustic tag {record['acoustic']}"]
        poetics = record["poetics"]
        path_text = poetics.get("path")
        if not path_text or not (root / path_text).is_file():
            return [f"{key}: poetics record {path_text} is missing"]
        if sha256_file(root / path_text) != poetics.get("sha256"):
            return [f"{key}: poetics record {path_text} hash changed"]
    return []


def load_v2(root: Path = ROOT) -> dict[str, Any]:
    """Load the versioned measured sidecar while preserving the v0.1.0 API."""
    from module_acoustics_v2 import load_v2 as load_document

    return load_document(root)


def generate_v2(root: Path = ROOT) -> dict[str, Any]:
    """Generate the versioned measured sidecar from committed probe output."""
    from module_acoustics_v2 import generate as generate_document

    return generate_document(root)


def check_v2(root: Path = ROOT) -> list[str]:
    """Validate the versioned measured sidecar and its hash pins."""
    from module_acoustics_v2 import check as check_document

    return check_document(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("generate", "check", "generate-v2", "check-v2")
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "generate-v2":
        print(json.dumps(generate_v2(), sort_keys=True))
        return 0
    if arguments.command == "check-v2":
        errors = check_v2()
        print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
        return 1 if errors else 0
    library = load_library(ROOT / INDEX)
    if arguments.command == "generate":
        print(json.dumps(generate(library), sort_keys=True))
        return 0
    errors = check(library)
    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
