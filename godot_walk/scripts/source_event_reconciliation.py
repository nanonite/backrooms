"""Link operator decision files to the append-only per-source event ledger.

Decision files (operator reviews, catalog admissions, accepted adaptations)
were sometimes written without a matching ledger event. This module finds those
files, plans never-backdated reconciliation events that cite them, and checks
that every such file is referenced by some event.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from source_decision_artifacts import (
    DecisionArtifact,
    describe_artifact,
    is_clear_acceptance,
    parse_timestamp,
)
from video_source_library import (
    LIBRARY,
    ROOT,
    SourceLibraryError,
    sha256_file,
    validate_index,
)

EVENT_RECONCILED = "historical_decision_reconciled"
EVENT_DEFERRED = "historical_decision_reconciliation_deferred"
DECISION_FILE_PATTERNS = (
    "operator_review.json",
    "catalog_admission_decision.json",
    "adaptation_*accepted*.json",
)
ROLE_ORDER = ("operator_review", "catalog_admission_decision", "accepted_adaptation")
LINK_WINDOW_SECONDS = 5.0
NO_APPROVAL_NOTE = (
    "Ledger backfill only. occurred_at_utc is the reconciliation time, not the "
    "decision time. No approval is created, changed or reopened."
)
DEFERRED_REASON = (
    "The file carries no decision timestamp of its own and cites no hash-verified "
    "operator record with one, so operator acceptance of this exact artifact is "
    "not independently attested. Pending operator confirmation."
)


def read_event_records(source_id: str, root: Path) -> list[dict[str, Any]]:
    path = root / LIBRARY / "sources" / source_id / "events.jsonl"
    if not path.is_file() or path.is_symlink():
        raise SourceLibraryError("Source event log is missing or unsafe")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def discover_decision_paths(
    source_id: str, manifest: dict[str, Any], root: Path
) -> list[str]:
    found = set()
    source_root = root / LIBRARY / "sources" / source_id
    for pattern in DECISION_FILE_PATTERNS:
        for path in (source_root / "rooms").glob(f"*/{pattern}"):
            if path.is_file() and not path.is_symlink():
                found.add(path.relative_to(root).as_posix())
    for room in manifest.get("room_adaptations", []):
        decision_path = room.get("decision_path")
        if isinstance(decision_path, str) and (root / decision_path).is_file():
            found.add(decision_path)
    return sorted(found)


def _string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


def referenced_paths(events: list[dict[str, Any]]) -> set[str]:
    return {
        text for event in events for text in _string_values(event.get("payload", {}))
    }


def stale_reconciliations(events: list[dict[str, Any]], root: Path) -> list[str]:
    stale = []
    for event in events:
        cited = event.get("payload", {}).get("reconciles")
        if not isinstance(cited, dict):
            continue
        artifact = root / str(cited.get("artifact_path", ""))
        if not artifact.is_file() or sha256_file(artifact) != cited.get(
            "artifact_sha256"
        ):
            stale.append(str(cited.get("artifact_path")))
    return stale


def unreferenced_decision_paths(
    source_id: str, manifest: dict[str, Any], events: list[dict[str, Any]], root: Path
) -> list[str]:
    referenced = referenced_paths(events)
    return [
        path
        for path in discover_decision_paths(source_id, manifest, root)
        if path not in referenced
    ]


def corresponding_sequence(
    artifact: DecisionArtifact, events: list[dict[str, Any]]
) -> int | None:
    original = parse_timestamp(artifact.timestamp) if artifact.timestamp else None
    if original is None or original.tzinfo is None:
        return None
    for event in events:
        payload = event.get("payload", {})
        occurred = parse_timestamp(event.get("occurred_at_utc", ""))
        if (
            event.get("event_type") == "room_candidate_reviewed"
            and payload.get("adaptation_id") == artifact.adaptation_id
            and payload.get("decision") == artifact.decision
            and occurred is not None
            and abs((occurred - original).total_seconds()) <= LINK_WINDOW_SECONDS
        ):
            return int(event["sequence"])
    return None


def reconciliation_payload(
    artifact: DecisionArtifact, events: list[dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    cited = {
        "issue": artifact.issue,
        "artifact_path": artifact.path,
        "artifact_sha256": artifact.sha256,
        "artifact_role": artifact.role,
        "original_decision": artifact.decision,
        "original_decision_timestamp": artifact.timestamp,
        "original_decision_timestamp_field": artifact.timestamp_field,
        "adaptation_id": artifact.adaptation_id,
        "candidate_identity": artifact.candidate_identity,
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "reconciles": cited,
        "registration_accepted": False,
        "scale_calibrated": False,
        "note": NO_APPROVAL_NOTE,
    }
    if is_clear_acceptance(artifact):
        cited["corresponds_to_sequence"] = corresponding_sequence(artifact, events)
        return EVENT_RECONCILED, payload
    payload["status"] = "not_reconciled_as_operator_decision"
    payload["reason"] = DEFERRED_REASON
    return EVENT_DEFERRED, payload


def _sort_key(artifact: DecisionArtifact) -> tuple[int, str, int, str]:
    parsed = parse_timestamp(artifact.timestamp) if artifact.timestamp else None
    role_rank = ROLE_ORDER.index(artifact.role) if artifact.role in ROLE_ORDER else 0
    if parsed is None:
        return (1, "", role_rank, artifact.path)
    return (0, parsed.replace(tzinfo=None).isoformat(), role_rank, artifact.path)


def plan_reconciliation(
    source_id: str,
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
    root: Path,
) -> list[tuple[str, dict[str, Any]]]:
    paths = unreferenced_decision_paths(source_id, manifest, events, root)
    artifacts = sorted((describe_artifact(path, root) for path in paths), key=_sort_key)
    return [reconciliation_payload(artifact, events) for artifact in artifacts]


def validate_decision_event_coverage(root: Path = ROOT) -> None:
    """Fail when a decision file has no event, or a reconciled file changed."""
    problems = []
    for entry in validate_index(root):
        source_id = entry["source_id"]
        manifest = json.loads(
            (root / entry["manifest_path"]).read_text(encoding="utf-8")
        )
        events = read_event_records(source_id, root)
        problems.extend(
            f"{source_id}: no event references {path}"
            for path in unreferenced_decision_paths(source_id, manifest, events, root)
        )
        problems.extend(
            f"{source_id}: reconciled artifact changed or missing: {path}"
            for path in stale_reconciliations(events, root)
        )
    if problems:
        raise SourceLibraryError("; ".join(problems))
