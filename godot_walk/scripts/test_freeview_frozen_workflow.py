"""Freeze guard for the seed-review v1 workflow this addendum sits beside.

These hashes may only change in a new versioned workflow slice. Editing a v1
file to make this test pass defeats its purpose.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
FROZEN_FILES = {
    "godot_walk/seed_review/WORKFLOW_V1.md": (
        "84d7d1669b6dbfcce9064bb918df524349640fd5ef7305674bc40c1f01d903b6"
    ),
    "godot_walk/seed_review/workflow.v1.json": (
        "3c07613e1af1f3801bec79bdbc1bfe0350aa3b97c9dfd1d5c4c87f501ac870ec"
    ),
    "godot_walk/seed_review/schemas/seed_review_receipt.schema.json": (
        "951533bf58c12126bc54a40ac4a235a107b237ae9390641aef51495a5a2a8d1f"
    ),
    "godot_walk/seed_review/schemas/seed_review_request.schema.json": (
        "9e7db8f29b6484b493dc93d2506c8f7b244110e2a30f4e22d178380e38d3c743"
    ),
    "godot_walk/seed_review/schemas/seed_review_response.schema.json": (
        "a30c3b49b6ed2562014a9465ffae897860e91df4813dd204f804c87ac95e2cf5"
    ),
}


class FrozenWorkflowTests(unittest.TestCase):
    def test_v1_workflow_files_are_byte_identical(self) -> None:
        for relative, expected in FROZEN_FILES.items():
            with self.subTest(path=relative):
                digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(expected, digest)

    def test_addendum_is_versioned_and_advisory(self) -> None:
        addendum = ROOT / "godot_walk/seed_review/WORKFLOW_V1_1_ADDENDUM.md"
        text = addendum.read_text(encoding="utf-8")
        self.assertIn("1.1.0", text)
        self.assertIn("advisory", text.lower())
        self.assertIn("`workflow.v1.json`", text)
        self.assertIn("v1 runner", text)


if __name__ == "__main__":
    unittest.main()
