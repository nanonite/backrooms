"""Operator-gated state rules for each source's Hunyuan-first workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

DEFAULT_ATTEMPT_LIMIT = 3
ONE_TIME_EXTENDED_LIMIT = DEFAULT_ATTEMPT_LIMIT + 1
SECOND_EXTENDED_LIMIT = ONE_TIME_EXTENDED_LIMIT + 2
ATTEMPT_LIMIT_EXTENSIONS = (
    (DEFAULT_ATTEMPT_LIMIT, ONE_TIME_EXTENDED_LIMIT, 1),
    (ONE_TIME_EXTENDED_LIMIT, SECOND_EXTENDED_LIMIT, 2),
)
ALLOWED_SOURCE_DECISIONS = {"proceed", "proceed_with_limitations", "reject"}
ALLOWED_IMPROVEMENT = {"improved", "no_improvement", "uncertain"}
ROOM_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ATTEMPT_ID_PATTERN = re.compile(r"^attempt-\d{3}$")
RETRY_ATTEMPT_SUFFIX = "-retry-001"
RETRY_ATTEMPT_ID_PATTERN = re.compile(r"^attempt-(\d{3})-retry-(\d{3})$")
MAX_PREFLIGHT_RETRIES = 3


class WorkflowGateError(ValueError):
    """A worker attempted to cross an operator or safety checkpoint."""


@dataclass(frozen=True)
class WorkflowState:
    source_decision: str | None
    selected_seed: dict[str, Any] | None
    attempts_used: int
    attempt_limit: int
    awaiting_feedback: bool
    consecutive_no_improvement: int
    stopped_reason: str | None
    manual_fallback_allowed: bool

    @property
    def can_start_attempt(self) -> bool:
        return (
            self.source_decision in {"proceed", "proceed_with_limitations"}
            and self.selected_seed is not None
            and self.attempts_used < self.attempt_limit
            and not self.awaiting_feedback
            and self.stopped_reason is None
        )


def evaluate_workflow(
    manifest: dict[str, Any], events: list[dict[str, Any]]
) -> WorkflowState:
    policy = manifest.get("hunyuan", {})
    configured_limit = policy.get("policy_invocation_limit", DEFAULT_ATTEMPT_LIMIT)
    historical = policy.get("historical_invocations", 0)
    if (
        not isinstance(configured_limit, int)
        or isinstance(configured_limit, bool)
        or configured_limit != DEFAULT_ATTEMPT_LIMIT
    ):
        raise WorkflowGateError("Unsupported per-source Hunyuan invocation limit")
    if not isinstance(historical, int) or historical < 0:
        raise WorkflowGateError("Historical Hunyuan invocation count is invalid")
    limit = _effective_attempt_limit(configured_limit, historical, events)
    source_decision = _latest_value(events, "source_suitability_decision", "decision")
    selected_seed = _latest_payload(events, "seed_selected")
    attempt_state = _attempt_state(events, historical, limit)
    preflight_retries = _preflight_retry_state(events, historical, limit)
    blocked = _blocking_event(events, preflight_retries)
    manual_decision = _latest_value(events, "manual_fallback_decision", "choice")
    stop_reason = _stop_reason(
        source_decision, historical, limit, attempt_state, blocked, manual_decision
    )
    accepted_room = _room_candidate_accepted(events)
    if accepted_room:
        authorization = _room_attempt_authorization(
            events,
            accepted_room,
            selected_seed,
            historical,
            attempt_state["attempts_used"],
            limit,
            attempt_state["awaiting_feedback"],
        )
        if authorization == "absent":
            if stop_reason is None:
                stop_reason = _accepted_room_stop_reason(accepted_room)
        elif authorization == "consumed" and stop_reason is None:
            stop_reason = "authorized room panorama attempt already started"
    return WorkflowState(
        source_decision=source_decision,
        selected_seed=selected_seed,
        attempts_used=attempt_state["attempts_used"],
        attempt_limit=limit,
        awaiting_feedback=attempt_state["awaiting_feedback"],
        consecutive_no_improvement=attempt_state["consecutive_no_improvement"],
        stopped_reason=stop_reason,
        manual_fallback_allowed=(
            source_decision in {"proceed", "proceed_with_limitations"}
            and selected_seed is not None
            and _manual_fallback_allowed(
                attempt_state, limit, stop_reason, manual_decision, accepted_room
            )
        ),
    )


def _effective_attempt_limit(
    configured_limit: int, historical: int, events: list[dict[str, Any]]
) -> int:
    authorizations = [
        (index, event["payload"])
        for index, event in enumerate(events)
        if event["event_type"] == "hunyuan_budget_extension_approved"
    ]
    if len(authorizations) > len(ATTEMPT_LIMIT_EXTENSIONS):
        raise WorkflowGateError("Per-source attempt extension limit exceeded")
    limit = configured_limit
    for extension_index, (event_index, authorization) in enumerate(authorizations):
        previous, next_limit, addition = ATTEMPT_LIMIT_EXTENSIONS[extension_index]
        prefix = events[:event_index]
        starts = {
            event["payload"]["attempt_id"]
            for event in prefix
            if event["event_type"] == "hunyuan_attempt_started"
        }
        results = {
            event["payload"]["attempt_id"]
            for event in prefix
            if event["event_type"] == "hunyuan_attempt_result"
        }
        feedback = {
            event["payload"]["attempt_id"]
            for event in prefix
            if event["event_type"] == "hunyuan_operator_feedback"
        }
        numeric_limits = (
            authorization.get("previous_limit"),
            authorization.get("new_limit"),
            authorization.get("additional_invocations"),
        )
        if (
            any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in numeric_limits
            )
            or authorization.get("previous_limit") != previous
            or authorization.get("new_limit") != next_limit
            or authorization.get("additional_invocations") != addition
            or authorization.get("authorization_source")
            != "explicit_operator_instruction"
            or not isinstance(authorization.get("rationale"), str)
            or not authorization["rationale"].strip()
            or limit != previous
            or historical + len(starts) != previous
            or starts != results
            or starts != feedback
        ):
            raise WorkflowGateError(
                "Per-source budget extension is invalid or precedes completed feedback"
            )
        limit = next_limit
    return limit


def _latest_value(
    events: list[dict[str, Any]], event_type: str, key: str
) -> str | None:
    matches = [
        event["payload"].get(key)
        for event in events
        if event["event_type"] == event_type
    ]
    return matches[-1] if matches else None


def _latest_payload(
    events: list[dict[str, Any]], event_type: str
) -> dict[str, Any] | None:
    matches = [
        event["payload"] for event in events if event["event_type"] == event_type
    ]
    return matches[-1] if matches else None


def _room_candidate_accepted(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if (
            event["event_type"] == "room_candidate_reviewed"
            and event["payload"].get("decision") == "accepted"
        ):
            return event["payload"]
    return None


def _accepted_room_stop_reason(room: dict[str, Any]) -> str:
    adaptation_id = room.get("adaptation_id", "accepted candidate")
    return f"operator accepted room candidate {adaptation_id}; panorama loop complete"


def _room_attempt_authorization(
    events: list[dict[str, Any]],
    accepted_room: dict[str, Any],
    selected_seed: dict[str, Any] | None,
    historical: int,
    attempts_used: int,
    limit: int,
    awaiting_feedback: bool,
) -> str:
    authorizations = [
        (index, event)
        for index, event in enumerate(events)
        if event["event_type"] == "hunyuan_room_attempt_authorized"
    ]
    if not authorizations:
        return "absent"
    if len(authorizations) != 1:
        raise WorkflowGateError(
            "Only one post-acceptance room attempt may be authorized"
        )

    authorization_index, authorization = authorizations[0]
    accepted_index = _latest_accepted_room_index(events, accepted_room)
    seed_index = _latest_event_index(events, "seed_selected")
    payload = authorization["payload"]
    seed = payload.get("seed_frame")
    starts_before = sum(
        event["event_type"] == "hunyuan_attempt_started"
        for event in events[:authorization_index]
    )
    attempt_number = historical + starts_before + 1
    attempt_id = f"attempt-{attempt_number:03d}"
    if (
        authorization_index <= accepted_index
        or authorization_index <= seed_index
        or not isinstance(selected_seed, dict)
        or not isinstance(seed, dict)
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("room_id"), str)
        or ROOM_ID_PATTERN.fullmatch(payload["room_id"]) is None
        or payload.get("scope") != "one_new_room_panorama"
        or payload.get("authorization_source") != "explicit_operator_instruction"
        or payload.get("attempt_id") != attempt_id
        or seed != selected_seed
        or not isinstance(payload.get("rationale"), str)
        or not payload["rationale"].strip()
    ):
        raise WorkflowGateError("Post-acceptance room attempt authorization is invalid")

    starts = [
        event
        for event in events[authorization_index + 1 :]
        if event["event_type"] == "hunyuan_attempt_started"
    ]
    retry_authorizations = {
        event["payload"].get("retry_attempt_id")
        for event in events
        if event["event_type"] == "hunyuan_preflight_retry_approved"
    }
    allowed_attempt_ids = {attempt_id}
    candidate_retry_id = attempt_id
    for _ in range(MAX_PREFLIGHT_RETRIES):
        candidate_retry_id = next_retry_attempt_id(candidate_retry_id)
        if candidate_retry_id is None:
            break
        if candidate_retry_id in retry_authorizations:
            allowed_attempt_ids.add(candidate_retry_id)
    matching_starts = [
        event
        for event in starts
        if event["payload"].get("attempt_id") in allowed_attempt_ids
    ]
    if (
        any(event not in matching_starts for event in starts)
        or len(matching_starts) > 1
    ):
        raise WorkflowGateError("Authorized room attempt was bypassed or repeated")
    if matching_starts:
        if matching_starts[0]["payload"].get("seed_frame_sha256") != seed.get("sha256"):
            raise WorkflowGateError("Authorized attempt used a different source seed")
        return "consumed"
    if (
        attempt_number != limit
        or attempts_used != attempt_number - 1
        or awaiting_feedback
    ):
        raise WorkflowGateError(
            "Post-acceptance authorization must bind the single remaining attempt"
        )
    return "pending"


def _latest_accepted_room_index(
    events: list[dict[str, Any]], room: dict[str, Any]
) -> int:
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if (
            event["event_type"] == "room_candidate_reviewed"
            and event["payload"] is room
        ):
            return index
    raise WorkflowGateError("Accepted room decision is missing from the event ledger")


def _latest_event_index(events: list[dict[str, Any]], event_type: str) -> int:
    return max(
        (
            index
            for index, event in enumerate(events)
            if event["event_type"] == event_type
        ),
        default=-1,
    )


def _attempt_state(
    events: list[dict[str, Any]], historical: int, limit: int
) -> dict[str, Any]:
    starts = {
        event["payload"]["attempt_id"]: event["payload"]
        for event in events
        if event["event_type"] == "hunyuan_attempt_started"
    }
    results = _payloads_by_attempt(events, "hunyuan_attempt_result")
    feedback = _payloads_by_attempt(events, "hunyuan_operator_feedback")
    attempts_used = historical + len(starts)
    last_id = next(reversed(starts), None)
    awaiting = last_id is not None and (
        last_id not in results or last_id not in feedback
    )
    return {
        "attempts_used": attempts_used,
        "awaiting_feedback": awaiting,
        "consecutive_no_improvement": _count_trailing_no_improvement(feedback),
        "results": results,
        "feedback": feedback,
        "starts": starts,
        "failure_modes": _repeated_failure_modes(feedback),
        "last_id": last_id,
        "limit": limit,
    }


def _payloads_by_attempt(
    events: list[dict[str, Any]], event_type: str
) -> dict[str, dict[str, Any]]:
    return {
        event["payload"]["attempt_id"]: event["payload"]
        for event in events
        if event["event_type"] == event_type
    }


def _count_trailing_no_improvement(feedback: dict[str, dict[str, Any]]) -> int:
    count = 0
    for item in reversed(list(feedback.values())):
        if item["improvement"] != "no_improvement":
            break
        count += 1
    return count


def _repeated_failure_modes(feedback: dict[str, dict[str, Any]]) -> set[str]:
    modes: dict[str, int] = {}
    last_feedback: dict[str, dict[str, Any]] = {}
    for item in feedback.values():
        mode = item.get("failure_mode")
        if mode:
            modes[mode] = modes.get(mode, 0) + 1
            last_feedback[mode] = item
    return {
        mode
        for mode, count in modes.items()
        if count > 1 and last_feedback[mode].get("plausible_next_step") is False
    }


def _blocking_event(
    events: list[dict[str, Any]], authorized_sequences: set[int]
) -> str | None:
    for event in events:
        if event["event_type"] == "hunyuan_preflight_blocked" and (
            event.get("sequence") not in authorized_sequences
        ):
            reason = event["payload"].get("reason", "unspecified guard condition")
            return f"GPU resource preflight blocked: {reason}"
    return None


def _preflight_retry_state(
    events: list[dict[str, Any]], historical: int, limit: int
) -> set[int]:
    """Validate every retry authorization and return the blocked sequences it covers."""
    authorizations = [
        event
        for event in events
        if event["event_type"] == "hunyuan_preflight_retry_approved"
    ]
    if len(authorizations) > MAX_PREFLIGHT_RETRIES:
        raise WorkflowGateError("Per-source preflight retry limit exceeded")
    authorized_sequences: set[int] = set()
    used_retry_ids: set[str] = set()
    for authorization in authorizations:
        _validate_preflight_retry_authorization(
            events,
            authorization,
            authorized_sequences,
            used_retry_ids,
            historical,
            limit,
        )
        authorized_sequences.add(authorization["payload"]["blocked_event_sequence"])
        used_retry_ids.add(authorization["payload"]["retry_attempt_id"])
    return authorized_sequences


def _validate_preflight_retry_authorization(
    events: list[dict[str, Any]],
    authorization: dict[str, Any],
    authorized_sequences: set[int],
    used_retry_ids: set[str],
    historical: int,
    limit: int,
) -> None:
    payload = authorization["payload"]
    blocked_sequence = payload.get("blocked_event_sequence")
    authorization_sequence = authorization.get("sequence", 0)
    blocked = _blocked_event_at(events, blocked_sequence)
    blocked_id = blocked_attempt_id(blocked)
    retry_id = payload.get("retry_attempt_id")
    expected_id = next_retry_attempt_id(blocked_id)
    slot_number = _attempt_slot_number(blocked_id)
    starts_before = sum(
        1
        for event in events
        if event["event_type"] == "hunyuan_attempt_started"
        and event.get("sequence", 0) < authorization_sequence
    )
    if (
        blocked is None
        or not _is_sequence_number(blocked_sequence)
        or not _is_sequence_number(authorization_sequence)
        or blocked_id is None
        or expected_id is None
        or slot_number != historical + starts_before + 1
        or slot_number > limit
        or authorization_sequence <= blocked_sequence
        or blocked_sequence in authorized_sequences
        or retry_id != expected_id
        or retry_id in used_retry_ids
        or _retry_ordinal(retry_id) > MAX_PREFLIGHT_RETRIES
        or payload.get("authorization_source") != "explicit_operator_instruction"
        or payload.get("guard_receipt") != blocked["payload"].get("guard_receipt")
        or not isinstance(payload.get("rationale"), str)
        or not payload["rationale"].strip()
        or _blocked_event_superseded(events, blocked_sequence, authorization_sequence)
        or _started_between(events, blocked_sequence, authorization_sequence)
        or _attempt_started_for(events, blocked_id)
    ):
        raise WorkflowGateError("Preflight retry authorization is invalid")


def _blocked_event_at(
    events: list[dict[str, Any]], sequence: Any
) -> dict[str, Any] | None:
    if not _is_sequence_number(sequence):
        return None
    return next(
        (
            event
            for event in events
            if event["event_type"] == "hunyuan_preflight_blocked"
            and event.get("sequence") == sequence
        ),
        None,
    )


def _is_sequence_number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _blocked_event_superseded(
    events: list[dict[str, Any]], blocked_sequence: int, authorization_sequence: int
) -> bool:
    return any(
        event["event_type"] == "hunyuan_preflight_blocked"
        and blocked_sequence < event.get("sequence", 0) < authorization_sequence
        for event in events
    )


def _started_between(
    events: list[dict[str, Any]], blocked_sequence: int, authorization_sequence: int
) -> bool:
    return any(
        event["event_type"] == "hunyuan_attempt_started"
        and blocked_sequence < event.get("sequence", 0) < authorization_sequence
        for event in events
    )


def _attempt_started_for(events: list[dict[str, Any]], attempt_id: str) -> bool:
    return any(
        event["event_type"] == "hunyuan_attempt_started"
        and event["payload"].get("attempt_id") == attempt_id
        for event in events
    )


def _attempt_slot_number(attempt_id: str | None) -> int | None:
    if attempt_id is None:
        return None
    retry_match = RETRY_ATTEMPT_ID_PATTERN.fullmatch(attempt_id)
    if retry_match is not None:
        return int(retry_match.group(1))
    if ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is not None:
        return int(attempt_id.removeprefix("attempt-"))
    return None


def _retry_ordinal(attempt_id: Any) -> int:
    if not isinstance(attempt_id, str):
        return 0
    retry_match = RETRY_ATTEMPT_ID_PATTERN.fullmatch(attempt_id)
    return int(retry_match.group(2)) if retry_match is not None else 0


def blocked_attempt_id(blocked: dict[str, Any] | None) -> str | None:
    if blocked is None:
        return None
    receipt = blocked["payload"].get("guard_receipt")
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        return None
    attempt_id = PurePosixPath(receipt["path"]).parent.name
    if (
        ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is not None
        or RETRY_ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is not None
    ):
        return attempt_id
    return None


def next_retry_attempt_id(attempt_id: str | None) -> str | None:
    """Return the next bounded retry id for a blocked attempt, or None."""
    if attempt_id is None:
        return None
    retry_match = RETRY_ATTEMPT_ID_PATTERN.fullmatch(attempt_id)
    if retry_match is not None:
        number, retry_number = retry_match.groups()
        return f"attempt-{number}-retry-{int(retry_number) + 1:03d}"
    if ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is not None:
        return f"{attempt_id}{RETRY_ATTEMPT_SUFFIX}"
    return None


def _stop_reason(
    decision: str | None,
    historical: int,
    limit: int,
    attempt_state: dict[str, Any],
    blocked: str | None,
    manual_decision: str | None,
) -> str | None:
    if manual_decision == "proceed_manual":
        return "operator selected manual fallback"
    if manual_decision == "reject_source":
        return "operator rejected source after Hunyuan"
    if decision == "reject":
        return "operator rejected source"
    if blocked:
        return blocked
    if historical > limit:
        return "historical invocations already exceed the configured cap"
    if attempt_state["consecutive_no_improvement"] >= 2:
        return "two consecutive Hunyuan results received no improvement feedback"
    if attempt_state["failure_modes"]:
        return "repeated failure has no plausible next step"
    if attempt_state["attempts_used"] >= limit:
        return "per-source Hunyuan invocation cap reached"
    return None


def _manual_fallback_allowed(
    attempt_state: dict[str, Any],
    limit: int,
    stop_reason: str | None,
    manual_decision: str | None,
    accepted_room: dict[str, Any] | None,
) -> bool:
    if accepted_room is not None:
        return False
    if manual_decision is not None:
        return False
    if attempt_state["awaiting_feedback"]:
        return False
    if stop_reason == "operator rejected source":
        return False
    if stop_reason is not None:
        return True
    if attempt_state["attempts_used"] >= limit:
        return True
    last_id = attempt_state["last_id"]
    result = attempt_state["results"].get(last_id, {})
    return result.get("status") in {"failed", "timed_out", "unavailable"}


def require_source_decision(decision: str, rationale: str) -> None:
    if decision not in ALLOWED_SOURCE_DECISIONS:
        raise WorkflowGateError(
            "Source decision must be proceed, proceed_with_limitations, or reject"
        )
    if not isinstance(rationale, str) or not rationale.strip():
        raise WorkflowGateError("Source decisions require an operator rationale")


def require_seed_selection(state: WorkflowState, frame: dict[str, Any]) -> None:
    if state.source_decision not in {"proceed", "proceed_with_limitations"}:
        raise WorkflowGateError("Approve source suitability before selecting a seed")
    operation = frame.get("decode_operation")
    if operation == "direct_source_video_decode_no_resize_or_edit":
        if not frame.get("path") or not frame.get("sha256") or not frame.get("frame_id"):
            raise WorkflowGateError(
                "Seed selection must identify the exact frame path and hash"
            )
        return
    if operation == "direct_source_picture_import_no_resize_or_edit":
        if (
            not frame.get("path")
            or not frame.get("sha256")
            or not frame.get("image_id")
            or not isinstance(frame.get("capture_index"), int)
        ):
            raise WorkflowGateError(
                "Image seed selection must identify the exact image path and hash"
            )
        return
    raise WorkflowGateError(
        "Hunyuan seed must be directly decoded or imported from the source"
    )


def require_attempt_start(state: WorkflowState) -> None:
    if not state.can_start_attempt:
        reason = (
            state.stopped_reason
            or "required source, seed, or feedback checkpoint is pending"
        )
        raise WorkflowGateError(f"Hunyuan attempt is not authorized: {reason}")


def require_feedback(
    improvement: str,
    reason: str,
    failure_mode: str | None,
    plausible_next_step: bool | None,
) -> None:
    if improvement not in ALLOWED_IMPROVEMENT:
        raise WorkflowGateError(
            "Feedback must classify improvement as improved, no_improvement, or uncertain"
        )
    if not isinstance(reason, str) or not reason.strip():
        raise WorkflowGateError("Every Hunyuan result requires operator feedback")
    if failure_mode is not None and plausible_next_step is None:
        raise WorkflowGateError(
            "Failure feedback must record whether a plausible next step exists"
        )
