"""Tests for deterministic labelled image collections."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freeview_image_collections import (
    CollectionError,
    build_collection_spec,
    collection_images,
    distractor_count,
    resolve_collection_path,
    scan_image_directory,
    take_sample,
    verify_picture_set_manifest,
    verify_scene_manifest,
)
from PIL import Image


def _write_image(path: Path, color: tuple[int, int, int], size=(32, 24)) -> None:
    Image.new("RGB", size, color).save(path)


def _directory(root: Path, name: str, count: int) -> Path:
    directory = root / name
    directory.mkdir()
    channel = sum(name.encode()) % 200
    for index in range(count):
        _write_image(directory / f"img_{index:03d}.png", (index * 7 % 256, channel, 90))
    return directory


class ScanTests(unittest.TestCase):
    def test_scan_is_sorted_hashed_and_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "scene", 3)
            records = scan_image_directory(directory, "scene", root)
        self.assertEqual(
            [record.image_id for record in records],
            ["scene/img_000.png", "scene/img_001.png", "scene/img_002.png"],
        )
        self.assertTrue(all(len(record.sha256) == 64 for record in records))
        self.assertTrue(all(record.role == "scene" for record in records))
        self.assertTrue(all(record.path.startswith("scene/") for record in records))
        self.assertTrue(all(record.width == 32 for record in records))

    def test_duplicate_bytes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "scene", 2)
            (directory / "copy.png").write_bytes(
                (directory / "img_000.png").read_bytes()
            )
            with self.assertRaises(CollectionError):
                scan_image_directory(directory, "scene", root)

    def test_unsupported_files_and_empty_directories_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "scene"
            directory.mkdir()
            (directory / "notes.txt").write_text("not an image", encoding="utf-8")
            with self.assertRaises(CollectionError):
                scan_image_directory(directory, "scene", root)
            with self.assertRaises(FileNotFoundError):
                scan_image_directory(root / "missing", "scene", root)

    def test_unknown_role_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "scene", 1)
            with self.assertRaises(CollectionError):
                scan_image_directory(directory, "rival", root)


class SampleTests(unittest.TestCase):
    def _records(self, count: int, role: str = "scene"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, role, count)
            return scan_image_directory(directory, role, root)

    def test_sample_is_deterministic_and_seeded(self) -> None:
        records = self._records(12)
        first = take_sample(records, 5, 7)
        second = take_sample(records, 5, 7)
        self.assertEqual(
            [record.image_id for record in first],
            [record.image_id for record in second],
        )
        other = take_sample(records, 5, 8)
        self.assertNotEqual(
            [record.image_id for record in first],
            [record.image_id for record in other],
        )

    def test_sample_cannot_exceed_the_pool(self) -> None:
        records = self._records(3)
        with self.assertRaises(CollectionError):
            take_sample(records, 4, 1)
        with self.assertRaises(CollectionError):
            take_sample(records, 0, 1)

    def test_distractor_count_targets_the_combined_fraction(self) -> None:
        self.assertEqual(distractor_count(0.50, 57), 57)
        self.assertEqual(distractor_count(0.25, 57), 19)
        self.assertEqual(distractor_count(0.10, 57), 6)
        with self.assertRaises(CollectionError):
            distractor_count(0.0, 57)
        with self.assertRaises(CollectionError):
            distractor_count(1.0, 57)


class BuildTests(unittest.TestCase):
    def _spec(self, scene_count: int = 12, distractor_count_value: int = 8):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene = scan_image_directory(
                _directory(root, "scene", scene_count), "scene", root
            )
            distractors = scan_image_directory(
                _directory(root, "distractor", distractor_count_value),
                "distractor",
                root,
            )
        return build_collection_spec(
            scene,
            distractors,
            seeds=(11, 12),
            mix_levels=(0.25, 0.50),
            room_sample=6,
            k_values=(3, 5),
        )

    def test_collections_have_exact_counts_and_roles(self) -> None:
        spec = self._spec()
        names = [collection["name"] for collection in spec["collections"]]
        self.assertEqual(
            names,
            [
                "clean-full",
                "clean-seed-11",
                "mixed-25-seed-11",
                "mixed-50-seed-11",
                "clean-seed-12",
                "mixed-25-seed-12",
                "mixed-50-seed-12",
                "mixed-all",
                "distractor-only",
            ],
        )
        by_name = {collection["name"]: collection for collection in spec["collections"]}
        mixed = by_name["mixed-25-seed-11"]
        self.assertEqual(mixed["scene_count"], 6)
        self.assertEqual(mixed["distractor_count"], 2)
        self.assertAlmostEqual(mixed["realized_distractor_fraction"], 0.25, places=6)
        roles = [image["role"] for image in collection_images(mixed)]
        self.assertEqual(roles.count("scene"), 6)
        self.assertEqual(roles.count("distractor"), 2)
        self.assertEqual(
            [image["image_id"] for image in collection_images(mixed)],
            sorted(image["image_id"] for image in collection_images(mixed)),
        )

    def test_build_is_deterministic(self) -> None:
        first = self._spec()
        second = self._spec()
        self.assertEqual(first, second)

    def test_distractor_sets_are_nested_across_mix_levels(self) -> None:
        spec = self._spec()
        by_name = {collection["name"]: collection for collection in spec["collections"]}
        small = {
            image["image_id"]
            for image in collection_images(by_name["mixed-25-seed-11"])
            if image["role"] == "distractor"
        }
        large = {
            image["image_id"]
            for image in collection_images(by_name["mixed-50-seed-11"])
            if image["role"] == "distractor"
        }
        self.assertTrue(small < large)

    def test_oversized_mix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene = scan_image_directory(_directory(root, "scene", 10), "scene", root)
            distractors = scan_image_directory(
                _directory(root, "distractor", 3), "distractor", root
            )
        with self.assertRaises(CollectionError):
            build_collection_spec(
                scene,
                distractors,
                seeds=(1,),
                mix_levels=(0.50,),
                room_sample=10,
            )

    def test_cross_role_duplicates_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene_dir = _directory(root, "scene", 1)
            distractor_dir = root / "distractor"
            distractor_dir.mkdir()
            (distractor_dir / "copy.png").write_bytes(
                (scene_dir / "img_000.png").read_bytes()
            )
            scene = scan_image_directory(scene_dir, "scene", root)
            distractors = scan_image_directory(distractor_dir, "distractor", root)
        with self.assertRaises(CollectionError):
            build_collection_spec(
                scene, distractors, seeds=(1,), mix_levels=(0.5,), room_sample=1
            )


class ManifestTests(unittest.TestCase):
    def test_scene_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "scene", 2)
            records = scan_image_directory(directory, "scene", root)
            entries = [
                {
                    "path": f"room/images_4/{Path(record.path).name}",
                    "sha256": record.sha256,
                }
                for record in records
            ]
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(entries), encoding="utf-8")
            summary = verify_scene_manifest(manifest, records, "images_4")
        self.assertEqual(summary["matched_images"], 2)

    def test_scene_manifest_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "scene", 2)
            records = scan_image_directory(directory, "scene", root)
            entries = [
                {
                    "path": f"room/images_4/{Path(record.path).name}",
                    "sha256": "0" * 64,
                }
                for record in records
            ]
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(entries), encoding="utf-8")
            with self.assertRaises(CollectionError):
                verify_scene_manifest(manifest, records, "images_4")

    def test_picture_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "pictures", 2)
            records = scan_image_directory(directory, "distractor", root)
            document = {
                "content": {
                    "picture_set": [
                        {
                            "path": f"data/pictures/x/{Path(record.path).name}",
                            "sha256": record.sha256,
                        }
                        for record in records
                    ]
                }
            }
            manifest = root / "picture_manifest.json"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            summary = verify_picture_set_manifest(manifest, records)
        self.assertEqual(summary["matched_images"], 2)

    def test_missing_manifest_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = _directory(root, "pictures", 2)
            records = scan_image_directory(directory, "distractor", root)
            document = {
                "content": {
                    "picture_set": [
                        {
                            "path": "data/pictures/x/missing.png",
                            "sha256": "0" * 64,
                        }
                    ]
                }
            }
            manifest = root / "picture_manifest.json"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(CollectionError):
                verify_picture_set_manifest(manifest, records)


class PathTests(unittest.TestCase):
    def test_repo_relative_and_absolute_paths_resolve(self) -> None:
        root = Path("/repo")
        self.assertEqual(
            resolve_collection_path("data/a.png", root), root / "data/a.png"
        )
        self.assertEqual(
            resolve_collection_path("/data/a.png", root), Path("/data/a.png")
        )


if __name__ == "__main__":
    unittest.main()
