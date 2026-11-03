"""Append a catalog-admitted room to a versioned source manifest snapshot."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from register_video_sources import write_index_snapshot
from video_source_library import (
    INDEX_PATH,
    LIBRARY,
    ROOT,
    SourceLibraryError,
    lock_file,
    manifest_lineage_hashes,
    sha256_file,
    utc_now,
    validate_index,
    write_new_json,
)

SOURCE_ID_PATTERN = re.compile(r"^video-[0-9a-f]{16}$")
MANIFEST_VERSION_PATTERN = re.compile(r"source_manifest-v([2-9]|[1-9][0-9]+)\.json")
ROOM_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")


def register_room(
    source_id: str,
    adaptation_path: str,
    decision_path: str,
    root: Path = ROOT,
) -> tuple[str, str]:
    _validate_source_id(source_id)
    source_dir = root / LIBRARY / "sources" / source_id
    with (
        lock_file(source_dir / ".worker.lock"),
        lock_file(root / LIBRARY / ".index.lock"),
    ):
        return _register_locked(source_id, adaptation_path, decision_path, root)


def _register_locked(
    source_id: str, adaptation_path: str, decision_path: str, root: Path
) -> tuple[str, str]:
    entries = validate_index(root)
    entry = _find_source(entries, source_id)
    manifest_path = root / entry["manifest_path"]
    manifest = _read_object(manifest_path)
    room = _build_room_reference(
        source_id, manifest, adaptation_path, decision_path, root
    )
    existing = _find_identical_room(manifest, room)
    if existing:
        return entry["manifest_path"], entry["manifest_sha256"]
    return _write_successor(source_id, entry, manifest, room, root)


def _build_room_reference(
    source_id: str,
    manifest: dict[str, Any],
    adaptation_path: str,
    decision_path: str,
    root: Path,
) -> dict[str, Any]:
    adaptation, adaptation_hash = _read_artifact(adaptation_path, root)
    decision, decision_hash = _read_artifact(decision_path, root)
    module, catalog_snapshot, snapshot_hash, catalog_version = _verify_admission(
        adaptation,
        decision,
        decision_path,
        decision_hash,
        adaptation_path,
        adaptation_hash,
        root,
    )
    _verify_source_identity(adaptation, manifest, source_id)
    scene_path = _scene_repository_path(adaptation, root)
    return {
        "issue": decision.get("issue", 167),
        "adaptation_id": adaptation["adaptation_id"],
        "adaptation_version": adaptation["resolved_adaptation"]["candidate_version"],
        "candidate_identity": adaptation["candidate_identity"],
        "adaptation_path": adaptation_path,
        "adaptation_sha256": adaptation_hash,
        "decision_path": decision_path,
        "decision_sha256": decision_hash,
        "decision_status": "accepted_catalog_admission",
        "scene_path": scene_path,
        "scene_sha256": sha256_file(root / scene_path),
        "catalog_snapshot_path": catalog_snapshot,
        "catalog_snapshot_sha256": snapshot_hash,
        "catalog_admission": {
            "status": "admitted",
            "module_id": module["id"],
            "module_version": module["version"],
            "catalog_version": catalog_version,
        },
    }


def _verify_admission(
    adaptation: dict[str, Any],
    decision: dict[str, Any],
    decision_path: str,
    decision_hash: str,
    adaptation_path: str,
    adaptation_hash: str,
    root: Path,
) -> tuple[dict[str, Any], str, str, str]:
    candidate_identity = adaptation.get("candidate_identity")
    approval = adaptation.get("operator_decision", {})
    if decision.get("decision") == "accepted_standalone_module_admission":
        _verify_standalone_catalog_decision(
            adaptation,
            decision,
            approval,
            adaptation_path,
            adaptation_hash,
            root,
        )
        module, snapshot, snapshot_hash, version = _catalog_module(
            decision, adaptation, root
        )
        _verify_standalone_module_scope(module, decision)
        return module, snapshot, snapshot_hash, version
    if (
        not isinstance(candidate_identity, str)
        or re.fullmatch(r"[0-9a-f]{64}", candidate_identity) is None
        or adaptation.get("status") != "accepted_reference"
        or adaptation.get("registration_accepted") is not False
        or adaptation.get("scale_calibrated") is not False
        or adaptation.get("resolved_adaptation", {}).get("catalog_admission")
        != "admitted"
        or approval.get("status") != "accepted"
        or approval.get("candidate_fingerprint") != candidate_identity
        or approval.get("decision_record_path") != decision_path
        or approval.get("decision_sha256") != decision_hash
        or decision.get("decision") != "accepted"
        or decision.get("candidate_identity") != candidate_identity
        or decision.get("registration_accepted") is not False
        or decision.get("scale_calibrated") is not False
    ):
        raise SourceLibraryError(
            "Room decision does not accept this admitted candidate"
        )
    module, snapshot, snapshot_hash, version = _catalog_module(
        decision, adaptation, root
    )
    return module, snapshot, snapshot_hash, version


def _verify_standalone_catalog_decision(
    adaptation: dict[str, Any],
    decision: dict[str, Any],
    approval: dict[str, Any],
    adaptation_path: str,
    adaptation_hash: str,
    root: Path,
) -> None:
    candidate_identity = adaptation.get("candidate_identity")
    visual_decision_path = approval.get("decision_record_path")
    visual_decision_hash = approval.get("decision_sha256")
    visual_decision, actual_visual_hash = _read_artifact(visual_decision_path, root)
    if (
        not _valid_candidate_identity(candidate_identity)
        or adaptation.get("status") != "accepted_reference"
        or adaptation.get("registration_accepted") is not False
        or adaptation.get("scale_calibrated") is not False
        or approval.get("status") != "accepted"
        or approval.get("candidate_fingerprint") != candidate_identity
        or actual_visual_hash != visual_decision_hash
    ):
        raise SourceLibraryError(
            "Standalone catalog decision does not bind the accepted room candidate"
        )
    _verify_visual_decision(
        visual_decision, adaptation, adaptation_path, candidate_identity
    )
    _verify_catalog_admission_binding(
        decision,
        adaptation,
        adaptation_path,
        adaptation_hash,
        visual_decision_path,
        visual_decision_hash,
        candidate_identity,
    )


def _verify_visual_decision(
    visual_decision: dict[str, Any],
    adaptation: dict[str, Any],
    adaptation_path: str,
    candidate_identity: str,
) -> None:
    if (
        visual_decision.get("decision") != "accepted"
        or visual_decision.get("candidate_identity") != candidate_identity
        or visual_decision.get("adaptation_id") != adaptation.get("adaptation_id")
        or visual_decision.get("accepted_record_path") != adaptation_path
        or visual_decision.get("registration_accepted") is not False
        or visual_decision.get("scale_calibrated") is not False
    ):
        raise SourceLibraryError("Original visual decision does not match this room")


def _verify_catalog_admission_binding(
    decision: dict[str, Any],
    adaptation: dict[str, Any],
    adaptation_path: str,
    adaptation_hash: str,
    visual_decision_path: str,
    visual_decision_hash: str,
    candidate_identity: str,
) -> None:
    valid_directive = isinstance(decision.get("operator_directive"), str)
    valid_directive = valid_directive and bool(decision["operator_directive"].strip())
    if (
        decision.get("adaptation_id") != adaptation.get("adaptation_id")
        or decision.get("candidate_identity") != candidate_identity
        or decision.get("accepted_record_path") != adaptation_path
        or decision.get("accepted_record_sha256") != adaptation_hash
        or decision.get("visual_decision_path") != visual_decision_path
        or decision.get("visual_decision_sha256") != visual_decision_hash
        or decision.get("scope") != "standalone_only"
        or decision.get("layout_eligible") is not False
        or decision.get("tested_connector_pairs") != []
        or not valid_directive
        or decision.get("registration_accepted") is not False
        or decision.get("scale_calibrated") is not False
    ):
        raise SourceLibraryError("Standalone catalog admission scope is invalid")


def _valid_candidate_identity(candidate_identity: Any) -> bool:
    return isinstance(candidate_identity, str) and re.fullmatch(
        r"[0-9a-f]{64}", candidate_identity
    ) is not None


def _verify_standalone_module_scope(
    module: dict[str, Any], decision: dict[str, Any]
) -> None:
    if (
        module.get("layout_eligible") is not False
        or module.get("sockets") != []
        or decision.get("tested_connector_pairs") != []
        or decision.get("module_id") != module.get("id")
        or decision.get("module_version") != module.get("version")
    ):
        raise SourceLibraryError(
            "Standalone admission must not imply layout or connector eligibility"
        )


def _catalog_module(
    decision: dict[str, Any], adaptation: dict[str, Any], root: Path
) -> tuple[dict[str, Any], str, str, str]:
    catalog_path = _safe_artifact_path(decision.get("catalog_path"), root)
    catalog = _read_object(catalog_path)
    version = decision.get("catalog_version")
    if catalog.get("catalog_version") != version:
        raise SourceLibraryError(
            "Admission decision does not match the live catalog version"
        )
    module = _find_catalog_module(catalog, decision)
    scene_path = _scene_repository_path(adaptation, root)
    expected_scene = f"res://{scene_path.removeprefix('godot_walk/')}"
    if module.get("scene") != expected_scene:
        raise SourceLibraryError(
            "Admitted module scene differs from the candidate scene"
        )
    catalog_id = catalog.get("catalog_id")
    if (
        not isinstance(catalog_id, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", catalog_id) is None
    ):
        raise SourceLibraryError("Room catalog has an unsafe stable ID")
    snapshot_rel = (
        f"godot_walk/room_catalog/catalog_snapshots/{catalog_id}-{version}.json"
    )
    snapshot_path = _safe_artifact_path(snapshot_rel, root)
    snapshot = _read_object(snapshot_path)
    if snapshot.get("catalog_version") != version:
        raise SourceLibraryError("Catalog snapshot version does not match admission")
    snapshot_hash = sha256_file(snapshot_path)
    if decision.get("decision") == "accepted_standalone_module_admission" and (
        decision.get("catalog_snapshot_path") != snapshot_rel
        or decision.get("catalog_snapshot_sha256") != snapshot_hash
    ):
        raise SourceLibraryError(
            "Standalone admission does not bind the exact catalog snapshot"
        )
    snapshot_module = _find_catalog_module(snapshot, decision)
    if snapshot_module != module:
        raise SourceLibraryError(
            "Catalog snapshot module differs from the live admission"
        )
    return module, snapshot_rel, snapshot_hash, version


def _find_catalog_module(
    catalog: dict[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    module_id = decision.get("module_id")
    module_version = decision.get("module_version")
    modules = catalog.get("modules")
    if not isinstance(modules, list):
        raise SourceLibraryError("Room catalog has no module list")
    for module in modules:
        if module.get("id") == module_id and module.get("version") == module_version:
            return module
    raise SourceLibraryError("Admitted module version is absent from its catalog")


def _verify_source_identity(
    adaptation: dict[str, Any], manifest: dict[str, Any], source_id: str
) -> None:
    if adaptation.get("adaptation_id") is None or not ROOM_ID_PATTERN.fullmatch(
        adaptation["adaptation_id"]
    ):
        raise SourceLibraryError("Adaptation ID is not a safe stable room ID")
    source = adaptation.get("source_observations", {}).get("video", {})
    registered = manifest.get("canonical_video", {})
    if (
        manifest.get("source_id") != source_id
        or source.get("path") != registered.get("path")
        or source.get("sha256") != registered.get("sha256")
    ):
        raise SourceLibraryError("Room adaptation references a different source video")


def _scene_repository_path(adaptation: dict[str, Any], root: Path) -> str:
    scene = adaptation.get("resolved_adaptation", {}).get("scene_path")
    if not isinstance(scene, str):
        raise SourceLibraryError(
            "Room candidate scene must be a repository Godot resource"
        )
    if scene.startswith("res://"):
        relative = f"godot_walk/{scene.removeprefix('res://')}"
    elif scene.startswith("godot_walk/"):
        relative = scene
    else:
        raise SourceLibraryError(
            "Room candidate scene must be a repository Godot resource"
        )
    _safe_artifact_path(relative, root)
    return relative


def _find_identical_room(
    manifest: dict[str, Any], room: dict[str, Any]
) -> dict[str, Any] | None:
    for existing in manifest.get("room_adaptations", []):
        if existing.get("adaptation_path") != room["adaptation_path"]:
            continue
        if existing != room:
            raise SourceLibraryError(
                "Room adaptation path is already linked with different data"
            )
        return existing
    return None


def _write_successor(
    source_id: str,
    entry: dict[str, Any],
    manifest: dict[str, Any],
    room: dict[str, Any],
    root: Path,
) -> tuple[str, str]:
    prior_path = entry["manifest_path"]
    prior_version = _manifest_version(prior_path)
    version = prior_version + 1
    source_folder = LIBRARY / "sources" / source_id
    successor_rel = (source_folder / f"source_manifest-v{version}.json").as_posix()
    successor = dict(manifest)
    successor.update(
        {
            "schema_version": 2,
            "manifest_version": version,
            "supersedes": {"path": prior_path, "sha256": entry["manifest_sha256"]},
            "recorded_at_utc": utc_now(),
        }
    )
    successor.setdefault("room_adaptations", []).append(room)
    successor_path = root / successor_rel
    write_new_json(successor_path, successor)
    successor_hash = sha256_file(successor_path)
    manifest_lineage_hashes(
        {"source_id": source_id, "manifest_path": successor_rel}, root
    )
    updated_entry = dict(entry)
    updated_entry.update(
        {"manifest_path": successor_rel, "manifest_sha256": successor_hash}
    )
    _replace_index_entry(source_id, updated_entry, root)
    validate_index(root)
    return successor_rel, successor_hash


def _replace_index_entry(
    source_id: str, replacement: dict[str, Any], root: Path
) -> None:
    index_path = root / INDEX_PATH
    index = _read_object(index_path)
    entries = index.get("sources")
    if not isinstance(entries, list):
        raise SourceLibraryError("Source index has no source list")
    updated = [
        replacement if item.get("source_id") == source_id else item for item in entries
    ]
    if updated == entries:
        raise SourceLibraryError(
            "Source index entry disappeared during room registration"
        )
    write_index_snapshot(root, updated, int(index["index_version"]) + 1)


def _manifest_version(path_text: str) -> int:
    name = PurePosixPath(path_text).name
    if name == "source_manifest.json":
        return 1
    match = MANIFEST_VERSION_PATTERN.fullmatch(name)
    if match is None:
        raise SourceLibraryError("Unsupported source-manifest version path")
    return int(match.group(1))


def _find_source(entries: list[dict[str, Any]], source_id: str) -> dict[str, Any]:
    for entry in entries:
        if entry["source_id"] == source_id:
            return entry
    raise SourceLibraryError(f"Unknown source ID: {source_id}")


def _read_artifact(path_text: str, root: Path) -> tuple[dict[str, Any], str]:
    path = _safe_artifact_path(path_text, root)
    return _read_object(path), sha256_file(path)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceLibraryError(f"Cannot read JSON record: {path}") from error
    if not isinstance(value, dict):
        raise SourceLibraryError(f"Expected a JSON object: {path}")
    return value


def _safe_artifact_path(path_text: Any, root: Path) -> Path:
    if not isinstance(path_text, str) or "\\" in path_text:
        raise SourceLibraryError("Artifact path must be a repository-relative path")
    relative = PurePosixPath(path_text)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in path_text.split("/")
    ):
        raise SourceLibraryError(f"Unsafe artifact path: {path_text}")
    path = root.joinpath(*relative.parts)
    resolved_root = root.resolve()
    absolute = path.absolute()
    if not absolute.is_relative_to(resolved_root):
        raise SourceLibraryError(f"Artifact path escapes the repository: {path_text}")
    current = resolved_root
    for component in absolute.relative_to(resolved_root).parts:
        current /= component
        if current.is_symlink():
            raise SourceLibraryError(f"Artifact path uses a symlink: {path_text}")
    if not path.is_file():
        raise SourceLibraryError(f"Artifact is missing or unsafe: {path_text}")
    return path


def _validate_source_id(source_id: str) -> None:
    if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise SourceLibraryError("Unsafe source ID")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id")
    parser.add_argument("--adaptation", required=True)
    parser.add_argument("--decision", required=True)
    arguments = parser.parse_args()
    try:
        manifest_path, digest = register_room(
            arguments.source_id, arguments.adaptation, arguments.decision
        )
    except (OSError, SourceLibraryError) as error:
        parser.error(str(error))
    print(json.dumps({"manifest_path": manifest_path, "manifest_sha256": digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
