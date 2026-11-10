"""End-to-end picture-set intake tests (issue 221)."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import jsonschema
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_source_panogen
import source_ingestion_gpu
import source_ingestion_runner
import template_validate as tv
from generate_picture_set_fixture import create_picture_set
from module_profile import build_profile, write_profile
from picture_set_sources import IMPORT_OPERATION
from register_picture_sources import (
    inventory_pictures,
    register_picture_set,
)
from source_ingestion_policy import WorkflowGateError
from source_ingestion_runner import approve_picture_seed
from video_source_library import (
    PICTURE_SET_SOURCE_KIND,
    SourceLibraryError,
    picture_set_sha256,
    sha256_file,
    validate_index,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md"
CATALOG_SNAPSHOT = (
    ROOT
    / "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.5.0.json"
)


class PictureSetIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data/pictures").mkdir(parents=True)
        (self.root / "data/videos").mkdir(parents=True)
        self.pictures = create_picture_set(
            self.root / "data/pictures/synthetic-set-001",
            count=3,
            size=(1024, 768),
        )
        self.source_id = register_picture_set(self.pictures[0].parent, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _approve(self) -> None:
        source_ingestion_runner.record_source_review(
            self.source_id,
            "proceed",
            "Synthetic intake check; a real picture set still needs operator review.",
            self.root,
        )

    def _import_and_select(self) -> dict:
        receipt = source_ingestion_runner.import_images(
            self.source_id, "seed-candidates-001", self.root
        )
        image = json.loads(receipt.read_text(encoding="utf-8"))["images"][0]
        approve_picture_seed(
            self.source_id,
            image["image_id"],
            "Synthetic fixture choice for issue 221 intake checks.",
            self.root,
        )
        source_ingestion_runner.select_image(
            self.source_id, image["image_id"], image["path"], self.root
        )
        return image

    def test_registration_writes_v3_manifest_and_hashes_every_image(self) -> None:
        entries = validate_index(self.root)
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual(self.source_id, entry["source_id"])
        self.assertTrue(self.source_id.startswith("picture-set-"))
        manifest_path = self.root / entry["manifest_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(3, manifest["schema_version"])
        self.assertEqual(3, manifest["manifest_version"])
        self.assertEqual(PICTURE_SET_SOURCE_KIND, manifest["source_kind"])
        self.assertIsNone(manifest["content"]["video"])
        images = manifest["content"]["picture_set"]
        self.assertEqual(3, len(images))
        for image in images:
            source = self.root / image["path"]
            self.assertEqual(sha256_file(source), image["sha256"])
            with Image.open(source) as handle:
                self.assertEqual(handle.size, (image["width"], image["height"]))
        self.assertEqual(picture_set_sha256(images), entry["source_sha256"])
        self.assertFalse(manifest["registration_accepted"])
        self.assertFalse(manifest["scale_calibrated"])
        index = json.loads(
            (self.root / "godot_walk/source_library/index.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(2, index["schema_version"])

    def test_registration_is_idempotent_and_rejects_a_changed_set(self) -> None:
        original_manifest = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "source_manifest-v3.json"
        ).read_bytes()
        self.assertEqual(
            self.source_id,
            register_picture_set(self.pictures[0].parent, self.root),
        )
        self.assertEqual(
            original_manifest,
            (
                self.root
                / "godot_walk/source_library/sources"
                / self.source_id
                / "source_manifest-v3.json"
            ).read_bytes(),
        )
        Image.new("RGB", (32, 24), (1, 2, 3)).save(self.pictures[0])
        with self.assertRaisesRegex(SourceLibraryError, "changed at its canonical path"):
            register_picture_set(self.pictures[0].parent, self.root)

    def test_inventory_and_validation_cover_picture_directories(self) -> None:
        second = create_picture_set(
            self.root / "data/pictures/synthetic-set-002", count=2
        )
        registered = inventory_pictures(self.root)
        self.assertEqual(2, len(registered))
        self.assertIn(
            register_picture_set(second[0].parent, self.root),
            registered,
        )
        self.assertEqual(2, len(validate_index(self.root)))

    def test_import_waits_for_source_review_and_refuses_overwrite(self) -> None:
        with self.assertRaisesRegex(WorkflowGateError, "approve source suitability"):
            source_ingestion_runner.import_images(
                self.source_id, "seed-candidates-001", self.root
            )
        self._approve()
        source_ingestion_runner.import_images(
            self.source_id, "seed-candidates-001", self.root
        )
        with self.assertRaises(FileExistsError):
            source_ingestion_runner.import_images(
                self.source_id, "seed-candidates-001", self.root
            )

    def test_picture_source_rejects_video_only_stage_names(self) -> None:
        self._approve()
        with self.assertRaisesRegex(WorkflowGateError, "use import-images"):
            source_ingestion_runner.extract_frames(
                self.source_id, "frames-001", [0], self.root
            )
        with self.assertRaisesRegex(WorkflowGateError, "use select-image"):
            source_ingestion_runner.select_seed(
                self.source_id, "frame_0001", "frame.png", self.root
            )

    def test_picture_set_has_no_invented_timestamp(self) -> None:
        self._approve()
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(
            [
                "prepare-picture-seed-review",
                "approve-picture-seed",
                "import-images",
                "select-image",
            ],
            status["next_worker_actions"],
        )
        self._import_and_select()
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        seed = status["selected_seed"]
        self.assertEqual(IMPORT_OPERATION, seed["decode_operation"])
        self.assertEqual("img_0001", seed["image_id"])
        self.assertNotIn("frame_id", seed)
        self.assertNotIn("timestamp_seconds", seed)
        self.assertNotIn("presentation_timestamp_seconds", seed)
        self.assertEqual(
            status["source_sha256"], seed["source_image_set_sha256"]
        )

    def test_tampered_import_or_source_image_stops_selection(self) -> None:
        self._approve()
        receipt = source_ingestion_runner.import_images(
            self.source_id, "seed-candidates-001", self.root
        )
        image = json.loads(receipt.read_text(encoding="utf-8"))["images"][0]
        imported = self.root / image["path"]
        imported.write_bytes(b"tampered")
        with self.assertRaisesRegex(SourceLibraryError, "missing or changed"):
            source_ingestion_runner.select_image(
                self.source_id, image["image_id"], image["path"], self.root
            )
        imported.write_bytes((self.pictures[0]).read_bytes())
        self.pictures[0].write_bytes(b"changed source")
        with self.assertRaisesRegex(SourceLibraryError, "changed"):
            source_ingestion_runner.select_image(
                self.source_id, image["image_id"], image["path"], self.root
            )

    def test_guard_and_panogen_bind_the_image_set_hash_and_image_id(self) -> None:
        self._approve()
        image = self._import_and_select()
        _manifest, _events, entry = source_ingestion_runner.load_source(
            self.source_id, self.root
        )
        seed = source_ingestion_runner.source_status(
            self.source_id, self.root
        )["selected_seed"]
        settings = source_ingestion_gpu._attempt_settings(
            self.source_id,
            entry,
            seed,
            "attempt-001",
            "Synthetic picture-set panorama.",
            512,
            256,
            42,
            "sequential_cpu",
            2700,
        )
        self.assertEqual(PICTURE_SET_SOURCE_KIND, settings["source_kind"])
        self.assertEqual(entry["source_sha256"], settings["source_image_set_sha256"])
        self.assertEqual("img_0001", settings["seed_image_id"])
        command = source_ingestion_gpu._panogen_command(
            self.root / seed["path"],
            self.root / "attempt-001",
            settings,
            {"path": "guard.json", "sha256": "a" * 64},
            self.root,
        )
        self.assertIn("--source-image-set-sha256", command)
        self.assertIn(entry["source_sha256"], command)
        self.assertIn("--image-id", command)
        self.assertIn("img_0001", command)
        self.assertNotIn("--source-video-sha256", command)

        guard = self.root / "guard.json"
        guard.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "source_id": self.source_id,
                    "source_kind": PICTURE_SET_SOURCE_KIND,
                    "source_image_set_sha256": entry["source_sha256"],
                    "source_manifest_sha256": entry["manifest_sha256"],
                    "seed_frame_sha256": image["sha256"],
                    "seed_image_id": image["image_id"],
                    "seed_review_decision": seed["seed_review_decision"],
                    "seed_review_decision_sha256": seed["seed_review_decision"][
                        "decision_sha256"
                    ],
                    "seed_image_width": seed["width"],
                    "seed_image_height": seed["height"],
                    "seed_image_source_path": seed["source_image_path"],
                    "seed_image_capture_index": seed["capture_index"],
                }
            ),
            encoding="utf-8",
        )
        arguments = SimpleNamespace(
            source_kind=PICTURE_SET_SOURCE_KIND,
            source_id=self.source_id,
            source_image_set_sha256=entry["source_sha256"],
            source_video_sha256=None,
            image_id=image["image_id"],
            source_manifest_sha256=entry["manifest_sha256"],
            seed_frame_sha256=image["sha256"],
            seed_frame=self.root / image["path"],
            guard_receipt=guard,
            guard_receipt_sha256=hashlib.sha256(guard.read_bytes()).hexdigest(),
        )
        run_source_panogen._validate_guard_and_seed(arguments)
        mutated = json.loads(guard.read_text(encoding="utf-8"))
        mutated["source_image_set_sha256"] = "0" * 64
        guard.write_text(json.dumps(mutated), encoding="utf-8")
        arguments.guard_receipt_sha256 = hashlib.sha256(guard.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "image-set-bound"):
            run_source_panogen._validate_guard_and_seed(arguments)

    def test_picture_set_produces_a_module_profile(self) -> None:
        self._approve()
        image = self._import_and_select()
        snapshot = self.root / CATALOG_SNAPSHOT.relative_to(ROOT)
        snapshot.parent.mkdir(parents=True)
        shutil.copyfile(CATALOG_SNAPSHOT, snapshot)
        template = self.root / TEMPLATE.relative_to(ROOT)
        template.parent.mkdir(parents=True)
        shutil.copyfile(TEMPLATE, template)
        schema = self.root / "godot_walk/room_catalog/module_profile.schema.json"
        schema.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            ROOT / "godot_walk/room_catalog/module_profile.schema.json", schema
        )
        room = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "rooms/synthetic-picture-room"
        )
        room.mkdir(parents=True)
        poetics_path = room / "module_poetics_v2.json"
        poetics = {
            "schema_version": 1,
            "deriver_version": "test",
            "module_id": "synthetic_picture_room_v1",
            "version": 1,
            "source_id": self.source_id,
            "room_dir": room.relative_to(self.root).as_posix(),
            "library_index": {"path": "library-index.json", "sha256": "0" * 64},
            "catalog_snapshot_sha256": sha256_file(snapshot),
            "metadata_status": "operator_accepted",
            "origin": "source_picture_set",
            "shape": {
                "footprint_xz": [[0, 0], [4, 0], [4, 3], [0, 3]],
                "vertex_count": 4,
                "area_m2": 12.0,
                "bbox_xz": {"min": [0, 0], "max": [4, 3]},
                "aspect": 1.333333,
                "convexity": 1.0,
                "rectilinear": True,
                "primitive": "box",
                "shape_stage": 0,
                "symmetry": "D2",
                "ceiling_height_m": 2.4,
            },
            "ports": {
                "tested_sockets": [],
                "untested_sockets": ["north"],
                "port_slots": [],
            },
            "features": [],
            "voids": [],
            "layers": {
                "shape": {"scene": None},
                "surface": {"visual_assets": []},
                "collision": {"provenance": None, "collision_footprint_xz": None},
                "light": {"value": None, "note": "not derived"},
            },
            "translation_chain": [
                {"stage": "direct_frame", "evidence": [image["path"]]},
                {
                    "stage": "hunyuan_panorama",
                    "evidence": ["godot_walk/panorama.png"],
                },
                {
                    "stage": "godot_room",
                    "evidence": ["res://synthetic/room.tscn"],
                },
            ],
            "poetics": {
                "form_role": "figure",
                "rarity_tier": 1,
                "apollonian": 0.3,
                "dionysian": 0.7,
                "style_tags": ["carpet_floor"],
                "surface_salience": "A plain synthetic room.",
                "unique_details": [],
                "poetics_status": "operator_confirmed",
            },
            "eligibility": {
                "layout_eligible_derived": False,
                "catalog_layout_eligible": None,
            },
        }
        poetics_path.write_text(json.dumps(poetics, indent=2) + "\n", encoding="utf-8")
        profile = build_profile(
            poetics,
            poetics_path.relative_to(self.root).as_posix(),
            {
                "module_id": "synthetic_picture_room_v1",
                "version": 1,
                "catalog_layout_eligible": None,
                "sockets": [
                    {
                        "id": "north",
                        "compatibility_type": "level_doorway_2m_v1",
                        "clear_size_m": [2.0, 2.1],
                        "floor_elevation_m": 0.0,
                    }
                ],
            },
            sha256_file(snapshot),
            self.root,
        )
        self.assertEqual("source_picture_set", profile["origin"])
        self.assertEqual(self.source_id, profile["source_id"])
        self.assertEqual("direct_image", profile["translation_chain"][0]["stage"])
        self.assertEqual(image["path"], profile["translation_chain"][0]["evidence"][0])
        self.assertEqual([], tv.module_profile_errors(profile, self.root))
        written = write_profile(
            profile, room / "module_profile_v1.json", self.root
        )
        self.assertTrue((self.root / written["path"]).is_file())
        self.assertEqual(
            sha256_file(self.root / written["path"]), written["sha256"]
        )
        with self.assertRaises(FileExistsError):
            write_profile(profile, room / "module_profile_v1.json", self.root)

    def test_picture_set_manifest_matches_the_v3_schema(self) -> None:
        manifest_path = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "source_manifest-v3.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = tv.load_schema(
            Path("godot_walk/source_library/source_manifest_v3.schema.json"),
            ROOT,
        )
        jsonschema.Draft202012Validator(schema).validate(manifest)


class PictureSetRegistrationGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data/pictures").mkdir(parents=True)
        self.pictures = create_picture_set(
            self.root / "data/pictures/guard-set", count=1
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_unsupported_or_outside_inputs_are_rejected(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        Image.new("RGB", (8, 8)).save(outside / "a.png")
        with self.assertRaises(SourceLibraryError):
            register_picture_set(outside, self.root)
        nested = self.root / "data/pictures/nested/set"
        nested.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(nested / "a.png")
        with self.assertRaises(SourceLibraryError):
            register_picture_set(nested, self.root)

    def test_empty_or_unsupported_picture_set_is_rejected(self) -> None:
        empty = self.root / "data/pictures/empty"
        empty.mkdir(parents=True)
        with self.assertRaisesRegex(SourceLibraryError, "no supported images"):
            register_picture_set(empty, self.root)
        notes = self.root / "data/pictures/notes"
        notes.mkdir(parents=True)
        (notes / "readme.txt").write_text("not an image", encoding="utf-8")
        with self.assertRaisesRegex(SourceLibraryError, "no supported images"):
            register_picture_set(notes, self.root)


if __name__ == "__main__":
    unittest.main()
