#!/usr/bin/env python3
"""Track pipeline stage state for resumability and provenance.

Each stage records its input hash, output hash, and status in a JSON file
inside the scene directory. Before running a stage, the pipeline checks
whether a previous record exists with matching hashes; if so, the stage is
skipped. This gives:

* **Resumability** — unchanged stages are skipped after an interruption.
* **Invalidation** — changing an input or setting changes the hash, so the
  stage re-runs.
* **Provenance** — every stage records the hashes of its inputs and outputs.

The state file is ``pipeline_state.json`` inside the scene directory. It is
written atomically (temp file + rename) so an interrupted write cannot corrupt
the record.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = "pipeline_state.json"


@dataclass
class StageRecord:
    """One stage's recorded state."""

    stage: str
    input_hash: str
    output_hash: str
    timestamp: str
    status: str  # "success" | "failed" | "skipped"
    log_path: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
            "status": self.status,
            "log_path": self.log_path,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StageRecord":
        return cls(
            stage=data["stage"],
            input_hash=data["input_hash"],
            output_hash=data["output_hash"],
            timestamp=data["timestamp"],
            status=data["status"],
            log_path=data.get("log_path", ""),
            detail=data.get("detail", ""),
        )


def file_hash(path: Path) -> str:
    """Return the SHA-256 of a file, or ``""`` if it does not exist."""
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_hash(*items: str) -> str:
    """Return a stable SHA-256 over a sequence of strings.

    Used to hash settings and other non-file inputs alongside file hashes.
    """
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def load_state(scene_dir: Path) -> dict[str, StageRecord]:
    """Load the pipeline state file, returning an empty dict if absent."""
    path = scene_dir / STATE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    records: dict[str, StageRecord] = {}
    for stage_name, record_data in data.items():
        try:
            records[stage_name] = StageRecord.from_dict(record_data)
        except (KeyError, TypeError):
            continue
    return records


def save_state(scene_dir: Path, records: dict[str, StageRecord]) -> None:
    """Write the state file atomically."""
    path = scene_dir / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {name: record.to_dict() for name, record in records.items()}
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".pipeline_state.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def should_skip(
    scene_dir: Path,
    stage_name: str,
    input_hash: str,
) -> StageRecord | None:
    """Return the existing record if the stage can be skipped, else ``None``.

    A stage is skipped only when a previous record exists, its status is
    ``"success"``, and its input hash matches. A failed record never causes a
    skip — the stage must be retried.
    """
    records = load_state(scene_dir)
    record = records.get(stage_name)
    if record is None:
        return None
    if record.status != "success":
        return None
    if record.input_hash != input_hash:
        return None
    return record


def record_success(
    scene_dir: Path,
    stage_name: str,
    input_hash: str,
    output_hash: str,
    log_path: str = "",
    detail: str = "",
) -> StageRecord:
    """Record a successful stage and persist the state."""
    record = StageRecord(
        stage=stage_name,
        input_hash=input_hash,
        output_hash=output_hash,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="success",
        log_path=log_path,
        detail=detail,
    )
    records = load_state(scene_dir)
    records[stage_name] = record
    save_state(scene_dir, records)
    return record


def record_failure(
    scene_dir: Path,
    stage_name: str,
    input_hash: str,
    detail: str = "",
) -> StageRecord:
    """Record a failed stage and persist the state."""
    record = StageRecord(
        stage=stage_name,
        input_hash=input_hash,
        output_hash="",
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="failed",
        log_path="",
        detail=detail,
    )
    records = load_state(scene_dir)
    records[stage_name] = record
    save_state(scene_dir, records)
    return record


def stage_log_path(scene_dir: Path, stage_name: str) -> Path:
    """Return the log file path for a stage."""
    return scene_dir / "logs" / ("%s.log" % stage_name)
