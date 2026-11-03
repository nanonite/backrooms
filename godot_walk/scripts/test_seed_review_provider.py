"""Unit tests for response parsing, usage metadata, and command construction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_review_errors import SeedReviewError
from seed_review_provider import (
    ModelIdentity,
    ModelInvocation,
    OpenCodeCliModel,
    build_opencode_command,
    enforce_model_policy,
    extract_response_text,
    extract_usage_payload,
)
from seed_review_response import extract_json_object, normalise_response
from seed_review_usage import usage_from_payload


class SeedReviewProviderTests(unittest.TestCase):
    def test_opencode_command_uses_individual_files_not_a_sheet(self) -> None:
        command = build_opencode_command(
            "opencode/nemotron-3.5-super-vl-free",
            (Path("a.png"), Path("b.png"), Path("c.png")),
            "prompt",
        )
        self.assertEqual("opencode", command[0])
        self.assertEqual(3, command.count("--file"))
        self.assertNotIn("contact", " ".join(command).lower())
        self.assertEqual("prompt", command[-1])

    def test_usage_is_unreported_when_provider_is_silent(self) -> None:
        usage = usage_from_payload(None, 0.0)
        self.assertFalse(usage.reported)
        self.assertIsNone(usage.input_tokens)
        self.assertIsNone(usage.actual_cost_usd)
        self.assertEqual("unavailable", usage.source)

    def test_usage_reads_nested_provider_values(self) -> None:
        usage = usage_from_payload(
            {
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 30,
                    "cost_usd": 0.002,
                }
            },
            0.001,
        )
        self.assertTrue(usage.reported)
        self.assertEqual(150, usage.total_tokens)
        self.assertEqual(0.002, usage.estimated_cost_usd)
        self.assertEqual("provider_response", usage.source)

    def test_recorded_fixture_usage_respects_false_report_flag(self) -> None:
        usage = usage_from_payload(
            {
                "listed_price_usd": 0.0,
                "provider_usage_metadata_reported": False,
                "actual_token_count": None,
            },
            0.0,
            source="recorded_fixture",
        )
        self.assertFalse(usage.reported)
        self.assertIsNone(usage.total_tokens)
        self.assertEqual("unavailable", usage.source)

    def test_usage_payload_is_found_in_event_stream(self) -> None:
        payload = extract_usage_payload(
            '{"type":"start"}\n'
            '{"type":"step_finish","usage":{"input_tokens":5,'
            '"output_tokens":2}}\n'
        )
        self.assertIsNotNone(payload)
        usage = usage_from_payload(payload, None)
        self.assertTrue(usage.reported)
        self.assertEqual(7, usage.total_tokens)

    def test_response_text_is_extracted_from_opencode_json_events(self) -> None:
        event_stream = (
            '{"type":"step_start"}\n'
            '{"type":"text","part":{"type":"text",'
            '"text":"{\\"selected_frame_id\\":\\"frame_0001\\"}"}}\n'
            '{"type":"step_finish"}\n'
        )
        self.assertEqual(
            '{"selected_frame_id":"frame_0001"}',
            extract_response_text(event_stream),
        )

    def test_response_text_keeps_plain_text_output(self) -> None:
        self.assertEqual("model response", extract_response_text("model response"))

    def test_live_adapter_invokes_opencode_and_decodes_text_events(self) -> None:
        identity = ModelIdentity(
            provider="opencode",
            model="nemotron-3.5-super-vl-free",
            image_input_supported=True,
            image_input_support_basis="smoke_tested",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
        )
        invocation = ModelInvocation(
            identity=identity,
            prompt="Return JSON.",
            image_paths=(Path("frame.png"),),
            timeout_seconds=30,
        )
        output = (
            '{"type":"text","part":{"type":"text",'
            '"text":"{\\"selected_frame_id\\":\\"frame_0001\\"}"}}\n'
        )
        completed = SimpleNamespace(
            returncode=0,
            stdout=output,
            stderr="",
        )
        with patch(
            "seed_review_provider.subprocess.run", return_value=completed
        ) as subprocess_run:
            response = OpenCodeCliModel().invoke(invocation)
        self.assertEqual("completed", response.status)
        self.assertEqual('{"selected_frame_id":"frame_0001"}', response.raw_text)
        self.assertEqual(1, subprocess_run.call_count)
        command = subprocess_run.call_args.args[0]
        self.assertEqual("opencode", command[0])
        self.assertIn("--file", command)
        self.assertEqual(30, subprocess_run.call_args.kwargs["timeout"])

    def test_live_adapter_records_structured_provider_quota_error(self) -> None:
        identity = ModelIdentity(
            provider="opencode",
            model="nemotron-3.5-super-vl-free",
            image_input_supported=True,
            image_input_support_basis="smoke_tested",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
        )
        invocation = ModelInvocation(
            identity=identity,
            prompt="Return JSON.",
            image_paths=(Path("frame.png"),),
            timeout_seconds=30,
        )
        output = (
            '{"type":"error","error":{"type":"provider.quota",'
            '"message":"Free usage limit reached","status":429}}\n'
        )
        completed = SimpleNamespace(returncode=1, stdout=output, stderr="")
        with patch("seed_review_provider.subprocess.run", return_value=completed):
            response = OpenCodeCliModel().invoke(invocation)
        self.assertEqual("error", response.status)
        self.assertIn("provider.quota", response.error)
        self.assertIn("Free usage limit reached", response.error)
        self.assertIn("HTTP 429", response.error)

    def test_extract_json_object_ignores_surrounding_text(self) -> None:
        value = extract_json_object(
            'Analysis first.\n{"selected_frame_id":"frame_0001",'
            '"ranked_alternatives":[],"evidence":"x","uncertainty":"y",'
            '"confidence_1_to_5":3,"use_original_frame_not_a_composite":true}\n'
        )
        self.assertEqual("frame_0001", value["selected_frame_id"])

    def test_extract_json_object_requires_seed_selection(self) -> None:
        with self.assertRaises(SeedReviewError) as caught:
            extract_json_object('{"note":"no selection"}')
        self.assertEqual("invalid_response", caught.exception.code)

    def test_normalise_abstention_marks_operator_review(self) -> None:
        value = normalise_response(
            {
                "selected_frame_id": None,
                "ranked_alternatives": [],
                "evidence": "Frames are indistinguishable.",
                "uncertainty": "No supportable choice.",
                "confidence_1_to_5": 2,
                "use_original_frame_not_a_composite": True,
            },
            {"frame_0000", "frame_0001"},
            3,
        )
        self.assertEqual("abstained", value["selection_status"])
        self.assertTrue(value["requires_operator_review"])

    def test_normalise_rejects_alternatives_outside_candidate_set(self) -> None:
        with self.assertRaises(SeedReviewError) as caught:
            normalise_response(
                {
                    "selected_frame_id": "frame_0000",
                    "ranked_alternatives": ["frame_9999"],
                    "evidence": "x",
                    "uncertainty": "y",
                    "confidence_1_to_5": 4,
                    "use_original_frame_not_a_composite": True,
                },
                {"frame_0000", "frame_0001"},
                3,
            )
        self.assertEqual("invalid_response", caught.exception.code)

    def test_paid_policy_requires_ceiling_and_accounting(self) -> None:
        identity = ModelIdentity(
            provider="opencode",
            model="paid",
            image_input_supported=True,
            image_input_support_basis="unit_test",
            is_free=False,
            listed_price_usd=1.0,
            accounting="provider_reported",
        )
        with self.assertRaises(SeedReviewError) as caught:
            enforce_model_policy(identity, None, True)
        self.assertEqual("paid_call_requires_hard_ceiling", caught.exception.code)
        with self.assertRaises(SeedReviewError) as caught:
            enforce_model_policy(identity, 0.01, False)
        self.assertEqual("paid_call_requires_accounting", caught.exception.code)
        self.assertTrue(enforce_model_policy(identity, 0.01, True))

    def test_free_policy_does_not_authorize_paid_call(self) -> None:
        identity = ModelIdentity(
            provider="opencode",
            model="free",
            image_input_supported=True,
            image_input_support_basis="unit_test",
            is_free=True,
            listed_price_usd=0.0,
            accounting="free_no_charge",
        )
        self.assertFalse(enforce_model_policy(identity, None, False))


if __name__ == "__main__":
    unittest.main()
