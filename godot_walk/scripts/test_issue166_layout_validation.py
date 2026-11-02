"""Regression tests for the bounded issue 166 layout validator."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from issue149_layout_core import canonical_json
from validate_issue166_layout import (
    ROOT,
    _historical_archive_matches,
    validate_bundle,
)

LAYOUT = (
    ROOT / "godot_walk/evidence/2026-10-26-four-room-transfer/layout_four_room.json"
)


class Issue166LayoutValidationTests(unittest.TestCase):
    def test_candidate_layout_validates(self) -> None:
        _, errors = validate_bundle(LAYOUT)
        self.assertEqual(errors, [])

    def test_only_the_pinned_historical_layout_tool_hash_uses_the_archive(self) -> None:
        valid = {
            "path": "godot_walk/scripts/issue149_layout_core.py",
            "sha256": "0170c37c402018aad118894e380c681c7cdb070bb4ba9d7ba4f8908ca9e283bf",
        }
        changed = {**valid, "sha256": "0" * 64}
        self.assertTrue(_historical_archive_matches(valid))
        self.assertFalse(_historical_archive_matches(changed))

    def test_misaligned_socket_is_rejected(self) -> None:
        errors = _validate_mutation(lambda layout: _move(layout, "R003", 0.5, 0.0))
        self.assertTrue(any("socket transforms" in error for error in errors))

    def test_overlapping_walkable_placement_is_rejected(self) -> None:
        errors = _validate_mutation(lambda layout: _move(layout, "R003", -4.0, 0.0))
        self.assertTrue(any("footprints overlap" in error for error in errors))

    def test_unconnected_open_socket_is_rejected(self) -> None:
        errors = _validate_mutation(lambda layout: layout["connections"].pop())
        self.assertTrue(
            any("open socket is not connected" in error for error in errors)
        )


def _move(layout: dict, instance_id: str, dx: float, dz: float) -> None:
    placement = next(
        item for item in layout["placements"] if item["instance_id"] == instance_id
    )
    placement["transform"]["position"][0] += dx
    placement["transform"]["position"][2] += dz


def _validate_mutation(change) -> list[str]:
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    change(layout)
    layout.pop("layout_sha256")
    layout["layout_sha256"] = hashlib.sha256(canonical_json(layout)).hexdigest()
    encoded = (
        json.dumps(layout, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    with tempfile.TemporaryDirectory(prefix="issue166-layout-") as directory:
        path = Path(directory) / "layout.json"
        path.write_bytes(encoded)
        Path(str(path) + ".sha256").write_text(
            f"{hashlib.sha256(encoded).hexdigest()}  layout.json\n"
        )
        _, errors = validate_bundle(path)
    return errors


if __name__ == "__main__":
    unittest.main()
