"""CPU-only checks for the finite #164 three-room layout."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest

from build_issue164_layout import _mark_mechanically_validated
from issue149_layout_core import canonical_json, load_catalog_snapshot
from issue164_layout import (
    LARGE_ROOM_ID,
    LAYOUT_ID,
    build_layout,
    validate_chain_layout,
)


class Issue164LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot, cls.catalog_hash, _ = load_catalog_snapshot()
        cls.layout = build_layout(
            cls.snapshot,
            cls.catalog_hash,
            "res://evidence/2026-10-24-issue-164/catalog_snapshot.json",
        )

    def test_layout_is_deterministic_three_room_chain(self) -> None:
        again = build_layout(
            self.snapshot,
            self.catalog_hash,
            "res://evidence/2026-10-24-issue-164/catalog_snapshot.json",
        )
        self.assertEqual(canonical_json(self.layout), canonical_json(again))
        self.assertEqual(self.layout["layout_id"], LAYOUT_ID)
        self.assertEqual(len(self.layout["placements"]), 3)
        self.assertEqual(
            len({item["module_id"] for item in self.layout["placements"]}), 3
        )
        self.assertEqual(len(self.layout["connections"]), 2)
        self.assertEqual(validate_chain_layout(self.layout, self.snapshot), [])

    def test_hall_socket_matches_pocket_capsule_clearance_and_floor(self) -> None:
        modules = {item["id"]: item for item in self.snapshot["modules"]}
        room = modules[LARGE_ROOM_ID]
        socket = room["sockets"][0]
        self.assertEqual(socket["clear_size_m"], [2.0, 2.1])
        self.assertGreaterEqual(socket["clear_size_m"][0], 0.6)
        self.assertGreaterEqual(socket["clear_size_m"][1], 1.2)
        self.assertEqual(socket["floor_elevation_m"], -1.27099049)
        self.assertGreaterEqual(socket["approach_clearance_m"], 1.2)

    def test_disconnected_chain_is_rejected(self) -> None:
        broken = {**self.layout, "connections": self.layout["connections"][:1]}
        self.assertTrue(validate_chain_layout(broken, self.snapshot))

    def test_mechanical_promotion_keeps_operator_review_pending(self) -> None:
        candidate = copy.deepcopy(self.layout)
        serialized = _mark_mechanically_validated(candidate)
        promoted = json.loads(serialized)
        payload = dict(promoted)
        expected = payload.pop("layout_sha256")
        self.assertEqual(promoted["mechanical_status"], "mechanically_validated")
        self.assertEqual(promoted["operator_status"], "review_pending")
        self.assertTrue(
            all(
                edge["mechanical_status"]
                == "mechanically_validated_review_pending"
                and edge["operator_status"] == "review_pending"
                for edge in promoted["connections"]
            )
        )
        self.assertEqual(hashlib.sha256(canonical_json(payload)).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
