"""Derive and validate mechanical module_poetics drafts from a library index.

Only mechanical fields are filled. Poetics fields stay null or empty until an
operator accepts them. Nothing here edits a module, the catalog or any event log.
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
    canonical_bytes,
    plan_write,
    repo_relative,
    resolve_cli_path,
    sha256_file,
    write_new,
)
from library_index import (  # noqa: E402
    LibraryIndexError,
    load_json,
    load_verified_index,
    resolve_pointer,
)
from module_metadata_accept import AcceptError, accept_kit, add_accept_flags, flags_from_args  # noqa: E402
from poetics_geometry import analyze_shape, num, port_slots  # noqa: E402
from poetics_signs import build_features, build_voids, translation_chain  # noqa: E402

DERIVER_VERSION = "module-poetics-0.1.0"
SCHEMA_PATH = Path("godot_walk/room_catalog/module_poetics.schema.json")
DEFAULT_INDEX = Path(
    "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
)
KIT_DRAFT_DIR = Path("godot_walk/room_catalog/module_poetics")
SOURCE_ROOM_PREFIX = "godot_walk/source_library/sources/"
SOURCE_DRAFT_NAME = "module_poetics_v1.json"
LIGHT_NOTE = "not derived"


def draft_path(entry: dict[str, Any], root: Path = ROOT) -> Path:
    room_dir = entry.get("room_dir")
    if room_dir and room_dir.startswith(SOURCE_ROOM_PREFIX):
        return root / room_dir / SOURCE_DRAFT_NAME
    return root / KIT_DRAFT_DIR / f"{entry['module_id']}-v{entry['version']}.json"


def tested_socket_map(
    entry: dict[str, Any], pairs: list[dict[str, Any]]
) -> dict[str, list[dict[str, str]]]:
    tested: dict[str, list[dict[str, str]]] = {}
    for pair in pairs:
        for module_id, socket_id in (pair["from"], pair["to"]):
            if module_id == entry["module_id"]:
                tested.setdefault(socket_id, []).append(
                    {"pair_id": pair["id"], "placement_scope": pair["placement_scope"]}
                )
    return tested


def build_ports(
    entry: dict[str, Any], module: dict[str, Any], pairs: list[dict[str, Any]]
) -> dict[str, Any]:
    tested = tested_socket_map(entry, pairs)
    socket_ids = [socket["id"] for socket in entry["sockets"]]
    missing = sorted(set(tested) - set(socket_ids))
    if missing:
        raise LibraryIndexError(f"{entry['module_id']} pair sockets missing: {missing}")
    return {
        "tested_sockets": [
            {"socket_id": socket_id, "pairs": sorted(tested[socket_id], key=lambda p: p["pair_id"])}
            for socket_id in sorted(tested)
        ],
        "untested_sockets": sorted(set(socket_ids) - set(tested)),
        "port_slots": port_slots(module["placement_footprint_xz"], entry["sockets"]),
    }


def build_shape(module: dict[str, Any]) -> dict[str, Any]:
    shape = analyze_shape(module["placement_footprint_xz"])
    floor, ceiling = module.get("floor_elevation_m"), module.get("ceiling_elevation_m")
    shape["ceiling_height_m"] = None if floor is None or ceiling is None else num(ceiling - floor)
    return shape


def build_layers(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "shape": {"scene": module.get("scene")},
        "surface": {"visual_assets": sorted(module.get("visual_assets") or [])},
        "collision": {
            "provenance": module.get("collision_provenance"),
            "collision_footprint_xz": module.get("collision_footprint_xz"),
        },
        "light": {"value": None, "note": LIGHT_NOTE},
    }


def empty_poetics() -> dict[str, Any]:
    return {
        "form_role": None,
        "rarity_tier": None,
        "apollonian": None,
        "dionysian": None,
        "style_tags": [],
        "surface_salience": None,
        "unique_details": [],
        "poetics_status": "operator_pending",
    }


def derive_record(
    entry: dict[str, Any],
    module: dict[str, Any],
    pairs: list[dict[str, Any]],
    index_ref: dict[str, str],
    snapshot_sha256: str,
) -> dict[str, Any]:
    ports = build_ports(entry, module, pairs)
    status = "draft_mechanical"
    paths = (module.get("source_provenance") or []) + (module.get("visual_assets") or [])
    return {
        "schema_version": 1,
        "deriver_version": DERIVER_VERSION,
        "module_id": entry["module_id"],
        "version": entry["version"],
        "source_id": entry["source_id"],
        "room_dir": entry["room_dir"],
        "library_index": index_ref,
        "catalog_snapshot_sha256": snapshot_sha256,
        "metadata_status": status,
        "origin": "source_video" if entry["source_id"] else "authored_kit",
        "shape": build_shape(module),
        "ports": ports,
        "features": build_features(module),
        "voids": build_voids(module),
        "layers": build_layers(module),
        "translation_chain": translation_chain(entry["source_id"], entry["scene"], paths),
        "poetics": empty_poetics(),
        "eligibility": {
            "layout_eligible_derived": bool(ports["tested_sockets"])
            and status == "operator_accepted",
            "catalog_layout_eligible": entry["catalog_layout_eligible"],
        },
    }


def load_index_context(index_path: Path, root: Path) -> tuple[dict, dict, dict[str, str]]:
    index = load_verified_index(index_path, root)
    snapshot = load_json(root / index["snapshot_path"])
    ref = {"path": repo_relative(index_path, root), "sha256": sha256_file(index_path)}
    return index, snapshot, ref


def derive_all_records(index_path: Path, root: Path = ROOT) -> list[tuple[Path, dict]]:
    index, snapshot, ref = load_index_context(index_path, root)
    results = []
    for entry in index["modules"]:
        module = resolve_pointer(snapshot, entry["location"])
        if (module["id"], module["version"]) != (entry["module_id"], entry["version"]):
            raise LibraryIndexError(f"Index location is stale: {entry['location']}")
        record = derive_record(entry, module, index["connector_pairs"], ref, index["snapshot_sha256"])
        results.append((draft_path(entry, root), record))
    paths = [path for path, _ in results]
    if len(set(paths)) != len(paths):
        raise LibraryIndexError("Two modules map to the same draft path")
    return results


def derive_all(index_path: Path, root: Path = ROOT) -> list[dict[str, str]]:
    """Write every draft; check all targets first so a refusal writes nothing."""
    planned = [
        (path, canonical_bytes(record)) for path, record in derive_all_records(index_path, root)
    ]
    statuses = [plan_write(path, data) for path, data in planned]
    for (path, data), status in zip(planned, statuses):
        if status == "create":
            write_new(path, data)
    return [
        {"draft": repo_relative(path, root), "status": "created" if s == "create" else s}
        for (path, _), s in zip(planned, statuses)
    ]


def schema_errors(record: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(record)
    ]


def check_draft(
    path: Path, entry: dict[str, Any], ref: dict[str, str], snapshot_sha: str, schema: dict
) -> list[str]:
    if not path.is_file():
        return [f"missing draft for {entry['module_id']}: {path}"]
    record = load_json(path)
    errors = [f"{path.name}: {message}" for message in schema_errors(record, schema)]
    if record.get("library_index") != ref:
        errors.append(f"{path}: library_index path/hash does not match current index")
    if record.get("catalog_snapshot_sha256") != snapshot_sha:
        errors.append(f"{path}: catalog_snapshot_sha256 does not match current snapshot")
    if (record.get("module_id"), record.get("version")) != (entry["module_id"], entry["version"]):
        errors.append(f"{path}: module identity does not match {entry['module_id']}")
    return errors


def validate_drafts(index_path: Path, root: Path = ROOT) -> dict[str, Any]:
    index, _, ref = load_index_context(index_path, root)
    schema = load_json(root / SCHEMA_PATH)
    errors: list[str] = []
    for entry in index["modules"]:
        errors += check_draft(
            draft_path(entry, root), entry, ref, index["snapshot_sha256"], schema
        )
    return {"valid": not errors, "draft_count": len(index["modules"]), "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    derive = commands.add_parser("derive-all", help="Write one draft per indexed module")
    derive.add_argument("--index", type=Path, required=True)
    validate = commands.add_parser("validate", help="Check drafts against schema and hashes")
    validate.add_argument("--index", type=Path, default=ROOT / DEFAULT_INDEX)
    kit = commands.add_parser("accept-kit", help="Operator-accept a kit module (no source video)")
    kit.add_argument("--index", type=Path, default=ROOT / DEFAULT_INDEX)
    kit.add_argument("--module-id", required=True)
    add_accept_flags(kit)
    arguments = parser.parse_args(argv)
    index_path = resolve_cli_path(arguments.index)
    try:
        if arguments.command == "derive-all":
            print(json.dumps(derive_all(index_path), sort_keys=True, indent=2))
            return 0
        if arguments.command == "accept-kit":
            result = accept_kit(index_path, arguments.module_id, flags_from_args(arguments), draft_path)
            print(json.dumps(result, sort_keys=True))
            return 0
        result = validate_drafts(index_path)
    except (LibraryIndexError, AcceptError, ValueError, OSError, KeyError) as error:
        print(f"module_poetics: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
