"""Seeded structural map generator (shape stages 0-3) and validator.

Writes a map, a fill-candidates file and an optional SVG. Neither output is
playable: cells stay unfilled until shape rooms and accepted module metadata
exist. Nothing here edits the catalog, snapshots, rooms or event logs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import (
    ROOT,
    DeterministicWriteError,
    canonical_bytes,
    plan_write,
    repo_relative,
    resolve_cli_path,
    sha256_bytes,
    write_new,
)
from gmap_build import (
    DEFAULT_DEGENERATE_MAX,
    GENERATOR_VERSION,
    GENERATOR_VERSION_V2,
    VERSIONS,
    build_map,
)
from gmap_fill import build_fill
from gmap_floor_regions import palette_summary
from gmap_grow import GenerationError
from gmap_library import load_library
from gmap_reverb import reverb_summary
from gmap_rules import Errors, err
from gmap_svg import render_svg
from gmap_validate import validate_document
from library_index import LibraryIndexError, load_json

OUT_DIR = Path("godot_walk/room_catalog/generative_maps")
FILL_SCHEMA = Path("godot_walk/room_catalog/generative_map_fill.schema.json")


def generate(
    seed: int,
    index_path: Path,
    cells: int = 12,
    stage_max: int | None = None,
    svg: bool = False,
    root: Path = ROOT,
    out_dir: Path | None = None,
    version: str = GENERATOR_VERSION,
    degenerate_max: int = DEFAULT_DEGENERATE_MAX,
) -> dict[str, Any]:
    """Generate and write map/fill(/svg); refuses to overwrite different content."""
    library = load_library(index_path, root)
    document = build_map(seed, library, cells, stage_max, version, degenerate_max)
    map_bytes = canonical_bytes(document)
    fill = build_fill(document, sha256_bytes(map_bytes), library)
    target = out_dir or root / OUT_DIR
    planned = [
        (target / f"{document['map_id']}.json", map_bytes),
        (target / f"{document['map_id']}.fill.json", canonical_bytes(fill)),
    ]
    if svg:
        planned.append((target / f"{document['map_id']}.svg", render_svg(document).encode("utf-8")))
    statuses = [plan_write(path, data) for path, data in planned]
    for (path, data), status in zip(planned, statuses):
        if status == "create":
            write_new(path, data)
    return {
        "map_id": document["map_id"],
        "attempt": document["attempt"],
        "summary": {
            "reverb": reverb_summary(document),
            "floor_palettes": palette_summary(document),
        },
        "files": [
            {"path": display(path, root), "status": "created" if s == "create" else s}
            for (path, _), s in zip(planned, statuses)
        ],
    }


def display(path: Path, root: Path) -> str:
    try:
        return repo_relative(path, root)
    except ValueError:
        return str(path)


def fill_errors(map_path: Path, document: dict[str, Any], root: Path) -> Errors:
    """Check the sibling fill file, when present, against the map file."""
    fill_path = map_path.with_name(f"{map_path.stem}.fill.json")
    if not fill_path.is_file():
        return []
    fill = load_json(fill_path)
    validator = Draft202012Validator(load_json(root / FILL_SCHEMA))
    errors = [err("fill_schema", "fill_schema", e.message) for e in validator.iter_errors(fill)]
    if errors:
        return errors
    if fill["map_file"]["sha256"] != sha256_bytes(map_path.read_bytes()):
        errors.append(err("fill_schema", "fill_stale_map_hash", fill_path.name))
    expected = {c["cell_id"]: c["role"] == "void" for c in document["cells"]}
    got = {c["cell_id"]: c["cell_status"] == "void" for c in fill["cells"]}
    if expected != got:
        errors.append(err("fill_schema", "fill_cells_mismatch", fill_path.name))
    return errors


def validate_path(map_path: Path, root: Path = ROOT) -> Errors:
    document = load_json(map_path)
    errors = validate_document(document, root)
    return errors or fill_errors(map_path, document, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate", help="Write <map_id>.json, .fill.json and optional .svg")
    gen.add_argument("--seed", type=int, required=True)
    gen.add_argument("--index", type=Path, required=True)
    gen.add_argument("--cells", type=int, default=12)
    gen.add_argument("--stage-max", type=int, default=None, choices=(0, 1, 2, 3), help="default 1 (2 in gmap-0.4.0; 3 in gmap-0.7.0)")
    gen.add_argument("--svg", action="store_true")
    gen.add_argument("--generator-version", choices=VERSIONS, default=GENERATOR_VERSION_V2)
    gen.add_argument(
        "--degenerate-max", type=int, default=DEFAULT_DEGENERATE_MAX,
        help="gmap-0.2.0: most degenerate (corner-doorway) cells; 0 disables",
    )
    val = commands.add_parser("validate", help="Schema plus all rule checks for a map")
    val.add_argument("map", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "generate":
            if not 0 <= arguments.seed <= 4294967295:
                raise GenerationError("--seed must be within 0..4294967295")
            result = generate(
                arguments.seed,
                resolve_cli_path(arguments.index),
                arguments.cells,
                arguments.stage_max,
                arguments.svg,
                version=arguments.generator_version,
                degenerate_max=arguments.degenerate_max,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        path = resolve_cli_path(arguments.map)
        document = load_json(path)
        errors = validate_document(document)
        if not errors:
            errors = fill_errors(path, document, root=ROOT)
        summary = {
            "reverb": reverb_summary(document),
            "floor_palettes": palette_summary(document),
        }
    except (GenerationError, DeterministicWriteError, LibraryIndexError, ValueError, OSError, KeyError) as error:
        print(f"generative_map: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "valid": not errors,
                "errors": errors,
                "map": path.name,
                "summary": summary,
            },
            sort_keys=True,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
