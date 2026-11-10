"""Register local data/pictures picture sets without copying or editing them."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from register_video_sources import write_index_snapshot
from source_event_reconciliation import validate_decision_event_coverage
from video_source_library import (
    INDEX_PATH,
    LIBRARY,
    PICTURE_DIR,
    PICTURE_SET_SOURCE_KIND,
    ROOT,
    SourceLibraryError,
    canonical_picture_set_path,
    lock_file,
    picture_set_sha256,
    probe_picture_set,
    safe_source_id,
    sha256_file,
    utc_now,
    validate_index,
    write_new_json,
    write_new_jsonl_event,
)

PictureProbe = Callable[[Path, Path], list[dict[str, Any]]]


def _source_manifest(
    source_id: str, relative: str, images: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "manifest_version": 3,
        "source_id": source_id,
        "source_kind": PICTURE_SET_SOURCE_KIND,
        "created_at_utc": utc_now(),
        "content": {
            "video": None,
            "picture_set": images,
            "audio": {"present": False, "path": None, "sha256": None},
        },
        "capture": {
            "camera_model": None,
            "lens": None,
            "intrinsics": {"fx": None, "fy": None, "cx": None, "cy": None},
            "distortion": None,
            "capture_height_m": None,
            "orientation": None,
        },
        "scale": {
            "status": "uncalibrated",
            "method": None,
            "anchor": None,
            "confidence": 0.0,
            "evidence": [],
        },
        "lighting": {
            "status": "unknown",
            "color_temp_k": None,
            "illuminance_lux": None,
            "fixtures": [],
            "confidence": 0.0,
            "evidence": [],
        },
        "source_review": {"status": "pending_operator_review", "decision": None},
        "frame_references": [],
        "hunyuan": {
            "status": "not_attempted",
            "attempts": [],
            "historical_attempts": [],
            "historical_invocations": 0,
            "policy_invocation_limit": 3,
            "policy_note": "Picture-set registration does not authorize a model run.",
        },
        "room_adaptations": [],
        "historical_artifacts": [],
        "registration_accepted": False,
        "scale_calibrated": False,
        "modeling_note": (
            "Picture-set images are direct source inputs. Import records image "
            "identity and dimensions; it never invents a frame timestamp."
        ),
    }


def _copy_image_records(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(image) for image in images]


def _verify_unchanged(
    directory: Path,
    relative: str,
    images: list[dict[str, Any]],
    root: Path,
    probe: PictureProbe,
) -> None:
    current = probe(directory, root)
    if current != images:
        raise SourceLibraryError(
            f"Picture set changed while it was being registered: {relative}"
        )


def _index_entry(
    source_id: str,
    source_path: str,
    digest: str,
    manifest_path: Path,
    root: Path,
) -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_path": source_path,
        "source_sha256": digest,
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
    }


def register_picture_set(
    picture_dir: Path,
    root: Path = ROOT,
    probe: PictureProbe = probe_picture_set,
) -> str:
    """Register one direct picture-set directory and return its source ID."""
    directory, relative = canonical_picture_set_path(picture_dir, root)
    images = probe(directory, root)
    if not images:
        raise SourceLibraryError(f"Picture set contains no supported images: {relative}")
    digest = picture_set_sha256(images)
    source_id = safe_source_id(digest, PICTURE_SET_SOURCE_KIND)
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
        manifest = _source_manifest(source_id, relative, _copy_image_records(images))
        with tempfile.TemporaryDirectory(
            dir=source_root, prefix=f".{source_id}."
        ) as temporary:
            temporary_dir = Path(temporary)
            manifest_path = temporary_dir / "source_manifest-v3.json"
            write_new_json(manifest_path, manifest)
            event = {
                "schema_version": 1,
                "sequence": 1,
                "event_type": "source_registered",
                "occurred_at_utc": utc_now(),
                "source_id": source_id,
                "source_kind": PICTURE_SET_SOURCE_KIND,
                "source_sha256": digest,
                "source_image_set_sha256": digest,
                "source_manifest_sha256": sha256_file(manifest_path),
                "payload": {
                    "source_kind": PICTURE_SET_SOURCE_KIND,
                    "source_path": relative,
                    "image_count": len(images),
                },
            }
            write_new_jsonl_event(temporary_dir / "events.jsonl", event)
            _verify_unchanged(directory, relative, images, root, probe)
            os.rename(temporary_dir, source_dir)
        manifest_path = source_dir / "source_manifest-v3.json"
        entries.append(
            _index_entry(source_id, relative, digest, manifest_path, root)
        )
        write_index_snapshot(
            root, entries, int(existing_index.get("index_version", 0)) + 1
        )
        validate_index(root)
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


def inventory_pictures(
    root: Path = ROOT, probe: PictureProbe = probe_picture_set
) -> list[str]:
    picture_dir = root / PICTURE_DIR
    if not picture_dir.is_dir() or picture_dir.is_symlink():
        raise SourceLibraryError("Local intake directory data/pictures does not exist")
    registered = []
    for path in sorted(picture_dir.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_dir() and not path.is_symlink():
            registered.append(register_picture_set(path, root, probe))
    return registered


def _safe_picture_set_argument(value: str, root: Path) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise SourceLibraryError("Picture-set path must be repository-relative")
    return root.joinpath(*relative.parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "register", "validate"))
    parser.add_argument(
        "picture_set",
        nargs="?",
        help="Directory below data/pictures for the register action",
    )
    arguments = parser.parse_args()
    try:
        if arguments.action == "inventory":
            source_ids = inventory_pictures()
            print(
                json.dumps(
                    {"registered_count": len(source_ids), "source_ids": source_ids},
                    indent=2,
                )
            )
            return 0
        if arguments.action == "register":
            if not arguments.picture_set:
                parser.error("register requires a picture-set directory")
            path = _safe_picture_set_argument(arguments.picture_set, ROOT)
            print(json.dumps({"source_id": register_picture_set(path)}, indent=2))
            return 0
        entries = validate_index()
        validate_decision_event_coverage()
        print(json.dumps({"valid": True, "registered_count": len(entries)}, indent=2))
        return 0
    except (OSError, SourceLibraryError) as error:
        parser.error(str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
