"""Ingest and verify the #195 video batch against the generation template.

The batch descriptor is ``godot_walk/source_library/batches/issue-195.json``.
``upgrade`` writes versioned source manifests (a v2 bridge when the source only
has a v1 record, then a schema-v3 template snapshot) and never rewrites a
committed manifest. ``check`` validates the batch contract: every source has a
v3 snapshot, every admitted module from the batch has a profile, acoustics and
surface/palette descriptor, and no registration or scale flag was invented.
Operator decisions are reported as pending, never fabricated.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import template_validate as tv
from deterministic_json import ROOT, repo_relative, sha256_file
from library_index import load_verified_index
from register_video_sources import append_event, write_index_snapshot
from source_ingestion_runner import source_status
from template_manifest_v3 import (
    MANIFEST_SCHEMA_VERSION,
    ManifestUpgradeError,
    build_v2,
    build_v3,
    load_manifest,
    manifest_version,
    verify_v3,
    write_successor,
)
from template_module_contract import module_contract_errors
from video_source_library import (
    INDEX_PATH,
    LIBRARY,
    VIDEO_SOURCE_KIND,
    SourceLibraryError,
    manifest_lineage_hashes,
    manifest_video_content,
    validate_index,
)

BATCH_PATH = Path("godot_walk/source_library/batches/issue-195.json")
LIBRARY_INDEX_PATH = Path(
    "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json"
)
TEMPLATE_VERSION = "generation-template-0.1.0"
UPGRADE_EVENT = "source_manifest_v3_recorded"
EXPECTED_BATCH_SIZE = 10
EXPECTED_ISSUES = tuple(range(171, 181))


class BatchError(ValueError):
    """The batch descriptor or one of its source upgrades is invalid."""


@dataclass(frozen=True)
class SourceUpgrade:
    """One batch source and the template manifest it now points at."""

    source_id: str
    entry: dict[str, Any]
    manifest: dict[str, Any]
    predecessor_path: str
    predecessor_sha256: str
    status: str


def load_batch(root: Path = ROOT) -> dict[str, Any]:
    path = root / BATCH_PATH
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BatchError(
            f"Cannot read batch descriptor {BATCH_PATH}: {error}"
        ) from error
    if not isinstance(record, dict):
        raise BatchError("Batch descriptor must be a JSON object")
    errors = batch_record_errors(record)
    if errors:
        raise BatchError("; ".join(errors))
    return record


def batch_record_errors(record: dict[str, Any]) -> list[str]:
    errors = []
    if record.get("schema_version") != 1:
        errors.append("batch schema_version must be 1")
    if record.get("batch_id") != "issue-195" or record.get("issue") != 195:
        errors.append("batch identity must be issue-195")
    if record.get("template_version") != TEMPLATE_VERSION:
        errors.append(f"batch template_version must be {TEMPLATE_VERSION}")
    sources = record.get("sources")
    if not isinstance(sources, list) or len(sources) != EXPECTED_BATCH_SIZE:
        errors.append(f"batch must list {EXPECTED_BATCH_SIZE} sources")
        return errors
    issues, source_ids = [], []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"sources[{index}] must be an object")
            continue
        issue, source_id = source.get("issue"), source.get("source_id")
        if issue not in EXPECTED_ISSUES:
            errors.append(f"sources[{index}].issue is outside #171-#180")
        if not isinstance(source_id, str) or not source_id.startswith("video-"):
            errors.append(f"sources[{index}].source_id must be a video source")
        issues.append(issue)
        source_ids.append(source_id)
    if sorted(issues) != list(EXPECTED_ISSUES):
        errors.append("batch must cover each issue #171-#180 exactly once")
    if len(set(source_ids)) != len(source_ids):
        errors.append("batch source IDs must be unique")
    return errors


def _find_entry(entries: list[dict[str, Any]], source_id: str) -> dict[str, Any]:
    entry = next((item for item in entries if item["source_id"] == source_id), None)
    if entry is None:
        raise BatchError(f"Batch source is not registered: {source_id}")
    return entry


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise BatchError(f"Source event log is missing: {path}")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _verify_v2(
    manifest: dict[str, Any],
    video: dict[str, Any],
    source_id: str,
    parent_path: str,
    parent_hash: str,
    root: Path,
) -> None:
    if (
        manifest.get("schema_version") != 2
        or manifest.get("source_id") != source_id
        or manifest.get("supersedes") != {"path": parent_path, "sha256": parent_hash}
    ):
        raise ManifestUpgradeError("v2 manifest successor identity is invalid")
    current = manifest_video_content(manifest)
    for key in ("path", "sha256", "metadata"):
        if current.get(key) != video.get(key):
            raise ManifestUpgradeError("v2 manifest video identity changed")
    errors = tv.source_manifest_errors(manifest, root)
    if errors:
        raise ManifestUpgradeError("; ".join(errors))


def _existing_v3_errors(
    manifest: dict[str, Any], entry: dict[str, Any], root: Path
) -> list[str]:
    errors = tv.source_manifest_errors(manifest, root)
    try:
        video = manifest_video_content(manifest)
    except SourceLibraryError as error:
        return errors + [str(error)]
    if (
        video.get("path") != entry["source_path"]
        or video.get("sha256") != entry["source_sha256"]
    ):
        errors.append("v3 manifest video identity differs from the source index")
    try:
        manifest_lineage_hashes(entry, root)
    except (SourceLibraryError, ManifestUpgradeError) as error:
        errors.append(f"v3 manifest chain is invalid: {error}")
    return errors


def upgrade_source(
    source_id: str,
    root: Path = ROOT,
    entries: list[dict[str, Any]] | None = None,
) -> SourceUpgrade:
    """Write or adopt the latest v3 template snapshot for one registered source."""
    entries = validate_index(root) if entries is None else entries
    entry = _find_entry(entries, source_id)
    manifest_path = root / entry["manifest_path"]
    manifest = load_manifest(manifest_path)
    if manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION:
        errors = _existing_v3_errors(manifest, entry, root)
        if errors:
            raise BatchError("; ".join(errors))
        parent = manifest.get("supersedes") or {}
        return SourceUpgrade(
            source_id,
            entry,
            manifest,
            parent.get("path", ""),
            parent.get("sha256", ""),
            "unchanged",
        )
    video = manifest_video_content(manifest)
    source_dir = manifest_path.parent
    if manifest.get("schema_version") == 1:
        v2_path = source_dir / "source_manifest-v2.json"
        if v2_path.is_file():
            v2 = load_manifest(v2_path)
        else:
            v2 = build_v2(manifest, entry["manifest_path"], entry["manifest_sha256"])
            write_successor(v2_path, v2)
        v2_relative = repo_relative(v2_path, root)
        v2_hash = sha256_file(v2_path)
        _verify_v2(
            v2, video, source_id, entry["manifest_path"], entry["manifest_sha256"], root
        )
        parent_path, parent_hash = v2_relative, v2_hash
    else:
        v2 = manifest
        parent_path, parent_hash = entry["manifest_path"], entry["manifest_sha256"]
    version = max(manifest_version(entry["manifest_path"]) + 1, 3)
    v3_path = source_dir / f"source_manifest-v{version}.json"
    if v3_path.is_file():
        v3 = load_manifest(v3_path)
    else:
        v3 = build_v3(v2, parent_path, parent_hash, version)
        write_successor(v3_path, v3)
    verify_v3(v3, video, source_id, parent_path, parent_hash, root)
    updated = dict(entry)
    updated.update(
        {
            "manifest_path": repo_relative(v3_path, root),
            "manifest_sha256": sha256_file(v3_path),
        }
    )
    manifest_lineage_hashes(updated, root)
    return SourceUpgrade(
        source_id,
        updated,
        v3,
        parent_path,
        parent_hash,
        "created" if updated != entry else "unchanged",
    )


def upgrade_batch(root: Path = ROOT) -> list[dict[str, Any]]:
    """Upgrade every batch source and point the index at the new manifests."""
    batch = load_batch(root)
    entries = validate_index(root)
    by_id = {entry["source_id"]: entry for entry in entries}
    results: list[SourceUpgrade] = []
    for source in batch["sources"]:
        result = upgrade_source(source["source_id"], root, entries)
        results.append(result)
        by_id[result.source_id] = result.entry
    if any(by_id[entry["source_id"]] != entry for entry in entries):
        index = json.loads((root / INDEX_PATH).read_text(encoding="utf-8"))
        updated = [by_id[entry["source_id"]] for entry in entries]
        write_index_snapshot(root, updated, int(index["index_version"]) + 1)
        validate_index(root)
    appended = [_append_upgrade_event(result, root) for result in results]
    return [
        {
            "source_id": result.source_id,
            "issue": _issue_for(batch, result.source_id),
            "manifest_path": result.entry["manifest_path"],
            "manifest_sha256": result.entry["manifest_sha256"],
            "status": result.status,
            "event": event_status,
        }
        for result, event_status in zip(results, appended)
    ]


def _issue_for(batch: dict[str, Any], source_id: str) -> int:
    return next(
        source["issue"]
        for source in batch["sources"]
        if source["source_id"] == source_id
    )


def _append_upgrade_event(result: SourceUpgrade, root: Path) -> str:
    path = root / LIBRARY / "sources" / result.source_id / "events.jsonl"
    events = _read_events(path)
    recorded = any(
        event.get("event_type") == UPGRADE_EVENT
        and event.get("payload", {}).get("manifest_sha256")
        == result.entry["manifest_sha256"]
        for event in events
    )
    if recorded:
        return "unchanged"
    append_event(
        result.source_id,
        UPGRADE_EVENT,
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "source_kind": VIDEO_SOURCE_KIND,
            "manifest_path": result.entry["manifest_path"],
            "manifest_sha256": result.entry["manifest_sha256"],
            "predecessor_path": result.predecessor_path,
            "predecessor_sha256": result.predecessor_sha256,
            "template_version": TEMPLATE_VERSION,
            "registration_accepted": False,
            "scale_calibrated": False,
            "note": (
                "CPU-only template snapshot. No operator decision, model call "
                "or catalog admission is created by this event."
            ),
        },
        root,
    )
    return "appended"


def batch_status(root: Path = ROOT) -> dict[str, Any]:
    """Return per-source gate state and the module contract for the batch."""
    batch = load_batch(root)
    entries = validate_index(root)
    modules = load_verified_index(root / LIBRARY_INDEX_PATH, root)["modules"]
    sources = []
    for source in batch["sources"]:
        source_id = source["source_id"]
        entry = _find_entry(entries, source_id)
        manifest = load_manifest(root / entry["manifest_path"])
        status = source_status(source_id, root)
        source_modules = [
            item for item in modules if item.get("source_id") == source_id
        ]
        sources.append(
            {
                "issue": source["issue"],
                "source_id": source_id,
                "manifest_path": entry["manifest_path"],
                "manifest_sha256": entry["manifest_sha256"],
                "manifest_schema_version": manifest.get("schema_version"),
                "manifest_source_review": manifest.get("source_review"),
                "registration_accepted": manifest.get("registration_accepted"),
                "scale_calibrated": manifest.get("scale_calibrated"),
                "source_decision": status["source_decision"],
                "selected_seed": status["selected_seed"],
                "next_worker_actions": status["next_worker_actions"],
                "admitted_module_ids": [item["module_id"] for item in source_modules],
                "module_contract_errors": {
                    item["module_id"]: module_contract_errors(item, root)
                    for item in source_modules
                },
            }
        )
    return {
        "batch_id": batch["batch_id"],
        "template_version": batch["template_version"],
        "source_count": len(sources),
        "admitted_module_count": sum(
            len(source["admitted_module_ids"]) for source in sources
        ),
        "sources": sources,
    }


def batch_errors(root: Path = ROOT) -> list[str]:
    """Validate every source and module named by the batch contract."""
    try:
        batch = load_batch(root)
        entries = validate_index(root)
        modules = load_verified_index(root / LIBRARY_INDEX_PATH, root)["modules"]
    except (BatchError, SourceLibraryError, OSError, ValueError) as error:
        return [str(error)]
    errors: list[str] = []
    for source in batch["sources"]:
        source_id = source["source_id"]
        entry = _find_entry(entries, source_id)
        manifest = load_manifest(root / entry["manifest_path"])
        label = f"{source_id}:"
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            errors.append(f"{label} latest manifest is not template schema v3")
        errors.extend(
            f"{label} {error}" for error in tv.source_manifest_errors(manifest, root)
        )
        try:
            video = manifest_video_content(manifest)
        except SourceLibraryError as error:
            errors.append(f"{label} {error}")
            continue
        if (
            video.get("path") != entry["source_path"]
            or video.get("sha256") != entry["source_sha256"]
        ):
            errors.append(f"{label} manifest video differs from the source index")
        events_path = root / LIBRARY / "sources" / source_id / "events.jsonl"
        if not events_path.is_file():
            errors.append(f"{label} source event log is missing")
            continue
        events = _read_events(events_path)
        if not any(
            event.get("event_type") == UPGRADE_EVENT
            and event.get("source_manifest_sha256") == entry["manifest_sha256"]
            and event.get("payload", {}).get("manifest_sha256")
            == entry["manifest_sha256"]
            for event in events
        ):
            errors.append(f"{label} missing the v3 manifest audit event")
        for module in modules:
            if module.get("source_id") != source_id:
                continue
            errors.extend(
                f"{module['module_id']}: {error}"
                for error in module_contract_errors(module, root)
            )
    return errors


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "upgrade", "check"))
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    try:
        if arguments.command == "upgrade":
            _print({"batch_id": "issue-195", "sources": upgrade_batch(root)})
            return 0
        if arguments.command == "status":
            _print(batch_status(root))
            return 0
        errors = batch_errors(root)
        _print({"valid": not errors, "batch_id": "issue-195", "errors": errors})
        return 0 if not errors else 1
    except (
        BatchError,
        SourceLibraryError,
        ManifestUpgradeError,
        OSError,
        ValueError,
    ) as error:
        _print({"valid": False, "batch_id": "issue-195", "errors": [str(error)]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
