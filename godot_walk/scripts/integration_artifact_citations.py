"""Ledger citation check for module_poetics_v2 and integration proposal files.

Part of the #170 decision-file check: an accepted-metadata or proposal file in a
source's room folders is only valid when an event cites its exact path and hash.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_source_library import LIBRARY, sha256_file

ACCEPTED_EVENT = "module_metadata_accepted"
RECORDED_EVENT = "integration_proposal_recorded"


def _problem(source_id: str, path: str, digest: str, cited: set[tuple[str, str]], event: str) -> str | None:
    if (path, digest) in cited:
        return None
    if any(cited_path == path for cited_path, _ in cited):
        return f"{source_id}: {event} cites {path} but its bytes changed"
    return f"{source_id}: no {event} event cites {path}"


def uncited_integration_artifacts(
    source_id: str, events: list[dict[str, Any]], root: Path
) -> list[str]:
    """Problems for v2 metadata or proposal files that no matching event cites."""
    accepted = {
        (e["payload"].get("path"), e["payload"].get("sha256"))
        for e in events
        if e.get("event_type") == ACCEPTED_EVENT
    }
    recorded = {
        (item.get("path"), item.get("sha256"))
        for e in events
        if e.get("event_type") == RECORDED_EVENT
        for item in e["payload"].get("proposals", [])
    }
    rooms = root / LIBRARY / "sources" / source_id / "rooms"
    problems = []
    checks = (
        (rooms.glob("*/module_poetics_v2.json"), accepted, ACCEPTED_EVENT),
        (rooms.glob("*/integration_proposals/**/*.json"), recorded, RECORDED_EVENT),
    )
    for files, cited, event in checks:
        for file in sorted(files):
            if not file.is_file() or file.is_symlink():
                continue
            relative = file.relative_to(root).as_posix()
            found = _problem(source_id, relative, sha256_file(file), cited, event)
            if found:
                problems.append(found)
    return problems
