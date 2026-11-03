"""Append-only receipt storage and input fingerprints."""

from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path
from typing import Any

from seed_review_candidates import CandidateSet
from seed_review_errors import SeedReviewError
from seed_review_paths import (
    ROOT,
    canonical_json,
    canonical_sha256,
    repo_relative,
    sha256_file,
)
from seed_review_provider import ModelIdentity
from seed_review_sources import SourceRecord
from seed_review_workflow import WorkflowSpec

INDEX_FILENAME = "receipts.jsonl"
INDEX_SCHEMA_VERSION = 1


def build_input_fingerprint(
    *,
    spec: WorkflowSpec,
    source: SourceRecord,
    candidate_set: CandidateSet,
    identity: ModelIdentity,
    prompt_sha256: str,
    timeout_seconds: float,
    confidence_threshold: int,
    invocation_mode: str,
    replay_response_sha256: str | None,
) -> str:
    provided = list(candidate_set.reviewed) + list(candidate_set.excluded)
    return canonical_sha256(
        {
            "workflow_spec_sha256": spec.manifest_sha256,
            "schema_sha256": spec.schema_sha256,
            "source_id": source.source_id,
            "source_video_sha256": source.video_sha256,
            "source_manifest_sha256": source.manifest_sha256,
            "candidates": [
                {
                    "frame_id": item.candidate.frame_id,
                    "index_zero_based": item.candidate.index_zero_based,
                    "pts_seconds": item.candidate.pts_seconds,
                    "sha256": item.candidate.sha256,
                }
                for item in provided
            ],
            "mechanical_shortlist_applied": (
                candidate_set.mechanical_shortlist_applied
            ),
            "model_reference": identity.reference,
            "image_input_supported": identity.image_input_supported,
            "prompt_sha256": prompt_sha256,
            "timeout_seconds": round(float(timeout_seconds), 6),
            "confidence_threshold": confidence_threshold,
            "invocation_mode": invocation_mode,
            "replay_response_sha256": replay_response_sha256,
        }
    )


def finalize_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in receipt.items() if key != "receipt_id"}
    finalized = dict(receipt)
    finalized["receipt_id"] = canonical_sha256(body)
    return finalized


def write_receipt(
    receipt: dict[str, Any],
    receipts_dir: Path,
    root: Path = ROOT,
) -> Path:
    source_id = receipt.get("source", {}).get("source_id")
    if not isinstance(source_id, str):
        raise SeedReviewError("receipt_invalid", "Receipt lacks a source ID")
    directory = _receipt_directory(receipts_dir, source_id, root)
    _preflight_index(directory, receipt["receipt_id"])
    filename = (
        f"{_compact_time(receipt['created_at_utc'])}-{receipt['receipt_id'][:12]}.json"
    )
    target = directory / filename
    if target.is_symlink():
        raise SeedReviewError("unsafe_receipt_path", "Receipt path is a symlink")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o644)
    except FileExistsError as error:
        raise SeedReviewError(
            "receipt_exists",
            f"Receipt already exists and will not be overwritten: {target}",
        ) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    append_receipt_index(receipt, target, receipts_dir, root)
    return target


def _preflight_index(directory: Path, receipt_id: str) -> None:
    index_path = directory / INDEX_FILENAME
    if not index_path.is_file():
        return
    content = index_path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        raise SeedReviewError(
            "receipt_index_corrupt", "Receipt index ends with a partial record"
        )
    lines = content.splitlines()
    _validate_index_lines(lines)
    if any(json.loads(line).get("receipt_id") == receipt_id for line in lines):
        raise SeedReviewError("receipt_exists", "Receipt ID is already indexed")


def append_receipt_index(
    receipt: dict[str, Any],
    receipt_path: Path,
    receipts_dir: Path,
    root: Path = ROOT,
) -> dict[str, Any]:
    source_id = receipt["source"]["source_id"]
    directory = _receipt_directory(receipts_dir, source_id, root)
    index_path = directory / INDEX_FILENAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(index_path, flags, 0o644)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        content = stream.read()
        lines = content.splitlines()
        if content and not content.endswith("\n"):
            raise SeedReviewError(
                "receipt_index_corrupt", "Receipt index ends with a partial record"
            )
        _validate_index_lines(lines)
        if any(
            json.loads(line).get("receipt_id") == receipt["receipt_id"]
            for line in lines
        ):
            raise SeedReviewError("receipt_exists", "Receipt ID is already indexed")
        record = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "sequence": len(lines) + 1,
            "receipt_id": receipt["receipt_id"],
            "receipt_sha256": sha256_file(receipt_path),
            "input_fingerprint": receipt["input_fingerprint"],
            "path": repo_relative(receipt_path, root),
            "created_at_utc": receipt["created_at_utc"],
            "status": receipt["status"],
            "source_id": source_id,
            "source_video_sha256": receipt["source"]["video_sha256"],
        }
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
        stream.write("\n")
        stream.flush()
    return record


def find_existing_receipt(
    receipts_dir: Path,
    source_id: str,
    input_fingerprint: str,
    root: Path = ROOT,
) -> dict[str, Any] | None:
    directory = _receipt_directory(receipts_dir, source_id, root, create=False)
    index_path = directory / INDEX_FILENAME
    if not index_path.is_file():
        return None
    content = index_path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        raise SeedReviewError(
            "receipt_index_corrupt", "Receipt index ends with a partial record"
        )
    for line in content.splitlines():
        record = json.loads(line)
        if record.get("input_fingerprint") == input_fingerprint:
            return record
    return None


def _receipt_directory(
    receipts_dir: Path, source_id: str, root: Path, *, create: bool = True
) -> Path:
    if not re.fullmatch(r"video-[0-9a-f]{16}", source_id):
        raise SeedReviewError("unsafe_source_id", "Unsafe source ID for receipts")
    repo = root.resolve()
    base = receipts_dir if receipts_dir.is_absolute() else repo / receipts_dir
    candidate = base / source_id
    _reject_symlink_components(candidate, repo)
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(repo):
        raise SeedReviewError(
            "unsafe_receipt_path", "Receipt directory escapes the repository"
        )
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(candidate, repo)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(repo):
            raise SeedReviewError(
                "unsafe_receipt_path", "Receipt directory escapes the repository"
            )
    return resolved


def _reject_symlink_components(path: Path, repo: Path) -> None:
    candidate = path.absolute()
    if not candidate.is_relative_to(repo):
        raise SeedReviewError(
            "unsafe_receipt_path", "Receipt path escapes the repository"
        )
    current = repo
    for component in candidate.relative_to(repo).parts:
        current /= component
        if current.is_symlink():
            raise SeedReviewError(
                "unsafe_receipt_path", f"Receipt path uses a symlink: {current}"
            )


def _validate_index_lines(lines: list[str]) -> None:
    for expected, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise SeedReviewError(
                "receipt_index_corrupt", "Receipt index contains invalid JSON"
            ) from error
        if (
            not isinstance(record, dict)
            or record.get("schema_version") != INDEX_SCHEMA_VERSION
            or record.get("sequence") != expected
        ):
            raise SeedReviewError(
                "receipt_index_corrupt", "Receipt index sequence is invalid"
            )


def _compact_time(created_at_utc: str) -> str:
    compact = re.sub(r"[^0-9A-Za-z]", "", created_at_utc)
    if not compact:
        raise SeedReviewError("receipt_invalid", "Receipt timestamp is invalid")
    return compact[:20]


def canonical_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return canonical_json(receipt)
