"""End-to-end tests for immutable catalog bindings on historical bundles."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import video_adaptation_evidence
import video_adaptation_validation
from video_adaptation_errors import AdaptationValidationError
from video_adaptation_validation import ROOT, validate_bundle

BUNDLES = (
    ROOT / "godot_walk/room_catalog/adaptations/room-large-v1.json",
    ROOT / "godot_walk/room_catalog/adaptations/corridor-corner-v2.json",
)
LIVE_CATALOG = "godot_walk/room_catalog/catalog.json"
SNAPSHOT = "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.2.0.json"


class HistoricalCatalogBundleTests(unittest.TestCase):
    def test_live_catalog_growth_does_not_invalidate_either_real_bundle(self) -> None:
        catalog = json.loads((ROOT / LIVE_CATALOG).read_text(encoding="utf-8"))
        catalog["modules"].append(
            {"id": "unrelated-test-room", "version": 1, "scene": "unused"}
        )
        with tempfile.TemporaryDirectory() as temporary:
            changed_catalog = Path(temporary) / "catalog.json"
            changed_catalog.write_text(json.dumps(catalog), encoding="utf-8")
            original = video_adaptation_evidence.resolve_repo_path

            def route_live_catalog(
                path_text: str, root: Path = ROOT, *, require_file: bool = False
            ) -> Path:
                if path_text == LIVE_CATALOG:
                    return changed_catalog
                return original(path_text, root, require_file=require_file)

            with patch.object(
                video_adaptation_evidence,
                "resolve_repo_path",
                side_effect=route_live_catalog,
            ):
                for bundle in BUNDLES:
                    with self.subTest(bundle=bundle.name):
                        validate_bundle(bundle)

    def test_tampered_snapshot_fails_for_either_real_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tampered_snapshot = Path(temporary) / "catalog-snapshot.json"
            tampered_snapshot.write_text('{"modules":[]}', encoding="utf-8")
            original = video_adaptation_evidence.resolve_repo_path

            def route_snapshot(
                path_text: str, root: Path = ROOT, *, require_file: bool = False
            ) -> Path:
                if path_text == SNAPSHOT:
                    return tampered_snapshot
                return original(path_text, root, require_file=require_file)

            with patch.object(
                video_adaptation_evidence,
                "resolve_repo_path",
                side_effect=route_snapshot,
            ):
                for bundle in BUNDLES:
                    with (
                        self.subTest(bundle=bundle.name),
                        self.assertRaisesRegex(
                            AdaptationValidationError, "snapshot hash mismatch"
                        ),
                    ):
                        validate_bundle(bundle)

    def test_referenced_module_and_dependency_changes_fail_full_validation(
        self,
    ) -> None:
        bundle = BUNDLES[0]
        frozen = json.loads((ROOT / SNAPSHOT).read_text(encoding="utf-8"))
        module_id = "godot_source_textured_large_room_v1"
        missing = json.loads(json.dumps(frozen))
        missing["modules"] = [
            item for item in missing["modules"] if item["id"] != module_id
        ]
        changed_version = json.loads(json.dumps(frozen))
        next(item for item in changed_version["modules"] if item["id"] == module_id)[
            "version"
        ] += 1
        changed_dependency = json.loads(json.dumps(frozen))
        changed_module = next(
            item for item in changed_dependency["modules"] if item["id"] == module_id
        )
        changed_module["dependencies"] = [
            "godot_walk/scripts/video_adaptation_errors.py"
        ]

        for snapshot, message in (
            (missing, "module reference is missing or changed"),
            (changed_version, "module reference is missing or changed"),
            (changed_dependency, "Required runtime dependency is not fingerprinted"),
        ):
            with (
                self.subTest(message=message),
                patch.object(
                    video_adaptation_validation, "_load_snapshot", return_value=snapshot
                ),
                self.assertRaisesRegex(AdaptationValidationError, message),
            ):
                validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
