"""Resumable CPU intake runner tests using temporary local records."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import source_ingestion_runner
from register_video_sources import append_event, register_video
from source_ingestion_policy import WorkflowGateError
from video_source_library import SourceLibraryError, sha256_file


def fake_probe(_path: Path) -> dict[str, object]:
    return {
        "width": 1920,
        "height": 1080,
        "fps": 24.0,
        "frame_count": 96,
        "duration_seconds": 4.0,
    }


class SourceIngestionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        video_dir = self.root / "data/videos"
        video_dir.mkdir(parents=True)
        self.video = video_dir / "room.mp4"
        self.video.write_bytes(b"video bytes")
        self.source_id = register_video(self.video, self.root, fake_probe)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _fake_extract(self, source_path: str, _indices: list[int], output: str) -> Path:
        source_digest = sha256_file(self.root / source_path)
        output_dir = self.root / output
        output_dir.mkdir(parents=True)
        frame_path = output_dir / "frame_0001.png"
        Image.new("RGB", (1920, 1080), (20, 30, 40)).save(frame_path)
        relative_frame = frame_path.relative_to(self.root).as_posix()
        manifest = {
            "schema_version": 1,
            "source_video": source_path,
            "source_video_sha256": source_digest,
            "metadata": fake_probe(self.video),
            "decoder": "ffmpeg select by decoded zero-based frame index",
            "frames": [
                {
                    "frame_id": "frame_0001",
                    "index_zero_based": 0,
                    "timestamp_seconds": 0.0,
                    "path": relative_frame,
                    "sha256": sha256_file(frame_path),
                    "decode_operation": "direct_source_video_decode_no_resize_or_edit",
                }
            ],
        }
        manifest_path = output_dir / "extraction_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def _approve_source(self) -> None:
        source_ingestion_runner.record_source_review(
            self.source_id,
            "proceed_with_limitations",
            "The sampled interior is useful for one bounded room.",
            self.root,
        )

    def _append_completed_attempt(self, attempt_id: str, seed_sha256: str) -> None:
        append_event(
            self.source_id,
            "hunyuan_attempt_started",
            {"attempt_id": attempt_id, "seed_frame_sha256": seed_sha256},
            self.root,
        )
        append_event(
            self.source_id,
            "hunyuan_attempt_result",
            {"attempt_id": attempt_id, "status": "produced"},
            self.root,
        )
        append_event(
            self.source_id,
            "hunyuan_operator_feedback",
            {
                "attempt_id": attempt_id,
                "improvement": "improved",
                "reason": "The bounded panorama was useful.",
            },
            self.root,
        )

    def test_status_returns_hash_bound_source_scope_and_next_action(self) -> None:
        pending = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(
            f"godot_walk/source_library/sources/{self.source_id}",
            pending["worker_output_root"],
        )
        self.assertEqual("review-source", pending["next_worker_actions"][0])
        self.assertEqual(64, len(pending["source_manifest_sha256"]))

        self._approve_source()
        approved = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(
            ["extract-frames", "select-seed"], approved["next_worker_actions"]
        )

    def test_frame_extraction_waits_for_source_suitability(self) -> None:
        with patch.object(source_ingestion_runner, "extract_source_frames") as extract:
            with self.assertRaisesRegex(
                WorkflowGateError, "approve source suitability"
            ):
                source_ingestion_runner.extract_frames(
                    self.source_id, "run-001", [0], self.root
                )
            extract.assert_not_called()

    def test_source_review_corrections_are_append_only_and_explicit(self) -> None:
        source_ingestion_runner.record_source_review(
            self.source_id,
            "proceed",
            "Initial sampled footage looks usable.",
            self.root,
        )
        source_ingestion_runner.record_source_review(
            self.source_id,
            "reject",
            "Full clip review found no stable room view.",
            self.root,
        )
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual("reject", status["source_decision"])
        event_path = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "events.jsonl"
        )
        events = [json.loads(line) for line in event_path.read_text().splitlines()]
        reviews = [
            item
            for item in events
            if item["event_type"] == "source_suitability_decision"
        ]
        self.assertEqual(2, len(reviews))
        self.assertEqual(2, reviews[1]["payload"]["supersedes_sequence"])

    def test_sequential_budget_extensions_are_append_only_and_feedback_gated(
        self,
    ) -> None:
        self._approve_source()
        append_event(
            self.source_id,
            "seed_selected",
            {
                "frame_id": "frame_0001",
                "path": "godot_walk/source_library/test/frame_0001.png",
                "sha256": "a" * 64,
                "decode_operation": "direct_source_video_decode_no_resize_or_edit",
            },
            self.root,
        )
        for number in range(1, 4):
            attempt_id = f"attempt-{number:03d}"
            append_event(
                self.source_id,
                "hunyuan_attempt_started",
                {"attempt_id": attempt_id},
                self.root,
            )
            append_event(
                self.source_id,
                "hunyuan_attempt_result",
                {"attempt_id": attempt_id, "status": "failed"},
                self.root,
            )
            append_event(
                self.source_id,
                "hunyuan_operator_feedback",
                {
                    "attempt_id": attempt_id,
                    "improvement": "uncertain",
                    "reason": "The result could not be judged.",
                    "failure_mode": "cuda_oom",
                    "plausible_next_step": True,
                },
                self.root,
            )
        original_manifest_hash = source_ingestion_runner.load_source(
            self.source_id, self.root
        )[2]["manifest_sha256"]

        source_ingestion_runner.record_budget_extension(
            self.source_id,
            4,
            "Operator approved one diagnostic inference.",
            self.root,
        )
        state = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(4, state["attempt_limit"])
        self.assertEqual(3, state["attempts_used"])
        self.assertTrue(state["can_start_attempt"])
        self.assertEqual(original_manifest_hash, state["source_manifest_sha256"])
        with self.assertRaisesRegex(WorkflowGateError, "feedback-complete exhaustion"):
            source_ingestion_runner.record_budget_extension(
                self.source_id,
                4,
                "A second extension is not allowed.",
                self.root,
            )
        append_event(
            self.source_id,
            "hunyuan_attempt_started",
            {"attempt_id": "attempt-004"},
            self.root,
        )
        append_event(
            self.source_id,
            "hunyuan_attempt_result",
            {"attempt_id": "attempt-004", "status": "resource_stopped"},
            self.root,
        )
        append_event(
            self.source_id,
            "hunyuan_operator_feedback",
            {
                "attempt_id": "attempt-004",
                "improvement": "uncertain",
                "reason": "No output; feedback was recorded before extending.",
                "failure_mode": "swap_growth_guard",
                "plausible_next_step": True,
            },
            self.root,
        )
        source_ingestion_runner.record_budget_extension(
            self.source_id,
            6,
            "Operator approved two further supervised attempts.",
            self.root,
        )
        expanded = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(6, expanded["attempt_limit"])
        self.assertEqual(4, expanded["attempts_used"])
        self.assertTrue(expanded["can_start_attempt"])
        with self.assertRaisesRegex(WorkflowGateError, "feedback-complete exhaustion"):
            source_ingestion_runner.record_budget_extension(
                self.source_id,
                8,
                "A third extension is not allowed.",
                self.root,
            )

    def test_accepted_room_allows_one_seed_bound_remaining_room_attempt(self) -> None:
        self._approve_source()
        with patch.object(
            source_ingestion_runner,
            "extract_source_frames",
            side_effect=self._fake_extract,
        ):
            first_receipt = source_ingestion_runner.extract_frames(
                self.source_id, "room-one-seed", [0], self.root
            )
        first_frame = json.loads(first_receipt.read_text())["frames"][0]
        with patch.object(
            source_ingestion_runner,
            "_presentation_timestamp_seconds",
            return_value=0.0,
        ):
            source_ingestion_runner.select_seed(
                self.source_id, first_frame["frame_id"], first_frame["path"], self.root
            )

        for number in range(1, 4):
            self._append_completed_attempt(
                f"attempt-{number:03d}", first_frame["sha256"]
            )
        source_ingestion_runner.record_budget_extension(
            self.source_id, 4, "One bounded attempt.", self.root
        )
        self._append_completed_attempt("attempt-004", first_frame["sha256"])
        source_ingestion_runner.record_budget_extension(
            self.source_id, 6, "Two bounded attempts.", self.root
        )
        self._append_completed_attempt("attempt-005", first_frame["sha256"])
        append_event(
            self.source_id,
            "room_candidate_reviewed",
            {"adaptation_id": "accepted-room-v1", "decision": "accepted"},
            self.root,
        )

        with patch.object(
            source_ingestion_runner,
            "extract_source_frames",
            side_effect=self._fake_extract,
        ):
            second_receipt = source_ingestion_runner.extract_frames(
                self.source_id, "room-two-seed", [0], self.root
            )
        second_frame = json.loads(second_receipt.read_text())["frames"][0]
        with patch.object(
            source_ingestion_runner,
            "_presentation_timestamp_seconds",
            return_value=1.0,
        ):
            source_ingestion_runner.select_seed(
                self.source_id,
                second_frame["frame_id"],
                second_frame["path"],
                self.root,
            )

        source_ingestion_runner.authorize_room_attempt(
            self.source_id,
            "debris-window-room",
            "Operator approved the second direct-source seed.",
            self.root,
        )

        state = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertTrue(state["can_start_attempt"])
        self.assertEqual(5, state["attempts_used"])
        self.assertEqual(6, state["attempt_limit"])
        event_path = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "events.jsonl"
        )
        ledger = [json.loads(line) for line in event_path.read_text().splitlines()]
        authorization = ledger[-1]["payload"]
        self.assertEqual("attempt-006", authorization["attempt_id"])
        self.assertEqual(second_frame["sha256"], authorization["seed_frame"]["sha256"])

    def test_preflight_retry_authorization_preserves_blocked_attempt(self) -> None:
        self._approve_source()
        seed = {
            "frame_id": "frame_0001",
            "index_zero_based": 0,
            "timestamp_seconds": 0.0,
            "path": "godot_walk/source_library/test/frame_0001.png",
            "sha256": "b" * 64,
            "decode_operation": "direct_source_video_decode_no_resize_or_edit",
            "source_video_sha256": source_ingestion_runner.load_source(
                self.source_id, self.root
            )[2]["source_sha256"],
        }
        append_event(self.source_id, "seed_selected", seed, self.root)
        for number in range(1, 4):
            attempt_id = f"attempt-{number:03d}"
            append_event(
                self.source_id,
                "hunyuan_attempt_started",
                {"attempt_id": attempt_id},
                self.root,
            )
            append_event(
                self.source_id,
                "hunyuan_attempt_result",
                {"attempt_id": attempt_id, "status": "failed"},
                self.root,
            )
            append_event(
                self.source_id,
                "hunyuan_operator_feedback",
                {
                    "attempt_id": attempt_id,
                    "improvement": "uncertain",
                    "reason": "The result could not be judged.",
                    "failure_mode": "cuda_oom",
                    "plausible_next_step": True,
                },
                self.root,
            )
        source_ingestion_runner.record_budget_extension(
            self.source_id, 4, "One diagnostic attempt is approved.", self.root
        )

        attempt_dir = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "hunyuan/attempt-004"
        )
        attempt_dir.mkdir(parents=True)
        config = {
            "source_id": self.source_id,
            "attempt_id": "attempt-004",
            "seed_frame": {"sha256": seed["sha256"]},
        }
        config_path = attempt_dir / "attempt_config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        guard_path = attempt_dir / "gpu_guard.json"
        guard_path.write_text(
            json.dumps(
                {
                    "status": "blocked",
                    "source_id": self.source_id,
                    "attempt_id": "attempt-004",
                }
            ),
            encoding="utf-8",
        )
        original_guard_hash = sha256_file(guard_path)
        guard_reference = {
            "path": guard_path.relative_to(self.root).as_posix(),
            "sha256": original_guard_hash,
        }
        append_event(
            self.source_id,
            "hunyuan_preflight_blocked",
            {"reason": "insufficient RAM", "guard_receipt": guard_reference},
            self.root,
        )

        source_ingestion_runner.record_preflight_retry_authorization(
            self.source_id,
            "The operator explicitly requested one retry after resources became available.",
            self.root,
        )
        state = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(3, state["attempts_used"])
        self.assertEqual(4, state["attempt_limit"])
        self.assertTrue(state["can_start_attempt"])
        self.assertEqual(original_guard_hash, sha256_file(guard_path))
        self.assertFalse((attempt_dir.parent / "attempt-004-retry-001").exists())
        with self.assertRaisesRegex(WorkflowGateError, "unused final slot"):
            source_ingestion_runner.record_preflight_retry_authorization(
                self.source_id, "A duplicate retry is not authorized.", self.root
            )

    def test_presentation_timestamp_uses_ffprobe_frame_pts_by_index(self) -> None:
        completed = source_ingestion_runner.subprocess.CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout="36.400000\n36.433333\n36.466667\n",
            stderr="",
        )
        with patch.object(
            source_ingestion_runner.subprocess, "run", return_value=completed
        ) as run:
            timestamp = source_ingestion_runner._presentation_timestamp_seconds(
                self.video, 2
            )
        self.assertEqual(36.466667, timestamp)
        self.assertIn("frame=best_effort_timestamp_time", run.call_args.args[0])

    def test_cpu_stages_are_source_locked(self) -> None:
        with (
            source_ingestion_runner._source_lock(self.source_id, self.root),
            self.assertRaisesRegex(WorkflowGateError, "already claimed"),
        ):
            source_ingestion_runner.record_source_review(
                self.source_id,
                "proceed",
                "This competing worker must not claim the source.",
                self.root,
            )

    def test_extract_and_select_bind_seed_to_source_and_receipt(self) -> None:
        self._approve_source()
        with patch.object(
            source_ingestion_runner,
            "extract_source_frames",
            side_effect=self._fake_extract,
        ):
            manifest_path = source_ingestion_runner.extract_frames(
                self.source_id, "run-001", [0], self.root
            )
        extraction = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame = extraction["frames"][0]
        with patch.object(
            source_ingestion_runner,
            "_presentation_timestamp_seconds",
            return_value=0.0,
        ):
            source_ingestion_runner.select_seed(
                self.source_id, frame["frame_id"], frame["path"], self.root
            )
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(frame["path"], status["selected_seed"]["path"])
        self.assertEqual(
            "direct_source_video_decode_no_resize_or_edit",
            status["selected_seed"]["decode_operation"],
        )
        self.assertEqual(0.0, status["selected_seed"]["presentation_timestamp_seconds"])

    def test_frame_batch_and_seed_refuse_overwrite_or_tampering(self) -> None:
        self._approve_source()
        with patch.object(
            source_ingestion_runner,
            "extract_source_frames",
            side_effect=self._fake_extract,
        ) as extract:
            receipt = source_ingestion_runner.extract_frames(
                self.source_id, "run-001", [0], self.root
            )
            with self.assertRaises(FileExistsError):
                source_ingestion_runner.extract_frames(
                    self.source_id, "run-001", [0], self.root
                )
            extract.assert_called_once()
        extraction = json.loads(receipt.read_text(encoding="utf-8"))
        frame = extraction["frames"][0]
        receipt.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(SourceLibraryError, "receipt"):
            source_ingestion_runner.select_seed(
                self.source_id, frame["frame_id"], frame["path"], self.root
            )

    def test_changed_source_hash_stops_resume(self) -> None:
        self.video.write_bytes(b"changed")
        with self.assertRaisesRegex(SourceLibraryError, "Source video changed"):
            source_ingestion_runner.source_status(self.source_id, self.root)

    def test_path_traversal_and_invalid_run_id_are_rejected(self) -> None:
        with self.assertRaises(SourceLibraryError):
            source_ingestion_runner.extract_frames(
                self.source_id, "../bad", [0], self.root
            )
        with self.assertRaises(SourceLibraryError):
            source_ingestion_runner.select_seed(
                self.source_id,
                "frame_0001",
                "godot_walk/source_library/sources/../../outside.png",
                self.root,
            )


if __name__ == "__main__":
    unittest.main()
