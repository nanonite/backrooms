"""CPU-only tests for Hunyuan cap, operator gates, and early stopping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from source_ingestion_policy import (
    WorkflowGateError,
    evaluate_workflow,
    require_attempt_start,
    require_feedback,
    require_seed_selection,
    require_source_decision,
)


def event(event_type: str, payload: dict) -> dict:
    return {"event_type": event_type, "payload": payload}


class SourceIngestionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {
            "hunyuan": {"historical_invocations": 0, "policy_invocation_limit": 3}
        }
        self.source_and_seed = [
            event("source_suitability_decision", {"decision": "proceed"}),
            event(
                "seed_selected",
                {
                    "frame_id": "frame-001",
                    "path": "godot_walk/source_library/sources/video-0123456789abcdef/frames/seed.png",
                    "sha256": "a" * 64,
                    "decode_operation": "direct_source_video_decode_no_resize_or_edit",
                },
            ),
        ]

    def _completed_attempts(
        self, count: int, improvement: str = "improved"
    ) -> list[dict]:
        events = []
        for number in range(1, count + 1):
            attempt_id = f"attempt-{number:03d}"
            events.extend(
                [
                    event("hunyuan_attempt_started", {"attempt_id": attempt_id}),
                    event(
                        "hunyuan_attempt_result",
                        {"attempt_id": attempt_id, "status": "produced"},
                    ),
                    event(
                        "hunyuan_operator_feedback",
                        {
                            "attempt_id": attempt_id,
                            "improvement": improvement,
                            "reason": "reviewed",
                        },
                    ),
                ]
            )
        return events

    def _five_attempt_room_history(self) -> tuple[list[dict], dict]:
        events = self.source_and_seed + self._completed_attempts(3, "uncertain")
        events.append(
            event(
                "hunyuan_budget_extension_approved",
                {
                    "previous_limit": 3,
                    "new_limit": 4,
                    "additional_invocations": 1,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "One bounded retry.",
                },
            )
        )
        events.extend(
            [
                event("hunyuan_attempt_started", {"attempt_id": "attempt-004"}),
                event(
                    "hunyuan_attempt_result",
                    {"attempt_id": "attempt-004", "status": "resource_stopped"},
                ),
                event(
                    "hunyuan_operator_feedback",
                    {
                        "attempt_id": "attempt-004",
                        "improvement": "uncertain",
                        "reason": "Guard stopped the attempt.",
                        "failure_mode": "swap_growth_guard",
                        "plausible_next_step": True,
                    },
                ),
                event(
                    "hunyuan_budget_extension_approved",
                    {
                        "previous_limit": 4,
                        "new_limit": 6,
                        "additional_invocations": 2,
                        "authorization_source": "explicit_operator_instruction",
                        "rationale": "Two bounded invocations.",
                    },
                ),
                event("hunyuan_attempt_started", {"attempt_id": "attempt-005"}),
                event(
                    "hunyuan_attempt_result",
                    {"attempt_id": "attempt-005", "status": "produced"},
                ),
                event(
                    "hunyuan_operator_feedback",
                    {
                        "attempt_id": "attempt-005",
                        "improvement": "improved",
                        "reason": "Useful panorama.",
                    },
                ),
                event(
                    "room_candidate_reviewed",
                    {
                        "adaptation_id": "accepted-room-v1",
                        "decision": "accepted",
                    },
                ),
            ]
        )
        second_seed = {
            "frame_id": "frame-152",
            "path": "godot_walk/source_library/sources/video-0123456789abcdef/frames/room-2/frame.png",
            "sha256": "c" * 64,
            "source_video_sha256": "d" * 64,
            "decode_operation": "direct_source_video_decode_no_resize_or_edit",
        }
        events.append(event("seed_selected", second_seed))
        return events, second_seed

    def test_source_and_seed_checkpoints_precede_attempts(self) -> None:
        state = evaluate_workflow(self.manifest, [])
        with self.assertRaisesRegex(WorkflowGateError, "pending"):
            require_attempt_start(state)
        require_source_decision("proceed", "Different interior architecture")
        with self.assertRaisesRegex(WorkflowGateError, "Approve source suitability"):
            require_seed_selection(state, self.source_and_seed[1]["payload"])
        state = evaluate_workflow(self.manifest, self.source_and_seed)
        require_attempt_start(state)

    def test_non_direct_or_incomplete_seed_is_rejected(self) -> None:
        state = evaluate_workflow(self.manifest, [self.source_and_seed[0]])
        with self.assertRaises(WorkflowGateError):
            require_seed_selection(
                state,
                {
                    "frame_id": "render",
                    "path": "render.png",
                    "sha256": "b" * 64,
                    "decode_operation": "render_capture",
                },
            )

    def test_attempt_requires_feedback_before_next_attempt(self) -> None:
        events = self.source_and_seed + [
            event("hunyuan_attempt_started", {"attempt_id": "attempt-001"}),
            event(
                "hunyuan_attempt_result",
                {"attempt_id": "attempt-001", "status": "produced"},
            ),
        ]
        state = evaluate_workflow(self.manifest, events)
        self.assertTrue(state.awaiting_feedback)
        with self.assertRaisesRegex(WorkflowGateError, "pending"):
            require_attempt_start(state)

    def test_two_no_improvement_reviews_stop_without_automatic_retry(self) -> None:
        events = self.source_and_seed + self._completed_attempts(2, "no_improvement")
        state = evaluate_workflow(self.manifest, events)
        self.assertEqual(2, state.consecutive_no_improvement)
        self.assertIn("two consecutive", state.stopped_reason)
        with self.assertRaises(WorkflowGateError):
            require_attempt_start(state)
        self.assertTrue(state.manual_fallback_allowed)

    def test_per_video_cap_blocks_fourth_attempt(self) -> None:
        events = self.source_and_seed + self._completed_attempts(3)
        state = evaluate_workflow(self.manifest, events)
        self.assertEqual(3, state.attempts_used)
        self.assertEqual(
            "per-source Hunyuan invocation cap reached", state.stopped_reason
        )
        with self.assertRaises(WorkflowGateError):
            require_attempt_start(state)

    def test_explicit_one_time_budget_event_allows_only_attempt_four(self) -> None:
        events = self.source_and_seed + self._completed_attempts(3, "uncertain")
        state = evaluate_workflow(self.manifest, events)
        self.assertEqual(3, state.attempt_limit)
        self.assertFalse(state.can_start_attempt)

        events.append(
            event(
                "hunyuan_budget_extension_approved",
                {
                    "previous_limit": 3,
                    "new_limit": 4,
                    "additional_invocations": 1,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "One diagnostic attempt is approved.",
                },
            )
        )
        state = evaluate_workflow(self.manifest, events)
        self.assertEqual(4, state.attempt_limit)
        self.assertEqual(3, state.attempts_used)
        self.assertTrue(state.can_start_attempt)
        require_attempt_start(state)

    def test_invalid_or_repeated_budget_extension_is_rejected(self) -> None:
        events = self.source_and_seed + self._completed_attempts(3, "uncertain")
        authorization = event(
            "hunyuan_budget_extension_approved",
            {
                "previous_limit": 3,
                "new_limit": 5,
                "additional_invocations": 2,
                "authorization_source": "explicit_operator_instruction",
                "rationale": "Too many attempts.",
            },
        )
        with self.assertRaisesRegex(WorkflowGateError, "extension is invalid"):
            evaluate_workflow(self.manifest, events + [authorization])
        authorization["payload"].update(new_limit=4, additional_invocations=1)
        with self.assertRaisesRegex(WorkflowGateError, "extension is invalid"):
            evaluate_workflow(self.manifest, events + [authorization, authorization])

    def test_second_extension_requires_fourth_attempt_feedback_and_caps_at_six(self):
        events = self.source_and_seed + self._completed_attempts(3, "uncertain")
        events.append(
            event(
                "hunyuan_budget_extension_approved",
                {
                    "previous_limit": 3,
                    "new_limit": 4,
                    "additional_invocations": 1,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "One diagnostic attempt is approved.",
                },
            )
        )
        second_extension = event(
            "hunyuan_budget_extension_approved",
            {
                "previous_limit": 4,
                "new_limit": 6,
                "additional_invocations": 2,
                "authorization_source": "explicit_operator_instruction",
                "rationale": "Two more supervised attempts are approved.",
            },
        )
        with self.assertRaisesRegex(WorkflowGateError, "extension is invalid"):
            evaluate_workflow(self.manifest, events + [second_extension])

        fourth_attempt = "attempt-004-retry-001"
        events.extend(
            [
                event("hunyuan_attempt_started", {"attempt_id": fourth_attempt}),
                event(
                    "hunyuan_attempt_result",
                    {"attempt_id": fourth_attempt, "status": "resource_stopped"},
                ),
                event(
                    "hunyuan_operator_feedback",
                    {
                        "attempt_id": fourth_attempt,
                        "improvement": "uncertain",
                        "reason": "No panorama; the guard stopped for swap growth.",
                        "failure_mode": "swap_growth_guard",
                        "plausible_next_step": True,
                    },
                ),
            ]
        )
        events.append(second_extension)
        state = evaluate_workflow(self.manifest, events)
        self.assertEqual(6, state.attempt_limit)
        self.assertEqual(4, state.attempts_used)
        self.assertTrue(state.can_start_attempt)

    def test_accepted_room_stops_panorama_loop_before_unused_cap(self) -> None:
        events = self.source_and_seed + self._completed_attempts(2, "improved")
        events.append(
            event(
                "room_candidate_reviewed",
                {
                    "adaptation_id": "industrial-hall-panorama-v3",
                    "decision": "accepted",
                    "scope": "one standalone room candidate",
                },
            )
        )

        state = evaluate_workflow(self.manifest, events)

        self.assertFalse(state.can_start_attempt)
        self.assertFalse(state.manual_fallback_allowed)
        self.assertIn("panorama loop complete", state.stopped_reason)
        with self.assertRaisesRegex(WorkflowGateError, "panorama loop complete"):
            require_attempt_start(state)

    def test_seed_bound_room_authorization_unlocks_only_the_last_invocation(self):
        events, seed = self._five_attempt_room_history()
        events.append(
            event(
                "hunyuan_room_attempt_authorized",
                {
                    "schema_version": 1,
                    "room_id": "debris-window-interior",
                    "scope": "one_new_room_panorama",
                    "attempt_id": "attempt-006",
                    "seed_frame": seed,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "Operator approved this seed and requested the run.",
                },
            )
        )

        state = evaluate_workflow(self.manifest, events)

        self.assertEqual(5, state.attempts_used)
        self.assertEqual(6, state.attempt_limit)
        self.assertTrue(state.can_start_attempt)

        events.append(
            event(
                "hunyuan_attempt_started",
                {"attempt_id": "attempt-006", "seed_frame_sha256": seed["sha256"]},
            )
        )
        events.extend(
            [
                event(
                    "hunyuan_attempt_result",
                    {"attempt_id": "attempt-006", "status": "produced"},
                ),
                event(
                    "hunyuan_operator_feedback",
                    {
                        "attempt_id": "attempt-006",
                        "improvement": "uncertain",
                        "reason": "Awaiting operator review.",
                    },
                ),
            ]
        )
        state = evaluate_workflow(self.manifest, events)
        self.assertFalse(state.can_start_attempt)
        self.assertEqual(
            "per-source Hunyuan invocation cap reached", state.stopped_reason
        )

    def test_room_authorization_must_bind_the_latest_selected_seed(self):
        events, seed = self._five_attempt_room_history()
        mismatched = {**seed, "sha256": "e" * 64}
        events.append(
            event(
                "hunyuan_room_attempt_authorized",
                {
                    "schema_version": 1,
                    "room_id": "debris-window-interior",
                    "scope": "one_new_room_panorama",
                    "attempt_id": "attempt-006",
                    "seed_frame": mismatched,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "Operator approved the selected frame.",
                },
            )
        )

        with self.assertRaisesRegex(WorkflowGateError, "authorization is invalid"):
            evaluate_workflow(self.manifest, events)

    def test_room_authorization_cannot_bypass_an_unconsumed_attempt_or_pending_review(
        self,
    ):
        events, seed = self._five_attempt_room_history()
        authorization = event(
            "hunyuan_room_attempt_authorized",
            {
                "schema_version": 1,
                "room_id": "debris-window-interior",
                "scope": "one_new_room_panorama",
                "attempt_id": "attempt-006",
                "seed_frame": seed,
                "authorization_source": "explicit_operator_instruction",
                "rationale": "Operator approved the selected frame.",
            },
        )
        events.append(authorization)
        events.append(event("hunyuan_attempt_started", {"attempt_id": "attempt-007"}))

        with self.assertRaisesRegex(WorkflowGateError, "bypassed or repeated"):
            evaluate_workflow(self.manifest, events)

    def test_historical_over_cap_source_is_not_retried(self) -> None:
        manifest = {
            "hunyuan": {"historical_invocations": 4, "policy_invocation_limit": 3}
        }
        state = evaluate_workflow(manifest, self.source_and_seed)
        self.assertEqual(4, state.attempts_used)
        self.assertFalse(state.can_start_attempt)

    def test_historical_cap_alone_does_not_bypass_source_seed_gate(self) -> None:
        manifest = {
            "hunyuan": {
                "historical_invocations": 4,
                "policy_invocation_limit": 3,
            }
        }
        state = evaluate_workflow(manifest, [])
        self.assertIn("historical invocations", state.stopped_reason)
        self.assertFalse(state.manual_fallback_allowed)

    def test_rejected_source_does_not_authorize_manual_adaptation(self) -> None:
        events = [event("source_suitability_decision", {"decision": "reject"})]
        state = evaluate_workflow(self.manifest, events)
        self.assertFalse(state.can_start_attempt)
        self.assertFalse(state.manual_fallback_allowed)

    def test_gpu_preflight_block_is_a_terminal_stop(self) -> None:
        events = self.source_and_seed + [
            event("hunyuan_preflight_blocked", {"reason": "insufficient VRAM"})
        ]
        state = evaluate_workflow(self.manifest, events)
        self.assertIn("preflight blocked", state.stopped_reason)
        self.assertTrue(state.manual_fallback_allowed)

    def test_authorized_preflight_retry_uses_only_the_unused_fourth_slot(self) -> None:
        events = self.source_and_seed + self._completed_attempts(3, "uncertain")
        events.append(
            event(
                "hunyuan_budget_extension_approved",
                {
                    "previous_limit": 3,
                    "new_limit": 4,
                    "additional_invocations": 1,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "One additional diagnostic is approved.",
                },
            )
        )
        blocked = event(
            "hunyuan_preflight_blocked",
            {
                "reason": "insufficient RAM",
                "guard_receipt": {
                    "path": "attempt-004/gpu_guard.json",
                    "sha256": "a" * 64,
                },
            },
        )
        blocked["sequence"] = len(events) + 1
        events.append(blocked)
        for sequence, item in enumerate(events, start=1):
            item["sequence"] = sequence
        blocked_sequence = blocked["sequence"]
        authorization = event(
            "hunyuan_preflight_retry_approved",
            {
                "blocked_event_sequence": blocked_sequence,
                "guard_receipt": blocked["payload"]["guard_receipt"],
                "retry_attempt_id": "attempt-004-retry-001",
                "authorization_source": "explicit_operator_instruction",
                "rationale": "The operator explicitly requested one retry.",
            },
        )
        authorization["sequence"] = len(events) + 1

        state = evaluate_workflow(self.manifest, events + [authorization])
        self.assertEqual(4, state.attempt_limit)
        self.assertEqual(3, state.attempts_used)
        self.assertTrue(state.can_start_attempt)

        started = event(
            "hunyuan_attempt_started", {"attempt_id": "attempt-004-retry-001"}
        )
        started["sequence"] = len(events) + 2
        state = evaluate_workflow(self.manifest, events + [authorization, started])
        self.assertEqual(4, state.attempts_used)
        self.assertFalse(state.can_start_attempt)
        self.assertIn("cap reached", state.stopped_reason)

    def test_preflight_retry_cannot_change_receipt_or_repeat_authorization(
        self,
    ) -> None:
        events = self.source_and_seed + self._completed_attempts(3, "uncertain")
        events.append(
            event(
                "hunyuan_budget_extension_approved",
                {
                    "previous_limit": 3,
                    "new_limit": 4,
                    "additional_invocations": 1,
                    "authorization_source": "explicit_operator_instruction",
                    "rationale": "One additional diagnostic is approved.",
                },
            )
        )
        blocked = event(
            "hunyuan_preflight_blocked",
            {
                "reason": "insufficient RAM",
                "guard_receipt": {
                    "path": "attempt-004/gpu_guard.json",
                    "sha256": "a" * 64,
                },
            },
        )
        blocked["sequence"] = len(events) + 1
        events.append(blocked)
        for sequence, item in enumerate(events, start=1):
            item["sequence"] = sequence
        payload = {
            "blocked_event_sequence": blocked["sequence"],
            "guard_receipt": {"path": "attempt-004/gpu_guard.json", "sha256": "b" * 64},
            "retry_attempt_id": "attempt-004-retry-001",
            "authorization_source": "explicit_operator_instruction",
            "rationale": "The operator explicitly requested one retry.",
        }
        invalid = event("hunyuan_preflight_retry_approved", payload)
        invalid["sequence"] = len(events) + 1
        with self.assertRaisesRegex(WorkflowGateError, "authorization is invalid"):
            evaluate_workflow(self.manifest, events + [invalid])
        valid = event(
            "hunyuan_preflight_retry_approved",
            {
                **payload,
                "guard_receipt": blocked["payload"]["guard_receipt"],
            },
        )
        valid["sequence"] = len(events) + 1
        duplicate = {**valid, "sequence": len(events) + 2}
        with self.assertRaisesRegex(WorkflowGateError, "Only one preflight retry"):
            evaluate_workflow(self.manifest, events + [valid, duplicate])

    def test_repeated_failure_requires_operator_plausibility_assessment(self) -> None:
        with self.assertRaisesRegex(WorkflowGateError, "plausible next step"):
            require_feedback("uncertain", "same failure", "oom", None)
        events = self.source_and_seed + self._completed_attempts(2)
        events[-1]["payload"].update(
            {"failure_mode": "oom", "plausible_next_step": False}
        )
        events[-4]["payload"].update(
            {"failure_mode": "oom", "plausible_next_step": True}
        )
        state = evaluate_workflow(self.manifest, events)
        self.assertIn("repeated failure", state.stopped_reason)

    def test_latest_failure_review_controls_early_stop(self) -> None:
        events = self.source_and_seed + self._completed_attempts(2)
        events[-1]["payload"].update(
            {"failure_mode": "oom", "plausible_next_step": True}
        )
        events[-4]["payload"].update(
            {"failure_mode": "oom", "plausible_next_step": False}
        )
        state = evaluate_workflow(self.manifest, events)
        self.assertIsNone(state.stopped_reason)


if __name__ == "__main__":
    unittest.main()
