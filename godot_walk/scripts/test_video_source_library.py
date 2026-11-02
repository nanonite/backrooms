"""Regression tests for safe, append-only source-video registration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from register_video_sources import append_event, inventory, register_video
from video_source_library import SourceLibraryError, validate_index


def fake_probe(_path: Path) -> dict[str, object]:
    return {
        "width": 1920,
        "height": 1080,
        "fps": 24.0,
        "frame_count": 96,
        "duration_seconds": 4.0,
    }


class VideoSourceLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data/videos").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _video(self, filename: str = "sample.mp4", data: bytes = b"video") -> Path:
        video = self.root / "data/videos" / filename
        video.write_bytes(data)
        return video

    def test_registration_is_idempotent_and_records_one_event(self) -> None:
        video = self._video()
        source_id = register_video(video, self.root, fake_probe)
        manifest_path = (
            self.root
            / "godot_walk/source_library/sources"
            / source_id
            / "source_manifest.json"
        )
        event_path = manifest_path.parent / "events.jsonl"
        original_manifest = manifest_path.read_bytes()
        original_event = event_path.read_bytes()

        self.assertEqual(source_id, register_video(video, self.root, fake_probe))
        self.assertEqual(original_manifest, manifest_path.read_bytes())
        self.assertEqual(original_event, event_path.read_bytes())
        self.assertEqual(1, len(validate_index(self.root)))
        self.assertEqual(1, len(original_event.splitlines()))

    def test_duplicate_content_at_another_path_is_rejected(self) -> None:
        first = self._video()
        register_video(first, self.root, fake_probe)
        second = self._video("copy.mp4")
        with self.assertRaisesRegex(SourceLibraryError, "Duplicate source content"):
            register_video(second, self.root, fake_probe)

    def test_changed_video_at_registered_path_is_rejected(self) -> None:
        video = self._video()
        register_video(video, self.root, fake_probe)
        video.write_bytes(b"changed video")
        with self.assertRaisesRegex(
            SourceLibraryError, "changed at its canonical path"
        ):
            register_video(video, self.root, fake_probe)

    def test_outside_and_symlink_inputs_are_rejected(self) -> None:
        outside = self.root / "outside.mp4"
        outside.write_bytes(b"video")
        with self.assertRaises(SourceLibraryError):
            register_video(outside, self.root, fake_probe)
        target = self._video("target.mp4")
        alias = self.root / "data/videos/alias.mp4"
        alias.symlink_to(target)
        with self.assertRaisesRegex(SourceLibraryError, "symlink"):
            register_video(alias, self.root, fake_probe)

    def test_tampered_manifest_or_video_fails_validation(self) -> None:
        video = self._video()
        source_id = register_video(video, self.root, fake_probe)
        manifest_path = (
            self.root
            / "godot_walk/source_library/sources"
            / source_id
            / "source_manifest.json"
        )
        manifest_path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(SourceLibraryError, "manifest changed"):
            validate_index(self.root)

    def test_events_append_without_rewriting_prior_records(self) -> None:
        video = self._video()
        source_id = register_video(video, self.root, fake_probe)
        event_path = (
            self.root / "godot_walk/source_library/sources" / source_id / "events.jsonl"
        )
        first_line = event_path.read_bytes()
        append_event(
            source_id,
            "source_review_requested",
            {"checkpoint": "seed_selection"},
            self.root,
        )
        lines = event_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(first_line, (lines[0] + "\n").encode())
        self.assertEqual(2, json.loads(lines[1])["sequence"])

    def test_inventory_registers_only_supported_direct_files(self) -> None:
        self._video("one.mp4")
        self._video("notes.txt")
        ids = inventory(self.root, fake_probe)
        self.assertEqual(1, len(ids))
        self.assertEqual(1, len(validate_index(self.root)))


if __name__ == "__main__":
    unittest.main()
