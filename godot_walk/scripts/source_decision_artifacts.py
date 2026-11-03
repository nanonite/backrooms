"""Describe operator decision files: decision, original timestamp and issue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from video_source_library import sha256_file

TIMESTAMP_FIELDS = (
    "reviewed_at_utc",
    "recorded_at_utc",
    "reviewed_at",
    "reviewed_at_local_date",
)
# Issue numbers for decision files whose own content does not name an issue.
ROOM_FOLDER_ISSUES = {
    "industrial-hall-panorama-v3": 167,
    "debris-window-rock-room-v1": 168,
    "issue168-two-room-connection-v1": 168,
}


@dataclass(frozen=True)
class DecisionArtifact:
    path: str
    sha256: str
    role: str
    issue: int | None
    decision: str | None
    timestamp: str | None
    timestamp_field: str | None
    adaptation_id: str | None
    candidate_identity: str | None


def _role(path: str) -> str:
    name = Path(path).name
    if name.startswith("adaptation_"):
        return "accepted_adaptation"
    return name.removesuffix(".json")


def _decision_of(record: dict[str, Any]) -> str | None:
    nested = record.get("operator_decision")
    for value in (
        record.get("decision"),
        nested.get("status") if isinstance(nested, dict) else None,
    ):
        if isinstance(value, str):
            return value
    return None


def _timestamp_of(record: dict[str, Any], root: Path) -> tuple[str | None, str | None]:
    for field in TIMESTAMP_FIELDS:
        if isinstance(record.get(field), str):
            return record[field], field
    nested = record.get("operator_decision")
    if not isinstance(nested, dict) or not isinstance(
        nested.get("decision_record_path"), str
    ):
        return None, None
    cited = root / nested["decision_record_path"]
    if not cited.is_file() or sha256_file(cited) != nested.get("decision_sha256"):
        return None, None
    value, field = _timestamp_of(json.loads(cited.read_text(encoding="utf-8")), root)
    cited_field = f"{nested['decision_record_path']}#{field}"
    return (value, cited_field) if value else (None, None)


def _issue_of(path: str, record: dict[str, Any]) -> int | None:
    if isinstance(record.get("issue"), int):
        return record["issue"]
    parts = Path(path).parts
    return next(
        (ROOM_FOLDER_ISSUES[part] for part in parts if part in ROOM_FOLDER_ISSUES),
        _issue_from_evidence_folder(parts),
    )


def _issue_from_evidence_folder(parts: tuple[str, ...]) -> int | None:
    for part in parts:
        if "-issue-" in part and part.rsplit("-", 1)[-1].isdigit():
            return int(part.rsplit("-", 1)[-1])
    return None


def describe_artifact(path: str, root: Path) -> DecisionArtifact:
    record = json.loads((root / path).read_text(encoding="utf-8"))
    timestamp, field = _timestamp_of(record, root)
    return DecisionArtifact(
        path=path,
        sha256=sha256_file(root / path),
        role=_role(path),
        issue=_issue_of(path, record),
        decision=_decision_of(record),
        timestamp=timestamp,
        timestamp_field=field,
        adaptation_id=record.get("adaptation_id"),
        candidate_identity=record.get("candidate_identity"),
    )


def is_clear_acceptance(artifact: DecisionArtifact) -> bool:
    return (
        artifact.timestamp is not None
        and artifact.decision is not None
        and artifact.decision.startswith("accepted")
    )


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
