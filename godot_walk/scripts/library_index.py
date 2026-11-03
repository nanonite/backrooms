"""Derived library index: one view over top-level and nested catalog modules.

The generators read only top-level `modules` / `tested_connector_pairs`.
Admitted source-video rooms and their accepted connector pairs also live in
`source_video_adaptations`. This index reads both locations and never edits
the catalog or any snapshot.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import (  # noqa: E402
    ROOT,
    canonical_bytes,
    repo_relative,
    resolve_cli_path,
    sha256_file,
    write_deterministic,
)

INDEX_GENERATOR_VERSION = "library-index-0.1.0"
INDEX_DIR = Path("godot_walk/room_catalog/library_index")
SOURCE_ID_PATTERN = re.compile(r"video-[0-9a-f]{16}")
SOURCE_SCENE_PREFIX = "res://source_library/sources/"
EXACT_SCOPE_PATTERN = re.compile(r"exact[ _-](pair|placement)", re.IGNORECASE)


class LibraryIndexError(ValueError):
    """The catalog snapshot or the index violates the index contract."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise LibraryIndexError(f"{path} must contain a JSON object")
    return value


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve a JSON pointer such as /modules/6 (no escapes are used)."""
    node = document
    for part in pointer.split("/")[1:]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def iter_module_candidates(catalog: dict[str, Any]) -> Iterator[tuple[str, dict]]:
    for number, module in enumerate(catalog.get("modules") or []):
        yield f"/modules/{number}", module
    for a_number, adaptation in enumerate(catalog.get("source_video_adaptations") or []):
        for r_number, room in enumerate(adaptation.get("rooms") or []):
            yield f"/source_video_adaptations/{a_number}/rooms/{r_number}", room


def pick_authoritative(
    key: tuple[str, int], group: list[tuple[str, dict]]
) -> tuple[str, dict, str | None]:
    """Top-level wins; the nested duplicate becomes adaptation_reference."""
    if len(group) == 1:
        return group[0][0], group[0][1], None
    top = [item for item in group if item[0].startswith("/modules/")]
    nested = [item for item in group if not item[0].startswith("/modules/")]
    if len(top) != 1 or len(nested) != 1:
        pointers = sorted(pointer for pointer, _ in group)
        raise LibraryIndexError(f"Duplicate module {key}: {pointers}")
    return top[0][0], top[0][1], nested[0][0]


def parse_source_id(scene: str | None, provenance: list[str]) -> str | None:
    for text in [scene or "", *provenance]:
        match = SOURCE_ID_PATTERN.search(text)
        if match:
            return match.group(0)
    return None


def scene_room_dir(scene: str | None) -> str | None:
    """Repo path of a source-library room folder, else None."""
    if not scene or not scene.startswith(SOURCE_SCENE_PREFIX):
        return None
    return "godot_walk/" + scene[len("res://") :].rsplit("/", 1)[0]


def module_entry(
    pointer: str, module: dict[str, Any], reference: str | None
) -> dict[str, Any]:
    scene = module.get("scene")
    sockets = sorted(module.get("sockets") or [], key=lambda socket: socket["id"])
    return {
        "module_id": module["id"],
        "version": module["version"],
        "location": pointer,
        "adaptation_reference": reference,
        "source_id": parse_source_id(scene, module.get("source_provenance") or []),
        "room_dir": scene_room_dir(scene),
        "scene": scene,
        "kind": module.get("kind"),
        "variant_status": module.get("variant_status"),
        "integration_scope": module.get("integration_scope"),
        "catalog_layout_eligible": module.get("layout_eligible"),
        "sockets": sockets,
    }


def build_modules(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[tuple[str, dict]]] = {}
    for pointer, module in iter_module_candidates(catalog):
        key = (module["id"], module["version"])
        groups.setdefault(key, []).append((pointer, module))
    entries = []
    for key, group in groups.items():
        pointer, module, reference = pick_authoritative(key, group)
        entries.append(module_entry(pointer, module, reference))
    return sorted(entries, key=lambda entry: (entry["module_id"], entry["version"]))


def iter_pair_candidates(catalog: dict[str, Any]) -> Iterator[tuple[str, dict]]:
    for number, pair in enumerate(catalog.get("tested_connector_pairs") or []):
        yield f"/tested_connector_pairs/{number}", pair
    for number, adaptation in enumerate(catalog.get("source_video_adaptations") or []):
        pair = adaptation.get("tested_connector_pair")
        if pair:
            yield f"/source_video_adaptations/{number}/tested_connector_pair", pair


def placement_scope(pair: dict[str, Any]) -> str:
    text = f"{pair.get('status') or ''} {pair.get('scope') or ''}"
    return "exact_pair_only" if EXACT_SCOPE_PATTERN.search(text) else "pair"


def pair_entry(pointer: str, pair: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pair["id"],
        "from": list(pair["from"]),
        "to": list(pair["to"]),
        "status": pair.get("status"),
        "scope": pair.get("scope"),
        "location": pointer,
        "placement_scope": placement_scope(pair),
        "evidence": sorted(pair.get("evidence") or []),
    }


def build_pairs(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [pair_entry(pointer, pair) for pointer, pair in iter_pair_candidates(catalog)]
    ids = [entry["id"] for entry in entries]
    duplicates = sorted({pair_id for pair_id in ids if ids.count(pair_id) > 1})
    if duplicates:
        raise LibraryIndexError(f"Duplicate connector pair ids: {duplicates}")
    return sorted(entries, key=lambda entry: entry["id"])


def validate_pair_endpoints(
    modules: list[dict[str, Any]], pairs: list[dict[str, Any]]
) -> None:
    """Every pair endpoint must resolve to exactly one indexed module socket."""
    by_id: dict[str, list[dict[str, Any]]] = {}
    for module in modules:
        by_id.setdefault(module["module_id"], []).append(module)
    for pair in pairs:
        for module_id, socket_id in (pair["from"], pair["to"]):
            candidates = by_id.get(module_id, [])
            if len(candidates) != 1:
                raise LibraryIndexError(
                    f"Pair {pair['id']} endpoint module {module_id} resolves to "
                    f"{len(candidates)} indexed modules"
                )
            if socket_id not in {socket["id"] for socket in candidates[0]["sockets"]}:
                raise LibraryIndexError(
                    f"Pair {pair['id']} endpoint {module_id} has no socket {socket_id}"
                )


def build_index_document(
    catalog: dict[str, Any], snapshot_path: str, snapshot_sha256: str
) -> dict[str, Any]:
    modules = build_modules(catalog)
    pairs = build_pairs(catalog)
    validate_pair_endpoints(modules, pairs)
    return {
        "schema_version": 1,
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "snapshot_path": snapshot_path,
        "snapshot_sha256": snapshot_sha256,
        "index_generator_version": INDEX_GENERATOR_VERSION,
        "modules": modules,
        "connector_pairs": pairs,
    }


def display_path(path: Path, root: Path) -> str:
    try:
        return repo_relative(path, root)
    except ValueError:
        return str(path)


def index_file_name(document: dict[str, Any]) -> str:
    return f"{document['catalog_id']}-{document['catalog_version']}.json"


def build_index(
    snapshot: Path, root: Path = ROOT, out_dir: Path | None = None
) -> dict[str, Any]:
    """Build and write the index; refuse to overwrite different content."""
    snapshot_path = root / repo_relative(snapshot, root)
    catalog = load_json(snapshot_path)
    document = build_index_document(
        catalog, repo_relative(snapshot_path, root), sha256_file(snapshot_path)
    )
    data = canonical_bytes(document)
    target = (out_dir or root / INDEX_DIR) / index_file_name(document)
    status = write_deterministic(target, data)
    return {
        "index": display_path(target, root),
        "status": status,
        "module_count": len(document["modules"]),
        "pair_count": len(document["connector_pairs"]),
    }


def load_verified_index(index_path: Path, root: Path = ROOT) -> dict[str, Any]:
    """Load an index and check it still matches its snapshot file."""
    document = load_json(index_path)
    snapshot = root / document["snapshot_path"]
    if not snapshot.is_file():
        raise LibraryIndexError(f"Index snapshot is missing: {document['snapshot_path']}")
    if sha256_file(snapshot) != document["snapshot_sha256"]:
        raise LibraryIndexError(f"Snapshot hash changed since indexing: {snapshot}")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Write the library index for a snapshot")
    build.add_argument("--snapshot", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = build_index(resolve_cli_path(arguments.snapshot))
    except (LibraryIndexError, ValueError, OSError, KeyError) as error:
        print(f"library_index: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
