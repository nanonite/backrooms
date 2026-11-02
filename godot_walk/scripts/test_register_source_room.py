"""Regression tests for immutable source-manifest room admission."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from register_source_room import register_room
from register_video_sources import register_video
from source_ingestion_runner import load_source
from video_source_library import SourceLibraryError, sha256_file, validate_index


def fake_probe(_path: Path) -> dict[str, object]:
    return {
        "width": 1280,
        "height": 720,
        "fps": 30.0,
        "frame_count": 90,
        "duration_seconds": 3.0,
    }


class RegisterSourceRoomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        videos = self.root / "data/videos"
        videos.mkdir(parents=True)
        self.video = videos / "sample.mp4"
        self.video.write_bytes(b"source video")
        self.source_id = register_video(self.video, self.root, fake_probe)
        self.source_dir = (
            self.root / "godot_walk/source_library/sources" / self.source_id
        )
        self.original_manifest = self.source_dir / "source_manifest.json"
        self.original_hash = sha256_file(self.original_manifest)
        self.events = self.source_dir / "events.jsonl"
        self.original_events = self.events.read_bytes()
        self.adaptation_path, self.decision_path = self._write_accepted_candidate()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_accepted_candidate(self) -> tuple[str, str]:
        room_dir = self.source_dir / "rooms/test-room-v1"
        room_dir.mkdir(parents=True)
        scene = room_dir / "room.tscn"
        scene.write_text("[gd_scene format=3]\n", encoding="utf-8")
        candidate_identity = hashlib.sha256(b"accepted candidate").hexdigest()
        catalog_path = Path("godot_walk/room_catalog/catalog.json")
        catalog_snapshot = Path(
            "godot_walk/room_catalog/catalog_snapshots/test-kit-1.0.0.json"
        )
        module = {
            "id": "test_module_v1",
            "version": 1,
            "scene": f"res://{scene.relative_to(self.root / 'godot_walk').as_posix()}",
        }
        catalog = {
            "catalog_id": "test-kit",
            "catalog_version": "1.0.0",
            "modules": [module],
        }
        self._write_json(catalog_path, catalog)
        self._write_json(catalog_snapshot, catalog)
        decision_rel = f"{room_dir.relative_to(self.root).as_posix()}/decision.json"
        decision = {
            "decision": "accepted",
            "candidate_identity": candidate_identity,
            "module_id": "test_module_v1",
            "module_version": 1,
            "catalog_path": catalog_path.as_posix(),
            "catalog_version": "1.0.0",
            "registration_accepted": False,
            "scale_calibrated": False,
        }
        decision_file = self._write_json(Path(decision_rel), decision)
        decision_hash = sha256_file(decision_file)
        adaptation_rel = f"{room_dir.relative_to(self.root).as_posix()}/adaptation.json"
        adaptation = {
            "schema_version": 3,
            "adaptation_id": "test-room-v1",
            "candidate_identity": candidate_identity,
            "status": "accepted_reference",
            "registration_accepted": False,
            "scale_calibrated": False,
            "source_observations": {
                "video": {
                    "path": "data/videos/sample.mp4",
                    "sha256": sha256_file(self.video),
                }
            },
            "resolved_adaptation": {
                "candidate_version": "test-room-v1",
                "catalog_admission": "admitted",
                "scene_path": module["scene"],
            },
            "operator_decision": {
                "status": "accepted",
                "decision_record_path": decision_rel,
                "decision_sha256": decision_hash,
                "candidate_fingerprint": candidate_identity,
            },
        }
        self._write_json(Path(adaptation_rel), adaptation)
        return adaptation_rel, decision_rel

    def _write_json(self, relative: Path, value: dict) -> Path:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return target

    def test_admission_creates_versioned_manifest_and_preserves_history(self) -> None:
        manifest_path, manifest_hash = register_room(
            self.source_id, self.adaptation_path, self.decision_path, self.root
        )

        entries = validate_index(self.root)
        current = entries[0]
        manifest, events, loaded_entry = load_source(self.source_id, self.root)
        self.assertEqual(current["manifest_path"], manifest_path)
        self.assertEqual(current["manifest_sha256"], manifest_hash)
        self.assertEqual("source_manifest-v2.json", Path(manifest_path).name)
        self.assertEqual(self.original_hash, sha256_file(self.original_manifest))
        self.assertEqual(self.original_events, self.events.read_bytes())
        self.assertEqual(
            "accepted_catalog_admission",
            manifest["room_adaptations"][0]["decision_status"],
        )
        self.assertEqual(loaded_entry["manifest_sha256"], manifest_hash)
        self.assertEqual(1, len(events))

    def test_registration_is_idempotent_and_does_not_overwrite_snapshot(self) -> None:
        first = register_room(
            self.source_id, self.adaptation_path, self.decision_path, self.root
        )
        second = register_room(
            self.source_id, self.adaptation_path, self.decision_path, self.root
        )
        self.assertEqual(first, second)
        index = json.loads(
            (self.root / "godot_walk/source_library/index.json").read_text()
        )
        self.assertEqual(2, index["index_version"])

    def test_decision_for_another_candidate_is_rejected_before_index_change(
        self,
    ) -> None:
        decision_file = self.root / self.decision_path
        decision = json.loads(decision_file.read_text())
        decision["candidate_identity"] = "0" * 64
        decision_file.write_text(json.dumps(decision) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(SourceLibraryError, "candidate"):
            register_room(
                self.source_id, self.adaptation_path, self.decision_path, self.root
            )
        self.assertEqual(
            "source_manifest.json",
            Path(validate_index(self.root)[0]["manifest_path"]).name,
        )

    def test_parent_manifest_tampering_invalidates_successor(self) -> None:
        register_room(
            self.source_id, self.adaptation_path, self.decision_path, self.root
        )
        self.original_manifest.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(SourceLibraryError, "predecessor changed"):
            validate_index(self.root)


if __name__ == "__main__":
    unittest.main()
