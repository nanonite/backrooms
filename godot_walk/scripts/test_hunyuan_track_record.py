"""Tests the append-only index of confirmed Hunyuan workflow rounds."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from build_hunyuan_track_record import (
    DESIGN_ROUNDS,
    TRACK_SCHEMA,
    append_records,
    build_record,
)
from hunyuan_round1_records import validate_document

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"


class HunyuanTrackRecordTests(unittest.TestCase):
    def test_confirmed_round_bundles_build_valid_records(self) -> None:
        for suffix in ("1", "2"):
            bundle = PROJECT / "evidence" / f"2026-10-21-issue-151-round-{suffix}"
            record = build_record(bundle)
            validate_document(record, TRACK_SCHEMA)
            self.assertEqual(record["skillopt_state"], "data_collection_only")
            self.assertEqual(len(record["variant_specs"]), 2)
            self.assertEqual(
                len(
                    record["gate_results"]["visual_metrics"]["measurements"][
                        "variant_pixel_deltas"
                    ]
                ),
                9,
            )

    def test_index_contains_only_confirmed_rounds_with_metric_snapshots(self) -> None:
        index = DESIGN_ROUNDS / "hunyuan_track_record.jsonl"
        records = [
            json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()
        ]
        for record in records:
            validate_document(record, TRACK_SCHEMA)
        self.assertEqual(
            [record["round_id"] for record in records],
            ["hunyuan-psx-r1", "hunyuan-psx-r2"],
        )
        self.assertNotIn("hunyuan-psx-r3", [r["round_id"] for r in records])
        self.assertTrue(
            all(
                "variant_pixel_deltas"
                in record["gate_results"]["visual_metrics"]["measurements"]
                for record in records
            )
        )

    def test_record_preserves_inferred_view_labels_and_directives(self) -> None:
        bundle = PROJECT / "evidence" / "2026-10-21-issue-151-round-2"
        record = build_record(bundle)
        reasons = [
            choice["reason"] for choice in record["operator_feedback"]["view_choices"]
        ]
        self.assertTrue(any("Auto-filled" in reason for reason in reasons))
        self.assertEqual(
            record["operator_feedback"]["next_round_directives"][0]["directive_id"],
            "hunyuan-psx-r2-d1",
        )

    def test_track_record_refuses_overwrite_and_duplicate_round_ids(self) -> None:
        first = build_record(PROJECT / "evidence" / "2026-10-21-issue-151-round-1")
        with tempfile.TemporaryDirectory(dir=DESIGN_ROUNDS) as directory:
            output = Path(directory) / "track_record.jsonl"
            append_records(output, [first])
            with self.assertRaises(FileExistsError):
                append_records(output, [first])
            with self.assertRaises(ValueError):
                append_records(output, [first], allow_append=True)


if __name__ == "__main__":
    unittest.main()
