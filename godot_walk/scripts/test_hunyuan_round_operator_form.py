"""Regression tests for the local Hunyuan operator review page."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot_walk" / "scripts"))
from hunyuan_round1_contract import VARIANTS, VIEW_IDS
from hunyuan_round1_operator_form import write_review_page


class OperatorFormTests(unittest.TestCase):
    def test_next_round_form_uses_round_two_variant_ids(self) -> None:
        variants = ("preserve_hunyuan", "column_box_source_face")
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            write_review_page(
                out_dir,
                _metrics(),
                round_id="hunyuan-psx-r2",
                variants=variants,
            )
            page = (out_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn("Hunyuan PSX Room | Round 2", page)
        self.assertIn("name='choice_patch_anchor'", page)
        self.assertIn("column_box_source_face", page)
        self.assertNotIn("source_surface_cleanup", page)

    def test_view_controls_are_inside_feedback_form(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            write_review_page(out_dir, _metrics())
            page = (out_dir / "index.html").read_text(encoding="utf-8")

        form_start = page.index('<form id="feedback"')
        form_end = page.index("</form>")
        self.assertEqual(page.count('<form id="feedback"'), 1)
        self.assertEqual(page.count("</form>"), 1)
        for view_id in VIEW_IDS:
            choice = page.index(f"name='choice_{view_id}'")
            reason = page.index(f"name='reason_{view_id}'")
            self.assertLess(form_start, choice)
            self.assertLess(choice, form_end)
            self.assertLess(form_start, reason)
            self.assertLess(reason, form_end)
        self.assertLess(form_start, page.index('id="feedback_import"'))
        self.assertLess(page.index('id="feedback_import"'), form_end)

    def test_importer_restores_saved_notes_without_guessing_blank_views(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            write_review_page(out_dir, _metrics())
            page = (out_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn("imported.variant_decisions", page)
        self.assertIn("imported.overall_walkthrough_notes", page)
        self.assertIn("view.choice!==null", page)
        self.assertIn("Feedback JSON loaded. Review the choices", page)
        self.assertIn("fetch('operator_feedback.json'", page)
        self.assertIn("applyFeedback(imported)", page)
        self.assertIn("Submit feedback to workspace", page)
        self.assertIn("fetch('/submit'", page)
        self.assertIn("Download JSON copy", page)


def _metrics() -> dict:
    return {
        "per_view_noise_ceiling_pct": {view_id: 0.0 for view_id in VIEW_IDS},
        "variant_pixel_deltas": [
            {
                "view_id": view_id,
                "diff_pct": 1.0,
                "diff_image": None,
                "interpretation": "measurable change",
            }
            for view_id in VIEW_IDS
        ],
        "variants": list(VARIANTS),
    }


if __name__ == "__main__":
    unittest.main()
