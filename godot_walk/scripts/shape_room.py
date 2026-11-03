"""Deterministic shape-room specs (proposal section 5, stages 0-1) for a generative map.

`generate` writes one spec per cell plus index.json below
godot_walk/room_catalog/shape_rooms/<map_id>/ (pending mode: the pending/ subdirectory).
`validate` regenerates the specs from the map and compares bytes and schema.
Rooms never change the map; nothing here edits the map, fill, catalog or library.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import (  # noqa: E402
    ROOT,
    DeterministicWriteError,
    canonical_bytes,
    plan_write,
    repo_relative,
    resolve_cli_path,
    sha256_bytes,
    write_new,
)
from generative_map import display, validate_path  # noqa: E402
from library_index import load_json  # noqa: E402
from shape_room_checks import ShapeRoomError  # noqa: E402
from shape_room_raster import RasterError  # noqa: E402
from shape_room_rng import GENERATOR_VERSION  # noqa: E402
from shape_room_spec import build_spec  # noqa: E402

OUT_DIR = Path("godot_walk/room_catalog/shape_rooms")
SCHEMA = Path("godot_walk/room_catalog/shape_room.schema.json")
MODES = ("pending", "all_walkable")
PENDING_STATUS = "shape_room_pending"


def edge_links(document: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """port_id -> (port at the other end, connector) for every edge end."""
    links = {}
    for edge in document["edges"]:
        links[edge["from"]] = (edge["to"], edge["connector"])
        links[edge["to"]] = (edge["from"], edge["connector"])
    return links


def selected_cells(document: dict[str, Any], fill: dict[str, Any], mode: str) -> list[tuple[dict[str, Any], str]]:
    status = {c["cell_id"]: c["cell_status"] for c in fill["cells"]}
    chosen = []
    for cell in document["cells"]:
        if cell["role"] == "void":
            continue
        if mode == "pending" and status[cell["cell_id"]] != PENDING_STATUS:
            continue
        chosen.append((cell, status[cell["cell_id"]]))
    return chosen


def index_entry(spec: dict[str, Any], data: bytes) -> dict[str, Any]:
    return {
        "cell_id": spec["cell_id"],
        "file": f"{spec['cell_id']}.json",
        "sha256": sha256_bytes(data),
        "original_cell_status": spec["original_cell_status"],
        "primitive": spec["primitive"],
        "primitive_class": spec["primitive_class"],
        "construction": spec["construction"],
    }


def derive(map_path: Path, mode: str, root: Path = ROOT) -> dict[str, bytes]:
    """File name -> bytes for every spec and the index, for `mode`."""
    if mode not in MODES:
        raise ShapeRoomError(f"--mode must be one of {MODES}")
    errors = validate_path(map_path, root)
    if errors:
        raise ShapeRoomError(f"map {map_path.name} is invalid: {errors[0]}")
    document = load_json(map_path)
    fill = load_json(map_path.with_name(f"{map_path.stem}.fill.json"))
    map_sha = sha256_bytes(map_path.read_bytes())
    links = edge_links(document)
    files: dict[str, bytes] = {}
    entries = []
    for cell, status in selected_cells(document, fill, mode):
        spec = build_spec(document, map_sha, cell, status, links)
        data = canonical_bytes(spec)
        files[f"{cell['cell_id']}.json"] = data
        entries.append(index_entry(spec, data))
    index = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "map_id": document["map_id"],
        "map_file": {"name": map_path.name, "sha256": map_sha},
        "mode": mode,
        "rooms": entries,
    }
    files["index.json"] = canonical_bytes(index)
    return files


def target_dir(map_id: str, mode: str, root: Path, out_dir: Path | None) -> Path:
    base = out_dir or root / OUT_DIR
    return base / map_id / ("pending" if mode == "pending" else "")


def generate(map_path: Path, mode: str, root: Path = ROOT, out_dir: Path | None = None) -> dict[str, Any]:
    files = derive(map_path, mode, root)
    target = target_dir(load_json(map_path)["map_id"], mode, root, out_dir)
    statuses = {name: plan_write(target / name, data) for name, data in files.items()}
    for name, data in files.items():
        if statuses[name] == "create":
            write_new(target / name, data)
    created = sorted(n for n, s in statuses.items() if s == "create")
    return {"directory": display(target, root), "mode": mode, "files": len(files), "created": len(created)}


def schema_errors(path: Path, root: Path) -> list[str]:
    schema = load_json(root / SCHEMA)
    spec_validator = Draft202012Validator(schema)
    index_validator = Draft202012Validator({"$ref": "#/$defs/index", "$defs": schema["$defs"]})
    errors = []
    for file in sorted(path.glob("*.json")):
        validator = index_validator if file.name == "index.json" else spec_validator
        errors.extend(f"{file.name}: {e.message}" for e in validator.iter_errors(load_json(file)))
    return errors


def validate(map_path: Path, mode: str, root: Path = ROOT, out_dir: Path | None = None) -> list[str]:
    files = derive(map_path, mode, root)
    target = target_dir(load_json(map_path)["map_id"], mode, root, out_dir)
    errors = []
    for name, data in sorted(files.items()):
        path = target / name
        if not path.is_file():
            errors.append(f"{name}: missing")
        elif path.read_bytes() != data:
            errors.append(f"{name}: differs from the content derived from the map")
    return errors or schema_errors(target, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--map", type=Path, required=True)
        command.add_argument("--mode", choices=MODES, default="all_walkable")
    arguments = parser.parse_args(argv)
    try:
        path = resolve_cli_path(arguments.map)
        if arguments.command == "generate":
            print(json.dumps(generate(path, arguments.mode), sort_keys=True))
            return 0
        errors = validate(path, arguments.mode)
    except (ShapeRoomError, RasterError, DeterministicWriteError, ValueError, OSError, KeyError) as error:
        print(f"shape_room: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"valid": not errors, "errors": errors, "map": path.name, "mode": arguments.mode}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
