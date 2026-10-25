"""Serve a Hunyuan review bundle and save validated operator feedback locally."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hunyuan_round1_contract import SCHEMA_DIR
from hunyuan_round1_records import validate_document, validate_feedback_for_round
from jsonschema import ValidationError

MAX_REQUEST_BYTES = 1_000_000


def save_submission(bundle_dir: Path, feedback: dict[str, Any]) -> Path:
    bundle_dir = bundle_dir.resolve()
    manifest_path = bundle_dir / "round_manifest.json"
    feedback_path = bundle_dir / "operator_feedback.json"
    manifest = _read_json(manifest_path)
    validate_document(manifest, SCHEMA_DIR / "hunyuan_round.schema.json")
    if (
        manifest.get("status") != "awaiting_operator_review"
        or manifest.get("operator_feedback", {}).get("status")
        != "pending_operator_review"
    ):
        raise ValueError("Only pending review bundles can accept feedback")
    if (
        feedback_path.is_file()
        and _read_json(feedback_path).get("status") == "confirmed"
    ):
        raise ValueError("Confirmed feedback records cannot be replaced")
    if feedback.get("round_id") != manifest.get("round_id"):
        raise ValueError("Feedback round_id does not match this review bundle")
    if feedback.get("status") != "confirmed":
        raise ValueError("Only confirmed feedback can be submitted")

    validate_document(feedback, SCHEMA_DIR / "operator_feedback.schema.json")
    validate_feedback_for_round(feedback, manifest)
    manifest["status"] = "operator_reviewed"
    manifest["operator_feedback"]["status"] = "confirmed"
    validate_document(manifest, SCHEMA_DIR / "hunyuan_round.schema.json")

    _atomic_write_json(feedback_path, feedback)
    _atomic_write_json(manifest_path, manifest)
    return feedback_path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def make_handler(bundle_dir: Path) -> type[SimpleHTTPRequestHandler]:
    resolved_bundle = bundle_dir.resolve()

    class ReviewRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(resolved_bundle), **kwargs)

        def do_GET(self) -> None:
            if not self._is_expected_host():
                self.send_error(403, "Use the 127.0.0.1 review URL")
                return
            super().do_GET()

        def do_POST(self) -> None:
            if not self._is_expected_host():
                self.send_error(403, "Use the 127.0.0.1 review URL")
                return
            if self.path != "/submit":
                self.send_error(404, "Unknown submission endpoint")
                return
            if self.headers.get_content_type() != "application/json":
                self._send_json(415, {"error": "Content-Type must be application/json"})
                return
            self._handle_submission()

        def _is_expected_host(self) -> bool:
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected

        def _handle_submission(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send_json(411, {"error": "Content-Length is required"})
                return
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "Feedback payload size is invalid"})
                return
            try:
                feedback = json.loads(self.rfile.read(length))
                if not isinstance(feedback, dict):
                    raise TypeError("Feedback payload must be a JSON object")
                saved_path = save_submission(resolved_bundle, feedback)
            except (
                json.JSONDecodeError,
                ValidationError,
                TypeError,
                ValueError,
            ) as error:
                self._send_json(400, {"error": str(error)})
                return
            except OSError:
                self._send_json(
                    500, {"error": "Could not save feedback in the workspace"}
                )
                return
            self._send_json(
                200,
                {
                    "saved": True,
                    "path": saved_path.name,
                    "round_id": feedback["round_id"],
                },
            )

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

    return ReviewRequestHandler


def _open_review_page(url: str) -> bool:
    return webbrowser.open(url, new=2)


def validate_review_bundle(bundle_dir: Path, allow_confirmed: bool = False) -> None:
    if not (bundle_dir / "index.html").is_file():
        raise ValueError(f"Review page not found in {bundle_dir}")
    manifest_path = bundle_dir / "round_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Round manifest not found in {bundle_dir}")
    manifest = _read_json(manifest_path)
    feedback_status = manifest.get("operator_feedback", {}).get("status")
    is_confirmed = (
        manifest.get("status") == "operator_reviewed" or feedback_status == "confirmed"
    )
    if is_confirmed and not allow_confirmed:
        raise ValueError(
            "This bundle already has confirmed feedback; pass --allow-confirmed "
            "only to inspect a historical review."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-confirmed",
        action="store_true",
        help="allow viewing a completed historical review bundle",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="open the loopback review page in the default browser",
    )
    args = parser.parse_args()
    bundle_dir = args.bundle_dir.resolve()
    try:
        validate_review_bundle(bundle_dir, allow_confirmed=args.allow_confirmed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(bundle_dir))
    review_url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Review server ready: {review_url}")
    if args.open_browser and not _open_review_page(review_url):
        print("Browser launch failed; open the review URL manually.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Review server stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
