#!/usr/bin/env python3
"""Unit tests for design round specs and immutable-input discovery."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from psx_design_round_protection import collect_protected_paths
from psx_design_round_resources import check_capture_headroom
from psx_design_round_spec import DESIGN_ROUNDS, load_spec


class DesignRoundSpecTests(unittest.TestCase):
    def test_round_specs_validate(self) -> None:
        for number in range(2, 6):
            with self.subTest(round_number=number):
                spec = load_spec(DESIGN_ROUNDS / f"round-{number}.json")
                self.assertEqual(spec["round_id"], f"round-{number}")
                self.assertIn(spec["baseline"], spec["variants"])

    def test_invalid_variant_list_is_rejected(self) -> None:
        spec = json.loads((DESIGN_ROUNDS / "round-5.json").read_text())
        spec["variants"] = [spec["baseline"], spec["baseline"]]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.json"
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "invalid design round spec"):
                load_spec(path)


class ProtectedSetTests(unittest.TestCase):
    def test_collects_base_variant_round_inputs_and_prior_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "godot_walk"
            evidence = project / "evidence" / "2026-10-01-psx-design-old"
            variant_dir = project / "design_variants"
            source_dir = root / "inputs"
            evidence.mkdir(parents=True)
            variant_dir.mkdir()
            source_dir.mkdir()
            (root / "base.txt").write_text("fixed")
            (variant_dir / "old_variant.json").write_text("{}")
            (variant_dir / "current_variant.json").write_text("{}")
            (source_dir / "source.bin").write_bytes(b"source")
            (evidence / "capture.png").write_bytes(b"old evidence")
            (evidence / "review_manifest.json").write_text(json.dumps({
                "variants": ["old_variant"],
                "source_sha256": {"inputs/source.bin": "old hash"},
            }))
            out_dir = project / "evidence" / "2026-10-17-psx-design-new"
            spec = {"round_number": 8, "variants": ["current_variant"],
                    "additional_inputs": ["inputs/source.bin"]}

            paths = collect_protected_paths(spec, out_dir, root,
                                            ("base.txt",))

            relative = {path.relative_to(root).as_posix() for path in paths}
            self.assertIn("base.txt", relative)
            self.assertIn("godot_walk/design_variants/old_variant.json", relative)
            self.assertIn("godot_walk/design_variants/current_variant.json", relative)
            self.assertIn("inputs/source.bin", relative)
            self.assertIn("godot_walk/evidence/2026-10-01-psx-design-old/capture.png", relative)
            self.assertNotIn("godot_walk/evidence/2026-10-17-psx-design-new/capture.png", relative)


class CaptureHeadroomTests(unittest.TestCase):
    def test_aggregate_utilization_is_reported_not_mistaken_for_another_job(self) -> None:
        with patch("psx_design_round_resources._active_named_jobs", return_value=[]), \
                patch("psx_design_round_resources._active_gpu_jobs", return_value=[]), \
                patch("psx_design_round_resources._gpu_snapshot", return_value={
                    "free_vram_bytes": 8 * 1024**3,
                    "total_vram_bytes": 12 * 1024**3,
                    "utilization_pct": 12,
                }), \
                patch("psx_design_round_resources._compute_apps", return_value=[]), \
                patch("psx_design_round_resources._available_ram_bytes",
                      return_value=8 * 1024**3):
            result = check_capture_headroom()

        self.assertEqual(result["utilization_pct"], 12)


if __name__ == "__main__":
    unittest.main()
