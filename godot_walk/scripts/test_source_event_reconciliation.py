"""Ledger reconciliation tests: decision files must be referenced by events."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import source_ingestion_runner
from register_video_sources import append_event, register_video
from source_event_reconciliation import (
    EVENT_DEFERRED,
    EVENT_RECONCILED,
    read_event_records,
    validate_decision_event_coverage,
)
from video_source_library import LIBRARY, SourceLibraryError

ORIGINAL_TIMESTAMP = "2026-11-01T21:01:42.037279+00:00"


def fake_probe(_path: Path) -> dict[str, object]:
    return {
        "width": 1920,
        "height": 1080,
        "fps": 24.0,
        "frame_count": 96,
        "duration_seconds": 4.0,
    }


def sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SourceEventReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data/videos").mkdir(parents=True)
        video = self.root / "data/videos/room.mp4"
        video.write_bytes(b"video bytes")
        self.source_id = register_video(video, self.root, fake_probe)
        self.source_dir = self.root / LIBRARY / "sources" / self.source_id
        self.room_dir = self.source_dir / "rooms/test-room-v1"
        self.room_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _write(self, name: str, record: dict[str, object]) -> Path:
        path = self.room_dir / name
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def _operator_review(self) -> Path:
        return self._write(
            "operator_review.json",
            {
                "adaptation_id": "test-room-v1",
                "candidate_identity": "a" * 64,
                "decision": "accepted",
                "reviewed_at_utc": ORIGINAL_TIMESTAMP,
            },
        )

    def _accepted_adaptation(self, review: Path) -> Path:
        return self._write(
            "adaptation_accepted_v1.json",
            {
                "adaptation_id": "test-room-v1",
                "operator_decision": {
                    "status": "accepted",
                    "decision_record_path": self._relative(review),
                    "decision_sha256": sha256_text(review),
                },
            },
        )

    def _undated_admission(self) -> Path:
        return self._write(
            "catalog_admission_decision.json",
            {
                "issue": 168,
                "adaptation_id": "test-room-v1",
                "decision": "accepted_scoped_catalog_admission",
            },
        )

    def _event_types(self) -> list[str]:
        return [e["event_type"] for e in read_event_records(self.source_id, self.root)]

    def test_validator_passes_when_no_decision_files_exist(self) -> None:
        validate_decision_event_coverage(self.root)

    def test_validator_fails_for_unreferenced_decision_file(self) -> None:
        review = self._operator_review()
        with self.assertRaisesRegex(SourceLibraryError, self._relative(review)):
            validate_decision_event_coverage(self.root)

    def test_validator_ignores_other_room_files(self) -> None:
        self._write("adaptation_candidate.json", {"decision": "accepted"})
        validate_decision_event_coverage(self.root)

    def test_validator_accepts_any_event_that_cites_the_path(self) -> None:
        review = self._operator_review()
        append_event(
            self.source_id,
            "room_candidate_reviewed",
            {"decision_record_path": self._relative(review)},
            self.root,
        )
        validate_decision_event_coverage(self.root)

    def test_reconcile_makes_validator_pass(self) -> None:
        review = self._operator_review()
        self._accepted_adaptation(review)
        sequences = source_ingestion_runner.reconcile_historical(
            self.source_id, self.root
        )
        self.assertEqual(sequences, [2, 3])
        validate_decision_event_coverage(self.root)

    def test_reconcile_event_cites_artifact_hash_and_original_timestamp(self) -> None:
        review = self._operator_review()
        adaptation = self._accepted_adaptation(review)
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        by_path = {
            e["payload"]["reconciles"]["artifact_path"]: e
            for e in read_event_records(self.source_id, self.root)[1:]
        }
        direct = by_path[self._relative(review)]
        self.assertEqual(direct["event_type"], EVENT_RECONCILED)
        cited = direct["payload"]["reconciles"]
        self.assertEqual(cited["artifact_sha256"], sha256_text(review))
        self.assertEqual(cited["original_decision_timestamp"], ORIGINAL_TIMESTAMP)
        self.assertEqual(cited["original_decision"], "accepted")
        self.assertFalse(direct["payload"]["registration_accepted"])
        self.assertFalse(direct["payload"]["scale_calibrated"])
        inherited = by_path[self._relative(adaptation)]["payload"]["reconciles"]
        self.assertEqual(inherited["original_decision_timestamp"], ORIGINAL_TIMESTAMP)
        self.assertIn(
            "operator_review.json#reviewed_at_utc",
            inherited["original_decision_timestamp_field"],
        )

    def test_reconcile_is_never_backdated_and_keeps_existing_lines(self) -> None:
        self._operator_review()
        log = self.source_dir / "events.jsonl"
        before_bytes = log.read_bytes()
        started = datetime.now(timezone.utc)
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        self.assertTrue(log.read_bytes().startswith(before_bytes))
        event = read_event_records(self.source_id, self.root)[-1]
        occurred = datetime.fromisoformat(event["occurred_at_utc"])
        self.assertGreaterEqual(occurred, started)
        self.assertEqual(event["sequence"], 2)

    def test_reconcile_twice_does_not_duplicate_events(self) -> None:
        self._accepted_adaptation(self._operator_review())
        self._undated_admission()
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        snapshot = (self.source_dir / "events.jsonl").read_bytes()
        again = source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        self.assertEqual(again, [])
        self.assertEqual((self.source_dir / "events.jsonl").read_bytes(), snapshot)

    def test_undated_decision_is_deferred_not_reconciled(self) -> None:
        self._undated_admission()
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        self.assertEqual(self._event_types()[1:], [EVENT_DEFERRED])
        payload = read_event_records(self.source_id, self.root)[-1]["payload"]
        self.assertIsNone(payload["reconciles"]["original_decision_timestamp"])
        self.assertEqual(payload["status"], "not_reconciled_as_operator_decision")
        validate_decision_event_coverage(self.root)

    def test_adaptation_with_changed_review_hash_is_deferred(self) -> None:
        review = self._operator_review()
        self._accepted_adaptation(review)
        review.write_text(review.read_text() + "\n", encoding="utf-8")
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        self.assertEqual(self._event_types()[1:], [EVENT_RECONCILED, EVENT_DEFERRED])

    def test_rejected_decision_is_deferred(self) -> None:
        self._write(
            "operator_review.json",
            {"decision": "rejected", "reviewed_at_utc": ORIGINAL_TIMESTAMP},
        )
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        self.assertEqual(self._event_types()[1:], [EVENT_DEFERRED])

    def test_reconciled_event_links_existing_review_event(self) -> None:
        review = self._operator_review()
        append_event(
            self.source_id,
            "room_candidate_reviewed",
            {"adaptation_id": "test-room-v1", "decision": "accepted"},
            self.root,
        )
        log = self.source_dir / "events.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[-1])
        event["occurred_at_utc"] = "2026-11-01T21:01:42.034958+00:00"
        lines[-1] = json.dumps(event, separators=(",", ":"))
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        cited = read_event_records(self.source_id, self.root)[-1]["payload"][
            "reconciles"
        ]
        self.assertEqual(cited["artifact_path"], self._relative(review))
        self.assertEqual(cited["corresponds_to_sequence"], 2)

    def test_validator_fails_when_reconciled_file_changes(self) -> None:
        review = self._operator_review()
        source_ingestion_runner.reconcile_historical(self.source_id, self.root)
        review.write_text(review.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(SourceLibraryError, "changed or missing"):
            validate_decision_event_coverage(self.root)


if __name__ == "__main__":
    unittest.main()
