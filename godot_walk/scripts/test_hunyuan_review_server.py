"""Tests for direct, schema-validated operator feedback submission."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot_walk" / "scripts"))
from hunyuan_review_server import (
    _open_review_page,
    make_handler,
    save_submission,
    validate_review_bundle,
)
from hunyuan_round1_contract import ROUND_ID, VARIANTS, VIEW_IDS


class ReviewServerTests(unittest.TestCase):
    def test_confirmed_bundle_requires_historical_view_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            shutil.copy2(_round_manifest_path(), bundle / "round_manifest.json")
            (bundle / "index.html").write_text("<html></html>", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "confirmed feedback"):
                validate_review_bundle(bundle)

            validate_review_bundle(bundle, allow_confirmed=True)

    def test_pending_bundle_can_be_opened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            manifest = json.loads(_round_manifest_path().read_text())
            manifest["status"] = "awaiting_operator_review"
            manifest["operator_feedback"]["status"] = "pending_operator_review"
            (bundle / "round_manifest.json").write_text(json.dumps(manifest))
            (bundle / "index.html").write_text("<html></html>", encoding="utf-8")

            validate_review_bundle(bundle)

    @patch("hunyuan_review_server.webbrowser.open", return_value=True)
    def test_review_page_opens_in_browser(self, open_browser) -> None:
        result = _open_review_page("http://127.0.0.1:8765/")

        self.assertTrue(result)
        open_browser.assert_called_once_with("http://127.0.0.1:8765/", new=2)

    def test_submission_saves_feedback_and_updates_round_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            _write_pending_manifest(bundle)

            saved = save_submission(bundle, _confirmed_feedback())
            manifest = json.loads((bundle / "round_manifest.json").read_text())
            feedback = json.loads(saved.read_text())

        self.assertEqual(saved.name, "operator_feedback.json")
        self.assertEqual(feedback["status"], "confirmed")
        self.assertEqual(manifest["status"], "operator_reviewed")
        self.assertEqual(manifest["operator_feedback"]["status"], "confirmed")

    def test_confirmed_bundle_rejects_feedback_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            shutil.copy2(_round_manifest_path(), bundle / "round_manifest.json")
            with self.assertRaisesRegex(ValueError, "Only pending review bundles"):
                save_submission(bundle, _confirmed_feedback())

    def test_confirmed_feedback_file_cannot_be_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            _write_pending_manifest(bundle)
            target = bundle / "operator_feedback.json"
            original = json.dumps(_confirmed_feedback())
            target.write_text(original)

            with self.assertRaisesRegex(ValueError, "Confirmed feedback records"):
                save_submission(bundle, _confirmed_feedback())

            self.assertEqual(target.read_text(), original)

    def test_submission_uses_manifest_view_and_variant_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            manifest = _dynamic_round_manifest()
            (bundle / "round_manifest.json").write_text(json.dumps(manifest))
            saved = save_submission(bundle, _dynamic_feedback(manifest))
            self.assertEqual(
                json.loads(saved.read_text())["round_id"], "hunyuan-psx-r3"
            )

    def test_invalid_submission_does_not_replace_pending_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            _write_pending_manifest(bundle)
            pending = '{"status":"pending_operator_review"}\n'
            target = bundle / "operator_feedback.json"
            target.write_text(pending, encoding="utf-8")
            invalid = _confirmed_feedback()
            invalid["view_choices"][0]["choice"] = None

            with self.assertRaises(ValidationError):
                save_submission(bundle, invalid)

            self.assertEqual(target.read_text(encoding="utf-8"), pending)

    def test_http_submit_endpoint_writes_to_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            _write_pending_manifest(bundle)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bundle))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/submit",
                    data=json.dumps(_confirmed_feedback()).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=2) as response:
                    result = json.loads(response.read())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertTrue(result["saved"])
            self.assertEqual(result["path"], "operator_feedback.json")
            self.assertTrue((bundle / result["path"]).is_file())


def _round_manifest_path() -> Path:
    return (
        ROOT
        / "godot_walk"
        / "evidence"
        / "2026-10-21-issue-151-round-1"
        / "round_manifest.json"
    )


def _write_pending_manifest(bundle: Path) -> None:
    manifest = json.loads(_round_manifest_path().read_text())
    manifest["status"] = "awaiting_operator_review"
    manifest["operator_feedback"]["status"] = "pending_operator_review"
    (bundle / "round_manifest.json").write_text(json.dumps(manifest))


def _confirmed_feedback() -> dict:
    return {
        "schema_version": 1,
        "round_id": ROUND_ID,
        "status": "confirmed",
        "reviewer_timestamp": "2026-10-21T12:00:00Z",
        "view_choices": [
            {"view_id": view_id, "choice": "tie", "reason": "Comparable view."}
            for view_id in VIEW_IDS
        ],
        "variant_decisions": [
            {
                "variant_id": variant_id,
                "decision": "iterate",
                "reason": "Continue the authored iteration.",
            }
            for variant_id in VARIANTS
        ],
        "overall_walkthrough_notes": "The test route was stable.",
        "remaining_problems": [],
        "next_round_directives": ["Improve the column definition."],
        "confidence": 4,
    }


def _dynamic_round_manifest() -> dict:
    manifest = json.loads(_round_manifest_path().read_text())
    manifest["round_id"] = "hunyuan-psx-r3"
    manifest["capture"]["view_ids"] = ["ceiling_corner", "column_back"]
    manifest["variants"][1]["variant_id"] = "source_texture_ceiling"
    third = manifest["variants"][1].copy()
    third["variant_id"] = "corner_trim"
    manifest["variants"].append(third)
    manifest["status"] = "awaiting_operator_review"
    manifest["operator_feedback"]["status"] = "pending_operator_review"
    return manifest


def _dynamic_feedback(manifest: dict) -> dict:
    feedback = _confirmed_feedback()
    feedback["round_id"] = manifest["round_id"]
    feedback["view_choices"] = [
        {"view_id": view, "choice": "tie", "reason": "Comparable."}
        for view in manifest["capture"]["view_ids"]
    ]
    feedback["variant_decisions"] = [
        {
            "variant_id": variant["variant_id"],
            "decision": "iterate",
            "reason": "Continue.",
        }
        for variant in manifest["variants"]
    ]
    return feedback


if __name__ == "__main__":
    unittest.main()
