"""Fail-closed preconditions shared by the module-integration runner stages.

Everything here is read-only. A stage may continue only when the room folder
exists, its module sits in the newest library index for the current catalog
version, and the source ledger records an admission of that module.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from deterministic_json import repo_relative, sha256_file
from library_index import LibraryIndexError, load_json, load_verified_index
from source_ingestion_policy import ROOM_ID_PATTERN, WorkflowGateError
from video_source_library import LIBRARY

CATALOG_PATH = "godot_walk/room_catalog/catalog.json"
INDEX_DIR = "godot_walk/room_catalog/library_index"
ADMISSION_FILE = "catalog_admission_decision.json"
ADAPTATION_PATTERN = "adaptation_*accepted*.json"
EVENT_DERIVED = "module_metadata_derived"
EVENT_ACCEPTED = "module_metadata_accepted"
EVENT_RECORDED = "integration_proposal_recorded"
EVENT_DECIDED = "integration_proposal_decided"


def events_of(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event["event_type"] == event_type]


def current_index(root: Path) -> tuple[Path, dict[str, Any], str]:
    """Newest library index whose catalog_version matches catalog.json."""
    catalog_file = root / CATALOG_PATH
    if not catalog_file.is_file():
        raise WorkflowGateError(f"Catalog is missing: {CATALOG_PATH}")
    catalog = load_json(catalog_file)
    matches = []
    for path in sorted((root / INDEX_DIR).glob("*.json")):
        document = load_json(path)
        if (document.get("catalog_id"), document.get("catalog_version")) == (
            catalog.get("catalog_id"), catalog.get("catalog_version")
        ):
            matches.append(path)
    if not matches:
        raise WorkflowGateError(
            f"No library index for catalog version {catalog.get('catalog_version')}; "
            "build one with library_index.py first"
        )
    path = matches[-1]
    try:
        index = load_verified_index(path, root)
    except LibraryIndexError as error:
        raise WorkflowGateError(f"Library index is stale: {error}") from error
    return path, index, sha256_file(path)


def room_entry(
    source_id: str, room_id: str, index: dict[str, Any], root: Path
) -> dict[str, Any]:
    if not isinstance(room_id, str) or ROOM_ID_PATTERN.fullmatch(room_id) is None:
        raise WorkflowGateError("Room ID must be a lowercase hyphenated slug")
    folder = root / LIBRARY / "sources" / source_id / "rooms" / room_id
    if folder.is_symlink() or not folder.is_dir():
        raise WorkflowGateError(f"Unknown room folder for {source_id}: {room_id}")
    wanted = repo_relative(folder, root)
    for entry in index["modules"]:
        if entry["source_id"] == source_id and entry["room_dir"] == wanted:
            return entry
    raise WorkflowGateError(f"Room {room_id} has no module in the current library index")


def _file_matches(path: Any, digest: Any, root: Path) -> bool:
    if not isinstance(path, str) or not isinstance(digest, str):
        return False
    target = root / path
    return target.is_file() and not target.is_symlink() and sha256_file(target) == digest


def _decision_covers(path: str, entry: dict[str, Any], room_prefix: str, root: Path) -> bool:
    name = Path(path).name
    if path.startswith(room_prefix) and (
        name == ADMISSION_FILE or fnmatch.fnmatch(name, ADAPTATION_PATTERN)
    ):
        return True
    if name != ADMISSION_FILE:
        return False
    record = json.loads((root / path).read_text(encoding="utf-8"))
    listed = record.get("module_ids") or [record.get("module_id")]
    return entry["module_id"] in listed


def admission_sequence(
    events: list[dict[str, Any]], entry: dict[str, Any], root: Path
) -> int | None:
    """Sequence of the first event proving operator admission of this module."""
    room_prefix = entry["room_dir"] + "/"
    for event in events:
        payload = event.get("payload") or {}
        kind = event["event_type"]
        if kind == "catalog_admission_accepted":
            if (payload.get("module_id"), payload.get("module_version")) == (
                entry["module_id"], entry["version"]
            ):
                return event["sequence"]
            continue
        if kind == "historical_decision_reconciled":
            cited = payload.get("reconciles") or {}
            path, digest = cited.get("artifact_path"), cited.get("artifact_sha256")
        elif kind == "operator_catalog_admission_confirmed":
            path, digest = payload.get("confirmed_artifact_path"), payload.get("confirmed_artifact_sha256")
        else:
            continue
        if _file_matches(path, digest, root) and _decision_covers(path, entry, room_prefix, root):
            return event["sequence"]
    return None


def require_admission(events: list[dict[str, Any]], entry: dict[str, Any], root: Path) -> int:
    sequence = admission_sequence(events, entry, root)
    if sequence is None:
        raise WorkflowGateError(
            f"No admission event for {entry['module_id']}: expected catalog_admission_accepted, "
            "a reconciled admission/accepted-adaptation file or an operator confirmation"
        )
    return sequence


def derived_event(events: list[dict[str, Any]], entry: dict[str, Any]) -> dict[str, Any] | None:
    found = [
        event for event in events_of(events, EVENT_DERIVED)
        if event["payload"].get("module_id") == entry["module_id"]
        and event["payload"].get("version") == entry["version"]
    ]
    return found[-1] if found else None


def accepted_event(events: list[dict[str, Any]], entry: dict[str, Any]) -> dict[str, Any] | None:
    found = [
        event for event in events_of(events, EVENT_ACCEPTED)
        if event["payload"].get("module_id") == entry["module_id"]
        and event["payload"].get("version") == entry["version"]
    ]
    return found[-1] if found else None


def verified_draft(
    events: list[dict[str, Any]], entry: dict[str, Any], index_sha256: str, root: Path
) -> tuple[dict[str, Any], str, str]:
    """The derived v1 draft: (record, repo path, sha256), checked against ledger and index."""
    event = derived_event(events, entry)
    if event is None:
        raise WorkflowGateError(f"{entry['module_id']} has no module_metadata_derived event")
    payload = event["payload"]
    if not _file_matches(payload.get("draft_path"), payload.get("draft_sha256"), root):
        raise WorkflowGateError("Derived draft is missing or changed since it was logged")
    record = load_json(root / payload["draft_path"])
    if record["library_index"]["sha256"] != index_sha256 or payload.get("library_index_sha256") != index_sha256:
        raise WorkflowGateError("Derived draft is stale for the current library index")
    return record, payload["draft_path"], payload["draft_sha256"]
