"""Run source-scoped, CPU-only intake stages and preserve operator gates."""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import module_integration_stages as integration
from module_metadata_accept import AcceptFlags, add_accept_flags, flags_from_args
from PIL import Image
from register_video_sources import append_event
from source_event_reconciliation import plan_reconciliation
from source_ingestion_policy import (
    ATTEMPT_LIMIT_EXTENSIONS,
    ONE_TIME_EXTENDED_LIMIT,
    ROOM_ID_PATTERN,
    WorkflowGateError,
    WorkflowState,
    evaluate_workflow,
    require_feedback,
    require_seed_selection,
    require_source_decision,
)
from video_adaptation_sources import extract_source_frames
from video_source_library import (
    LIBRARY,
    ROOT,
    SourceLibraryError,
    manifest_lineage_hashes,
    sha256_file,
    validate_index,
)

RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
SOURCE_ID_PATTERN = re.compile(r"^video-[0-9a-f]{16}$")


def load_source(
    source_id: str, root: Path = ROOT
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise SourceLibraryError("Unsafe source ID")
    entries = validate_index(root)
    entry = next((item for item in entries if item["source_id"] == source_id), None)
    if entry is None:
        raise SourceLibraryError(f"Unknown source ID: {source_id}")
    manifest_path = root / entry["manifest_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events = _read_events(root / LIBRARY / "sources" / source_id / "events.jsonl", root)
    _verify_event_identity(events, source_id, entry, root)
    return manifest, events, entry


def _verify_event_identity(
    events: list[dict[str, Any]],
    source_id: str,
    entry: dict[str, Any],
    root: Path,
) -> None:
    manifest_hashes = manifest_lineage_hashes(entry, root)
    for event in events:
        if event.get("source_id") not in (None, source_id):
            raise SourceLibraryError("Event belongs to a different source")
        if event.get("source_video_sha256") not in (None, entry["source_sha256"]):
            raise SourceLibraryError("Event is stale for the registered source video")
        if event.get("source_manifest_sha256") not in (None, *manifest_hashes):
            raise SourceLibraryError(
                "Event is stale for the registered source manifest"
            )


def _read_events(path: Path, root: Path) -> list[dict[str, Any]]:
    result = []
    _reject_symlink_components(path, root)
    with path.open("r", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        lines = stream.read().splitlines()
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise SourceLibraryError(
                "Source event log contains invalid JSON"
            ) from error
        if event.get("sequence") != line_number:
            raise SourceLibraryError("Source event sequence is not contiguous")
        result.append(event)
    return result


def source_status(source_id: str, root: Path = ROOT) -> dict[str, Any]:
    manifest, events, entry = load_source(source_id, root)
    state = evaluate_workflow(manifest, events)
    return {
        "source_id": source_id,
        "source_path": entry["source_path"],
        "source_sha256": entry["source_sha256"],
        "source_manifest_path": entry["manifest_path"],
        "source_manifest_sha256": entry["manifest_sha256"],
        "worker_output_root": f"{LIBRARY.as_posix()}/sources/{source_id}",
        "source_decision": state.source_decision,
        "selected_seed": state.selected_seed,
        "attempts_used": state.attempts_used,
        "attempt_limit": state.attempt_limit,
        "awaiting_feedback": state.awaiting_feedback,
        "consecutive_no_improvement": state.consecutive_no_improvement,
        "stopped_reason": state.stopped_reason,
        "can_start_attempt": state.can_start_attempt,
        "manual_fallback_allowed": state.manual_fallback_allowed,
        "next_worker_actions": _next_worker_actions(state)
        + integration.available_stages(source_id, events, root),
    }


def _next_worker_actions(state: WorkflowState) -> list[str]:
    if state.source_decision is None:
        return ["review-source"]
    if state.source_decision == "reject":
        return []
    if state.awaiting_feedback:
        return ["feedback"]
    if state.selected_seed is None:
        return ["extract-frames", "select-seed"]
    if state.can_start_attempt:
        return ["run_source_hunyuan.py"]
    if state.manual_fallback_allowed:
        return ["manual-fallback"]
    return []


def record_source_review(
    source_id: str, decision: str, rationale: str, root: Path = ROOT
) -> None:
    require_source_decision(decision, rationale)
    with _source_lock(source_id, root):
        _, events, entry = load_source(source_id, root)
        prior = [
            event
            for event in events
            if event["event_type"] == "source_suitability_decision"
        ]
        payload = {
            "decision": decision,
            "rationale": rationale.strip(),
            "source_video_sha256": entry["source_sha256"],
        }
        if prior:
            payload["supersedes_sequence"] = prior[-1]["sequence"]
        append_event(source_id, "source_suitability_decision", payload, root)


@contextmanager
def _source_lock(source_id: str, root: Path) -> Iterator[None]:
    if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise SourceLibraryError("Unsafe source ID")
    path = root / LIBRARY / "sources" / source_id / ".worker.lock"
    _reject_symlink_components(path, root)
    if not path.parent.is_dir():
        raise SourceLibraryError("Cannot claim an unregistered source folder")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise WorkflowGateError(
                f"Source {source_id} is already claimed by another worker"
            ) from error
        yield
    finally:
        os.close(descriptor)


def extract_frames(
    source_id: str, run_id: str, indices: list[int], root: Path = ROOT
) -> Path:
    _validate_run_id(run_id)
    with _source_lock(source_id, root):
        manifest, events, entry = load_source(source_id, root)
        state = evaluate_workflow(manifest, events)
        if state.source_decision not in {"proceed", "proceed_with_limitations"}:
            raise WorkflowGateError(
                "Operator must approve source suitability before frame extraction"
            )
        source_path = entry["source_path"]
        output = f"{LIBRARY.as_posix()}/sources/{source_id}/frames/{run_id}"
        output_path = root / output
        if output_path.exists() or output_path.is_symlink():
            raise FileExistsError(f"Refusing to overwrite frame batch: {output}")
        source_file = root / source_path
        source_hash = sha256_file(source_file)
        if source_hash != entry["source_sha256"]:
            raise SourceLibraryError("Source hash changed before frame extraction")
        receipt = extract_source_frames(source_path, indices, output)
        if sha256_file(source_file) != source_hash:
            raise SourceLibraryError("Source hash changed during frame extraction")
        append_event(
            source_id,
            "direct_frame_batch_extracted",
            {
                "run_id": run_id,
                "source_video_sha256": source_hash,
                "extraction_manifest": receipt.relative_to(root).as_posix(),
                "extraction_manifest_sha256": sha256_file(receipt),
            },
            root,
        )
    return receipt


def _validate_run_id(run_id: str) -> None:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise SourceLibraryError("Run ID must be a lowercase alphanumeric slug")


def _direct_frame_record(
    source_id: str,
    frame_path: str,
    frame_id: str,
    source_manifest: dict[str, Any],
    events: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    source_folder = (LIBRARY / "sources" / source_id / "frames").as_posix() + "/"
    relative = PurePosixPath(frame_path)
    if (
        not frame_path.startswith(source_folder)
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in frame_path.split("/"))
        or "\\" in frame_path
    ):
        raise SourceLibraryError("Seed frame must be inside this source's frame folder")
    frame = root.joinpath(*relative.parts)
    _reject_symlink_components(root / source_folder, root)
    resolved_frame = frame.resolve(strict=False)
    if (
        not resolved_frame.is_relative_to(root.resolve())
        or not frame.is_file()
        or frame.is_symlink()
    ):
        raise SourceLibraryError("Selected source frame is missing or unsafe")
    manifests = sorted((root / source_folder).glob("*/extraction_manifest.json"))
    for manifest_path in manifests:
        _reject_symlink_components(manifest_path, root)
        manifest_relative = manifest_path.relative_to(root).as_posix()
        manifest_hash = sha256_file(manifest_path)
        if not _has_extraction_event(events, manifest_relative, manifest_hash):
            continue
        extraction = json.loads(manifest_path.read_text(encoding="utf-8"))
        _verify_extraction_identity(extraction, source_manifest)
        for item in extraction.get("frames", []):
            if item["frame_id"] == frame_id and item["path"] == frame_path:
                if item["sha256"] != sha256_file(frame):
                    raise SourceLibraryError("Selected source frame hash changed")
                if (
                    item["decode_operation"]
                    != "direct_source_video_decode_no_resize_or_edit"
                ):
                    raise SourceLibraryError(
                        "Selected frame is not a direct source-video decode"
                    )
                with Image.open(frame) as image:
                    expected = source_manifest["canonical_video"]["metadata"]
                    if image.size != (expected["width"], expected["height"]):
                        raise SourceLibraryError("Selected seed frame was resized")
                item["extraction_manifest"] = manifest_relative
                item["extraction_manifest_sha256"] = manifest_hash
                return item
    raise SourceLibraryError(
        "Frame ID and path do not appear in a source extraction receipt"
    )


def _has_extraction_event(events: list[dict[str, Any]], path: str, digest: str) -> bool:
    return any(
        event["event_type"] == "direct_frame_batch_extracted"
        and event["payload"].get("extraction_manifest") == path
        and event["payload"].get("extraction_manifest_sha256") == digest
        for event in events
    )


def _verify_extraction_identity(
    extraction: dict[str, Any], source_manifest: dict[str, Any]
) -> None:
    source = source_manifest["canonical_video"]
    if (
        extraction.get("source_video") != source["path"]
        or extraction.get("source_video_sha256") != source["sha256"]
        or extraction.get("decoder")
        != "ffmpeg select by decoded zero-based frame index"
    ):
        raise SourceLibraryError(
            "Frame extraction is not bound to the exact source video"
        )


def _reject_symlink_components(path: Path, root: Path) -> None:
    repo = root.resolve()
    current = repo
    absolute = path.absolute()
    if not absolute.is_relative_to(repo):
        raise SourceLibraryError("Frame evidence path escapes the repository")
    for component in absolute.relative_to(repo).parts:
        current /= component
        if current.is_symlink():
            raise SourceLibraryError(f"Frame evidence path uses a symlink: {current}")


def select_seed(
    source_id: str, frame_id: str, frame_path: str, root: Path = ROOT
) -> None:
    with _source_lock(source_id, root):
        manifest, events, entry = load_source(source_id, root)
        state = evaluate_workflow(manifest, events)
        frame = _direct_frame_record(
            source_id, frame_path, frame_id, manifest, events, root
        )
        frame["source_video_sha256"] = entry["source_sha256"]
        frame["presentation_timestamp_seconds"] = _presentation_timestamp_seconds(
            root / manifest["canonical_video"]["path"],
            frame["index_zero_based"],
        )
        frame["presentation_timestamp_source"] = (
            "ffprobe frame.best_effort_timestamp_time"
        )
        require_seed_selection(state, frame)
        append_event(source_id, "seed_selected", frame, root)


def authorize_room_attempt(
    source_id: str, room_id: str, rationale: str, root: Path = ROOT
) -> None:
    if not isinstance(room_id, str) or ROOM_ID_PATTERN.fullmatch(room_id) is None:
        raise WorkflowGateError("Room ID must be a lowercase hyphenated slug")
    if not isinstance(rationale, str) or not rationale.strip():
        raise WorkflowGateError("Room-attempt authorization requires a rationale")
    with _source_lock(source_id, root):
        manifest, events, entry = load_source(source_id, root)
        state = evaluate_workflow(manifest, events)
        accepted = _latest_accepted_room_event(events)
        if accepted is None or state.stopped_reason != _accepted_room_reason(accepted):
            raise WorkflowGateError(
                "A cleanly accepted room and no other stop condition are required"
            )
        seed_event = _latest_event(events, "seed_selected")
        if seed_event is None or seed_event[0] <= accepted[0]:
            raise WorkflowGateError(
                "Select a new direct-source seed after the accepted room"
            )
        if state.attempt_limit - state.attempts_used != 1 or state.awaiting_feedback:
            raise WorkflowGateError(
                "Room authorization requires exactly one unused invocation and no pending review"
            )
        seed = _verified_room_seed(
            source_id, manifest, events, state.selected_seed, entry, root
        )
        append_event(
            source_id,
            "hunyuan_room_attempt_authorized",
            {
                "schema_version": 1,
                "room_id": room_id,
                "scope": "one_new_room_panorama",
                "attempt_id": f"attempt-{state.attempts_used + 1:03d}",
                "seed_frame": seed,
                "authorization_source": "explicit_operator_instruction",
                "rationale": rationale.strip(),
            },
            root,
        )
        authorized = evaluate_workflow(manifest, load_source(source_id, root)[1])
        if not authorized.can_start_attempt:
            raise WorkflowGateError(
                "Recorded room authorization did not unlock the approved attempt"
            )


def _verified_room_seed(
    source_id: str,
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
    seed: dict[str, Any] | None,
    entry: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    if (
        not isinstance(seed, dict)
        or not isinstance(seed.get("path"), str)
        or not isinstance(seed.get("frame_id"), str)
        or seed.get("source_video_sha256") != entry["source_sha256"]
    ):
        raise WorkflowGateError("The selected room seed is stale for this source")
    verified = _direct_frame_record(
        source_id, seed["path"], seed["frame_id"], manifest, events, root
    )
    required_fields = (
        "frame_id",
        "index_zero_based",
        "path",
        "sha256",
        "decode_operation",
        "extraction_manifest",
        "extraction_manifest_sha256",
    )
    if any(seed.get(key) != verified.get(key) for key in required_fields):
        raise SourceLibraryError("Selected room seed no longer matches its extraction")
    return seed


def _latest_accepted_room_event(
    events: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]] | None:
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if (
            event["event_type"] == "room_candidate_reviewed"
            and event["payload"].get("decision") == "accepted"
        ):
            return index, event["payload"]
    return None


def _latest_event(
    events: list[dict[str, Any]], event_type: str
) -> tuple[int, dict[str, Any]] | None:
    for index in range(len(events) - 1, -1, -1):
        if events[index]["event_type"] == event_type:
            return index, events[index]["payload"]
    return None


def _accepted_room_reason(room_event: tuple[int, dict[str, Any]]) -> str:
    adaptation_id = room_event[1].get("adaptation_id", "accepted candidate")
    return f"operator accepted room candidate {adaptation_id}; panorama loop complete"


def _presentation_timestamp_seconds(video_path: Path, frame_index: int) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    timestamps = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if frame_index >= len(timestamps):
        raise SourceLibraryError("ffprobe did not return a PTS for the selected frame")
    try:
        value = float(timestamps[frame_index])
    except ValueError as error:
        raise SourceLibraryError("ffprobe returned an invalid frame PTS") from error
    if not math.isfinite(value) or value < 0:
        raise SourceLibraryError("ffprobe returned a non-finite or negative frame PTS")
    return value


def record_operator_feedback(
    source_id: str,
    attempt_id: str,
    improvement: str,
    reason: str,
    failure_mode: str | None = None,
    plausible_next_step: bool | None = None,
    root: Path = ROOT,
) -> None:
    with _source_lock(source_id, root):
        _, events, _ = load_source(source_id, root)
        started = any(
            event["event_type"] == "hunyuan_attempt_started"
            and event["payload"].get("attempt_id") == attempt_id
            for event in events
        )
        finished = any(
            event["event_type"] == "hunyuan_attempt_result"
            and event["payload"].get("attempt_id") == attempt_id
            for event in events
        )
        reviewed = any(
            event["event_type"] == "hunyuan_operator_feedback"
            and event["payload"].get("attempt_id") == attempt_id
            for event in events
        )
        if not started or not finished or reviewed:
            raise WorkflowGateError(
                "Feedback must review one finished, unreviewed attempt"
            )
        require_feedback(improvement, reason, failure_mode, plausible_next_step)
        append_event(
            source_id,
            "hunyuan_operator_feedback",
            {
                "attempt_id": attempt_id,
                "improvement": improvement,
                "reason": reason.strip(),
                "failure_mode": failure_mode,
                "plausible_next_step": plausible_next_step,
            },
            root,
        )


def record_budget_extension(
    source_id: str, new_limit: int, rationale: str, root: Path = ROOT
) -> None:
    if not rationale.strip():
        raise WorkflowGateError(
            "A per-source attempt extension needs an explicit rationale"
        )
    with _source_lock(source_id, root):
        manifest, events, _ = load_source(source_id, root)
        state = evaluate_workflow(manifest, events)
        expected_limit = next(
            (
                after
                for before, after, _ in ATTEMPT_LIMIT_EXTENSIONS
                if before == state.attempt_limit
            ),
            None,
        )
        if (
            expected_limit is None
            or new_limit != expected_limit
            or state.attempts_used != state.attempt_limit
            or state.awaiting_feedback
            or state.stopped_reason != "per-source Hunyuan invocation cap reached"
        ):
            raise WorkflowGateError(
                "Budget extension requires feedback-complete exhaustion of the current cap"
            )
        additional = new_limit - state.attempt_limit
        append_event(
            source_id,
            "hunyuan_budget_extension_approved",
            {
                "previous_limit": state.attempt_limit,
                "new_limit": new_limit,
                "additional_invocations": additional,
                "authorization_source": "explicit_operator_instruction",
                "rationale": rationale.strip(),
            },
            root,
        )


def record_preflight_retry_authorization(
    source_id: str, rationale: str, root: Path = ROOT
) -> None:
    if not rationale.strip():
        raise WorkflowGateError("A preflight retry requires an operator rationale")
    with _source_lock(source_id, root):
        manifest, events, _ = load_source(source_id, root)
        state = evaluate_workflow(manifest, events)
        blocked_events = [
            event
            for event in events
            if event["event_type"] == "hunyuan_preflight_blocked"
        ]
        if (
            state.attempt_limit != ONE_TIME_EXTENDED_LIMIT
            or state.attempts_used != state.attempt_limit - 1
            or state.awaiting_feedback
            or not state.selected_seed
            or not state.stopped_reason
            or not state.stopped_reason.startswith("GPU resource preflight blocked:")
            or not blocked_events
            or any(
                event["event_type"] == "hunyuan_preflight_retry_approved"
                for event in events
            )
        ):
            raise WorkflowGateError(
                "A preflight retry requires one unused final slot and a terminal resource block"
            )
        blocked = blocked_events[-1]
        if any(
            event["event_type"] == "hunyuan_attempt_started"
            and event.get("sequence", 0) > blocked.get("sequence", 0)
            for event in events
        ):
            raise WorkflowGateError("The blocked slot already started an inference")
        receipt = _verified_blocked_receipt(
            source_id, blocked, state.selected_seed, root
        )
        retry_attempt_id = f"attempt-{state.attempt_limit:03d}-retry-001"
        retry_dir = (
            root / LIBRARY / "sources" / source_id / "hunyuan" / retry_attempt_id
        )
        _reject_symlink_components(retry_dir, root)
        if retry_dir.exists():
            raise FileExistsError(f"Refusing to overwrite retry evidence: {retry_dir}")
        append_event(
            source_id,
            "hunyuan_preflight_retry_approved",
            {
                "blocked_event_sequence": blocked["sequence"],
                "guard_receipt": receipt,
                "retry_attempt_id": retry_attempt_id,
                "authorization_source": "explicit_operator_instruction",
                "rationale": rationale.strip(),
            },
            root,
        )
        updated = evaluate_workflow(manifest, load_source(source_id, root)[1])
        if not updated.can_start_attempt:
            raise WorkflowGateError(
                "Recorded retry authorization did not unlock the unused slot"
            )


def _verified_blocked_receipt(
    source_id: str,
    blocked: dict[str, Any],
    selected_seed: dict[str, Any],
    root: Path,
) -> dict[str, str]:
    receipt = blocked["payload"].get("guard_receipt")
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        raise WorkflowGateError("Blocked event has no verifiable guard receipt")
    expected_path = (
        f"{LIBRARY.as_posix()}/sources/{source_id}/hunyuan/attempt-004/gpu_guard.json"
    )
    if receipt["path"] != expected_path:
        raise WorkflowGateError(
            "Blocked guard receipt is not the recorded fourth attempt"
        )
    receipt_path = root / receipt["path"]
    _reject_symlink_components(receipt_path, root)
    if (
        not receipt_path.is_file()
        or receipt.get("sha256") != sha256_file(receipt_path)
        or receipt_path.parent.name != "attempt-004"
    ):
        raise WorkflowGateError("Blocked guard receipt is missing or has changed")
    record = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        record.get("status") != "blocked"
        or record.get("source_id") != source_id
        or record.get("attempt_id") != "attempt-004"
    ):
        raise WorkflowGateError(
            "Guard receipt does not describe the fourth blocked attempt"
        )
    config_path = receipt_path.parent / "attempt_config.json"
    _reject_symlink_components(config_path, root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        config.get("source_id") != source_id
        or config.get("attempt_id") != "attempt-004"
        or config.get("seed_frame", {}).get("sha256") != selected_seed.get("sha256")
    ):
        raise WorkflowGateError("Blocked attempt configuration is inconsistent")
    return receipt


def record_manual_fallback(
    source_id: str,
    choice: str,
    rationale: str,
    root: Path = ROOT,
    operator_authorized: bool = False,
) -> None:
    if choice not in {"proceed_manual", "reject_source"} or not rationale.strip():
        raise WorkflowGateError(
            "Manual fallback requires an explicit choice and rationale"
        )
    with _source_lock(source_id, root):
        manifest, events, _ = load_source(source_id, root)
        state = evaluate_workflow(manifest, events)
        if state.awaiting_feedback:
            raise WorkflowGateError(
                "Review the completed Hunyuan result before manual fallback"
            )
        if not state.manual_fallback_allowed and not operator_authorized:
            raise WorkflowGateError(
                "Manual fallback is not yet authorized by workflow state"
            )
        if operator_authorized and (
            state.source_decision not in {"proceed", "proceed_with_limitations"}
            or state.selected_seed is None
            or state.attempts_used == 0
        ):
            raise WorkflowGateError(
                "Operator-directed early fallback requires a reviewed source, seed, and attempt"
            )
        payload = {"choice": choice, "rationale": rationale.strip()}
        if operator_authorized and not state.manual_fallback_allowed:
            payload["authorization_source"] = "explicit_operator_instruction"
        append_event(
            source_id,
            "manual_fallback_decision",
            payload,
            root,
        )


def reconcile_historical(source_id: str, root: Path = ROOT) -> list[int]:
    """Append events for decision files no event references; safe to rerun."""
    with _source_lock(source_id, root):
        manifest, events, _ = load_source(source_id, root)
        plan = plan_reconciliation(source_id, manifest, events, root)
        first_sequence = len(events) + 1
        for event_type, payload in plan:
            append_event(source_id, event_type, payload, root)
    return list(range(first_sequence, first_sequence + len(plan)))


def derive_module_metadata(source_id: str, room_id: str, root: Path = ROOT) -> int | None:
    """Link the mechanical module_poetics draft to the ledger; None when already linked."""
    with _source_lock(source_id, root):
        _, events, _ = load_source(source_id, root)
        payload = integration.plan_derive(source_id, room_id, events, root)
        if payload is not None:
            append_event(source_id, "module_metadata_derived", payload, root)
            return len(events) + 1
    return None


def accept_module_metadata(
    source_id: str, room_id: str, flags: AcceptFlags, root: Path = ROOT
) -> int:
    """Operator step: write module_poetics_v2.json and log module_metadata_accepted."""
    with _source_lock(source_id, root):
        _, events, _ = load_source(source_id, root)
        payload = integration.plan_accept(source_id, room_id, flags, events, root)
        append_event(source_id, "module_metadata_accepted", payload, root)
        return len(events) + 1


def propose_integrations(
    source_id: str, room_id: str, maps: list[Path], root: Path = ROOT
) -> list[int]:
    """Write integration proposals per map and log one event for each new map."""
    with _source_lock(source_id, root):
        _, events, _ = load_source(source_id, root)
        payloads = integration.plan_propose(source_id, room_id, maps, events, root)
        for payload in payloads:
            append_event(source_id, "integration_proposal_recorded", payload, root)
        return list(range(len(events) + 1, len(events) + 1 + len(payloads)))


def decide_integration(
    source_id: str, proposal: Path, choice: str, reason: str, root: Path = ROOT
) -> int:
    """Operator step: log the choice for one recorded proposal; changes nothing else."""
    with _source_lock(source_id, root):
        _, events, _ = load_source(source_id, root)
        payload = integration.plan_decide(source_id, proposal, choice, reason, events, root)
        append_event(source_id, "integration_proposal_decided", payload, root)
        return len(events) + 1


def _indices(value: str) -> list[int]:
    try:
        values = [int(part) for part in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Frame indices must be comma-separated integers"
        ) from error
    if not values or len(values) != len(set(values)) or min(values) < 0:
        raise argparse.ArgumentTypeError(
            "Frame indices must be unique nonnegative integers"
        )
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("source_id")
    review_parser = commands.add_parser("review-source")
    review_parser.add_argument("source_id")
    review_parser.add_argument(
        "--decision",
        choices=("proceed", "proceed_with_limitations", "reject"),
        required=True,
    )
    review_parser.add_argument("--reason", required=True)
    extract_parser = commands.add_parser("extract-frames")
    extract_parser.add_argument("source_id")
    extract_parser.add_argument("--run-id", required=True)
    extract_parser.add_argument("--indices", required=True, type=_indices)
    seed_parser = commands.add_parser("select-seed")
    seed_parser.add_argument("source_id")
    seed_parser.add_argument("--frame-id", required=True)
    seed_parser.add_argument("--path", required=True)
    room_attempt_parser = commands.add_parser("authorize-room-attempt")
    room_attempt_parser.add_argument("source_id")
    room_attempt_parser.add_argument("--room-id", required=True)
    room_attempt_parser.add_argument("--reason", required=True)
    feedback_parser = commands.add_parser("feedback")
    feedback_parser.add_argument("source_id")
    feedback_parser.add_argument("--attempt-id", required=True)
    feedback_parser.add_argument(
        "--improvement",
        choices=("improved", "no_improvement", "uncertain"),
        required=True,
    )
    feedback_parser.add_argument("--reason", required=True)
    feedback_parser.add_argument("--failure-mode")
    feedback_parser.add_argument("--plausible-next-step", choices=("yes", "no"))
    budget_parser = commands.add_parser("authorize-budget-extension")
    budget_parser.add_argument("source_id")
    budget_parser.add_argument("--new-limit", type=int, required=True)
    budget_parser.add_argument("--reason", required=True)
    retry_parser = commands.add_parser("authorize-preflight-retry")
    retry_parser.add_argument("source_id")
    retry_parser.add_argument("--reason", required=True)
    fallback_parser = commands.add_parser("manual-fallback")
    fallback_parser.add_argument("source_id")
    fallback_parser.add_argument(
        "--choice", choices=("proceed_manual", "reject_source"), required=True
    )
    fallback_parser.add_argument("--reason", required=True)
    fallback_parser.add_argument(
        "--operator-directed",
        action="store_true",
        help="Record an explicit operator choice to stop after the reviewed attempt",
    )
    reconcile_parser = commands.add_parser(
        "reconcile-historical",
        help="Append never-backdated events for unreferenced decision files",
    )
    reconcile_parser.add_argument("source_id")
    derive_parser = commands.add_parser(
        "derive-module-metadata",
        help="Link the mechanical module_poetics draft of an admitted room to the ledger",
    )
    derive_parser.add_argument("source_id")
    derive_parser.add_argument("--room-id", required=True)
    accept_parser = commands.add_parser(
        "accept-module-metadata",
        help="Operator only: write module_poetics_v2.json from the derived draft",
    )
    accept_parser.add_argument("source_id")
    accept_parser.add_argument("--room-id", required=True)
    add_accept_flags(accept_parser)
    propose_parser = commands.add_parser(
        "propose-integrations",
        help="Mechanically fit an admitted room against generative-map cells",
    )
    propose_parser.add_argument("source_id")
    propose_parser.add_argument("--room-id", required=True)
    propose_parser.add_argument("--map", type=Path, action="append", required=True, dest="maps")
    decide_parser = commands.add_parser(
        "decide-integration",
        help="Operator only: record accept/reject/keep_standalone for a proposal",
    )
    decide_parser.add_argument("source_id")
    decide_parser.add_argument("--proposal", type=Path, required=True)
    decide_parser.add_argument(
        "--choice", choices=("accept", "reject", "keep_standalone"), required=True
    )
    decide_parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.action == "status":
        print(json.dumps(source_status(args.source_id), indent=2))
    elif args.action == "review-source":
        record_source_review(args.source_id, args.decision, args.reason)
    elif args.action == "extract-frames":
        print(
            extract_frames(args.source_id, args.run_id, args.indices).relative_to(ROOT)
        )
    elif args.action == "select-seed":
        select_seed(args.source_id, args.frame_id, args.path)
    elif args.action == "authorize-room-attempt":
        authorize_room_attempt(args.source_id, args.room_id, args.reason)
    elif args.action == "feedback":
        next_step = (
            None
            if args.plausible_next_step is None
            else args.plausible_next_step == "yes"
        )
        record_operator_feedback(
            args.source_id,
            args.attempt_id,
            args.improvement,
            args.reason,
            args.failure_mode,
            next_step,
        )
    elif args.action == "authorize-budget-extension":
        record_budget_extension(args.source_id, args.new_limit, args.reason)
    elif args.action == "authorize-preflight-retry":
        record_preflight_retry_authorization(args.source_id, args.reason)
    elif args.action == "manual-fallback":
        record_manual_fallback(
            args.source_id,
            args.choice,
            args.reason,
            operator_authorized=args.operator_directed,
        )
    elif args.action == "reconcile-historical":
        sequences = reconcile_historical(args.source_id)
        print(json.dumps({"appended_sequences": sequences}))
    elif args.action == "derive-module-metadata":
        sequence = derive_module_metadata(args.source_id, args.room_id)
        print(json.dumps({"appended_sequence": sequence}))
    elif args.action == "accept-module-metadata":
        flags = flags_from_args(args)
        print(json.dumps({"appended_sequence": accept_module_metadata(args.source_id, args.room_id, flags)}))
    elif args.action == "propose-integrations":
        sequences = propose_integrations(args.source_id, args.room_id, args.maps)
        print(json.dumps({"appended_sequences": sequences}))
    elif args.action == "decide-integration":
        sequence = decide_integration(args.source_id, args.proposal, args.choice, args.reason)
        print(json.dumps({"appended_sequence": sequence}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
