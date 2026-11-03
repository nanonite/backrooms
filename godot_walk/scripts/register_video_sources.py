"""Register local data/videos inputs without copying or editing source media."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from source_event_reconciliation import validate_decision_event_coverage
from video_source_library import (
    INDEX_PATH,
    LIBRARY,
    ROOT,
    VIDEO_DIR,
    Probe,
    SourceLibraryError,
    canonical_video_path,
    lock_file,
    probe_video,
    safe_source_id,
    sha256_file,
    utc_now,
    validate_index,
    write_new_json,
    write_new_jsonl_event,
)

HISTORICAL = {
    "room_large.mp4": {
        "issue": 163,
        "adaptation_path": "godot_walk/room_catalog/adaptations/room-large-v1.json",
        "decision_path": "godot_walk/evidence/2026-10-24-issue-163/operator_review.json",
        "evidence_manifest_path": "godot_walk/evidence/2026-10-24-issue-163/source_manifest.json",
        "report_path": "godot_walk/evidence/2026-10-24-issue-163/REPORT.md",
        "hunyuan_status": "historical_over_cap_no_panorama",
        "historical_invocations": 4,
    },
    "corridor_corner.mp4": {
        "issue": 165,
        "adaptation_path": "godot_walk/room_catalog/adaptations/corridor-corner-v2.json",
        "decision_path": "godot_walk/evidence/2026-10-25-issue-165/operator_review.json",
        "report_path": "godot_walk/evidence/2026-10-25-issue-165/REPORT.md",
        "hunyuan_status": "historical_manual_adaptation_without_attempt",
        "historical_invocations": 0,
    },
}


def historical_references(
    filename: str, root: Path
) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]
]:
    details = HISTORICAL.get(filename)
    if details is None:
        return (
            [],
            [],
            {"status": "not_attempted", "historical_invocations": 0, "attempts": []},
            [],
        )
    references = []
    for key in (
        "adaptation_path",
        "decision_path",
        "evidence_manifest_path",
        "report_path",
    ):
        relative = details.get(key)
        if relative is None:
            continue
        artifact = root / relative
        if not artifact.is_file():
            raise SourceLibraryError(f"Missing historical artifact: {relative}")
        references.append(
            {
                "role": key.removesuffix("_path"),
                "path": relative,
                "sha256": sha256_file(artifact),
            }
        )
    adaptation = json.loads(
        (root / details["adaptation_path"]).read_text(encoding="utf-8")
    )
    frames = _historical_frames(adaptation, details["adaptation_path"])
    room = {
        "issue": details["issue"],
        "adaptation_id": adaptation["adaptation_id"],
        "adaptation_path": details["adaptation_path"],
        "adaptation_sha256": sha256_file(root / details["adaptation_path"]),
        "decision_path": details["decision_path"],
        "decision_sha256": sha256_file(root / details["decision_path"]),
        "decision_status": adaptation["operator_decision"]["status"],
    }
    hunyuan = _historical_hunyuan(filename, details, root)
    return references, [room], hunyuan, frames


def _historical_frames(
    adaptation: dict[str, Any], record_path: str
) -> list[dict[str, Any]]:
    frames = []
    for frame in adaptation["source_observations"].get("frames", []):
        frames.append(
            {
                "frame_id": frame["frame_id"],
                "index_zero_based": frame["index_zero_based"],
                "timestamp_seconds": frame["timestamp_seconds"],
                "path": frame["path"],
                "sha256": frame["sha256"],
                "decode_operation": frame["decode_operation"],
                "historical_record_path": record_path,
            }
        )
    return frames


def _historical_hunyuan(
    filename: str, details: dict[str, Any], root: Path
) -> dict[str, Any]:
    attempts = []
    if filename == "room_large.mp4":
        worldgen = root / "godot_walk/evidence/2026-10-24-issue-163/worldgen"
        for status_path in sorted(worldgen.glob("*_status.json")):
            status = json.loads(status_path.read_text(encoding="utf-8"))
            attempt_name = status_path.name.removesuffix("_status.json")
            evidence_paths = [status_path, worldgen / f"{attempt_name}.log"]
            evidence_paths.extend(
                sorted(worldgen.glob(f"{attempt_name}_resources.jsonl"))
            )
            artifacts = [
                {
                    "path": item.relative_to(root).as_posix(),
                    "sha256": sha256_file(item),
                }
                for item in evidence_paths
                if item.is_file()
            ]
            attempts.append(
                {
                    "attempt_id": f"historical-{attempt_name}",
                    "status": status["status"],
                    "stop_reason": status.get("stop_reason"),
                    "elapsed_seconds": status.get("elapsed_seconds"),
                    "evidence": artifacts,
                }
            )
    return {
        "status": details["hunyuan_status"],
        "historical_invocations": details["historical_invocations"],
        "historical_attempts": attempts,
        "policy_invocation_limit": 3,
        "attempts": [],
        "policy_note": "Historical invocations are preserved separately and do not authorize a new run.",
    }


def _source_manifest(
    source_id: str,
    path: str,
    digest: str,
    metadata: dict[str, Any],
    filename: str,
    root: Path,
) -> dict[str, Any]:
    refs, rooms, historical_hunyuan, frames = historical_references(filename, root)
    _verify_historical_source(rooms, path, digest, root)
    return {
        "schema_version": 1,
        "source_id": source_id,
        "created_at_utc": utc_now(),
        "canonical_video": {"path": path, "sha256": digest, "metadata": metadata},
        "registration_accepted": False,
        "scale_calibrated": False,
        "source_review": {"status": "pending_operator_review", "decision": None},
        "frame_references": frames,
        "hunyuan": historical_hunyuan,
        "room_adaptations": rooms,
        "historical_artifacts": refs,
        "modeling_note": "Video-to-room multiplicity is zero-or-more; index records do not infer room boundaries or connectivity.",
    }


def _verify_historical_source(
    rooms: list[dict[str, Any]], path: str, digest: str, root: Path
) -> None:
    for room in rooms:
        adaptation_path = root / room["adaptation_path"]
        adaptation = json.loads(adaptation_path.read_text(encoding="utf-8"))
        source = adaptation["source_observations"]["video"]
        if source["path"] != path or source["sha256"] != digest:
            raise SourceLibraryError(
                f"Historical adaptation points to a different source: {room['adaptation_id']}"
            )
        for frame in adaptation["source_observations"].get("frames", []):
            frame_path = root / frame["path"]
            if not frame_path.is_file() or sha256_file(frame_path) != frame["sha256"]:
                raise SourceLibraryError(
                    f"Historical frame changed: {frame['frame_id']}"
                )


def _index_entry(
    source_id: str, source_path: str, digest: str, manifest_path: Path, root: Path
) -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_path": source_path,
        "source_sha256": digest,
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
    }


def write_index_snapshot(
    root: Path, entries: list[dict[str, Any]], revision: int
) -> None:
    index = {
        "schema_version": 1,
        "index_version": revision,
        "sources": sorted(entries, key=lambda item: item["source_id"]),
    }
    path = root / INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        json.dump(index, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def register_video(
    video_path: Path, root: Path = ROOT, probe: Probe = probe_video
) -> str:
    video, relative = canonical_video_path(video_path, root)
    digest = sha256_file(video)
    source_id = safe_source_id(digest)
    metadata = probe(video)
    if sha256_file(video) != digest:
        raise SourceLibraryError(
            f"Source changed while it was being inventoried: {relative}"
        )
    library = root / LIBRARY
    with lock_file(library / ".index.lock"):
        index_path = root / INDEX_PATH
        existing_index = (
            json.loads(index_path.read_text(encoding="utf-8"))
            if index_path.exists()
            else {"index_version": 0, "sources": []}
        )
        entries = existing_index.get("sources")
        if not isinstance(entries, list):
            raise SourceLibraryError("Source-library index has no valid source list")
        _reject_duplicate(entries, relative, digest)
        existing = next(
            (entry for entry in entries if entry["source_id"] == source_id), None
        )
        if existing:
            if (
                existing["source_path"] != relative
                or existing["source_sha256"] != digest
            ):
                raise SourceLibraryError(f"Source ID prefix collision: {source_id}")
            validate_index(root)
            return source_id
        source_dir = library / "sources" / source_id
        if source_dir.exists():
            raise SourceLibraryError(
                f"Unindexed source record already exists: {source_id}"
            )
        source_root = source_dir.parent
        source_root.mkdir(parents=True, exist_ok=True)
        manifest = _source_manifest(
            source_id, relative, digest, metadata, video.name, root
        )
        with tempfile.TemporaryDirectory(
            dir=source_root, prefix=f".{source_id}."
        ) as temporary:
            temporary_dir = Path(temporary)
            manifest_path = temporary_dir / "source_manifest.json"
            write_new_json(manifest_path, manifest)
            event = {
                "sequence": 1,
                "event_type": "source_registered",
                "occurred_at_utc": utc_now(),
                "source_manifest_sha256": sha256_file(manifest_path),
            }
            write_new_jsonl_event(temporary_dir / "events.jsonl", event)
            if sha256_file(video) != digest:
                raise SourceLibraryError(
                    f"Source changed during registration: {relative}"
                )
            os.rename(temporary_dir, source_dir)
        manifest_path = source_dir / "source_manifest.json"
        entries.append(_index_entry(source_id, relative, digest, manifest_path, root))
        write_index_snapshot(
            root, entries, int(existing_index.get("index_version", 0)) + 1
        )
    return source_id


def _reject_duplicate(
    entries: list[dict[str, Any]], relative: str, digest: str
) -> None:
    for entry in entries:
        if entry["source_path"] == relative and entry["source_sha256"] != digest:
            raise SourceLibraryError(
                f"Registered source changed at its canonical path: {relative}"
            )
        if entry["source_sha256"] == digest and entry["source_path"] != relative:
            raise SourceLibraryError(
                f"Duplicate source content already registered as {entry['source_id']}"
            )


def inventory(root: Path = ROOT, probe: Probe = probe_video) -> list[str]:
    video_dir = root / VIDEO_DIR
    if not video_dir.is_dir():
        raise SourceLibraryError("Local intake directory data/videos does not exist")
    registered = []
    for path in sorted(video_dir.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            registered.append(register_video(path, root, probe))
    return registered


def append_event(
    source_id: str, event_type: str, payload: dict[str, Any], root: Path = ROOT
) -> None:
    if (
        not isinstance(source_id, str)
        or re.fullmatch(r"video-[0-9a-f]{16}", source_id) is None
    ):
        raise SourceLibraryError("Unsafe source ID")
    if re.fullmatch(r"[a-z][a-z0-9_]{1,63}", event_type) is None:
        raise SourceLibraryError("Unsafe event type")
    path = root / LIBRARY / "sources" / source_id / "events.jsonl"
    entries = validate_index(root)
    source_entry = next(
        (entry for entry in entries if entry["source_id"] == source_id), None
    )
    if source_entry is None:
        raise SourceLibraryError("Cannot append events to an unregistered source")
    if not path.is_file() or path.is_symlink():
        raise SourceLibraryError("Source event log is missing or unsafe")
    with path.open("r+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        content = stream.read()
        lines = content.splitlines()
        if content and not content.endswith("\n"):
            raise SourceLibraryError("Source event log ends with a partial record")
        _validate_event_lines(lines)
        event = {
            "schema_version": 1,
            "sequence": len(lines) + 1,
            "event_type": event_type,
            "occurred_at_utc": utc_now(),
            "source_id": source_id,
            "source_video_sha256": source_entry["source_sha256"],
            "source_manifest_sha256": source_entry["manifest_sha256"],
            "payload": payload,
        }
        stream.seek(0, os.SEEK_END)
        stream.write(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _validate_event_lines(lines: list[str]) -> None:
    for sequence, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise SourceLibraryError(
                "Source event log contains invalid JSON"
            ) from error
        if event.get("sequence") != sequence:
            raise SourceLibraryError("Source event log sequence is not contiguous")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "validate"))
    arguments = parser.parse_args()
    if arguments.action == "inventory":
        source_ids = inventory()
        print(
            json.dumps(
                {"registered_count": len(source_ids), "source_ids": source_ids},
                indent=2,
            )
        )
        return 0
    entries = validate_index()
    validate_decision_event_coverage()
    print(json.dumps({"valid": True, "registered_count": len(entries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
