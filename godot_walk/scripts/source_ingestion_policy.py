"""Operator-gated state rules for each source's Hunyuan-first workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
    preflight_retry = _preflight_retry_authorization(
        events, attempt_state["attempts_used"], historical, limit
    )
    blocked = _blocking_event(
        events,
        preflight_retry["payload"]["blocked_event_sequence"]
        if preflight_retry
        else None,
    )
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
    matching_starts = [
        event for event in starts if event["payload"].get("attempt_id") == attempt_id
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
    events: list[dict[str, Any]], authorized_sequence: int | None
) -> str | None:
    for event in events:
        if event["event_type"] == "hunyuan_preflight_blocked" and not (
            authorized_sequence is not None
            and event.get("sequence") == authorized_sequence
        ):
            reason = event["payload"].get("reason", "unspecified guard condition")
            return f"GPU resource preflight blocked: {reason}"
    return None


def _preflight_retry_authorization(
    events: list[dict[str, Any]], attempts_used: int, historical: int, limit: int
) -> dict[str, Any] | None:
    authorizations = [
        event
        for event in events
        if event["event_type"] == "hunyuan_preflight_retry_approved"
    ]
    if not authorizations:
        return None
    if len(authorizations) != 1:
        raise WorkflowGateError("Only one preflight retry authorization is supported")
    authorization = authorizations[0]
    payload = authorization["payload"]
    blocked_sequence = payload.get("blocked_event_sequence")
    blocked = next(
        (
            event
            for event in events
            if event["event_type"] == "hunyuan_preflight_blocked"
            and event.get("sequence") == blocked_sequence
        ),
        None,
    )
    authorization_sequence = authorization.get("sequence", 0)
    expected_id = f"attempt-{ONE_TIME_EXTENDED_LIMIT:03d}-retry-001"
    starts_before_authorization = sum(
        1
        for event in events
        if event["event_type"] == "hunyuan_attempt_started"
        and event.get("sequence", 0) < authorization_sequence
    )
    next_extension = next(
        (
            event
            for event in events
            if event["event_type"] == "hunyuan_budget_extension_approved"
            and event.get("sequence", 0) > authorization_sequence
        ),
        None,
    )
    retry_window_end = (
        next_extension.get("sequence", 0) if next_extension is not None else None
    )
    starts_during_retry_window = [
        event
        for event in events
        if event["event_type"] == "hunyuan_attempt_started"
        and event.get("sequence", 0) > authorization_sequence
        and (retry_window_end is None or event.get("sequence", 0) < retry_window_end)
    ]
    all_retry_starts = [
        event
        for event in events
        if event["event_type"] == "hunyuan_attempt_started"
        and event["payload"].get("attempt_id") == expected_id
    ]
    if (
        blocked is None
        or not isinstance(blocked_sequence, int)
        or isinstance(blocked_sequence, bool)
        or authorization_sequence <= blocked_sequence
        or payload.get("authorization_source") != "explicit_operator_instruction"
        or payload.get("retry_attempt_id") != expected_id
        or payload.get("guard_receipt") != blocked["payload"].get("guard_receipt")
        or not isinstance(payload.get("rationale"), str)
        or not payload["rationale"].strip()
        or historical + starts_before_authorization != ONE_TIME_EXTENDED_LIMIT - 1
        or attempts_used > limit
        or any(
            event["payload"].get("attempt_id") != expected_id
            for event in starts_during_retry_window
        )
        or len(all_retry_starts) > 1
        or any(
            event["event_type"] == "hunyuan_attempt_started"
            and blocked_sequence < event.get("sequence", 0) < authorization_sequence
            for event in events
        )
    ):
        raise WorkflowGateError("Preflight retry authorization is invalid")
    return authorization


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
